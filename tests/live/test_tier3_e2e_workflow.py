import os
import tempfile
import unittest
import sqlite3
import pytest
from unittest.mock import patch, MagicMock

from src.daemon import run_pipeline_once, start_daemon
from src.cli import cli_status
from src.db import init_db


@pytest.mark.live
class TestTier3E2EWorkflow(unittest.TestCase):
    """Tier 3: End-to-End System Workflow Execution (R1-R5)."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_tier3_e2e.db")
        init_db(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_tier3_full_pipeline_once_execution(self):
        """Tier 3: Test complete end-to-end pipeline run_pipeline_once execution."""
        mock_reddit_response = {
            "data": {
                "children": [
                    {
                        "data": {
                            "id": "e2e_story_001",
                            "title": "Midnight Caller",
                            "selftext": "Every night at midnight, my phone rings once...",
                            "permalink": "/r/nosleep/comments/001/"
                        }
                    }
                ]
            }
        }
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_reddit_response
            mock_get.return_value = mock_resp

            pipeline_res = run_pipeline_once(db_path=self.db_path)

            self.assertEqual(pipeline_res["status"], "SUCCESS")
            self.assertEqual(pipeline_res["story_id"], "e2e_story_001")
            self.assertIn("drive_file_id", pipeline_res)
            self.assertIn("youtube_upload", pipeline_res)
            self.assertEqual(pipeline_res["youtube_upload"]["status"], "SUCCESS")

            # Verify SQLite DB state updated to COMPLETED
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM stories WHERE story_id = 'e2e_story_001'")
            row = cursor.fetchone()
            conn.close()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "COMPLETED", "Story status in database must be updated to COMPLETED after workflow execution.")

    def test_tier3_daemon_scheduler_and_cli_monitoring(self):
        """Tier 3: Test daemon scheduler loop and CLI monitoring status interface."""
        mock_reddit_response = {
            "data": {
                "children": [
                    {
                        "data": {
                            "id": "daemon_story_002",
                            "title": "Watcher in the Fog",
                            "selftext": "The fog settled over the lake...",
                            "permalink": "/r/nosleep/comments/002/"
                        }
                    }
                ]
            }
        }
        with patch("requests.get") as mock_get, patch("src.cli._is_daemon_running", return_value="RUNNING"):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_reddit_response
            mock_get.return_value = mock_resp

            # Run daemon for 1 scheduled iteration
            results = start_daemon(interval_seconds=1, max_runs=1, db_path=self.db_path, channels=["terror"])
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["status"], "SUCCESS")

            # Check CLI status interface output
            status = cli_status(db_path=self.db_path)
            self.assertEqual(status["queue"]["COMPLETED"], 1)
            self.assertEqual(status["daemon_status"], "RUNNING")


if __name__ == "__main__":
    unittest.main()
