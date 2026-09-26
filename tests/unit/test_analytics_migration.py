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


def test_migration_009_canonical_channels_analytics():
    """Verify MIGRATION_009 allows inserting canonical channels ('horror', 'drama', 'scifi')."""
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = tmp.name
        report = migrate_database(db_path)
        assert 9 in report.applied_versions

        with connect(db_path) as conn:
            # Seed a parent story to satisfy foreign key
            conn.execute(
                "INSERT INTO stories(story_id, title, content, url, channel) "
                "VALUES ('story_1', 'Scary Story', 'Raw horror content', 'https://example.com/1', 'horror')"
            )
            # Insert snapshots for canonical channels
            for ch in ("horror", "drama", "scifi", "moku", "aelithia"):
                conn.execute(
                    "INSERT INTO video_analytics_snapshots ("
                    "    video_id, story_id, channel, view_count, like_count, comment_count, "
                    "    avg_view_duration_sec, retention_rate_pct, snapshot_interval, recorded_at"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (f"vid_{ch}", "story_1", ch, 100, 10, 5, 45.0, 60.0, "24h", "2026-01-01T00:00:00Z"),
                )
            conn.commit()

            cur = conn.execute("SELECT COUNT(*) FROM video_analytics_snapshots")
            assert cur.fetchone()[0] == 5

            # Non-canonical channel must still be rejected by CHECK constraint
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO video_analytics_snapshots ("
                    "    video_id, story_id, channel, view_count, like_count, comment_count, "
                    "    avg_view_duration_sec, retention_rate_pct, snapshot_interval, recorded_at"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    ("vid_bad", "story_1", "invalid_channel", 1, 1, 0, 10.0, 10.0, "24h", "2026-01-01T00:00:00Z"),
                )


def test_migration_009_upgrades_legacy_check_constraint_and_preserves_data():
    """Verify that an existing database with legacy ('moku', 'aelithia') check constraint is safely rebuilt."""
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = tmp.name

        # Create old schema directly
        with connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS stories (
                    story_id TEXT PRIMARY KEY,
                    channel TEXT NOT NULL,
                    title TEXT NOT NULL,
                    raw_text TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS video_analytics_snapshots (
                    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id TEXT NOT NULL,
                    story_id TEXT NOT NULL,
                    channel TEXT NOT NULL CHECK(channel IN ('moku', 'aelithia')),
                    view_count INTEGER NOT NULL DEFAULT 0,
                    like_count INTEGER NOT NULL DEFAULT 0,
                    comment_count INTEGER NOT NULL DEFAULT 0,
                    avg_view_duration_sec REAL,
                    retention_rate_pct REAL,
                    snapshot_interval TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    FOREIGN KEY(story_id) REFERENCES stories(story_id)
                )
                """
            )
            conn.execute(
                "INSERT INTO stories(story_id, channel, title, raw_text, status, created_at) "
                "VALUES ('story_old', 'moku', 'Old Story', 'Old text', 'DRAFT', '2026-01-01T00:00:00Z')"
            )
            conn.execute(
                "INSERT INTO video_analytics_snapshots ("
                "    video_id, story_id, channel, view_count, like_count, comment_count, "
                "    avg_view_duration_sec, retention_rate_pct, snapshot_interval, recorded_at"
                ") VALUES ('vid_old', 'story_old', 'moku', 50, 5, 1, 30.0, 50.0, '24h', '2026-01-01T00:00:00Z')"
            )
            # Rejection with old schema
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO video_analytics_snapshots ("
                    "    video_id, story_id, channel, view_count, like_count, comment_count, "
                    "    avg_view_duration_sec, retention_rate_pct, snapshot_interval, recorded_at"
                    ") VALUES ('vid_horror', 'story_old', 'horror', 50, 5, 1, 30.0, 50.0, '24h', '2026-01-01T00:00:00Z')"
                )
            conn.commit()

        # Run migration to upgrade schema
        report = migrate_database(db_path)
        assert 9 in report.applied_versions

        with connect(db_path) as conn:
            # Verify old row preserved
            row = conn.execute("SELECT video_id, channel FROM video_analytics_snapshots WHERE video_id = 'vid_old'").fetchone()
            assert row is not None
            assert row["channel"] == "moku"

            # Verify horror now succeeds
            conn.execute(
                "INSERT INTO video_analytics_snapshots ("
                "    video_id, story_id, channel, view_count, like_count, comment_count, "
                "    avg_view_duration_sec, retention_rate_pct, snapshot_interval, recorded_at"
                ") VALUES ('vid_horror', 'story_old', 'horror', 75, 12, 3, 40.0, 55.0, '24h', '2026-01-01T00:00:00Z')"
            )
            conn.commit()
            row2 = conn.execute("SELECT video_id, channel FROM video_analytics_snapshots WHERE video_id = 'vid_horror'").fetchone()
            assert row2 is not None
            assert row2["channel"] == "horror"
