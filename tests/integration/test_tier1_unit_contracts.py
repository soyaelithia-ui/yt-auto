import os
import tempfile
import unittest
import sqlite3
import wave
import pytest
from unittest.mock import patch, MagicMock

from src.db import init_db, enqueue_story, get_pending_story, update_story_status
from src.scraper import fetch_reddit_stories
from src.llm import curate_script
from src.tts import generate_audio
from src.subtitles import create_subtitles
from src.video import compose_video, MIN_VIDEO_DURATION_SEC
from src.drive import upload_to_drive
from src.cleaner import verify_and_cleanup
from src.youtube.uploader import upload_video
from src.cli import cli_status

def _tone_frames(wav, n_samples):
    """Tono senoidal de baja amplitud como narracion sintetica.

    El silencio digital puro (muestras a cero) hace que loudnorm emita frames
    NaN y el encoder AAC falle ('Input contains (near) NaN/+-Inf') en las
    renders reales de compose_video; un tono valido representa audio TTS
    realista y mantiene el gate fail-closed.
    """
    import math
    import struct
    rate = wav.getframerate() or 8000
    return b"".join(
        struct.pack("<h", int(1200 * math.sin(2 * math.pi * 220 * i / rate)))
        for i in range(n_samples)
    )



@pytest.mark.vcr
class TestTier1UnitContracts(unittest.TestCase):
    """Tier 1: Opaque-Box Component Unit & Interface Contract Validation (R1-R5)."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_tier1.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_r1_db_wal_mode_and_deduplication(self):
        """R1: Test SQLite WAL mode initialization and task queue deduplication."""
        init_db(self.db_path)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode;")
        mode = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(mode.lower(), "wal", "SQLite DB must be initialized in WAL mode.")

        # Enqueue first story
        res1 = enqueue_story("story_101", "Title 1", "Content 1", "http://reddit.com/101", db_path=self.db_path)
        self.assertTrue(res1, "First story insertion should return True.")

        # Enqueue duplicate story_id
        res2 = enqueue_story("story_101", "Title 1 Duplicate", "Content 1", "http://reddit.com/101", db_path=self.db_path)
        self.assertFalse(res2, "Duplicate story_id insertion must return False.")

    def test_r1_db_status_transitions(self):
        """R1: Test state transitions: PENDING -> PROCESSING -> COMPLETED / FAILED."""
        enqueue_story("story_102", "Title 2", "Content 2", "http://reddit.com/102", db_path=self.db_path)
        story = get_pending_story(db_path=self.db_path)
        self.assertIsNotNone(story)
        self.assertEqual(story["story_id"], "story_102")
        self.assertEqual(story["status"], "PENDING")

        update_story_status("story_102", "PROCESSING", db_path=self.db_path)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM stories WHERE story_id = 'story_102'")
        status = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(status, "PROCESSING")

        update_story_status("story_102", "COMPLETED", db_path=self.db_path)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM stories WHERE story_id = 'story_102'")
        status = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(status, "COMPLETED")

    def test_r1_reddit_scraper_json_endpoint(self):
        """R1: Test Reddit Scraper using mock response for JSON endpoint."""
        mock_json_response = {
            "data": {
                "children": [
                    {
                        "data": {
                            "id": "nosleep_001",
                            "title": "A Strange Encounter",
                            "selftext": "It all started last week...",
                            "permalink": "/r/nosleep/comments/nosleep_001/a_strange_encounter/"
                        }
                    }
                ]
            }
        }
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_json_response
            mock_get.return_value = mock_resp

            stories = fetch_reddit_stories(subreddit="nosleep", limit=5)
            self.assertEqual(len(stories), 1)
            self.assertEqual(stories[0]["id"], "nosleep_001")
            self.assertEqual(stories[0]["title"], "A Strange Encounter")
            called_url = mock_get.call_args[0][0]
            self.assertTrue(
                any(f"/r/nosleep/{ep}.json" in called_url for ep in ["hot", "new", "top", "rising"]),
                "Scraper must use Reddit JSON endpoint."
            )

    def test_r1_llm_script_curation(self):
        """R1: Test the offline local curator with Spanish output."""
        raw_text = "Visita http://example.com [enlace](http://test.com)\nEdit: gracias.\nLa oscuridad parecía viva."
        title = "Bosque oscuro"
        script = curate_script(raw_text, title, provider="C", channel="moku")
        self.assertIn("Título: Bosque oscuro.", script)
        self.assertNotIn("http://example.com", script)
        self.assertNotIn("gracias.", script)
        self.assertIn("enlace", script)
        self.assertIn("La oscuridad parecía viva.", script)

    def test_r2_tts_and_srt_subtitles(self):
        """R2: Test local mock audio and SRT formatting without a remote TTS call."""
        audio_out = os.path.join(self.temp_dir.name, "test_speech.wav")
        script = "This is a test script for YouTube automation."
        with wave.open(audio_out, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(8_000)
            wav.writeframes(_tone_frames(wav, 16_000))
        audio_info = {
            "audio_path": audio_out,
            "duration_sec": 2.0,
            "word_timestamps": [
                {"word": "Prueba", "start": 0.0, "end": 1.0},
                {"word": "local", "start": 1.0, "end": 2.0},
            ],
        }

        self.assertTrue(os.path.exists(audio_info["audio_path"]))
        self.assertGreater(audio_info["duration_sec"], 0)
        self.assertTrue(len(audio_info["word_timestamps"]) > 0)

        srt_out = os.path.join(self.temp_dir.name, "test_subs.srt")
        create_subtitles(audio_info["word_timestamps"], srt_out)
        self.assertTrue(os.path.exists(srt_out))

        with open(srt_out, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("-->", content, "SRT subtitles must contain valid timecode arrows.")
        self.assertIn("1\n", content, "SRT subtitles must contain block sequence index.")

    def test_r2_video_duration_contract(self):
        """R2: Test the duration gate and a short local composition separately."""
        import wave
        audio_path = os.path.join(self.temp_dir.name, "short_audio.wav")
        with wave.open(audio_path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(44100)
            w.writeframes(_tone_frames(w, int(2 * 44100 * 0.5)))
        srt_path = os.path.join(self.temp_dir.name, "subs.srt")
        with open(srt_path, "w") as f:
            f.write("1\n00:00:00,000 --> 00:00:05,000\nHello\n")

        output_video = os.path.join(self.temp_dir.name, "output_video.mp4")

        # Duration <= 120 seconds must raise ValueError
        with self.assertRaises(ValueError):
            compose_video(
                audio_path,
                srt_path,
                "",
                output_video,
                duration_sec=100.0,
                channel="moku",
            )

        # A short local composition is permitted only when the test explicitly
        # disables the editorial duration gate.
        res = compose_video(
            audio_path,
            srt_path,
            "",
            output_video,
            duration_sec=2.0,
            channel="moku",
            min_duration=0.0,
        )
        self.assertEqual(res, output_video)
        self.assertTrue(os.path.exists(output_video))

    def test_r3_drive_and_cleaner_contracts(self):
        """R3: Test the mocked Drive interface without inspecting a real key."""
        test_file = os.path.join(self.temp_dir.name, "upload_me.mp4")
        with open(test_file, "wb") as f:
            f.write(b"VIDEO_BINARY_CONTENT")

        drive_id = upload_to_drive(
            test_file,
            folder_id="folder_123",
            sa_key_path=os.path.join(self.temp_dir.name, "missing-key.json"),
        )
        self.assertTrue(isinstance(drive_id, str))
        # Cleanup without a complete remote proof is intentionally blocked.
        self.assertFalse(verify_and_cleanup(test_file, drive_id))
        self.assertTrue(os.path.exists(test_file))

    def test_r4_hybrid_uploader_contract(self):
        """R4: Test the uploader's explicit offline mock without real cookies."""
        dummy_video = os.path.join(self.temp_dir.name, "yt_test.mp4")
        with open(dummy_video, "wb") as f:
            f.write(b"YT_VIDEO_CONTENT")

        cookies_path = os.path.join(self.temp_dir.name, "cookies.json")
        with open(cookies_path, "w", encoding="utf-8") as handle:
            handle.write("[]")
        result = upload_video(
            dummy_video,
            "Test Title",
            "Test Description",
            channel="moku",
            cookies_path=cookies_path,
        )
        self.assertEqual(result["status"], "TEST_MOCK")
        self.assertEqual(result["method"], "TEST_MOCK")

    def test_r5_cli_status_schema(self):
        """R5: Test CLI status monitoring dictionary schema."""
        init_db(self.db_path)
        status = cli_status(db_path=self.db_path)
        self.assertIn("queue", status)
        self.assertIn("disk_free_gb", status)
        self.assertIn("daemon_status", status)
        self.assertIn("PENDING", status["queue"])


if __name__ == "__main__":
    unittest.main()
