"""Unit tests for watchdog resiliency, format-adapted heartbeat timeouts, and pipeline active heartbeats."""

import os
import socket
import sqlite3
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.core.lease_reaper import (
    LeaseReaper,
    get_heartbeat_timeout_seconds,
    is_longform_lease,
)
from src.pipeline import active_heartbeat_scope


class TestWatchdogResiliency:
    """Tests for format-adaptive watchdog thresholds and active heartbeat emission."""

    def test_is_longform_lease_detection(self) -> None:
        """Correctly classify longform vs shortform lanes and owners."""
        assert is_longform_lease("moku-horror-long") is True
        assert is_longform_lease("aelithia-aita-long") is True
        assert is_longform_lease(owner="lane-moku-horror-long:worker:123") is True
        assert is_longform_lease("moku-scp-shorts") is False
        assert is_longform_lease("aelithia-drama-shorts") is False
        assert is_longform_lease() is False

    def test_get_heartbeat_timeout_seconds_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Default timeouts: 1800s for longform, 300s for shorts."""
        monkeypatch.delenv("HEARTBEAT_TIMEOUT_LONG_SECONDS", raising=False)
        monkeypatch.delenv("HEARTBEAT_TIMEOUT_SHORT_SECONDS", raising=False)
        monkeypatch.delenv("HEARTBEAT_TIMEOUT_SECONDS", raising=False)

        assert get_heartbeat_timeout_seconds("moku-horror-long") == 1800
        assert get_heartbeat_timeout_seconds("aelithia-aita-long") == 1800
        assert get_heartbeat_timeout_seconds("moku-scp-shorts") == 300
        assert get_heartbeat_timeout_seconds("aelithia-drama-shorts") == 300

    def test_get_heartbeat_timeout_seconds_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Environment variables override default heartbeat expiration thresholds."""
        monkeypatch.setenv("HEARTBEAT_TIMEOUT_LONG_SECONDS", "2400")
        monkeypatch.setenv("HEARTBEAT_TIMEOUT_SHORT_SECONDS", "450")

        assert get_heartbeat_timeout_seconds("moku-horror-long") == 2400
        assert get_heartbeat_timeout_seconds("moku-scp-shorts") == 450

    def test_longform_lease_not_reaped_at_400s_heartbeat(self, tmp_path: Path) -> None:
        """A longform lane lease with heartbeat age 400s (>300s) must NOT be reaped."""
        db_file = tmp_path / "shorts_queue.db"
        now_ts = int(time.time())
        cur_host = socket.gethostname()

        with sqlite3.connect(str(db_file)) as conn:
            conn.execute(
                "CREATE TABLE stories (story_id TEXT PRIMARY KEY, status TEXT, run_id TEXT, error_msg TEXT)"
            )
            conn.execute(
                "CREATE TABLE runs (run_id TEXT PRIMARY KEY, status TEXT, finished_at TEXT, error_code TEXT)"
            )
            conn.execute(
                "CREATE TABLE lane_leases (lane_id TEXT PRIMARY KEY, channel TEXT, owner TEXT, run_id TEXT, acquired_at INTEGER, heartbeat_at INTEGER, expires_at INTEGER)"
            )
            conn.execute(
                "CREATE TABLE leases (job_id TEXT PRIMARY KEY, channel TEXT, owner TEXT, run_id TEXT, acquired_at INTEGER, heartbeat_at INTEGER, expires_at INTEGER)"
            )

            # Insert longform lane lease with heartbeat age 400s
            conn.execute(
                "INSERT INTO stories VALUES ('story_long', 'CLAIMED', 'run_long', NULL)"
            )
            conn.execute("INSERT INTO runs VALUES ('run_long', 'PROCESSING', NULL, NULL)")
            conn.execute(
                "INSERT INTO lane_leases VALUES ('moku-horror-long', 'moku', ?, 'run_long', ?, ?, ?)",
                (
                    f"lane-moku-horror-long:{cur_host}:{os.getpid()}",
                    now_ts - 500,
                    now_ts - 400,  # 400s old: exceeds 300s but well within 1800s
                    now_ts + 3600,
                ),
            )

            # Insert short lane lease with heartbeat age 400s
            conn.execute(
                "INSERT INTO stories VALUES ('story_short', 'CLAIMED', 'run_short', NULL)"
            )
            conn.execute("INSERT INTO runs VALUES ('run_short', 'PROCESSING', NULL, NULL)")
            conn.execute(
                "INSERT INTO lane_leases VALUES ('moku-scp-shorts', 'moku', ?, 'run_short', ?, ?, ?)",
                (
                    f"lane-moku-scp-shorts:{cur_host}:{os.getpid()}",
                    now_ts - 500,
                    now_ts - 400,  # 400s old: exceeds 300s for shorts -> must be reaped
                    now_ts + 3600,
                ),
            )
            conn.commit()

        reaper = LeaseReaper(db_path=db_file)
        reaped = reaper.reap_once()

        # Only the short lane should have been reaped; longform lease must survive!
        assert reaped == 1

        with sqlite3.connect(str(db_file)) as conn:
            remaining_lanes = [
                row[0]
                for row in conn.execute(
                    "SELECT lane_id FROM lane_leases"
                ).fetchall()
            ]
            assert "moku-horror-long" in remaining_lanes
            assert "moku-scp-shorts" not in remaining_lanes

            short_run = conn.execute(
                "SELECT status, error_code FROM runs WHERE run_id = 'run_short'"
            ).fetchone()
            assert short_run[0] == "RETRYABLE_FAILED"
            assert short_run[1] == "heartbeat_timeout"

    def test_longform_lease_reaped_when_exceeding_format_threshold(
        self, tmp_path: Path
    ) -> None:
        """A longform lease exceeding the 1800s threshold IS reaped as heartbeat_timeout."""
        db_file = tmp_path / "shorts_queue.db"
        now_ts = int(time.time())
        cur_host = socket.gethostname()

        with sqlite3.connect(str(db_file)) as conn:
            conn.execute(
                "CREATE TABLE stories (story_id TEXT PRIMARY KEY, status TEXT, run_id TEXT, error_msg TEXT)"
            )
            conn.execute(
                "CREATE TABLE runs (run_id TEXT PRIMARY KEY, status TEXT, finished_at TEXT, error_code TEXT)"
            )
            conn.execute(
                "CREATE TABLE lane_leases (lane_id TEXT PRIMARY KEY, channel TEXT, owner TEXT, run_id TEXT, acquired_at INTEGER, heartbeat_at INTEGER, expires_at INTEGER)"
            )
            conn.execute(
                "CREATE TABLE leases (job_id TEXT PRIMARY KEY, channel TEXT, owner TEXT, run_id TEXT, acquired_at INTEGER, heartbeat_at INTEGER, expires_at INTEGER)"
            )

            conn.execute(
                "INSERT INTO stories VALUES ('story_long_stale', 'CLAIMED', 'run_long_stale', NULL)"
            )
            conn.execute(
                "INSERT INTO runs VALUES ('run_long_stale', 'PROCESSING', NULL, NULL)"
            )
            conn.execute(
                "INSERT INTO lane_leases VALUES ('aelithia-aita-long', 'aelithia', ?, 'run_long_stale', ?, ?, ?)",
                (
                    f"lane-aelithia-aita-long:{cur_host}:{os.getpid()}",
                    now_ts - 2500,
                    now_ts - 1900,  # 1900s old > 1800s threshold
                    now_ts + 3600,
                ),
            )
            conn.commit()

        reaper = LeaseReaper(db_path=db_file)
        reaped = reaper.reap_once()
        assert reaped == 1

        with sqlite3.connect(str(db_file)) as conn:
            assert (
                conn.execute("SELECT COUNT(*) FROM lane_leases").fetchone()[0]
                == 0
            )
            run = conn.execute(
                "SELECT status, error_code FROM runs WHERE run_id = 'run_long_stale'"
            ).fetchone()
            assert run[0] == "RETRYABLE_FAILED"
            assert run[1] == "heartbeat_timeout"

    def test_active_heartbeat_scope_background_ticker(self) -> None:
        """active_heartbeat_scope emits periodic heartbeats in the background."""
        mock_ctx = MagicMock()
        mock_ctx.run_id = "test_run_12345"
        mock_ctx.owner = "worker:123"
        mock_ctx.lease_seconds = 900
        mock_ctx._heartbeat_ticker_active = False

        heartbeat_calls: list[float] = []
        ticker_fired = threading.Event()

        def fake_heartbeat():
            heartbeat_calls.append(time.monotonic())
            if len(heartbeat_calls) >= 2:
                ticker_fired.set()
            return True

        mock_ctx.heartbeat = fake_heartbeat
        mock_ctx.require_heartbeat = MagicMock(return_value=None)

        with active_heartbeat_scope(mock_ctx, interval=0.02):
            assert mock_ctx.require_heartbeat.call_count >= 1
            ticker_fired.wait(timeout=1.0)

        # Background ticker should have fired multiple times
        assert len(heartbeat_calls) >= 2
        # After exit, _heartbeat_ticker_active is reset
        assert mock_ctx._heartbeat_ticker_active is False

    def test_active_heartbeat_scope_is_reentrant(self) -> None:
        """Nested active_heartbeat_scope calls do not spawn redundant tickers."""
        mock_ctx = MagicMock()
        mock_ctx.run_id = "test_run_reentrant"
        mock_ctx._heartbeat_ticker_active = False
        mock_ctx.heartbeat = MagicMock(return_value=True)
        mock_ctx.require_heartbeat = MagicMock(return_value=None)

        with active_heartbeat_scope(mock_ctx, interval=0.05):
            assert mock_ctx._heartbeat_ticker_active is True
            # Nested call should be a no-op
            with active_heartbeat_scope(mock_ctx, interval=0.05):
                assert mock_ctx._heartbeat_ticker_active is True
            assert mock_ctx._heartbeat_ticker_active is True

        assert mock_ctx._heartbeat_ticker_active is False

    def test_lanes_configuration_cadence_parameters(self) -> None:
        """Verify lanes.json config enforces alternating 15-min cadence for longform and 5-min for shorts."""
        import json

        config_path = Path(__file__).resolve().parent.parent.parent / "config" / "lanes.json"
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        lanes_by_id = {lane["id"]: lane for lane in data["lanes"] if lane.get("enabled")}

        # Longform lanes: 1800s gap, 900s offset between moku and aelithia
        moku_long = lanes_by_id["moku-horror-long"]
        aelithia_long = lanes_by_id["aelithia-aita-long"]

        assert moku_long["cadence"]["min_gap_seconds"] == 1800
        assert moku_long["cadence"]["initial_offset_seconds"] == 0

        assert aelithia_long["cadence"]["min_gap_seconds"] == 1800
        assert aelithia_long["cadence"]["initial_offset_seconds"] == 900

        # Shorts lanes: 600s gap, 300s offset between moku and aelithia
        moku_short = lanes_by_id["moku-scp-shorts"]
        aelithia_short = lanes_by_id["aelithia-drama-shorts"]

        assert moku_short["cadence"]["min_gap_seconds"] == 600
        assert moku_short["cadence"]["initial_offset_seconds"] == 0

        assert aelithia_short["cadence"]["min_gap_seconds"] == 600
        assert aelithia_short["cadence"]["initial_offset_seconds"] == 300
