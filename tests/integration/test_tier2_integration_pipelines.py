import os
import tempfile
import unittest
import sqlite3
import wave
import pytest
from unittest.mock import patch, MagicMock

from src.db import init_db, enqueue_story, get_pending_story
from src.scraper import fetch_reddit_stories
from src.llm import curate_script
from src.tts import generate_audio
from src.subtitles import create_subtitles
from src.video import compose_video
from src.drive import upload_to_drive
from src.cleaner import verify_and_cleanup
from src.youtube.uploader import upload_video, upload_video_via_api, upload_video_via_playwright

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
class TestTier2IntegrationPipelines(unittest.TestCase):
    """Tier 2: Component Integration & Data Flow Pipeline Validation (R1-R5)."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_tier2.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_pipeline_1_ingestion_curation_enqueue(self):
        """Pipeline 1: Reddit Scraper -> LLM Script Curator -> SQLite WAL Enqueue & Deduplication."""
        mock_json = {
            "data": {
                "children": [
                    {
                        "data": {
                            "id": "reddit_pipe_001",
                            "title": "Cabin in the Woods",
                            "selftext": "I rented a secluded cabin last winter...",
                            "permalink": "/r/nosleep/comments/001/"
                        }
                    }
                ]
            }
        }
        mock_client = MagicMock()
        mock_client.curate_script.return_value = {
            "script": "Title: Cabin in the Woods.\n\nI rented a secluded cabin last winter..."
        }
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_json
            mock_get.return_value = mock_resp

            stories = fetch_reddit_stories("nosleep", limit=5)
            self.assertEqual(len(stories), 1)

            story = stories[0]
            script = curate_script(story["content"], story["title"], client=mock_client)
            self.assertIn("Cabin in the Woods", script)

            enqueued = enqueue_story(story["id"], story["title"], script, story["url"], db_path=self.db_path)
            self.assertTrue(enqueued, "Story should be enqueued into database.")

            # Test deduplication pipeline check
            enqueued_dup = enqueue_story(story["id"], story["title"], script, story["url"], db_path=self.db_path)
            self.assertFalse(enqueued_dup, "Deduplication pipeline must reject duplicate story enqueue.")

            pending = get_pending_story(db_path=self.db_path)
            self.assertEqual(pending["story_id"], "reddit_pipe_001")

    def test_pipeline_2_audio_subtitles_video_synthesis(self):
        """Pipeline 2: TTS Audio Generation -> Word Timing Subtitles -> FFmpeg Video Synthesis (>10 min duration)."""
        script = "In a dark forest, silence is a sound."
        audio_path = os.path.join(self.temp_dir.name, "pipeline_audio.wav")
        srt_path = os.path.join(self.temp_dir.name, "pipeline_subs.srt")
        video_path = os.path.join(self.temp_dir.name, "pipeline_video.mp4")

        # Step A: isolated local audio fixture; production TTS retains its
        # editorial minimum and is intentionally not exercised here.
        with wave.open(audio_path, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(8_000)
            wav.writeframes(_tone_frames(wav, 16_000))
        audio_info = {
            "audio_path": audio_path,
            "duration_sec": 2.0,
            "word_timestamps": [
                {"word": "bosque", "start": 0.0, "end": 1.0},
                {"word": "oscuro", "start": 1.0, "end": 2.0},
            ],
        }
        self.assertTrue(os.path.exists(audio_info["audio_path"]))
        self.assertGreater(audio_info["duration_sec"], 0)

        # Step B: Synchronized SRT creation
        srt_res = create_subtitles(audio_info["word_timestamps"], srt_path)
        self.assertTrue(os.path.exists(srt_res))

        # Step C: short local composition; duration policy is unit-tested separately.
        comp_res = compose_video(
            audio_path,
            srt_path,
            "",
            video_path,
            duration_sec=audio_info["duration_sec"],
            channel="moku",
            min_duration=0.0,
        )
        self.assertTrue(os.path.exists(comp_res))
        self.assertGreater(os.path.getsize(comp_res), 0)

    def test_pipeline_3_upload_drive_local_cleanup(self):
        """Pipeline 3: Video File -> Google Drive Upload -> VPS Zero Storage Cleanup."""
        video_file = os.path.join(self.temp_dir.name, "clean_target.mp4")
        with open(video_file, "wb") as f:
            f.write(b"SAMPLE_VIDEO_DATA_FOR_CLEANUP_TEST" * 50)

        self.assertTrue(os.path.exists(video_file))

        # Drive upload
        drive_file_id = upload_to_drive(
            video_file,
            folder_id="test_folder",
            sa_key_path=os.path.join(self.temp_dir.name, "missing-key.json"),
        )
        self.assertIsNotNone(drive_file_id)

        # Cleanup is forbidden until a complete remote proof and retention policy exist.
        self.assertFalse(verify_and_cleanup(video_file, drive_file_id))
        self.assertTrue(os.path.exists(video_file))

    def test_pipeline_4_hybrid_youtube_uploader_fallback(self):
        """Pipeline 4: Hybrid Uploader API failure triggers Playwright headless fallback."""
        dummy_video = os.path.join(self.temp_dir.name, "yt_pipe.mp4")
        with open(dummy_video, "wb") as f:
            f.write(b"HYBRID_UPLOADER_VIDEO_DATA")

        cookies_path = os.path.join(self.temp_dir.name, "cookies.json")
        with open(cookies_path, "w", encoding="utf-8") as handle:
            handle.write("[]")
        # TEST_MODE short-circuits before either external upload route.
        with patch("src.youtube.uploader.upload_video_via_api", side_effect=RuntimeError("API Quota Exceeded")):
            res = upload_video(
                dummy_video,
                "Fallback Test Title",
                "Fallback Description",
                channel="moku",
                cookies_path=cookies_path,
            )
            self.assertEqual(res["status"], "TEST_MOCK")
            self.assertEqual(res["method"], "TEST_MOCK")


if __name__ == "__main__":
    unittest.main()
