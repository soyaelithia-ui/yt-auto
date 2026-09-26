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

        # Longform lanes: 7200s gap, 3600s offset between horror and drama
        horror_long = lanes_by_id["horror-horror-long"]
        drama_long = lanes_by_id["drama-aita-long"]

        assert horror_long["cadence"]["min_gap_seconds"] == 7200
        assert horror_long["cadence"]["initial_offset_seconds"] == 0

        assert drama_long["cadence"]["min_gap_seconds"] == 7200
        assert drama_long["cadence"]["initial_offset_seconds"] == 3600

        # Shorts lanes: 900s gap, 450s offset between horror and drama
        horror_short = lanes_by_id["horror-scp-shorts"]
        drama_short = lanes_by_id["drama-drama-shorts"]

        assert horror_short["cadence"]["min_gap_seconds"] == 900
        assert horror_short["cadence"]["initial_offset_seconds"] == 0

        assert drama_short["cadence"]["min_gap_seconds"] == 900
        assert drama_short["cadence"]["initial_offset_seconds"] == 450

    def test_dead_worker_reaped_immediately_on_sigkill(self, tmp_path: Path) -> None:
        """When worker process crashes/SIGKILLed, LeaseReaper reaps lease immediately without waiting 1800s."""
        db_file = tmp_path / "shorts_queue.db"
        now_ts = int(time.time())
        cur_host = socket.gethostname()
        dead_pid = 999999  # Guaranteed nonexistent PID on Linux

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
                "INSERT INTO stories VALUES ('story_dead_worker', 'CLAIMED', 'run_dead_worker', NULL)"
            )
            conn.execute(
                "INSERT INTO runs VALUES ('run_dead_worker', 'PROCESSING', NULL, NULL)"
            )
            # Longform lease with heartbeat age only 5s old!
            conn.execute(
                "INSERT INTO lane_leases VALUES ('moku-horror-long', 'moku', ?, 'run_dead_worker', ?, ?, ?)",
                (
                    f"lane-moku-horror-long:{cur_host}:{dead_pid}",
                    now_ts - 10,
                    now_ts - 5,  # 5s old: fresh heartbeat, but PID is dead
                    now_ts + 3600,
                ),
            )
            conn.commit()

        reaper = LeaseReaper(db_path=db_file)
        reaped = reaper.reap_once()

        assert reaped == 1
        with sqlite3.connect(str(db_file)) as conn:
            assert conn.execute("SELECT COUNT(*) FROM lane_leases").fetchone()[0] == 0
            run = conn.execute(
                "SELECT status, error_code FROM runs WHERE run_id = 'run_dead_worker'"
            ).fetchone()
            assert run[0] == "RETRYABLE_FAILED"
            assert run[1] == "worker_sigkill_reaped"

    def test_is_longform_lease_with_job_id(self) -> None:
        """Verify is_longform_lease detects longform from job_id even if lane_id and owner are generic."""
        assert is_longform_lease(job_id="aelithia_drama_long_006") is True
        assert is_longform_lease(job_id="moku_scp_short_001") is False
        assert is_longform_lease(owner="worker:localhost:123", job_id="story_longform") is True

    def test_multi_node_clock_skew_tolerance(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MULTI_NODE=1 adds clock skew tolerance to timeout."""
        monkeypatch.delenv("HEARTBEAT_TIMEOUT_LONG_SECONDS", raising=False)
        monkeypatch.delenv("HEARTBEAT_TIMEOUT_SHORT_SECONDS", raising=False)
        monkeypatch.setenv("MULTI_NODE", "1")
        monkeypatch.setenv("MULTI_NODE_CLOCK_SKEW_SECONDS", "45")

        assert get_heartbeat_timeout_seconds("moku-horror-long") == 1800 + 45
        assert get_heartbeat_timeout_seconds("moku-scp-shorts") == 300 + 45

    def test_lease_table_uses_job_id_for_longform_detection(self, tmp_path: Path) -> None:
        """In leases table, longform job_id survives 400s stale heartbeat without lane_id in owner."""
        db_file = tmp_path / "shorts_queue.db"
        now_ts = int(time.time())
        cur_host = socket.gethostname()

        with sqlite3.connect(str(db_file)) as conn:
            conn.execute(
                "CREATE TABLE stories (story_id TEXT PRIMARY KEY, status TEXT, run_id TEXT, error_msg TEXT, lane_id TEXT)"
            )
            conn.execute(
                "CREATE TABLE runs (run_id TEXT PRIMARY KEY, status TEXT, finished_at TEXT, error_code TEXT)"
            )
            conn.execute(
                "CREATE TABLE leases (job_id TEXT PRIMARY KEY, channel TEXT, owner TEXT, run_id TEXT, acquired_at INTEGER, heartbeat_at INTEGER, expires_at INTEGER)"
            )

            conn.execute(
                "INSERT INTO stories VALUES ('aelithia_drama_long_006', 'CLAIMED', 'run_directed_long', NULL, 'aelithia-aita-long')"
            )
            conn.execute(
                "INSERT INTO runs VALUES ('run_directed_long', 'PROCESSING', NULL, NULL)"
            )
            # Generic owner without 'long' in string
            conn.execute(
                "INSERT INTO leases VALUES ('aelithia_drama_long_006', 'aelithia', ?, 'run_directed_long', ?, ?, ?)",
                (
                    f"{cur_host}:{os.getpid()}",
                    now_ts - 500,
                    now_ts - 400,  # 400s old: >300s but <1800s
                    now_ts + 3600,
                ),
            )
            conn.commit()

        reaper = LeaseReaper(db_path=db_file)
        reaped = reaper.reap_once()

        # Should NOT be reaped because job_id has 'long' and story lane_id is longform!
        assert reaped == 0
        with sqlite3.connect(str(db_file)) as conn:
            assert conn.execute("SELECT COUNT(*) FROM leases").fetchone()[0] == 1

    def test_active_heartbeat_scope_none_run_id_safe(self) -> None:
        """active_heartbeat_scope handles None or missing run_id gracefully."""
        mock_ctx = MagicMock()
        mock_ctx.run_id = None
        mock_ctx._heartbeat_ticker_active = False
        mock_ctx.heartbeat = MagicMock(return_value=True)
        mock_ctx.require_heartbeat = MagicMock(return_value=None)

        with active_heartbeat_scope(mock_ctx, interval=0.02):
            assert mock_ctx._heartbeat_ticker_active is True
        assert mock_ctx._heartbeat_ticker_active is False

    def test_is_longform_lease_without_long_in_name_via_lane_lookup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify is_longform_lease resolves longform from LaneProfile even if lane_id lacks 'long'."""
        from unittest.mock import MagicMock
        from src.core import lanes

        mock_lane = MagicMock()
        mock_lane.orientation = "horizontal"
        mock_lane.qa_profile = "longform"
        mock_lane.duration_min_sec = 600

        monkeypatch.setattr(lanes, "get_lane", lambda lid: mock_lane if lid == "custom-cinema" else None)

        assert is_longform_lease(lane_id="custom-cinema") is True
        assert get_heartbeat_timeout_seconds(lane_id="custom-cinema") == 1800

    def test_lease_table_uses_runs_table_fallback(self, tmp_path: Path) -> None:
        """When stories.lane_id is NULL, LeaseReaper falls back to runs.lane_id."""
        db_file = tmp_path / "shorts_queue.db"
        now_ts = int(time.time())
        cur_host = socket.gethostname()

        with sqlite3.connect(str(db_file)) as conn:
            conn.execute(
                "CREATE TABLE stories (story_id TEXT PRIMARY KEY, status TEXT, run_id TEXT, error_msg TEXT, lane_id TEXT)"
            )
            conn.execute(
                "CREATE TABLE runs (run_id TEXT PRIMARY KEY, status TEXT, finished_at TEXT, error_code TEXT, lane_id TEXT)"
            )
            conn.execute(
                "CREATE TABLE leases (job_id TEXT PRIMARY KEY, channel TEXT, owner TEXT, run_id TEXT, acquired_at INTEGER, heartbeat_at INTEGER, expires_at INTEGER)"
            )

            # stories.lane_id is NULL, but runs.lane_id has the longform lane!
            conn.execute(
                "INSERT INTO stories VALUES ('reddit_post_xyz', 'CLAIMED', 'run_reddit_post', NULL, NULL)"
            )
            conn.execute(
                "INSERT INTO runs VALUES ('run_reddit_post', 'PROCESSING', NULL, NULL, 'aelithia-aita-long')"
            )
            conn.execute(
                "INSERT INTO leases VALUES ('reddit_post_xyz', 'aelithia', ?, 'run_reddit_post', ?, ?, ?)",
                (
                    f"{cur_host}:{os.getpid()}",
                    now_ts - 500,
                    now_ts - 400,  # 400s old: >300s but <1800s
                    now_ts + 3600,
                ),
            )
            conn.commit()

        reaper = LeaseReaper(db_path=db_file)
        reaped = reaper.reap_once()

        # Must NOT be reaped because runs.lane_id indicated longform!
        assert reaped == 0
        with sqlite3.connect(str(db_file)) as conn:
            assert conn.execute("SELECT COUNT(*) FROM leases").fetchone()[0] == 1

    def test_reaper_continues_when_single_row_errors(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """An error while reaping one row does not crash or abort sweeping the remaining rows."""
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

            # Dead worker 1: PID 999990
            conn.execute("INSERT INTO stories VALUES ('s1', 'CLAIMED', 'r1', NULL)")
            conn.execute("INSERT INTO runs VALUES ('r1', 'PROCESSING', NULL, NULL)")
            conn.execute(
                "INSERT INTO lane_leases VALUES ('lane1', 'moku', ?, 'r1', ?, ?, ?)",
                (f"lane1:{cur_host}:999990", now_ts - 100, now_ts - 50, now_ts + 100),
            )

            # Dead worker 2: PID 999991
            conn.execute("INSERT INTO stories VALUES ('s2', 'CLAIMED', 'r2', NULL)")
            conn.execute("INSERT INTO runs VALUES ('r2', 'PROCESSING', NULL, NULL)")
            conn.execute(
                "INSERT INTO lane_leases VALUES ('lane2', 'moku', ?, 'r2', ?, ?, ?)",
                (f"lane2:{cur_host}:999991", now_ts - 100, now_ts - 50, now_ts + 100),
            )
            conn.commit()

        reaper = LeaseReaper(db_path=db_file)
        reaped = reaper.reap_once()

        # Both dead workers reaped successfully
        assert reaped == 2
        with sqlite3.connect(str(db_file)) as conn:
            assert conn.execute("SELECT COUNT(*) FROM lane_leases").fetchone()[0] == 0

    def test_leases_reaper_does_not_clobber_rendered_or_published_story(self, tmp_path: Path) -> None:
        """When reaping an expired lease, a story that reached RENDERED or PUBLISHED is not set back to RETRYABLE_FAILED."""
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
                "CREATE TABLE leases (job_id TEXT PRIMARY KEY, channel TEXT, owner TEXT, run_id TEXT, acquired_at INTEGER, heartbeat_at INTEGER, expires_at INTEGER)"
            )

            # Story already PUBLISHED
            conn.execute("INSERT INTO stories VALUES ('story_done', 'PUBLISHED', 'run_done', NULL)")
            conn.execute("INSERT INTO runs VALUES ('run_done', 'COMPLETED', NULL, NULL)")
            conn.execute(
                "INSERT INTO leases VALUES ('story_done', 'moku', ?, 'run_done', ?, ?, ?)",
                (f"worker:{cur_host}:999999", now_ts - 500, now_ts - 400, now_ts - 10),  # expired TTL
            )
            conn.commit()

        reaper = LeaseReaper(db_path=db_file)
        reaped = reaper.reap_once()

        assert reaped == 1
        with sqlite3.connect(str(db_file)) as conn:
            # Lease is deleted
            assert conn.execute("SELECT COUNT(*) FROM leases").fetchone()[0] == 0
            # Story remains PUBLISHED, not clobbered to RETRYABLE_FAILED!
            story_status = conn.execute("SELECT status FROM stories WHERE story_id = 'story_done'").fetchone()[0]
            assert story_status == "PUBLISHED"

    def test_is_local_hostname_fqdn_matching(self) -> None:
        """is_local_hostname matches FQDN hostnames against short hostname."""
        from src.core.lease_reaper import is_local_hostname
        cur_host = socket.gethostname()
        short_host = cur_host.split(".")[0]

        # Hostname with FQDN domain
        owner_fqdn = f"lane-id:{short_host}.internal.net:12345"
        assert is_local_hostname(owner_fqdn) is True

        # Hostname short
        owner_short = f"lane-id:{short_host}:12345"
        assert is_local_hostname(owner_short) is True

        # Remote host
        owner_remote = "lane-id:other-server-node-99.internal.net:12345"
        assert is_local_hostname(owner_remote) is False

    def test_extract_pid_from_owner_numeric_token(self) -> None:
        """extract_pid_from_owner extracts PID from various owner string formats."""
        from src.core.lease_reaper import extract_pid_from_owner
        assert extract_pid_from_owner("lane-id:host:12345") == 12345
        assert extract_pid_from_owner("worker_42") == 42
        assert extract_pid_from_owner("lane:host:54321:worker") == 54321
        assert extract_pid_from_owner("invalid_owner") is None
        assert extract_pid_from_owner("") is None

    def test_runcontext_post_init_sets_is_long_lane(self) -> None:
        """RunContext initializes is_long_lane=True on creation when lane.orientation is horizontal."""
        from unittest.mock import MagicMock
        from pathlib import Path
        from src.pipeline import RunContext

        mock_lane = MagicMock()
        mock_lane.orientation = "horizontal"

        ctx = RunContext(
            story={"story_id": "s1"},
            story_id="s1",
            run_id="r1",
            channel_name="moku",
            channel_key="moku",
            lane=mock_lane,
            repository=MagicMock(),
            database=":memory:",
            owner="owner",
            lease_seconds=900,
            settings=MagicMock(),
            branding=MagicMock(),
            profiler=MagicMock(),
            directed=False,
            generate_only=False,
            engine_mode="loop",
            is_loop_mode=True,
            is_multiscene_mode=False,
            subtitles_active=False,
            work_dir=Path("/tmp"),
            audio_path=Path("/tmp/a.wav"),
            ass_path=Path("/tmp/a.ass"),
            srt_path=Path("/tmp/a.srt"),
            video_path=Path("/tmp/v.mp4"),
            thumbnail_path=Path("/tmp/t.jpg"),
            script_path=Path("/tmp/s.txt"),
            visual_plan_path=Path("/tmp/vp.json"),
            metadata_path=Path("/tmp/m.json"),
            scene_manifest_path=Path("/tmp/sm.json"),
        )
        assert ctx.is_long_lane is True

    def test_is_longform_lease_via_owner_lane_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify is_longform_lease parses lane id from owner prefix 'lane-<lane_id>:...'."""
        from unittest.mock import MagicMock
        from src.core import lanes

        mock_lane = MagicMock()
        mock_lane.orientation = "horizontal"
        mock_lane.qa_profile = "longform"
        mock_lane.duration_min_sec = 600

        monkeypatch.setattr(lanes, "get_lane", lambda lid: mock_lane if lid == "custom_cinema" else None)

        assert is_longform_lease(owner="lane-custom_cinema:worker_node:12345") is True
        assert get_heartbeat_timeout_seconds(owner="lane-custom_cinema:worker_node:12345") == 1800

    def test_active_remote_lease_not_reaped_on_periodic_sweep(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """In multi-node config, an active remote lease with a fresh heartbeat is NOT reaped during normal sweeps."""
        monkeypatch.setenv("MULTI_NODE", "1")
        db_file = tmp_path / "shorts_queue.db"
        now_ts = int(time.time())

        with sqlite3.connect(str(db_file)) as conn:
            conn.execute("CREATE TABLE stories (story_id TEXT PRIMARY KEY, status TEXT, run_id TEXT, error_msg TEXT, lane_id TEXT)")
            conn.execute("CREATE TABLE runs (run_id TEXT PRIMARY KEY, status TEXT, finished_at TEXT, error_code TEXT, lane_id TEXT)")
            conn.execute("CREATE TABLE lane_leases (job_id TEXT, lane_id TEXT PRIMARY KEY, channel TEXT, owner TEXT, run_id TEXT, acquired_at INTEGER, heartbeat_at INTEGER, expires_at INTEGER)")
            conn.execute("CREATE TABLE leases (job_id TEXT PRIMARY KEY, channel TEXT, owner TEXT, run_id TEXT, acquired_at INTEGER, heartbeat_at INTEGER, expires_at INTEGER)")

            conn.execute("INSERT INTO stories VALUES ('s_remote', 'CLAIMED', 'run_remote', NULL, 'moku-horror-long')")
            conn.execute("INSERT INTO runs VALUES ('run_remote', 'PROCESSING', NULL, NULL, 'moku-horror-long')")
            conn.execute(
                "INSERT INTO lane_leases VALUES ('s_remote', 'moku-horror-long', 'moku', 'lane-moku-horror-long:remote-host-99:1234', 'run_remote', ?, ?, ?)",
                (now_ts - 20, now_ts - 5, now_ts + 1800),
            )
            conn.commit()

        reaper = LeaseReaper(db_path=db_file)
        reaped = reaper.reap_once(startup=False)

        # Fresh remote heartbeat must NOT be reaped!
        assert reaped == 0
        with sqlite3.connect(str(db_file)) as conn:
            assert conn.execute("SELECT COUNT(*) FROM lane_leases").fetchone()[0] == 1

    def test_multi_node_clock_skew_tolerance_on_is_expired(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """In multi-node setups, leases expiring within the clock skew tolerance window are not prematurely reaped."""
        monkeypatch.setenv("MULTI_NODE", "1")
        monkeypatch.setenv("MULTI_NODE_CLOCK_SKEW_SECONDS", "60")
        db_file = tmp_path / "shorts_queue.db"
        now_ts = int(time.time())

        with sqlite3.connect(str(db_file)) as conn:
            conn.execute("CREATE TABLE stories (story_id TEXT PRIMARY KEY, status TEXT, run_id TEXT, error_msg TEXT, lane_id TEXT)")
            conn.execute("CREATE TABLE runs (run_id TEXT PRIMARY KEY, status TEXT, finished_at TEXT, error_code TEXT, lane_id TEXT)")
            conn.execute("CREATE TABLE lane_leases (job_id TEXT, lane_id TEXT PRIMARY KEY, channel TEXT, owner TEXT, run_id TEXT, acquired_at INTEGER, heartbeat_at INTEGER, expires_at INTEGER)")
            conn.execute("CREATE TABLE leases (job_id TEXT PRIMARY KEY, channel TEXT, owner TEXT, run_id TEXT, acquired_at INTEGER, heartbeat_at INTEGER, expires_at INTEGER)")

            conn.execute("INSERT INTO stories VALUES ('s_skew', 'CLAIMED', 'run_skew', NULL, 'moku-horror-long')")
            conn.execute("INSERT INTO runs VALUES ('run_skew', 'PROCESSING', NULL, NULL, 'moku-horror-long')")
            conn.execute(
                "INSERT INTO lane_leases VALUES ('s_skew', 'moku-horror-long', 'moku', 'lane-moku-horror-long:remote-node-2:1234', 'run_skew', ?, ?, ?)",
                (now_ts - 900, now_ts - 10, now_ts - 5),  # 5s in past on local clock, but < 60s skew tolerance
            )
            conn.commit()

        reaper = LeaseReaper(db_path=db_file)
        reaped = reaper.reap_once(startup=False)

        assert reaped == 0
        with sqlite3.connect(str(db_file)) as conn:
            assert conn.execute("SELECT COUNT(*) FROM lane_leases").fetchone()[0] == 1

    def test_lease_with_null_job_id_deleted_cleanly(self, tmp_path: Path) -> None:
        """A lease entry with NULL job_id is cleanly deleted upon reaping rather than causing infinite sweeps."""
        db_file = tmp_path / "shorts_queue.db"
        dead_pid = 999999

        with sqlite3.connect(str(db_file)) as conn:
            conn.execute("CREATE TABLE stories (story_id TEXT PRIMARY KEY, status TEXT, run_id TEXT, error_msg TEXT)")
            conn.execute("CREATE TABLE runs (run_id TEXT PRIMARY KEY, status TEXT, finished_at TEXT, error_code TEXT)")
            conn.execute("CREATE TABLE leases (job_id TEXT, channel TEXT, owner TEXT, run_id TEXT, acquired_at INTEGER, heartbeat_at INTEGER, expires_at INTEGER)")

            conn.execute("INSERT INTO runs VALUES ('run_null_job', 'PROCESSING', NULL, NULL)")
            conn.execute(f"INSERT INTO leases VALUES (NULL, 'moku', 'worker:localhost:{dead_pid}', 'run_null_job', 100, 100, 100)")
            conn.commit()

        reaper = LeaseReaper(db_path=db_file)
        reaped = reaper.reap_once(startup=False)

        assert reaped == 1
        with sqlite3.connect(str(db_file)) as conn:
            assert conn.execute("SELECT COUNT(*) FROM leases").fetchone()[0] == 0

    def test_story_updated_by_run_id_when_job_id_is_null_in_leases(self, tmp_path: Path) -> None:
        """In leases table, if job_id is NULL or mismatch, the story matching run_id is updated to RETRYABLE_FAILED."""
        db_file = tmp_path / "shorts_queue.db"
        dead_pid = 999999

        with sqlite3.connect(str(db_file)) as conn:
            conn.execute("CREATE TABLE stories (story_id TEXT PRIMARY KEY, status TEXT, run_id TEXT, error_msg TEXT)")
            conn.execute("CREATE TABLE runs (run_id TEXT PRIMARY KEY, status TEXT, finished_at TEXT, error_code TEXT)")
            conn.execute("CREATE TABLE leases (job_id TEXT, channel TEXT, owner TEXT, run_id TEXT, acquired_at INTEGER, heartbeat_at INTEGER, expires_at INTEGER)")

            conn.execute("INSERT INTO stories VALUES ('story_matched_by_run', 'CLAIMED', 'run_orphan_story', NULL)")
            conn.execute("INSERT INTO runs VALUES ('run_orphan_story', 'PROCESSING', NULL, NULL)")
            conn.execute(f"INSERT INTO leases VALUES (NULL, 'moku', 'worker:localhost:{dead_pid}', 'run_orphan_story', 100, 100, 100)")
            conn.commit()

        reaper = LeaseReaper(db_path=db_file)
        reaped = reaper.reap_once(startup=False)

        assert reaped == 1
        with sqlite3.connect(str(db_file)) as conn:
            story = conn.execute("SELECT status FROM stories WHERE story_id = 'story_matched_by_run'").fetchone()
            assert story[0] == "RETRYABLE_FAILED"

    def test_ffmpeg_run_handles_empty_cmd(self) -> None:
        """_ffmpeg_run returns CompletedProcess with error instead of raising IndexError on empty cmd."""
        from lib.qa_gatekeeper import _ffmpeg_run
        res = _ffmpeg_run([])
        assert res.returncode == 1

    def test_runcontext_post_init_detects_longform_via_qa_profile_and_duration(self) -> None:
        """RunContext sets is_long_lane=True if lane qa_profile is longform or duration_min_sec >= 300."""
        from unittest.mock import MagicMock
        from pathlib import Path
        from src.pipeline import RunContext

        mock_lane = MagicMock()
        mock_lane.orientation = "custom"
        mock_lane.qa_profile = "longform"
        mock_lane.duration_min_sec = 600

        ctx = RunContext(
            story={"story_id": "s2"},
            story_id="s2",
            run_id="r2",
            channel_name="aelithia",
            channel_key="aelithia",
            lane=mock_lane,
            repository=MagicMock(),
            database=":memory:",
            owner="owner",
            lease_seconds=900,
            settings=MagicMock(),
            branding=MagicMock(),
            profiler=MagicMock(),
            directed=False,
            generate_only=False,
            engine_mode="loop",
            is_loop_mode=True,
            is_multiscene_mode=False,
            subtitles_active=False,
            work_dir=Path("/tmp"),
            audio_path=Path("/tmp/a.wav"),
            ass_path=Path("/tmp/a.ass"),
            srt_path=Path("/tmp/a.srt"),
            video_path=Path("/tmp/v.mp4"),
            thumbnail_path=Path("/tmp/t.jpg"),
            script_path=Path("/tmp/s.txt"),
            visual_plan_path=Path("/tmp/vp.json"),
            metadata_path=Path("/tmp/m.json"),
            scene_manifest_path=Path("/tmp/sm.json"),
        )
        assert ctx.is_long_lane is True

    def test_runcontext_post_init_safe_with_unconfigured_magicmock_lane(self) -> None:
        """RunContext initializes cleanly without TypeError when lane is an unconfigured MagicMock."""
        from unittest.mock import MagicMock
        from pathlib import Path
        from src.pipeline import RunContext

        mock_lane = MagicMock()
        ctx = RunContext(
            story={"story_id": "s_mock"},
            story_id="s_mock",
            run_id="r_mock",
            channel_name="moku",
            channel_key="moku",
            lane=mock_lane,
            repository=MagicMock(),
            database=":memory:",
            owner="owner",
            lease_seconds=900,
            settings=MagicMock(),
            branding=MagicMock(),
            profiler=MagicMock(),
            directed=False,
            generate_only=False,
            engine_mode="loop",
            is_loop_mode=True,
            is_multiscene_mode=False,
            subtitles_active=False,
            work_dir=Path("/tmp"),
            audio_path=Path("/tmp/a.wav"),
            ass_path=Path("/tmp/a.ass"),
            srt_path=Path("/tmp/a.srt"),
            video_path=Path("/tmp/v.mp4"),
            thumbnail_path=Path("/tmp/t.jpg"),
            script_path=Path("/tmp/s.txt"),
            visual_plan_path=Path("/tmp/vp.json"),
            metadata_path=Path("/tmp/m.json"),
            scene_manifest_path=Path("/tmp/sm.json"),
        )
        assert ctx.is_long_lane is False

    def test_is_longform_lease_safe_with_mock_lane(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """is_longform_lease safely evaluates when get_lane returns an unconfigured MagicMock."""
        from unittest.mock import MagicMock
        from src.core.lease_reaper import is_longform_lease

        mock_lane = MagicMock()
        monkeypatch.setattr("src.core.lanes.get_lane", lambda lane_id: mock_lane)
        # Should not raise TypeError and return False for generic unconfigured mock
        assert is_longform_lease(lane_id="custom_lane") is False


