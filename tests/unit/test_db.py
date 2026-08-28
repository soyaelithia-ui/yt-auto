import asyncio
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from src.core.domain import JobStatus
from src.core.repository import (
    QueueRepository,
    compute_simhash_64,
    connect,
    wal_checkpoint_passive as repo_wal_checkpoint_passive,
)
from src.db import (
    _get_connection,
    async_enqueue_story,
    async_get_pending_story,
    async_init_db,
    async_is_story_duplicate,
    async_is_story_processed,
    async_reset_processing_stories,
    async_update_story_status,
    async_wal_checkpoint_passive,
    enqueue_story,
    get_db_connection,
    get_expired_pending_videos,
    get_pending_story,
    init_db,
    is_story_duplicate,
    is_story_processed,
    reset_processing_stories,
    update_story_status,
    update_video_status,
    wal_checkpoint_passive,
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

    def test_get_connection_pragmas(self):
        """Test _get_connection and get_db_connection configure 15s timeout, WAL, NORMAL sync, and FKs."""
        init_db(self.db_path)
        conn = _get_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA journal_mode;")
        self.assertEqual(cursor.fetchone()[0].lower(), "wal")

        cursor.execute("PRAGMA busy_timeout;")
        self.assertEqual(cursor.fetchone()[0], 15000)

        cursor.execute("PRAGMA synchronous;")
        # NORMAL synchronous is represented as 1 in SQLite
        self.assertEqual(cursor.fetchone()[0], 1)

        cursor.execute("PRAGMA foreign_keys;")
        self.assertEqual(cursor.fetchone()[0], 1)
        conn.close()

        with get_db_connection(self.db_path) as gconn:
            cur = gconn.cursor()
            cur.execute("PRAGMA busy_timeout;")
            self.assertEqual(cur.fetchone()[0], 15000)

    def test_enqueue_story_success(self):
        """Test enqueuing a new story returns True and saves row in DB."""
        res = enqueue_story(
            story_id="s101",
            title="Haunted House",
            content="Ghostly figures in the hallway...",
            url="https://reddit.com/r/nosleep/comments/s101",
            db_path=self.db_path,
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

    def test_is_story_duplicate_3_tiers(self):
        """Test 3-tier duplicate checks in is_story_duplicate: Tier 1 (ID/title/URL), Tier 2 (SHA-256), Tier 3 (SimHash)."""
        repo = QueueRepository(self.db_path)
        repo.initialize()

        content_1 = (
            "SCP-173 debe estar confinado en una habitación cerrada en todo momento. "
            "Cuando el personal deba entrar en el contenedor de contención de SCP-173, no menos de tres personas "
            "deben entrar y la puerta debe volver a cerrarse tras ellos. Dos personas deben mantener contacto visual continuo "
            "con SCP-173 hasta que todo el personal haya abandonado y vuelto a cerrar la celda. "
            "La criatura no puede moverse mientras esté en una línea de visión directa."
        )
        content_near = (
            "SCP-173 debe estar confinado en una habitación cerrada en todo momento. "
            "Cuando el personal deba entrar en el contenedor de contención de SCP-173, no menos de tres personas "
            "deben entrar y la puerta debe volver a cerrarse tras ellos. Dos personas deben mantener contacto visual continuo "
            "con SCP-173 hasta que todo el personal haya salido y vuelto a cerrar la celda. "
            "La criatura no puede moverse mientras esté en una línea de visión directa."
        )
        content_diff = "Hoy les traigo una receta tradicional de tacos al pastor caseros para el fin de semana."

        # Seed story
        repo.enqueue("s-dup-1", "SCP-173: La Escultura", content_1, "https://scp-wiki.wikidot.com/scp-173", "moku")
        h1 = compute_simhash_64(content_1)
        repo.record_fingerprint(
            run_id="run-dup-1",
            story_id="s-dup-1",
            channel="moku",
            kind="script",
            payload=content_1,
            normalized_text=content_1,
            simhash=h1,
        )

        # Tier 1: Exact ID, Title or URL
        self.assertTrue(is_story_duplicate("moku", "s-dup-1", db_path=self.db_path))
        self.assertTrue(is_story_duplicate("moku", "SCP-173: La Escultura", db_path=self.db_path))
        self.assertTrue(is_story_duplicate("moku", "https://scp-wiki.wikidot.com/scp-173", db_path=self.db_path))

        # Tier 2: Exact content (SHA-256) with different title/url
        self.assertTrue(is_story_duplicate("moku", "Nuevo Título Desconocido", content=content_1, db_path=self.db_path))

        # Tier 3: Near-duplicate content (SimHash Hamming <= 3) with different title/url
        self.assertTrue(is_story_duplicate("moku", "Otro Título Diferente", content=content_near, db_path=self.db_path))

        # Distinct story is not duplicate
        self.assertFalse(is_story_duplicate("moku", "Tacos al Pastor", content=content_diff, db_path=self.db_path))

        # Channel isolation: Duplicate in 'moku' is NOT a duplicate in 'aelithia'
        self.assertFalse(is_story_duplicate("aelithia", "SCP-173: La Escultura", content=content_1, db_path=self.db_path))

    def test_is_story_duplicate_empty_and_uninitialized(self):
        """Test is_story_duplicate handles empty strings and uninitialized db without crashing."""
        fresh_db = os.path.join(self.temp_dir.name, "uninit.db")
        self.assertFalse(is_story_duplicate("moku", "", None, db_path=fresh_db))
        self.assertFalse(is_story_duplicate("moku", "   ", "   ", db_path=fresh_db))

    def test_reset_processing_stories_dual_tier(self):
        """Test reset_processing_stories recovers both channel and lane expired leases."""
        repo = QueueRepository(self.db_path)
        repo.initialize()

        repo.enqueue("s-lease-ch", "Story Channel", "Content channel", "https://x/ch", "aelithia")
        repo.enqueue("s-lease-lane", "Story Lane", "Content lane", "https://x/lane", "moku", lane_id="moku-scp-shorts")

        # Claim with lease in the future
        import time
        now = int(time.time())
        claimed_ch = repo.claim("aelithia", "worker-1", lease_seconds=600, now=now)
        claimed_lane = repo.claim_for_lane("moku-scp-shorts", "moku", "worker-2", lease_seconds=600, now=now)
        self.assertIsNotNone(claimed_ch)
        self.assertIsNotNone(claimed_lane)

        # Before expiry, reset returns 0
        self.assertEqual(reset_processing_stories(db_path=self.db_path), 0)

        # Manually expire in DB
        with connect(self.db_path) as conn:
            conn.execute("UPDATE leases SET expires_at = 500")
            conn.execute("UPDATE lane_leases SET expires_at = 500")
            conn.commit()

        # Now reset recovers both
        recovered = reset_processing_stories(db_path=self.db_path)
        self.assertEqual(recovered, 2)

    def test_get_expired_pending_videos_and_update_video_status(self):
        """Test get_expired_pending_videos filters by status and cutoff timestamp."""
        init_db(self.db_path)
        now_dt = datetime.now(timezone.utc)
        old_time = (now_dt - timedelta(hours=3)).isoformat()
        recent_time = (now_dt + timedelta(hours=1)).isoformat()

        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO stories(story_id, title, content, url, status, created_at, channel)
                VALUES ('v1', 'Old Review', 'Desc 1', 'https://video/v1', 'pending_approval', ?, 'moku'),
                       ('v2', 'Recent Review', 'Desc 2', 'https://video/v2', 'pending_approval', ?, 'moku'),
                       ('v3', 'Old Completed', 'Desc 3', 'https://video/v3', 'COMPLETED', ?, 'moku')
                """,
                (old_time, recent_time, old_time),
            )
            conn.commit()

        cutoff = (now_dt - timedelta(hours=1)).isoformat()
        expired_videos = get_expired_pending_videos(cutoff, db_path=self.db_path)
        self.assertEqual(len(expired_videos), 1)
        self.assertEqual(expired_videos[0]["id"], "v1")

        # Update video status
        update_video_status("v1", "REJECTED", error_msg="Timeout review", db_path=self.db_path)
        with connect(self.db_path, read_only=True) as conn:
            row = conn.execute("SELECT status, error_msg FROM stories WHERE story_id = 'v1'").fetchone()
            self.assertEqual(row["status"], "REJECTED")
            self.assertEqual(row["error_msg"], "Timeout review")

    def test_async_db_helpers(self):
        """Test async non-blocking wrapper functions."""
        async def run_async_flow():
            await async_init_db(self.db_path)
            enq_ok = await async_enqueue_story(
                story_id="s-async-1",
                title="Async Title",
                content="Async Content",
                url="https://reddit.com/async_1",
                channel="moku",
                score=50,
                db_path=self.db_path,
            )
            self.assertTrue(enq_ok)

            processed = await async_is_story_processed("s-async-1", db_path=self.db_path)
            self.assertTrue(processed)

            is_dup = await async_is_story_duplicate("moku", "Async Title", db_path=self.db_path)
            self.assertTrue(is_dup)

            pending = await async_get_pending_story(db_path=self.db_path, claim=True, channel="moku")
            self.assertIsNotNone(pending)
            self.assertEqual(pending["story_id"], "s-async-1")

            await async_update_story_status("s-async-1", "COMPLETED", db_path=self.db_path)
            recovered = await async_reset_processing_stories(db_path=self.db_path)
            self.assertEqual(recovered, 0)

        asyncio.run(run_async_flow())

    def test_wal_checkpoint_passive(self):
        """Test passive WAL checkpoint execution and repository methods."""
        init_db(self.db_path)
        for i in range(5):
            enqueue_story(
                story_id=f"story_ckpt_{i}",
                title=f"Title {i}",
                content=f"Content {i}",
                url=f"https://example.com/ckpt_{i}",
                db_path=self.db_path,
            )

        # Standalone function
        busy, log_pages, ckpt_pages = wal_checkpoint_passive(self.db_path)
        self.assertEqual(busy, 0)
        self.assertIsInstance(log_pages, int)
        self.assertIsInstance(ckpt_pages, int)

        # Repository methods
        repo = QueueRepository(self.db_path)
        rbusy, rlog, rckpt = repo.wal_checkpoint_passive()
        self.assertEqual(rbusy, 0)

        cbusy, clog, cckpt = repo.checkpoint_wal(mode="PASSIVE")
        self.assertEqual(cbusy, 0)

        # Non-existent DB path returns safe defaults (0, 0, 0)
        non_existent = os.path.join(self.temp_dir.name, "non_existent.db")
        nbusy, nlog, nckpt = wal_checkpoint_passive(non_existent)
        self.assertEqual((nbusy, nlog, nckpt), (0, 0, 0))

    def test_async_wal_checkpoint_passive(self):
        """Test asynchronous passive WAL checkpointing."""
        init_db(self.db_path)
        enqueue_story(
            story_id="story_async_ckpt",
            title="Async Ckpt Title",
            content="Async Ckpt Content",
            url="https://example.com/async_ckpt",
            db_path=self.db_path,
        )

        busy, log_pages, ckpt_pages = asyncio.run(async_wal_checkpoint_passive(self.db_path))
        self.assertEqual(busy, 0)
        self.assertIsInstance(log_pages, int)
        self.assertIsInstance(ckpt_pages, int)


if __name__ == "__main__":
    unittest.main()


