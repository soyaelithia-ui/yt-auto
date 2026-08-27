import os
import tempfile
import unittest
import sqlite3
import pytest
from unittest.mock import patch, MagicMock

from src.db import init_db, enqueue_story, get_pending_story, update_story_status
from src.scraper import fetch_reddit_stories
from src.video import compose_video
from src.drive import upload_to_drive
from src.youtube.uploader import upload_video_via_playwright, upload_video
from src.daemon import run_pipeline_once
from src.cli import cli_status


@pytest.mark.vcr
class TestTier4AdversarialRecovery(unittest.TestCase):
    """Tier 4: Adversarial Edge Cases, Boundary Testing & Failure Recovery (R1-R5)."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_tier4.db")
        init_db(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_adversarial_video_duration_short_rejection(self):
        """Tier 4: Test rejection of video generation under 2 minutes (<=120 seconds)."""
        audio_path = os.path.join(self.temp_dir.name, "short.wav")
        with open(audio_path, "wb") as f:
            f.write(b"SHORT_AUDIO")
        srt_path = os.path.join(self.temp_dir.name, "subs.srt")
        with open(srt_path, "w") as f:
            f.write("1\n00:00:00,000 --> 00:00:01,000\nHi\n")

        out_video = os.path.join(self.temp_dir.name, "short_out.mp4")
        with self.assertRaises(ValueError) as ctx:
            compose_video(
                audio_path,
                srt_path,
                "",
                out_video,
                duration_sec=119.9,
                channel="moku",
            )
        self.assertIn("must exceed minimum", str(ctx.exception))

    def test_adversarial_pipeline_failure_recorded_in_db(self):
        """Tier 4: Test pipeline failure sets DB story status to FAILED with error_msg."""
        enqueue_story("fail_story_001", "Fail Title", "Content", "http://url.com", channel="moku", db_path=self.db_path)

        # Force TTS audio generation to generate duration <= 120 to trigger video composition failure
        with patch("src.tts.generate_audio") as mock_tts, \
             patch("src.llm.curate_script", return_value="Title: Fail Title.\n\nThis is some curated script content."):
            mock_tts.return_value = {
                "audio_path": os.path.join(self.temp_dir.name, "short.wav"),
                "word_timestamps": [{"word": "Hi", "start": 0.0, "end": 1.0}],
                "duration_sec": 50.0  # Under 120s
            }
            # Create short audio file to exist
            with open(os.path.join(self.temp_dir.name, "short.wav"), "wb") as f:
                f.write(b"SHORT")

            res = run_pipeline_once(channel="moku", db_path=self.db_path)
            self.assertIn(res.get("status"), ("FAILED", "RETRYABLE_FAILED"))

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT status, error_msg FROM stories WHERE story_id = 'fail_story_001'")
            row = cursor.fetchone()
            conn.close()

            self.assertIsNotNone(row)
            self.assertIn(row[0], ("FAILED", "RETRYABLE_FAILED"), "Story status must transition to FAILED or RETRYABLE_FAILED on error.")
            self.assertTrue(row[1] and len(row[1]) > 0, "Error message must be recorded in DB.")

    @patch.dict(os.environ, {"DRIVE_USE_GCLOUD": "0"})
    @patch("src.drive._mock_enabled", return_value=False)
    def test_adversarial_missing_drive_service_account_key(self, mock_enabled):
        """Tier 4: Test missing Google Drive Service Account key file raises FileNotFoundError."""
        dummy_file = os.path.join(self.temp_dir.name, "dummy.mp4")
        with open(dummy_file, "wb") as f:
            f.write(b"DATA")

        missing_key_path = os.path.join(self.temp_dir.name, "non_existent_drive_key.json")
        with self.assertRaises(FileNotFoundError):
            upload_to_drive(dummy_file, "folder_id", sa_key_path=missing_key_path)

    def test_adversarial_missing_decrypted_cookies_file(self):
        """Tier 4: Test missing decrypted cookies file raises FileNotFoundError."""
        dummy_file = os.path.join(self.temp_dir.name, "dummy.mp4")
        with open(dummy_file, "wb") as f:
            f.write(b"DATA")

        missing_cookies = os.path.join(self.temp_dir.name, "non_existent_cookies.json")
        with self.assertRaises(FileNotFoundError):
            upload_video_via_playwright(dummy_file, "Title", "Desc", ["tag"], cookies_path=missing_cookies)

    def test_adversarial_empty_reddit_response_graceful_handling(self):
        """Tier 4: Test Reddit scraper handles 404/empty responses without crashing."""
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_get.return_value = mock_resp

            stories = fetch_reddit_stories("non_existent_sub", limit=5)
            self.assertEqual(stories, [], "Empty/404 scraper response must return empty list.")

    def test_adversarial_cli_status_robustness(self):
        """Tier 4: Test CLI status interface handles non-existent DB path gracefully."""
        bad_db = os.path.join(self.temp_dir.name, "non_existent.db")
        status = cli_status(db_path=bad_db)
        self.assertIn("queue", status)
        self.assertEqual(status["queue"]["PENDING"], 0)
        self.assertIn("disk_free_gb", status)


if __name__ == "__main__":
    unittest.main()
