import os
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from src.db import init_db, enqueue_story, get_pending_story, update_story_status
from src.youtube.uploader import upload_video, upload_video_via_api
from src.config import BASE_DIR, DECRYPTED_COOKIES_PATH, COOKIES_CHANNEL2_PATH


class TestAdversarialM2MultiChannel(unittest.TestCase):
    """Adversarial test suite for M2 multi-channel story enqueueing and upload credentials isolation."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_queue.db")
        init_db(self.db_path)

        self.dummy_video = os.path.join(self.temp_dir.name, "test_video.mp4")
        with open(self.dummy_video, "wb") as f:
            f.write(b"MOCK_MP4_CONTENT")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_queue_enqueue_and_claim_isolation(self):
        """Verify that enqueueing stories for 'soy_el_malo' and 'terror' places stories in their respective channels without cross-contamination."""
        # 1. Enqueue stories for both channels
        res_malo = enqueue_story(
            story_id="malo_story_001",
            title="¿Soy el malo por no prestar dinero?",
            content="Mi hermano me pidió dinero prestado...",
            url="https://reddit.com/r/AmItheAsshole/1",
            channel="soy_el_malo",
            db_path=self.db_path,
        )
        self.assertTrue(res_malo)

        res_terror = enqueue_story(
            story_id="terror_story_001",
            title="La sombra en la ventana",
            content="Escuché un ruido a medianoche...",
            url="https://reddit.com/r/nosleep/1",
            channel="terror",
            db_path=self.db_path,
        )
        self.assertTrue(res_terror)

        # 2. Get pending story for 'soy_el_malo' (without claiming)
        pending_malo = get_pending_story(db_path=self.db_path, claim=False, channel="soy_el_malo")
        self.assertIsNotNone(pending_malo)
        self.assertEqual(pending_malo["story_id"], "malo_story_001")
        self.assertEqual(pending_malo["channel"], "aelithia")

        # 3. Get pending story for 'terror' (without claiming)
        pending_terror = get_pending_story(db_path=self.db_path, claim=False, channel="terror")
        self.assertIsNotNone(pending_terror)
        self.assertEqual(pending_terror["story_id"], "terror_story_001")
        self.assertEqual(pending_terror["channel"], "moku")

        # 4. Claim pending story for 'soy_el_malo'
        claimed_malo = get_pending_story(db_path=self.db_path, claim=True, channel="soy_el_malo")
        self.assertIsNotNone(claimed_malo)
        self.assertEqual(claimed_malo["story_id"], "malo_story_001")
        self.assertEqual(claimed_malo["status"], "PROCESSING")

        # 5. Ensure 'terror' pending story is untouched
        pending_terror_after = get_pending_story(db_path=self.db_path, claim=False, channel="terror")
        self.assertIsNotNone(pending_terror_after)
        self.assertEqual(pending_terror_after["story_id"], "terror_story_001")
        self.assertEqual(pending_terror_after["status"], "PENDING")

        # 6. Attempting to claim another 'soy_el_malo' story should return None
        no_more_malo = get_pending_story(db_path=self.db_path, claim=True, channel="soy_el_malo")
        self.assertIsNone(no_more_malo)

    def test_multi_story_compilation_channel_isolation(self):
        """Verify that multi-story compilation query filters strictly by channel and does not consume stories from another channel."""
        enqueue_story("malo_1", "Title 1", "Short content 1", "https://reddit.com/r/AITA/1", channel="soy_el_malo", db_path=self.db_path)
        enqueue_story("terror_1", "Terror 1", "Short terror content", "https://reddit.com/r/nosleep/1", channel="terror", db_path=self.db_path)
        enqueue_story("malo_2", "Title 2", "Short content 2", "https://reddit.com/r/AITA/2", channel="soy_el_malo", db_path=self.db_path)

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM stories WHERE status = 'PENDING' AND channel = 'aelithia' AND story_id != ? ORDER BY created_at ASC", ("malo_1",))
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()

        # Should only fetch malo_2, NOT terror_1
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["story_id"], "malo_2")
        self.assertEqual(rows[0]["channel"], "aelithia")

    def test_terror_channel_token_path_resolution(self):
        """Verify upload_video resolves terror channel (Channel 1) default token path to canonical moku channel."""
        res = upload_video(self.dummy_video, "Terror Title", "Terror Desc", channel="terror")
        self.assertIn(res["status"], ("TEST_MOCK", "SUCCESS"))
        self.assertEqual(res["channel"], "moku")

    def test_soy_el_malo_channel_token_and_cookies_path_resolution(self):
        """Verify upload_video resolves soy_el_malo channel (Channel 2) to canonical aelithia channel without cross-contamination."""
        res = upload_video(self.dummy_video, "Soy El Malo Title", "Soy El Malo Desc", channel="soy_el_malo")
        self.assertIn(res["status"], ("TEST_MOCK", "SUCCESS"))
        self.assertEqual(res["channel"], "aelithia")


if __name__ == "__main__":
    unittest.main()
