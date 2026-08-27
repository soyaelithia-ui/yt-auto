import os
import tempfile
import unittest
import sqlite3
from unittest.mock import patch, MagicMock

from src.db import (
    init_db,
    enqueue_story,
    get_pending_story,
    update_story_status,
    is_story_processed,
    _get_connection,
)
from src.scraper import fetch_reddit_stories
from src.llm import curate_script, sanitize_text


class TestM1RemediationEdgeCases(unittest.TestCase):
    """Explicit unit tests for the 6 Milestone 1 edge case remediations."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "remediation_test.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_1_llm_curate_script_none_content_guard(self):
        """1. Guard curate_script against None values in input story dicts."""
        input_story = [{"title": "None Story", "content": None}]
        result = curate_script(input_story)
        self.assertIn("Título: None Story.", result)
        self.assertTrue(len(result) > 0)

        input_story_none_title = [{"title": None, "content": None}]
        result_none_title = curate_script(input_story_none_title)
        self.assertIn("Título: Historia de Terror.", result_none_title)

    def test_2_llm_footnote_regex_truncation_defect(self):
        """2. Tighten footnote regex so sentence containing 'edit' (e.g. 'I tried to edit my journal') is not truncated."""
        sentence = "I tried to edit my journal late at night."
        cleaned = sanitize_text(sentence)
        self.assertEqual(cleaned, sentence)

        sentence_2 = "Edit was a key step in the process."
        cleaned_2 = sanitize_text(sentence_2)
        self.assertEqual(cleaned_2, sentence_2)

        # Confirm actual footnotes (with colon / dashes) are still removed
        footnote_text = "The shadows moved. Edit: fixed spelling errors."
        cleaned_footnote = sanitize_text(footnote_text)
        self.assertEqual(cleaned_footnote, "The shadows moved.")

    def test_3_llm_url_regex_sanitizer_www(self):
        """3. Add www. URL pattern matching to regex sanitizer."""
        raw = "Check out www.example.com or http://test.org for details."
        cleaned = sanitize_text(raw)
        self.assertNotIn("www.example.com", cleaned)
        self.assertNotIn("http://test.org", cleaned)
        self.assertEqual(cleaned, "Check out or for details.")

    def test_4_scraper_http_5xx_pullpush_fallback(self):
        """4. Ensure HTTP 500, 502, 503 status codes from direct Reddit trigger PullPush API fallback."""
        pullpush_payload = {
            "data": [
                {
                    "id": "pp500",
                    "title": "Fallback Story",
                    "selftext": "This content comes from PullPush fallback.",
                    "author": "fallback_author",
                    "permalink": "/r/nosleep/comments/pp500"
                }
            ]
        }

        for status in (500, 502, 503):
            with patch("requests.get") as mock_get:
                reddit_resp = MagicMock()
                reddit_resp.status_code = status

                pp_resp = MagicMock()
                pp_resp.status_code = 200
                pp_resp.json.return_value = pullpush_payload

                mock_get.side_effect = [reddit_resp, pp_resp]

                stories = fetch_reddit_stories(subreddit="nosleep", limit=5)
                self.assertEqual(len(stories), 1, f"Failed for status code {status}")
                self.assertEqual(stories[0]["id"], "pp500")

    def test_5_scraper_case_insensitive_deleted_post_filter(self):
        """5. Case-insensitive deleted post filter matching [deleted] and substrings 'deleted by' / 'removed by'."""
        mock_payload = {
            "data": {
                "children": [
                    {"data": {"id": "d1", "title": "T1", "selftext": "[DELETED]", "author": "user1"}},
                    {"data": {"id": "d2", "title": "T2", "selftext": "[Removed]", "author": "user2"}},
                    {"data": {"id": "d3", "title": "T3", "selftext": "Content deleted by author", "author": "user3"}},
                    {"data": {"id": "d4", "title": "T4", "selftext": "Content removed by moderator", "author": "user4"}},
                    {"data": {"id": "d5", "title": "[DELETED]", "selftext": "Valid content long enough", "author": "user5"}},
                    {"data": {"id": "d6", "title": "T6", "selftext": "Valid content long enough", "author": "DELETED BY MODERATOR"}},
                    {"data": {"id": "ok1", "title": "Good Title", "selftext": "Valid creepypasta content here.", "author": "author1"}}
                ]
            }
        }

        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_payload
            mock_get.return_value = mock_resp

            stories = fetch_reddit_stories(subreddit="nosleep", limit=10)
            passed_ids = [s["id"] for s in stories]
            self.assertEqual(passed_ids, ["ok1"])

    def test_6_db_connection_optimization_and_wal_pragma(self):
        """6. Avoid redundant init_db() calls and verify PRAGMA journal_mode=WAL on DB init."""
        init_db(self.db_path)
        self.assertTrue(os.path.exists(self.db_path))

        # Verify WAL journal mode
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode;")
        journal_mode = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(journal_mode.lower(), "wal")

        # Test enqueue_story and get_pending_story work directly without redundant init_db calls
        res = enqueue_story("s_rem_1", "Rem Title", "Rem Content", "http://rem1.com", channel="moku", db_path=self.db_path)
        self.assertTrue(res)

        story = get_pending_story(db_path=self.db_path, claim=True, channel="moku")
        self.assertIsNotNone(story)
        self.assertEqual(story["story_id"], "s_rem_1")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM stories WHERE story_id = 's_rem_1'")
        status = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(status, "PROCESSING")


if __name__ == "__main__":
    unittest.main()
