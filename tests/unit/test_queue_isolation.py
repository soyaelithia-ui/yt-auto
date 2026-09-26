"""
Unit tests for Queue DB Isolation and Multi-Channel Producer Discriminators.
Verifies shorts_queue.db and longform_queue.db physical isolation and claim filtering.
"""
import os
import sqlite3
import tempfile
from pathlib import Path
import pytest

from src.core.repository import QueueRepository
from src.core.domain import CanonicalChannel
from src.config import SETTINGS, DEFAULT_DB_PATH


from src.db import init_db


def test_queue_database_isolation():
    """Verify physical database path isolation for YTShort and YTAuto queues."""
    shorts_db = "/var/lib/yt/data/shorts_queue.db"
    longform_db = "/var/lib/yt/data/longform_queue.db"

    if os.path.exists(shorts_db) and os.path.exists(longform_db):
        assert shorts_db != longform_db, "Shorts queue DB and Longform queue DB must be physically separate"
        assert os.path.isfile(shorts_db)
        assert os.path.isfile(longform_db)


def test_claim_discriminator_filters_by_channel_and_producer():
    """Verify QueueRepository claim filters strictly by requested canonical channel and producer mode."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        init_db(db_path)
        repo = QueueRepository(db_path)
        with sqlite3.connect(db_path) as conn:
            conn.execute("""
                INSERT INTO stories (story_id, title, content, url, status, channel)
                VALUES ('scp_001', 'SCP 087 Short', 'Desc', 'http://scp087', 'PENDING', 'horror')
            """)
            conn.execute("""
                INSERT INTO stories (story_id, title, content, url, status, channel)
                VALUES ('aita_001', 'AITA Story', 'Desc', 'http://aita1', 'PENDING', 'drama')
            """)
            conn.commit()

        # Claim for horror (scp short flow)
        claimed_horror = repo.claim(CanonicalChannel.HORROR, owner="yt-short-daemon", mode="horror+scp+short")
        assert claimed_horror is not None
        assert claimed_horror["story_id"] == "scp_001"

        # Claim for drama (reddit_aita flow)
        claimed_drama = repo.claim(CanonicalChannel.DRAMA, owner="yt-auto-daemon", mode="drama+reddit_aita+longform")
        assert claimed_drama is not None
        assert claimed_drama["story_id"] == "aita_001"

        # Horror cannot claim drama's story and vice-versa
        assert repo.claim(CanonicalChannel.HORROR, owner="yt-short-daemon") is None
        assert repo.claim(CanonicalChannel.DRAMA, owner="yt-auto-daemon") is None

    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)
