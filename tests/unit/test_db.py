import os
import tempfile
import unittest
import sqlite3

from src.db import (
    init_db,
    enqueue_story,
    get_pending_story,
    update_story_status,
    is_story_processed,
)


class TestDatabaseManager(unittest.TestCase):
    """Unit tests for SQLite Database Manager (src/db.py)."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_queue.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_init_db_creates_table_wal_mode_and_timeout(self):
        """Test DB initialization sets WAL journal mode, busy timeout, and creates stories table."""
        init_db(self.db_path)
        self.assertTrue(os.path.exists(self.db_path))

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA journal_mode;")
        journal_mode = cursor.fetchone()[0]
        self.assertEqual(journal_mode.lower(), "wal")

        cursor.execute("PRAGMA busy_timeout;")
        busy_timeout = cursor.fetchone()[0]
        self.assertEqual(busy_timeout, 5000)

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stories';")
        table = cursor.fetchone()
        self.assertIsNotNone(table)
        conn.close()

    def test_enqueue_story_success(self):
        """Test enqueuing a new story returns True and saves row in DB."""
        res = enqueue_story(
            story_id="s101",
            title="Haunted House",
            content="Ghostly figures in the hallway...",
            url="https://reddit.com/r/nosleep/comments/s101",
            db_path=self.db_path
        )
        self.assertTrue(res)
        self.assertTrue(is_story_processed("s101", db_path=self.db_path))
        self.assertTrue(is_story_processed("https://reddit.com/r/nosleep/comments/s101", db_path=self.db_path))

    def test_enqueue_story_duplicate_id_prevention(self):
        """Test duplicate story_id insertion returns False."""
        res1 = enqueue_story("s102", "Title 1", "Content 1", "https://reddit.com/s102", db_path=self.db_path)
        self.assertTrue(res1)

        res2 = enqueue_story("s102", "Title 2", "Content 2", "https://reddit.com/s102_dup", db_path=self.db_path)
        self.assertFalse(res2, "Duplicate story_id must be rejected.")

    def test_enqueue_story_duplicate_url_prevention(self):
        """Test duplicate URL insertion returns False."""
        res1 = enqueue_story("s103", "Title A", "Content A", "https://reddit.com/same_url", db_path=self.db_path)
        self.assertTrue(res1)

        res2 = enqueue_story("s104", "Title B", "Content B", "https://reddit.com/same_url", db_path=self.db_path)
        self.assertFalse(res2, "Duplicate URL must be rejected.")

    def test_get_pending_story_without_claim(self):
        """Test get_pending_story without claim returns pending story without changing DB status."""
        enqueue_story("s105", "Title 5", "Content 5", "https://reddit.com/s105", db_path=self.db_path)

        story = get_pending_story(db_path=self.db_path, claim=False)
        self.assertIsNotNone(story)
        self.assertEqual(story["story_id"], "s105")
        self.assertEqual(story["status"], "PENDING")

        # Verify DB state remains PENDING
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM stories WHERE story_id = 's105'")
        status = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(status, "PENDING")

    def test_get_pending_story_with_claim(self):
        """Test atomic state claim: get_pending_story with claim=True updates status to PROCESSING in DB."""
        enqueue_story("s106", "Title 6", "Content 6", "https://reddit.com/s106", db_path=self.db_path)

        story = get_pending_story(
            db_path=self.db_path, claim=True, channel="moku"
        )
        self.assertIsNotNone(story)
        self.assertEqual(story["story_id"], "s106")

        # Verify DB status is updated to PROCESSING
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM stories WHERE story_id = 's106'")
        status = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(status, "PROCESSING")

    def test_get_pending_story_empty_queue(self):
        """Test get_pending_story returns None when queue is empty."""
        init_db(self.db_path)
        story = get_pending_story(db_path=self.db_path)
        self.assertIsNone(story)

    def test_update_story_status_transitions(self):
        """Test status transitions: PENDING -> PROCESSING -> COMPLETED / FAILED with error msg."""
        enqueue_story("s107", "Title 7", "Content 7", "https://reddit.com/s107", db_path=self.db_path)

        update_story_status("s107", "PROCESSING", db_path=self.db_path)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT status, error_msg FROM stories WHERE story_id = 's107'")
        row = cursor.fetchone()
        self.assertEqual(row[0], "PROCESSING")
        self.assertIsNone(row[1])

        update_story_status("s107", "FAILED", error_msg="Audio synthesis failed", db_path=self.db_path)
        cursor.execute("SELECT status, error_msg FROM stories WHERE story_id = 's107'")
        row = cursor.fetchone()
        self.assertEqual(row[0], "FAILED")
        self.assertEqual(row[1], "Audio synthesis failed")
        conn.close()

    def test_update_story_status_invalid_raises_value_error(self):
        """Test updating to invalid status raises ValueError."""
        enqueue_story("s108", "Title 8", "Content 8", "https://reddit.com/s108", db_path=self.db_path)
        with self.assertRaises(ValueError):
            update_story_status("s108", "UNKNOWN_STATUS", db_path=self.db_path)

    def test_is_story_processed(self):
        """Test is_story_processed returns True for existing story_id/url and False for unknown."""
        enqueue_story("s109", "Title 9", "Content 9", "https://reddit.com/s109", db_path=self.db_path)
        self.assertTrue(is_story_processed("s109", db_path=self.db_path))
        self.assertTrue(is_story_processed("https://reddit.com/s109", db_path=self.db_path))
        self.assertFalse(is_story_processed("s999", db_path=self.db_path))


if __name__ == "__main__":
    unittest.main()
