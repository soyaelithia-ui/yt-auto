"""Unit tests for LaneDaemonOrchestrator lifecycle, dispatch, and concurrency."""

from __future__ import annotations

import concurrent.futures
import os
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from src.core.contracts.daemon import LaneDaemonConfig
from src.core.domain import CanonicalChannel
from src.core.repository import connect, migrate_database
from src.core.scheduler import LanePick
from src.orchestrator.scheduler import LaneDaemonOrchestrator


@pytest.fixture
def test_db(tmp_path: pytest.TempPathFactory) -> str:
    db_file = str(tmp_path / "test_shorts_queue.db")
    migrate_database(db_file)
    return db_file


def test_orchestrator_initialization_flow(test_db: str) -> None:
    """Verify initialization flow: preflight, migrations, reaper, and lane seeding."""
    config = LaneDaemonConfig(db_path=test_db, apply_offsets=True)
    orchestrator = LaneDaemonOrchestrator(config)

    with (
        patch("src.orchestrator.scheduler.ensure_disk_available") as mock_preflight,
        patch("src.core.lease_reaper.LeaseReaper.reap_once") as mock_reap,
        patch("src.cleaner.clean_expired_failed_runs") as mock_clean_runs,
        patch("src.cleaner.clean_untracked_temp_files") as mock_clean_temp,
    ):
        orchestrator.initialize()
        mock_preflight.assert_called_once_with(test_db)
        mock_reap.assert_any_call(startup=True, channel=orchestrator.target_channel)
        mock_clean_runs.assert_called_once()
        mock_clean_temp.assert_called_once()


def test_orchestrator_tick_reaps_zombies_and_stale_leases(test_db: str) -> None:
    """Verify tick runs zombie reaping and stale lease recovery deterministically."""
    config = LaneDaemonConfig(db_path=test_db, enable_sweeps=False)
    orchestrator = LaneDaemonOrchestrator(config)

    mock_pool = MagicMock(spec=concurrent.futures.ThreadPoolExecutor)
    active_jobs: dict = {}

    with (
        patch.object(orchestrator, "_reap_zombies_safe", return_value=1) as mock_reap_zombies,
        patch("src.core.lease_reaper.LeaseReaper.reap_once") as mock_reap_leases,
    ):
        orchestrator.tick(mock_pool, active_jobs)
        mock_reap_zombies.assert_called_once()
        mock_reap_leases.assert_any_call(channel=orchestrator.target_channel)


def test_orchestrator_tick_dispatches_due_lanes_up_to_capacity(test_db: str) -> None:
    """Verify tick dispatches picks into thread pool up to capacity."""
    config = LaneDaemonConfig(db_path=test_db, max_parallel=2, enable_sweeps=False)
    orchestrator = LaneDaemonOrchestrator(config)

    mock_pool = MagicMock(spec=concurrent.futures.ThreadPoolExecutor)
    fut1 = concurrent.futures.Future()
    fut2 = concurrent.futures.Future()
    mock_pool.submit.side_effect = [fut1, fut2]

    picks = [
        LanePick("horror-scp-shorts", CanonicalChannel.HORROR, 1000, 1300),
        LanePick("drama-drama-shorts", CanonicalChannel.DRAMA, 1000, 1300),
    ]

    active_jobs: dict = {}
    with patch.object(orchestrator.lane_scheduler, "take_due_lanes", return_value=picks) as mock_take:
        orchestrator.tick(mock_pool, active_jobs)
        assert mock_take.call_count == 1
        assert len(active_jobs) == 2
        assert fut1 in active_jobs
        assert fut2 in active_jobs


def test_orchestrator_tick_excludes_currently_running_lanes(test_db: str) -> None:
    """Verify currently running lanes are excluded from subsequent pick queries."""
    config = LaneDaemonConfig(db_path=test_db, max_parallel=3, enable_sweeps=False)
    orchestrator = LaneDaemonOrchestrator(config)

    mock_pool = MagicMock(spec=concurrent.futures.ThreadPoolExecutor)
    existing_fut = concurrent.futures.Future()
    running_pick = LanePick("horror-scp-shorts", CanonicalChannel.HORROR, 1000, 1300)
    active_jobs = {existing_fut: (running_pick, time.monotonic())}

    with patch.object(orchestrator.lane_scheduler, "take_due_lanes", return_value=[]) as mock_take:
        orchestrator.tick(mock_pool, active_jobs)
        call_kwargs = mock_take.call_args.kwargs
        assert "exclude_lanes" in call_kwargs
        assert "horror-scp-shorts" in call_kwargs["exclude_lanes"]
        assert "horror-scp-shorts" not in call_kwargs["lanes_filter"]


def test_orchestrator_watchdog_timeout_cancels_and_records_failed(test_db: str) -> None:
    """Verify timed-out worker future is cancelled and recorded as RETRYABLE_FAILED."""
    config = LaneDaemonConfig(db_path=test_db, enable_sweeps=False)
    orchestrator = LaneDaemonOrchestrator(config)

    fut = concurrent.futures.Future()
    pick = LanePick("horror-scp-shorts", CanonicalChannel.HORROR, 1000, 1300)
    # Start time in the distant past
    active_jobs = {fut: (pick, time.monotonic() - 1000.0)}

    with (
        patch.object(orchestrator, "_turn_timeout_seconds", return_value=10.0),
        patch("src.core.process_watch.terminate_hung_ffmpeg") as mock_term,
        patch.object(orchestrator, "commit_empty") as mock_empty,
    ):
        results = orchestrator._watchdog_check(active_jobs)
        assert len(results) == 1
        assert results[0]["status"] == "RETRYABLE_FAILED"
        assert results[0]["error_code"] == "timeout"
        assert results[0]["lane"] == "horror-scp-shorts"
        assert fut.cancelled()
        assert len(active_jobs) == 0
        mock_term.assert_called_once()
        mock_empty.assert_called_once_with(pick)


def test_orchestrator_drain_futures_commits_cadence_and_releases_leases(test_db: str) -> None:
    """Verify successful future completion commits fire and cleans lane leases."""
    config = LaneDaemonConfig(db_path=test_db, enable_sweeps=False)
    orchestrator = LaneDaemonOrchestrator(config)

    fut = concurrent.futures.Future()
    fut.set_result({
        "status": "COMPLETED",
        "lane": "horror-scp-shorts",
        "channel": "horror",
        "run_id": "run-abc",
    })
    pick = LanePick("horror-scp-shorts", CanonicalChannel.HORROR, 1000, 1300)
    active_jobs = {fut: (pick, time.monotonic())}

    # Insert a dummy lease
    with connect(test_db) as conn:
        conn.execute("PRAGMA foreign_keys = OFF;")
        conn.execute(
            """INSERT INTO lane_leases
            (job_id, lane_id, channel, owner, run_id, acquired_at, heartbeat_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("story-1", "horror-scp-shorts", "horror", "worker-1", "run-abc", 1000, 1000, int(time.time()) + 500),
        )
        conn.commit()

    with patch.object(orchestrator, "commit_fire") as mock_commit_fire:
        results = orchestrator._drain_completed_futures(active_jobs)
        assert len(results) == 1
        assert results[0]["status"] == "COMPLETED"
        mock_commit_fire.assert_called_once_with(pick, run_id="run-abc")
        assert len(active_jobs) == 0

    # Ensure lease was removed
    with connect(test_db, read_only=True) as conn:
        row = conn.execute(
            "SELECT 1 FROM lane_leases WHERE lane_id = ?", ("horror-scp-shorts",)
        ).fetchone()
        assert row is None


def test_orchestrator_drain_futures_empty_commits_adaptive_backoff(test_db: str) -> None:
    """Verify LANE_EMPTY status commits adaptive backoff."""
    config = LaneDaemonConfig(db_path=test_db, enable_sweeps=False)
    orchestrator = LaneDaemonOrchestrator(config)

    fut = concurrent.futures.Future()
    fut.set_result({
        "status": "LANE_EMPTY",
        "lane": "drama-drama-shorts",
        "channel": "drama",
    })
    pick = LanePick("drama-drama-shorts", CanonicalChannel.DRAMA, 1000, 1300)
    active_jobs = {fut: (pick, time.monotonic())}

    with patch.object(orchestrator, "commit_empty") as mock_commit_empty:
        results = orchestrator._drain_completed_futures(active_jobs)
        assert len(results) == 1
        assert results[0]["status"] == "LANE_EMPTY"
        mock_commit_empty.assert_called_once_with(pick)


def test_orchestrator_sweeps_execution_cadence(test_db: str) -> None:
    """Verify 30s auto-publish sweep and maintenance sweeps trigger properly."""
    config = LaneDaemonConfig(db_path=test_db, enable_sweeps=True)
    orchestrator = LaneDaemonOrchestrator(config)
    orchestrator._last_auto_publish_sweep = time.monotonic() - 35.0
    orchestrator._last_24h_sweep = time.time() - 90000.0

    with (
        patch("src.daemon._run_auto_publish_sweep") as mock_pub_sweep,
        patch("src.daemon._run_24h_maintenance_sweep") as mock_24h_sweep,
        patch("src.core.repository.touch_daemon_liveness") as mock_liveness,
    ):
        orchestrator._run_sweeps_if_due(ticks=0)
        mock_pub_sweep.assert_called_once_with(channel=orchestrator.target_channel)
        mock_24h_sweep.assert_called_once()
        mock_liveness.assert_called_once_with(test_db)


def test_orchestrator_graceful_shutdown_drains_futures(test_db: str) -> None:
    """Verify request_shutdown stops run_loop and drains futures."""
    config = LaneDaemonConfig(db_path=test_db, max_ticks=10, enable_sweeps=False)
    orchestrator = LaneDaemonOrchestrator(config)

    # Immediately request shutdown
    orchestrator.request_shutdown()
    assert orchestrator.is_shutdown_requested() is True

    # Running run_loop should immediately exit cleanly
    results = orchestrator.run_loop()
    assert isinstance(results, list)


def test_orchestrator_responsive_sleep_aborts_immediately_on_shutdown(test_db: str) -> None:
    """Verify _responsive_sleep exits immediately (< 1.0s) upon request_shutdown."""
    config = LaneDaemonConfig(db_path=test_db)
    orchestrator = LaneDaemonOrchestrator(config)

    def trigger_shutdown_soon():
        time.sleep(0.05)
        orchestrator.request_shutdown()

    with patch("src.orchestrator.scheduler.is_test_environment", return_value=False):
        threading.Thread(target=trigger_shutdown_soon, daemon=True).start()

        start = time.monotonic()
        aborted = orchestrator._responsive_sleep(10.0, tick=0.5)
        elapsed = time.monotonic() - start

        assert aborted is True
        assert elapsed < 1.0


def test_daemon_start_daemon_lanes_delegates_to_orchestrator(test_db: str) -> None:
    """Verify start_daemon_lanes creates LaneDaemonOrchestrator and runs loop."""
    import src.daemon as daemon_mod

    with patch("src.orchestrator.scheduler.LaneDaemonOrchestrator.run_loop", return_value=[{"status": "COMPLETED"}]) as mock_run:
        results = daemon_mod.start_daemon_lanes(
            interval_seconds=45,
            max_picks=2,
            db_path=test_db,
            lanes_filter=["horror-scp-shorts"],
            max_parallel=2,
            generate_only=True,
            max_ticks=5,
        )
        assert mock_run.call_count == 1
        assert results == [{"status": "COMPLETED"}]
        # Check that hooks are set on daemon
        assert daemon_mod.scheduler_commit_fire is not None
        assert daemon_mod.scheduler_commit_empty is not None


def test_daemon_shutdown_flags_and_hooks_synchronized(test_db: str) -> None:
    """Ensure daemon request_shutdown/reset_shutdown synchronizes with orchestrator."""
    import src.daemon as daemon_mod

    config = LaneDaemonConfig(db_path=test_db)
    orchestrator = LaneDaemonOrchestrator(config)

    daemon_mod.reset_shutdown()
    assert orchestrator.is_shutdown_requested() is False

    daemon_mod.request_shutdown()
    assert orchestrator.is_shutdown_requested() is True

    daemon_mod.reset_shutdown()
    assert orchestrator.is_shutdown_requested() is False


def test_cli_handler_daemon_invocation(test_db: str) -> None:
    """Verify handle_daemon correctly constructs configuration and executes orchestrator."""
    import argparse
    from src.cli.handlers.daemon import handle_daemon

    args = argparse.Namespace(
        channel="horror",
        interval=30,
        lanes="horror-scp-shorts,horror-horror-long",
        max_parallel=2,
        generate_only=True,
        db_path=test_db,
    )

    with (
        patch("src.cli.handlers.daemon._get_locks", return_value=(MagicMock(), MagicMock())) as mock_locks,
        patch("src.orchestrator.scheduler.LaneDaemonOrchestrator.run_loop", return_value=[]) as mock_run,
    ):
        ret = handle_daemon(args)
        assert ret == 0
        acq, rel = mock_locks.return_value
        acq.assert_called_once_with("horror")
        rel.assert_called_once_with("horror")
        mock_run.assert_called_once()


def test_orchestrator_24h_sweep_ignores_ticks_and_checks_sqlite_state(test_db: str) -> None:
    """Verify ticks % 60 == 0 does NOT trigger 24h sweep when less than 24h elapsed (Issue #20)."""
    config = LaneDaemonConfig(db_path=test_db, enable_sweeps=True)
    orchestrator = LaneDaemonOrchestrator(config)
    now = time.time()
    orchestrator._last_24h_sweep = now - 300.0  # 5 minutes ago

    # Persist recent sweep in SQLite scheduler_state
    with connect(test_db) as conn:
        conn.execute("UPDATE scheduler_state SET last_24h_sweep_at = ? WHERE scheduler_id = 1", (int(now - 300),))
        conn.commit()

    with (
        patch("src.daemon._run_24h_maintenance_sweep") as mock_24h_sweep,
        patch("src.daemon._run_auto_publish_sweep"),
        patch("src.core.repository.touch_daemon_liveness"),
    ):
        # Even with ticks=60, it MUST NOT trigger
        orchestrator._run_sweeps_if_due(ticks=60)
        mock_24h_sweep.assert_not_called()

        # Now simulate 25 hours elapsed in scheduler_state
        conn_update = int(now - 90000.0)
        with connect(test_db) as conn:
            conn.execute("UPDATE scheduler_state SET last_24h_sweep_at = ? WHERE scheduler_id = 1", (conn_update,))
            conn.commit()
        orchestrator._last_24h_sweep = float(conn_update)

        orchestrator._run_sweeps_if_due(ticks=1)
        mock_24h_sweep.assert_called_once()


def test_orchestrator_watchdog_terminates_only_expired_lane_processes(test_db: str) -> None:
    """Verify watchdog timeout terminates only the timed out lane's processes without wiping siblings (Issue #21)."""
    from src.core.lifecycle import register_process, set_current_lane, get_lane_pids
    config = LaneDaemonConfig(db_path=test_db, enable_sweeps=False)
    orchestrator = LaneDaemonOrchestrator(config)

    # Register mock PIDs for two concurrent lanes
    set_current_lane("lane-horror")
    pid_horror = register_process(99991)
    set_current_lane("lane-drama")
    pid_drama = register_process(99992)
    set_current_lane(None)

    assert pid_horror in get_lane_pids("lane-horror")
    assert pid_drama in get_lane_pids("lane-drama")

    fut = concurrent.futures.Future()
    pick = LanePick("lane-horror", CanonicalChannel.HORROR, 1000, 1300)
    # Simulate start time far in the past to trigger turn timeout
    active_jobs = {fut: (pick, time.monotonic() - 20000.0)}

    with (
        patch("src.core.lifecycle.os.kill") as mock_kill,
        patch("src.core.lifecycle.os.getpgid", side_effect=lambda p: p),
        patch("src.core.lifecycle.os.killpg") as mock_killpg,
        patch("src.core.process_watch.terminate_hung_ffmpeg") as mock_hung,
    ):
        results = orchestrator._watchdog_check(active_jobs)
        assert len(results) == 1
        assert results[0]["status"] == "RETRYABLE_FAILED"
        assert results[0]["lane"] == "lane-horror"

        # lane-horror process was terminated
        assert pid_horror not in get_lane_pids("lane-horror")
        # sibling lane-drama process was NOT touched!
        assert pid_drama in get_lane_pids("lane-drama")
        # Global fallback terminate_hung_ffmpeg was NOT called because lane processes were handled
        mock_hung.assert_not_called()

        from src.core.lifecycle import unregister_process
        unregister_process(pid_drama)


def test_orchestrator_telegram_poller_lifecycle_supervision(test_db: str) -> None:
    """Verify orchestrator starts and supervises telegram callback poller in production (Issue #22)."""
    config = LaneDaemonConfig(db_path=test_db, enable_sweeps=True)
    orchestrator = LaneDaemonOrchestrator(config)

    with (
        patch("src.orchestrator.scheduler.is_test_environment", return_value=False),
        patch("src.daemon._start_telegram_callback_poller") as mock_start_poller,
        patch("src.core.repository.touch_daemon_liveness"),
    ):
        orchestrator.initialize()
        mock_start_poller.assert_called_once()
        mock_start_poller.reset_mock()

        # In _run_sweeps_if_due when thread is not running, it restarts
        orchestrator._run_sweeps_if_due(ticks=1)
        mock_start_poller.assert_called_once()



