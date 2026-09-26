"""Unit tests for SQLite repository Migration 009, token burn persistence, and telemetry queries."""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.repository import (
    EXPECTED_MIGRATION_VERSION,
    MIGRATION_009,
    QueueRepository,
    connect,
    migrate_database,
)


def _utc_iso(delta_hours: float = 0.0, delta_days: float = 0.0) -> str:
    """Helper to generate UTC ISO timestamp strings relative to now."""
    dt = datetime.now(timezone.utc) + timedelta(hours=delta_hours, days=delta_days)
    return dt.isoformat(timespec="seconds")


@pytest.fixture
def repo(tmp_path: Path) -> QueueRepository:
    db_path = tmp_path / "test_telemetry.db"
    r = QueueRepository(db_path)
    r.initialize()
    return r


def test_migration_009_schema_and_indices(tmp_path: Path) -> None:
    """Assert Migration 009 provisions token_burn_events (16 columns), 4 read indices, and system_events index."""
    db_path = tmp_path / "migration_test.db"
    report = migrate_database(db_path)

    assert 9 in report.applied_versions
    assert EXPECTED_MIGRATION_VERSION == 9

    with connect(db_path) as conn:
        # Verify schema_migrations entry
        row = conn.execute(
            "SELECT version, name, checksum FROM schema_migrations WHERE version = 9"
        ).fetchone()
        assert row is not None
        assert row["name"] == "pipeline_telemetry_and_token_burn"
        assert row["checksum"] != ""

        # Verify token_burn_events table columns
        cols = {
            r["name"]: r["type"].upper()
            for r in conn.execute("PRAGMA table_info(token_burn_events)").fetchall()
        }
        expected_columns = {
            "event_id",
            "ts",
            "run_id",
            "story_id",
            "channel",
            "provider",
            "model",
            "prompt_tokens",
            "completion_tokens",
            "cached_tokens",
            "reasoning_tokens",
            "total_tokens",
            "cost_usd",
            "duration_seconds",
            "status",
            "created_at",
        }
        assert set(cols.keys()) == expected_columns
        assert len(cols) == 16

        # Verify indices on token_burn_events
        tb_indices = {
            r["name"]
            for r in conn.execute("PRAGMA index_list(token_burn_events)").fetchall()
        }
        assert "idx_token_burn_ts" in tb_indices
        assert "idx_token_burn_run" in tb_indices
        assert "idx_token_burn_provider_model" in tb_indices
        assert "idx_token_burn_channel" in tb_indices

        # Verify index on system_events
        se_indices = {
            r["name"]
            for r in conn.execute("PRAGMA index_list(system_events)").fetchall()
        }
        assert "idx_events_type_ts" in se_indices

        # Verify CHECK constraint on status
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO token_burn_events (event_id, ts, provider, model, status)
                VALUES ('bad-1', '2026-09-25T12:00:00+00:00', 'gemini', 'flash', 'invalid_status')
                """
            )


def test_record_token_burn_persistence(repo: QueueRepository) -> None:
    """Validate QueueRepository.record_token_burn() persists LLM and TTS records accurately."""
    # Persist LLM record
    llm_id = repo.record_token_burn(
        run_id="run-llm-1",
        story_id="story-100",
        channel="horror",
        provider="antigravity_pro",
        model="gemini-2.5-pro",
        prompt_tokens=1500,
        completion_tokens=600,
        cached_tokens=500,
        reasoning_tokens=200,
        total_tokens=2100,
        cost_usd=0.0045,
        duration_seconds=1.85,
        status="success",
    )
    assert llm_id != ""

    # Persist TTS record (duration, character count mapped to total_tokens)
    tts_id = repo.record_token_burn(
        run_id="run-tts-1",
        story_id="story-100",
        channel="horror",
        provider="elevenlabs",
        model="es-ES-AlvaroNeural",
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=1250,
        cost_usd=0.0375,
        duration_seconds=3.42,
        status="success",
    )
    assert tts_id != ""

    # Verify rows in database
    with connect(repo.db_path, read_only=True) as conn:
        rows = {
            r["event_id"]: dict(r)
            for r in conn.execute("SELECT * FROM token_burn_events").fetchall()
        }
        assert llm_id in rows
        llm_row = rows[llm_id]
        assert llm_row["run_id"] == "run-llm-1"
        assert llm_row["channel"] == "horror"
        assert llm_row["provider"] == "antigravity_pro"
        assert llm_row["model"] == "gemini-2.5-pro"
        assert llm_row["prompt_tokens"] == 1500
        assert llm_row["completion_tokens"] == 600
        assert llm_row["cached_tokens"] == 500
        assert llm_row["reasoning_tokens"] == 200
        assert llm_row["total_tokens"] == 2100
        assert pytest.approx(llm_row["cost_usd"], 0.0001) == 0.0045
        assert pytest.approx(llm_row["duration_seconds"], 0.01) == 1.85
        assert llm_row["status"] == "success"

        assert tts_id in rows
        tts_row = rows[tts_id]
        assert tts_row["provider"] == "elevenlabs"
        assert tts_row["total_tokens"] == 1250
        assert pytest.approx(tts_row["cost_usd"], 0.0001) == 0.0375
        assert pytest.approx(tts_row["duration_seconds"], 0.01) == 3.42


def test_record_token_burn_fail_open_isolation(repo: QueueRepository) -> None:
    """Test that simulated SQLite write failures in record_token_burn log debug messages without raising."""
    with patch("src.core.repository.queue.connect") as mock_connect:
        mock_connect.side_effect = sqlite3.OperationalError("database is locked")
        # Should not raise exception
        event_id = repo.record_token_burn(
            provider="gemini_rest",
            model="gemini-2.5-pro",
            prompt_tokens=100,
            completion_tokens=50,
        )
        assert isinstance(event_id, str)


def test_query_token_burn_summary_aggregations(repo: QueueRepository) -> None:
    """Assert QueueRepository.query_token_burn_summary() aggregates tokens and USD costs over selectable windows."""
    now_ts = _utc_iso()
    recent_ts = _utc_iso(delta_hours=-2)
    stale_ts = _utc_iso(delta_hours=-36)

    # 1. Antigravity Pro record (recent)
    repo.record_token_burn(
        ts=now_ts,
        channel="horror",
        provider="antigravity_pro",
        model="gemini-2.5-pro",
        prompt_tokens=1000,
        completion_tokens=500,
        cached_tokens=200,
        reasoning_tokens=100,
        total_tokens=1500,
        cost_usd=0.003,
        duration_seconds=1.2,
    )

    # 2. Gemini REST record (recent)
    repo.record_token_burn(
        ts=recent_ts,
        channel="horror",
        provider="gemini_rest",
        model="gemini-2.5-flash",
        prompt_tokens=2000,
        completion_tokens=1000,
        cached_tokens=0,
        reasoning_tokens=0,
        total_tokens=3000,
        cost_usd=0.0015,
        duration_seconds=0.8,
    )

    # 3. TTS record on different channel (recent)
    repo.record_token_burn(
        ts=recent_ts,
        channel="drama",
        provider="elevenlabs",
        model="es-ES-AlvaroNeural",
        total_tokens=800,
        cost_usd=0.024,
        duration_seconds=2.5,
    )

    # 4. Old record outside 24h window
    repo.record_token_burn(
        ts=stale_ts,
        channel="horror",
        provider="antigravity_pro",
        model="gemini-2.5-pro",
        total_tokens=5000,
        cost_usd=0.010,
    )

    # Query 24h summary without channel filter
    summary = repo.query_token_burn_summary(window_hours=24)

    assert summary.window_hours == 24
    assert summary.total_prompt_tokens == 3000
    assert summary.total_completion_tokens == 1500
    assert summary.total_cached_tokens == 200
    assert summary.total_reasoning_tokens == 100
    assert summary.total_tokens == 5300
    assert pytest.approx(summary.total_cost_usd, 0.0001) == 0.0285
    assert summary.total_calls == 3
    assert summary.total_saturations == 0

    # Provider breakdown verification
    assert "antigravity_pro" in summary.provider_breakdown
    ag_summary = summary.provider_breakdown["antigravity_pro"]
    assert ag_summary["total_tokens"] == 1500
    assert pytest.approx(ag_summary["cost_usd"], 0.0001) == 0.003

    assert "gemini_rest" in summary.provider_breakdown
    gem_summary = summary.provider_breakdown["gemini_rest"]
    assert gem_summary["total_tokens"] == 3000

    assert "elevenlabs" in summary.provider_breakdown
    assert summary.provider_breakdown["elevenlabs"]["total_tokens"] == 800

    # Model breakdown verification
    assert "gemini-2.5-pro" in summary.model_breakdown
    assert "gemini-2.5-flash" in summary.model_breakdown
    assert "es-ES-AlvaroNeural" in summary.model_breakdown

    # Query with channel filter
    horror_summary = repo.query_token_burn_summary(window_hours=24, channel="horror")
    assert horror_summary.total_calls == 2
    assert horror_summary.total_tokens == 4500
    assert pytest.approx(horror_summary.total_cost_usd, 0.0001) == 0.0045


def test_query_token_burn_summary_saturation_tally(repo: QueueRepository) -> None:
    """Assert records with status = 'saturated' increment the saturation counter without distorting total tokens."""
    repo.record_token_burn(
        channel="horror",
        provider="antigravity_pro",
        model="gemini-2.5-pro",
        prompt_tokens=1000,
        completion_tokens=500,
        total_tokens=1500,
        cost_usd=0.003,
        status="success",
    )
    repo.record_token_burn(
        channel="horror",
        provider="antigravity_pro",
        model="gemini-2.5-pro",
        prompt_tokens=500,
        completion_tokens=0,
        total_tokens=0,
        cost_usd=0.0,
        status="saturated",
    )

    summary = repo.query_token_burn_summary(window_hours=24)
    assert summary.total_calls == 2
    assert summary.total_saturations == 1
    assert summary.total_tokens == 1500
    assert summary.provider_breakdown["antigravity_pro"]["saturations"] == 1


def test_prune_token_burn_events_retention(repo: QueueRepository) -> None:
    """Verify QueueRepository.prune_token_burn_events(retention_days=30) deletes stale records older than 30 days."""
    old_ts = _utc_iso(delta_days=-40)
    recent_ts = _utc_iso(delta_days=-5)

    repo.record_token_burn(
        ts=old_ts,
        provider="gemini_rest",
        model="gemini-2.5-flash",
        total_tokens=1000,
    )
    repo.record_token_burn(
        ts=old_ts,
        provider="gemini_rest",
        model="gemini-2.5-flash",
        total_tokens=2000,
    )
    repo.record_token_burn(
        ts=recent_ts,
        provider="gemini_rest",
        model="gemini-2.5-flash",
        total_tokens=500,
    )

    deleted_count = repo.prune_token_burn_events(retention_days=30)
    assert deleted_count == 2

    # Verify only recent record remains
    with connect(repo.db_path, read_only=True) as conn:
        rows = conn.execute("SELECT * FROM token_burn_events").fetchall()
        assert len(rows) == 1
        assert rows[0]["total_tokens"] == 500


def test_query_asset_rejection_counts(repo: QueueRepository) -> None:
    """Assert query_asset_rejection_counts aggregates automated QA defects and human review rejections."""
    # Emit automated QA rejections
    repo.record_system_event(
        "asset_rejection",
        level="WARNING",
        channel="horror",
        stage="stage_10_verify",
        details={"category": "sync", "asset_id": "video_shot_01.mp4", "measured_ms": 140},
    )
    repo.record_system_event(
        "asset_rejection",
        level="WARNING",
        channel="horror",
        stage="stage_10_verify",
        details={"category": "visual", "asset_id": "scenery_abyssal.jpg"},
    )
    repo.record_system_event(
        "asset_rejection",
        level="WARNING",
        channel="drama",
        stage="stage_10_verify",
        details={"category": "luminance", "asset_id": "dark_frame.png"},
    )

    # Human Telegram review rejection
    with connect(repo.db_path) as conn:
        conn.execute(
            """
            INSERT INTO review_jobs (
                job_id, version, project, channel, content_type,
                title, description, original_video_path, status,
                created_at, reviewed_at
            ) VALUES (
                'job-editorial-1', 1, 'YTShort', 'horror', 'short',
                'Title', 'Desc', '/tmp/video.mp4', 'REJECTED',
                ?, ?
            )
            """,
            (_utc_iso(delta_hours=-1), _utc_iso(delta_hours=-1)),
        )
        conn.commit()

    summary = repo.query_asset_rejection_counts(window_hours=24)
    assert summary.window_hours == 24
    assert summary.total_automated_rejections == 3
    assert summary.total_human_rejections == 1
    assert summary.total_rejections == 4
    assert summary.category_breakdown["sync"] == 1
    assert summary.category_breakdown["visual"] == 1
    assert summary.category_breakdown["luminance"] == 1
    assert summary.category_breakdown["editorial"] == 1
    assert summary.channel_breakdown["horror"] == 3
    assert summary.channel_breakdown["drama"] == 1
    assert len(summary.top_offending_assets) >= 3


def test_query_tube_incidents(repo: QueueRepository) -> None:
    """Assert query_tube_incidents retrieves operational incidents chronologically descending."""
    repo.record_system_event(
        "cookie_warning",
        level="WARNING",
        channel="horror",
        message="Cookie expiring in 36h",
        details={"channel": "horror", "hours_left": 36},
    )
    time.sleep(0.01)
    repo.record_system_event(
        "lease_recovered",
        level="INFO",
        channel="drama",
        message="Orphaned lease recovered",
        details={"lane_id": "drama-shorts", "owner": "worker-404"},
    )

    incidents = repo.query_tube_incidents(window_hours=24, limit=10)
    assert len(incidents) == 2
    # Chronological descending (newest first)
    assert incidents[0]["event_type"] == "lease_recovered"
    assert incidents[1]["event_type"] == "cookie_warning"
    assert incidents[0]["details"]["owner"] == "worker-404"


def test_query_channel_stoppages(repo: QueueRepository) -> None:
    """Assert query_channel_stoppages aggregates paused channels, active worker locks, and daemon heartbeat."""
    # 1. Paused channel control
    repo.pause_channel("drama", reason="Scheduled maintenance")

    # 2. Active lease and lane lease
    current = int(time.time())
    with connect(repo.db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        # Global lease (expired)
        conn.execute(
            """
            INSERT INTO runs (run_id, channel, status, owner, started_at, heartbeat_at)
            VALUES ('run-expired', 'scifi', 'processing', 'worker-old', '2026-09-25T10:00:00Z', '2026-09-25T10:00:00Z')
            """
        )
        conn.execute(
            """
            INSERT INTO stories (story_id, channel, title, content, url, status)
            VALUES ('story-expired', 'scifi', 'Expired Story', 'Content', 'https://example.com/expired', 'processing')
            """
        )
        conn.execute(
            """
            INSERT INTO leases (job_id, channel, owner, run_id, acquired_at, heartbeat_at, expires_at)
            VALUES ('story-expired', 'scifi', 'worker-old', 'run-expired', ?, ?, ?)
            """,
            (current - 300, current - 300, current - 60),
        )
        # Lane lease (active in future)
        conn.execute(
            """
            INSERT INTO runs (run_id, channel, lane_id, status, owner, started_at, heartbeat_at)
            VALUES ('run-active', 'horror', 'horror-shorts', 'processing', 'worker-act', '2026-09-25T12:00:00Z', '2026-09-25T12:00:00Z')
            """
        )
        conn.execute(
            """
            INSERT INTO stories (story_id, channel, lane_id, title, content, url, status)
            VALUES ('story-active', 'horror', 'horror-shorts', 'Active Story', 'Content', 'https://example.com/active', 'processing')
            """
        )
        conn.execute(
            """
            INSERT INTO lane_leases (job_id, lane_id, channel, owner, run_id, acquired_at, heartbeat_at, expires_at)
            VALUES ('story-active', 'horror-shorts', 'horror', 'worker-act', 'run-active', ?, ?, ?)
            """,
            (current, current, current + 900),
        )
        conn.commit()

    # Touch daemon liveness
    from src.core.repository.leases import touch_daemon_liveness
    touch_daemon_liveness(repo.db_path, now=current)

    stoppages = repo.query_channel_stoppages()
    assert stoppages.daemon_liveness_status == "HEALTHY"
    assert stoppages.heartbeat_age_seconds is not None
    assert stoppages.heartbeat_age_seconds <= 5

    # Check paused channels
    paused_channels = [p["channel"] for p in stoppages.paused_channels]
    assert "drama" in paused_channels

    # Check active & expired locks
    assert len(stoppages.active_locks) == 2
    assert stoppages.expired_locks_count == 1
