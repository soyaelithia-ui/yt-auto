"""Unit tests for Phase 1 analytics database migration (MIGRATION_007)."""
import sqlite3
import tempfile
from pathlib import Path

import pytest

from src.core.repository.migrations import connect, migrate_database


def test_migration_007_adds_scoring_and_cadence_fields():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = tmp.name

        # Apply migrations
        report = migrate_database(db_path)
        assert 7 in report.applied_versions

        with connect(db_path) as conn:
            # Check publications columns
            cur = conn.execute("PRAGMA table_info(publications)")
            cols = {row["name"]: row["type"] for row in cur.fetchall()}
            assert "actual_success_score" in cols
            assert "music_track" in cols

            # Check scheduler_state columns
            cur_sched = conn.execute("PRAGMA table_info(scheduler_state)")
            sched_cols = {row["name"]: row["type"] for row in cur_sched.fetchall()}
            assert "last_24h_sweep_at" in sched_cols

            # Check indices exist
            cur_idx = conn.execute("PRAGMA index_list(publications)")
            idx_names = {row["name"] for row in cur_idx.fetchall()}
            assert "idx_publications_score" in idx_names
            assert "idx_publications_sha256" in idx_names


def test_published_inventory_stores_and_retrieves_score_and_music():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = tmp.name
        from src.core.inventory import get_published_inventory, record_published_inventory

        record = record_published_inventory(
            db_path=db_path,
            run_id="run-test-1",
            story_id="story-test-1",
            video_id="vid_test_123",
            url="https://youtube.com/watch?v=vid_test_123",
            channel="moku",
            title="Test Story Video",
            description="Test description",
            actual_success_score=78.5,
            used_resources={"music": "assets/audio/music/dark_ambient_01.mp3"},
        )
        assert record.actual_success_score == 78.5
        assert record.music_track == "assets/audio/music/dark_ambient_01.mp3"

        # Verify retrieval from SQLite
        all_records = get_published_inventory(db_path=db_path, channel="moku")
        assert len(all_records) == 1
        assert all_records[0].actual_success_score == 78.5
        assert all_records[0].music_track == "assets/audio/music/dark_ambient_01.mp3"
