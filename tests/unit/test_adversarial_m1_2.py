import os
import tempfile
import unittest
import sqlite3
import subprocess
from unittest.mock import patch, MagicMock
import requests
from contextlib import contextmanager

from src.db import (
    init_db,
    enqueue_story,
    get_pending_story,
    update_story_status,
    is_story_processed,
    _get_connection
)
from src.scraper import fetch_reddit_stories, DEFAULT_USER_AGENT
from src.llm import (
    curate_script,
    sanitize_text,
    compile_stories_to_target_words,
    _curate_with_regex,
)


class TestTask1DBResilience(unittest.TestCase):
    """Task 1: SQLite DB resilience against corrupted files, missing dirs, invalid SQL."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_db_corrupted_file_garbage_bytes(self):
        """Test DB functions when DB file contains corrupt random binary garbage."""
        bad_db = os.path.join(self.temp_dir.name, "corrupt_garbage.db")
        with open(bad_db, "wb") as f:
            f.write(b"NOT_A_SQLITE_DB_GARBAGE_DATA_1234567890" * 20)

        # SQLite connect or execute on corrupted database should raise OperationalError or DatabaseError
        with self.assertRaises((sqlite3.DatabaseError, sqlite3.OperationalError)):
            init_db(bad_db)

        with self.assertRaises((sqlite3.DatabaseError, sqlite3.OperationalError)):
            enqueue_story("s1", "Title", "Content", "http://test.com/1", db_path=bad_db)

        with self.assertRaises((sqlite3.DatabaseError, sqlite3.OperationalError)):
            get_pending_story(db_path=bad_db)

        with self.assertRaises((sqlite3.DatabaseError, sqlite3.OperationalError)):
            update_story_status("s1", "PROCESSING", db_path=bad_db)

        with self.assertRaises((sqlite3.DatabaseError, sqlite3.OperationalError)):
            is_story_processed("s1", db_path=bad_db)

    def test_db_corrupted_file_truncated_header(self):
        """Test DB functions when DB file is truncated mid-header."""
        trunc_db = os.path.join(self.temp_dir.name, "corrupt_trunc.db")
        with open(trunc_db, "wb") as f:
            f.write(b"SQLite format 3\x00"[:10])  # Truncated SQLite magic header

        with self.assertRaises((sqlite3.DatabaseError, sqlite3.OperationalError)):
            init_db(trunc_db)

    def test_db_missing_parent_directories_nested(self):
        """Test init_db automatically creates deeply nested parent directories if missing."""
        nested_db = os.path.join(self.temp_dir.name, "a", "b", "c", "deep_queue.db")
        self.assertFalse(os.path.exists(os.path.dirname(nested_db)))

        init_db(nested_db)
        self.assertTrue(os.path.exists(nested_db))
        self.assertTrue(os.path.exists(os.path.dirname(nested_db)))

        # Verify story insertion works
        res = enqueue_story("s_nest", "Nested Title", "Content", "http://nest.com", db_path=nested_db)
        self.assertTrue(res)

    def test_db_missing_parent_dir_is_a_file(self):
        """Test behavior when parent directory path component is an existing regular file."""
        file_as_dir = os.path.join(self.temp_dir.name, "file.txt")
        with open(file_as_dir, "w") as f:
            f.write("I am a file, not a directory")

        invalid_path = os.path.join(file_as_dir, "sub", "queue.db")

        with self.assertRaises((NotADirectoryError, FileExistsError, OSError)):
            init_db(invalid_path)

    def test_db_read_only_permissions(self):
        """Test read-only file permissions raise write error when mutating DB."""
        ro_db = os.path.join(self.temp_dir.name, "readonly.db")
        init_db(ro_db)
        os.chmod(ro_db, 0o444)  # Read-only

        # Read operation should work or raise permission error depending on WAL
        try:
            # Enqueue write should fail due to read-only permission
            with self.assertRaises((sqlite3.OperationalError, PermissionError)):
                enqueue_story("s_ro", "RO Title", "Content", "http://ro.com", db_path=ro_db)
        finally:
            os.chmod(ro_db, 0o666)  # Restore permission for cleanup

    def test_db_sql_injection_resilience(self):
        """Test parametrized SQL queries safely handle SQL injection attack strings."""
        db_path = os.path.join(self.temp_dir.name, "injection.db")
        init_db(db_path)

        sql_injection_id = "s_inj'; DROP TABLE stories; --"
        sql_injection_title = "Title'); DELETE FROM stories; --"
        sql_injection_content = "Content' OR '1'='1"
        sql_injection_url = "http://inj.com/'; DROP TABLE stories; --"

        res = enqueue_story(
            story_id=sql_injection_id,
            title=sql_injection_title,
            content=sql_injection_content,
            url=sql_injection_url,
            db_path=db_path
        )
        self.assertTrue(res)

        # Verify table still exists and record stored verbatim
        story = get_pending_story(db_path=db_path, claim=False)
        self.assertIsNotNone(story)
        self.assertEqual(story["story_id"], sql_injection_id)
        self.assertEqual(story["title"], sql_injection_title)
        self.assertEqual(story["content"], sql_injection_content)
        self.assertEqual(story["url"], sql_injection_url)

        # Verify table was NOT dropped
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM stories;")
        count = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)

    def test_db_special_characters_nul_unicode(self):
        """Test DB handling of NUL bytes, unicode surrogates, quotes, and multi-line text."""
        db_path = os.path.join(self.temp_dir.name, "special_chars.db")
        init_db(db_path)

        complex_content = "Line 1\nLine 2\tTabbed \"Quotes\" 'Single'\nEmoji 👻🎃🔥\nNUL:\x00Byte"
        res = enqueue_story("s_spec", "Special Title 👻", complex_content, "http://spec.com", db_path=db_path)
        self.assertTrue(res)

        story = get_pending_story(db_path=db_path)
        self.assertEqual(story["content"], complex_content)

    def test_db_update_story_status_invalid_values(self):
        """Test update_story_status validates status enum strictly."""
        db_path = os.path.join(self.temp_dir.name, "status_val.db")
        enqueue_story("s_stat", "Title", "Content", "http://stat.com", db_path=db_path)

        invalid_statuses = ["pending", "COMPLETED; DROP TABLE stories;", "", "INVALID", None, 123]
        for inv in invalid_statuses:
            with self.assertRaises((ValueError, TypeError)):
                update_story_status("s_stat", inv, db_path=db_path)

    def test_db_path_is_a_directory(self):
        """Test behavior when db_path points to an existing directory instead of a file."""
        dir_as_db = os.path.join(self.temp_dir.name, "directory_db")
        os.makedirs(dir_as_db, exist_ok=True)

        with self.assertRaises((sqlite3.OperationalError, IsADirectoryError, PermissionError)):
            init_db(dir_as_db)

    def test_db_large_payload_insertion(self):
        """Test DB resilience when enqueuing large text payloads (e.g. 5 MB story content)."""
        db_path = os.path.join(self.temp_dir.name, "large_payload.db")
        init_db(db_path)

        large_content = "Word " * 1000000  # ~5MB string
        res = enqueue_story("s_large", "Large Title", large_content, "http://large.com", db_path=db_path)
        self.assertTrue(res)

        story = get_pending_story(db_path=db_path)
        self.assertEqual(len(story["content"]), len(large_content))
        self.assertEqual(story["content"][:20], large_content[:20])


class TestTask2RedditScraperEdgeCases(unittest.TestCase):
    """Task 2: Reddit scraper post filter edge cases (empty text, NSFW, stickied, deleted)."""

    def test_scraper_empty_text_and_missing_fields(self):
        """Test scraper filters out posts with empty selftext/title/id or missing keys."""
        mock_payload = {
            "data": {
                "children": [
                    # Missing selftext
                    {"data": {"id": "p1", "title": "Title 1"}},
                    # Empty selftext
                    {"data": {"id": "p2", "title": "Title 2", "selftext": ""}},
                    # Whitespace-only selftext
                    {"data": {"id": "p3", "title": "Title 3", "selftext": "   \n\t  "}},
                    # None selftext
                    {"data": {"id": "p4", "title": "Title 4", "selftext": None}},
                    # Empty title
                    {"data": {"id": "p5", "title": "", "selftext": "Valid body text long enough"}},
                    # Missing id
                    {"data": {"title": "Title 6", "selftext": "Valid body text long enough"}}
                ]
            }
        }
        with patch("requests.get") as mock_get, patch("src.scraper._load_canonical_stories", return_value=[]):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_payload
            mock_get.return_value = mock_resp

            stories = fetch_reddit_stories(subreddit="nosleep", limit=10, min_length=10)
            self.assertEqual(len(stories), 0, "All posts with empty/missing selftext/title/id must be filtered out.")

    def test_scraper_nsfw_posts_filtering(self):
        """Test scraper filters out over_18 and nsfw posts."""
        mock_payload = {
            "data": {
                "children": [
                    {"data": {"id": "ns1", "title": "T1", "selftext": "Content long enough 1", "over_18": True}},
                    {"data": {"id": "ns2", "title": "T2", "selftext": "Content long enough 2", "nsfw": True}},
                    {"data": {"id": "ns3", "title": "T3", "selftext": "Content long enough 3", "over_18": True, "nsfw": True}},
                    {"data": {"id": "ns4", "title": "T4", "selftext": "Content long enough 4", "over_18": False, "nsfw": False}}
                ]
            }
        }
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_payload
            mock_get.return_value = mock_resp

            stories = fetch_reddit_stories(subreddit="nosleep", limit=10, min_length=10)
            self.assertEqual(len(stories), 1)
            self.assertEqual(stories[0]["id"], "ns4")

    def test_scraper_stickied_and_pinned_posts(self):
        """Test scraper filters out stickied and pinned posts."""
        mock_payload = {
            "data": {
                "children": [
                    {"data": {"id": "st1", "title": "T1", "selftext": "Content long enough 1", "stickied": True}},
                    {"data": {"id": "st2", "title": "T2", "selftext": "Content long enough 2", "pinned": True}},
                    {"data": {"id": "st3", "title": "T3", "selftext": "Content long enough 3", "stickied": False, "pinned": False}}
                ]
            }
        }
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_payload
            mock_get.return_value = mock_resp

            stories = fetch_reddit_stories(subreddit="nosleep", limit=10, min_length=10)
            self.assertEqual(len(stories), 1)
            self.assertEqual(stories[0]["id"], "st3")

    def test_scraper_deleted_and_removed_text(self):
        """Test scraper filtering of [deleted] and [removed] text, title, and author."""
        mock_payload = {
            "data": {
                "children": [
                    {"data": {"id": "del1", "title": "T1", "selftext": "[deleted]", "author": "user1"}},
                    {"data": {"id": "del2", "title": "T2", "selftext": "[removed]", "author": "user2"}},
                    {"data": {"id": "del3", "title": "[deleted]", "selftext": "Content long enough 3", "author": "user3"}},
                    {"data": {"id": "del4", "title": "[removed]", "selftext": "Content long enough 4", "author": "user4"}},
                    {"data": {"id": "del5", "title": "T5", "selftext": "Content long enough 5", "author": "[deleted]"}},
                    # Variations in spacing or casing
                    {"data": {"id": "del6", "title": "T6", "selftext": " [deleted] ", "author": "user6"}},
                    {"data": {"id": "del7", "title": "T7", "selftext": "[DELETED]", "author": "user7"}},
                    {"data": {"id": "del8", "title": "T8", "selftext": "[Removed]", "author": "user8"}},
                    {"data": {"id": "del9", "title": "T9", "selftext": "[DELETED] [DELETED]", "author": "user9"}},
                    {"data": {"id": "del10", "title": "T10", "selftext": "[removed] by moderator", "author": "user10"}},
                    # Valid post
                    {"data": {"id": "ok1", "title": "Valid Title", "selftext": "This is a completely valid creepypasta text.", "author": "ghostwriter"}}
                ]
            }
        }
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_payload
            mock_get.return_value = mock_resp

            stories = fetch_reddit_stories(subreddit="nosleep", limit=10, min_length=10)
            passed_ids = [s["id"] for s in stories]
            self.assertNotIn("del1", passed_ids, "del1 [deleted] selftext should be filtered")
            self.assertNotIn("del2", passed_ids, "del2 [removed] selftext should be filtered")
            self.assertNotIn("del3", passed_ids, "del3 [deleted] title should be filtered")
            self.assertNotIn("del4", passed_ids, "del4 [removed] title should be filtered")
            self.assertNotIn("del5", passed_ids, "del5 [deleted] author should be filtered")
            self.assertNotIn("del6", passed_ids, "del6 ' [deleted] ' whitespace selftext should be filtered")
            self.assertNotIn("del7", passed_ids, "del7 [DELETED] uppercase selftext should be filtered")
            self.assertNotIn("del8", passed_ids, "del8 [Removed] mixed case selftext should be filtered")
            self.assertNotIn("del9", passed_ids, "del9 [DELETED] [DELETED] longer text should be filtered")
            self.assertNotIn("del10", passed_ids, "del10 [removed] by moderator text should be filtered")
            self.assertIn("ok1", passed_ids, "valid story ok1 should pass")

    def test_scraper_unexpected_payload_structures(self):
        """Test scraper robustness against unexpected JSON payload shapes (None, int, non-dict children)."""
        malformed_payloads = [
            None,
            "String response",
            12345,
            [],
            {},
            {"data": None},
            {"data": "invalid"},
            {"data": {"children": "not_a_list"}},
            {"data": {"children": [None, 123, "string", {"not_data": 1}]}}
        ]
        for payload in malformed_payloads:
            with patch("requests.get") as mock_get, patch("src.scraper._load_canonical_stories", return_value=[]):
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = payload
                mock_get.return_value = mock_resp

                stories = fetch_reddit_stories(subreddit="nosleep", limit=5)
                self.assertEqual(stories, [], f"Malformed payload {payload} must return empty list without raising exception.")


class TestTask3LLMScriptCurator(unittest.TestCase):
    """Task 3: LLM script curator malformed inputs & fallback providers A (agy), B (Gemini REST), C (regex)."""

    def test_llm_curate_script_malformed_empty_inputs(self):
        """Test curate_script handles empty, None, and malformed list/dict inputs gracefully."""
        # Empty string
        res1 = curate_script("", title="Empty Story")
        self.assertIn("Título: Empty Story.", res1)

        # None raw text
        res2 = curate_script(None, title="None Story")
        self.assertIn("Título: None Story.", res2)

        # Empty list
        res3 = curate_script([], title=None)
        self.assertIn("Historia de Terror", res3)

        # List with empty dict
        res4 = curate_script([{}], title="Dict Story")
        self.assertIn("Título: Dict Story.", res4)

        # List with dict with None fields
        res5 = curate_script([{"title": None, "content": None}])
        self.assertIn("Historia de Terror", res5)

    def test_llm_fallback_chain_custom_client_fails_regex_succeeds(self):
        """Test primary custom client fails -> fallback to regex succeeds in test environment."""
        raw_text = "Late at night, I heard a scratching sound coming from under my bed. Edit: thanks for reading!"
        title = "Scratching Sound"

        mock_client = MagicMock()
        mock_client.curate_script.side_effect = RuntimeError("Service unavailable")

        script = curate_script(raw_text, title=title, client=mock_client)
        self.assertIn("Título: Scratching Sound.", script)
        self.assertIn("Late at night, I heard a scratching sound coming from under my bed.", script)
        self.assertNotIn("Edit: thanks for reading!", script)




    def test_llm_provider_c_regex_sanitizer_edge_cases(self):
        """Test sanitize_text regex handling of markdown links, naked URLs, and edit notes."""
        test_cases = [
            (
                "Check out [my twitter](https://twitter.com/user) for updates.",
                "Check out my twitter for updates."
            ),
            (
                "Visit http://example.com or https://test.org/path?query=1 for more.",
                "Visit or for more."
            ),
            (
                "The monster reached out. EDIT: Wow this blew up! Thanks for gold!",
                "The monster reached out."
            ),
            (
                "Edit - 1: fixed spelling. The window shattered.",
                "The window shattered."
            ),
            (
                "[Link with (parentheses)](https://link.com)",
                "Link with (parentheses)"
            )
        ]
        for raw, expected in test_cases:
            cleaned = sanitize_text(raw)
            self.assertEqual(cleaned, expected, f"Failed on raw input: {raw}")


if __name__ == "__main__":
    unittest.main()
