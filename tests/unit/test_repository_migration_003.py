"""Unit tests for SQLite repository Migration 003: scene assets, analytics snapshots, and telemetry."""
import sqlite3
import pytest
from pathlib import Path
from src.core.repository import QueueRepository, migrate_database, connect

def test_migration_003_applied_successfully(tmp_path):
    db_path = tmp_path / "test_queue.db"
    repo = QueueRepository(db_path)
    report = repo.initialize()

    assert 3 in report.applied_versions or 1 in report.applied_versions
    assert report.quick_check == "ok"

    with connect(db_path) as conn:
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "story_scene_assets" in tables
        assert "video_analytics_snapshots" in tables
        assert "production_metrics" in tables

def test_record_and_get_scene_assets(tmp_path):
    db_path = tmp_path / "test_queue.db"
    repo = QueueRepository(db_path)
    repo.initialize()

    story_id = "story_test_001"
    repo.enqueue(story_id=story_id, title="Test Story", content="Content", url="https://reddit.com/r/test", channel="moku")
    lease = repo.claim("moku", owner="worker_1")
    run_id = lease["run_id"]

    assets = [
        {
            "scene_index": 0,
            "shot_index": 0,
            "asset_source": "curated_web",
            "source_url_or_path": "https://images.unsplash.com/photo-test-1",
            "framing_type": "WIDE_ESTABLISHING",
            "prompt_used": "spooky dark corridor",
            "dhash": "a1b2c3d4e5f60718",
            "duration_sec": 4.5,
        },
        {
            "scene_index": 0,
            "shot_index": 1,
            "asset_source": "local_bank",
            "source_url_or_path": "/assets/visual_bank/moku/scenery/abyssal_creature.jpg",
            "framing_type": "CLOSEUP_TENSION",
            "prompt_used": "shadowy figure in woods",
            "dhash": "1807f6e5d4c3b2a1",
            "duration_sec": 3.2,
        },
    ]

    inserted = repo.record_scene_assets(run_id=run_id, story_id=story_id, scene_assets=assets)
    assert inserted == 2

    retrieved = repo.get_scene_assets(story_id=story_id)
    assert len(retrieved) == 2
    assert retrieved[0]["asset_source"] == "curated_web"
    assert retrieved[0]["framing_type"] == "WIDE_ESTABLISHING"
    assert retrieved[1]["asset_source"] == "local_bank"
    assert retrieved[1]["duration_sec"] == 3.2

def test_record_and_get_production_metrics(tmp_path):
    db_path = tmp_path / "test_queue.db"
    repo = QueueRepository(db_path)
    repo.initialize()

    story_id = "story_test_002"
    repo.enqueue(story_id=story_id, title="Test Story 2", content="Content", url="https://reddit.com/r/test2", channel="aelithia")
    lease = repo.claim("aelithia", owner="worker_1")
    run_id = lease["run_id"]

    repo.record_production_metrics(
        run_id=run_id,
        story_id=story_id,
        audio_duration_sec=62.4,
        render_time_sec=18.5,
        tts_time_sec=4.2,
        video_size_bytes=15_400_200,
        integrated_lufs=-14.2,
        qa_audit_passed=True,
    )

    metrics = repo.get_production_metrics(run_id=run_id)
    assert metrics is not None
    assert metrics["run_id"] == run_id
    assert metrics["audio_duration_sec"] == 62.4
    assert metrics["render_time_sec"] == 18.5
    assert metrics["video_size_bytes"] == 15_400_200
    assert metrics["qa_audit_passed"] == 1

def test_record_and_get_analytics_snapshots(tmp_path):
    db_path = tmp_path / "test_queue.db"
    repo = QueueRepository(db_path)
    repo.initialize()

    story_id = "story_test_003"
    repo.enqueue(story_id=story_id, title="Test Story 3", content="Content", url="https://reddit.com/r/test3", channel="moku")

    snapshot_1 = repo.record_analytics_snapshot(
        video_id="yt_vid_123",
        story_id=story_id,
        channel="moku",
        view_count=150,
        like_count=25,
        comment_count=5,
        avg_view_duration_sec=45.2,
        retention_rate_pct=72.5,
        snapshot_interval="1h",
    )
    assert snapshot_1 is True

    snapshot_2 = repo.record_analytics_snapshot(
        video_id="yt_vid_123",
        story_id=story_id,
        channel="moku",
        view_count=1200,
        like_count=180,
        comment_count=35,
        avg_view_duration_sec=51.0,
        retention_rate_pct=81.2,
        snapshot_interval="24h",
    )
    assert snapshot_2 is True

    snapshots = repo.get_analytics_snapshots(story_id=story_id)
    assert len(snapshots) == 2
    assert snapshots[0]["snapshot_interval"] == "1h"
    assert snapshots[0]["view_count"] == 150
    assert snapshots[1]["snapshot_interval"] == "24h"
    assert snapshots[1]["view_count"] == 1200