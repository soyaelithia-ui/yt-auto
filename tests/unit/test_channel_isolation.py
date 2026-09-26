"""
Unit tests for multi-channel isolation, lifecycle independence, and dynamic discovery.
Validates Hitos 1 through 5 of the channel decoupling architecture.
"""
from __future__ import annotations

import os
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.channel_manager import (
    activate_channel,
    get_active_channels,
    get_channel_statuses,
    suspend_channel,
)
from src.core.channel_profile import ChannelProfileRegistry
from src.core.domain import CanonicalChannel, DynamicChannelKey, canonical_channel
from src.core.lease_reaper import LeaseReaper
from src.core.lock import (
    ChannelLock,
    ChannelLockError,
    _active_locks,
    _is_file_locked,
    acquire_lock,
    release_lock,
)
from src.core.repository import QueueRepository, migrate_database
from src.core.scheduler import PersistentScheduler
from src.daemon import (
    _acquire_telegram_poller_lock,
    _release_telegram_poller_lock,
    _start_telegram_callback_poller,
    start_daemon,
)


# =====================================================================
# Hito 1: Dynamic Channel Discovery & Zero Hardcoded Names
# =====================================================================

def test_dynamic_channel_discovery_no_hardcoding(tmp_path):
    """Channel statuses and active channels are determined dynamically from registry and DB."""
    active_ids = ChannelProfileRegistry.list_active_channel_ids()
    assert len(active_ids) >= 2
    assert "horror" in active_ids
    assert "drama" in active_ids

    db_path = str(tmp_path / "test_discovery.db")
    migrate_database(db_path)

    statuses = get_channel_statuses(db_path)
    for cid in active_ids:
        assert cid in statuses
        assert statuses[cid]["status"] in ("ACTIVE", "SUSPENDED")

    active_list = get_active_channels(db_path)
    for cid in active_ids:
        assert cid in active_list

    # Suspend one channel dynamically
    suspended = suspend_channel("horror", reason="test maintenance", db_path=db_path)
    assert suspended.get("status") == "SUSPENDED"

    statuses_after = get_channel_statuses(db_path)
    assert statuses_after["horror"]["status"] == "SUSPENDED"
    assert statuses_after["drama"]["status"] == "ACTIVE"
    assert "horror" not in get_active_channels(db_path)
    assert "drama" in get_active_channels(db_path)

    # Resume channel
    resumed = activate_channel("horror", db_path=db_path)
    assert resumed.get("status") == "ACTIVE"
    assert "horror" in get_active_channels(db_path)


def test_dynamic_channel_key_protocol():
    """DynamicChannelKey provides .value property for dynamic channels."""
    key = DynamicChannelKey("custom_channel")
    assert key == "custom_channel"
    assert key.value == "custom_channel"
    assert isinstance(key, str)


# =====================================================================
# Hito 2: Safe LeaseReaper & Alive Sibling Process Protection
# =====================================================================

def test_lease_reaper_respects_alive_sibling_process(tmp_path):
    """LeaseReaper(startup=True) must NOT delete active leases of running sibling processes."""
    db_file = tmp_path / "reaper_test.db"
    cur_host = socket.gethostname()
    alive_pid = os.getpid()
    dead_pid = 999999
    now_ts = int(time.time())

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
        conn.execute(
            "CREATE TABLE lane_leases (lane_id TEXT PRIMARY KEY, channel TEXT, owner TEXT, run_id TEXT, acquired_at INTEGER, heartbeat_at INTEGER, expires_at INTEGER)"
        )

        # Active lease of sibling channel owned by ALIVE process
        conn.execute(
            "INSERT INTO stories VALUES ('story_moku_alive', 'PROCESSING', 'run_moku_alive', NULL)"
        )
        conn.execute(
            "INSERT INTO runs VALUES ('run_moku_alive', 'PROCESSING', NULL, NULL)"
        )
        conn.execute(
            "INSERT INTO leases VALUES ('story_moku_alive', 'moku', ?, 'run_moku_alive', ?, ?, ?)",
            (f"worker:{cur_host}:{alive_pid}", now_ts - 30, now_ts - 5, now_ts + 900),
        )

        # Stale lease of crashed worker (DEAD pid)
        conn.execute(
            "INSERT INTO stories VALUES ('story_aelithia_dead', 'PROCESSING', 'run_aelithia_dead', NULL)"
        )
        conn.execute(
            "INSERT INTO runs VALUES ('run_aelithia_dead', 'PROCESSING', NULL, NULL)"
        )
        conn.execute(
            "INSERT INTO leases VALUES ('story_aelithia_dead', 'aelithia', ?, 'run_aelithia_dead', ?, ?, ?)",
            (f"worker:{cur_host}:{dead_pid}", now_ts - 60, now_ts - 10, now_ts + 900),
        )
        conn.commit()

    # Startup reap for aelithia channel should NOT kill moku's alive lease
    reaper = LeaseReaper(db_path=db_file)
    reaped = reaper.reap_once(startup=True, channel="aelithia")
    assert reaped == 1

    with sqlite3.connect(str(db_file)) as conn:
        conn.row_factory = sqlite3.Row
        # Moku's alive lease must remain intact
        moku_lease = conn.execute("SELECT * FROM leases WHERE channel = 'moku'").fetchone()
        assert moku_lease is not None
        moku_story = conn.execute("SELECT status FROM stories WHERE story_id = 'story_moku_alive'").fetchone()
        assert moku_story["status"] == "PROCESSING"

        # Aelithia's dead lease must have been reaped
        aelithia_lease = conn.execute("SELECT * FROM leases WHERE channel = 'aelithia'").fetchone()
        assert aelithia_lease is None
        aelithia_story = conn.execute("SELECT status FROM stories WHERE story_id = 'story_aelithia_dead'").fetchone()
        assert aelithia_story["status"] == "RETRYABLE_FAILED"


def test_lease_reaper_channel_filter_isolation(tmp_path):
    """reap_once(channel=...) only reaps the targeted channel's leases."""
    db_file = tmp_path / "reaper_filter.db"
    cur_host = socket.gethostname()
    dead_pid = 999999
    now_ts = int(time.time())

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

        # Both channels have dead-worker leases
        conn.execute(
            "INSERT INTO stories VALUES ('s_moku', 'PROCESSING', 'r_moku', NULL), ('s_aelithia', 'PROCESSING', 'r_aelithia', NULL)"
        )
        conn.execute(
            "INSERT INTO runs VALUES ('r_moku', 'PROCESSING', NULL, NULL), ('r_aelithia', 'PROCESSING', NULL, NULL)"
        )
        conn.execute(
            "INSERT INTO lane_leases VALUES "
            "('moku-horror-long', 'moku', ?, 'r_moku', ?, ?, ?), "
            "('aelithia-aita-long', 'aelithia', ?, 'r_aelithia', ?, ?, ?)",
            (
                f"worker:{cur_host}:{dead_pid}", now_ts - 50, now_ts - 5, now_ts + 900,
                f"worker:{cur_host}:{dead_pid}", now_ts - 50, now_ts - 5, now_ts + 900,
            ),
        )
        conn.commit()

    reaper = LeaseReaper(db_path=db_file)
    # Reap only moku
    reaped = reaper.reap_once(channel="moku")
    assert reaped == 1

    with sqlite3.connect(str(db_file)) as conn:
        remaining_lanes = [r[0] for r in conn.execute("SELECT channel FROM lane_leases").fetchall()]
        assert "moku" not in remaining_lanes
        assert "aelithia" in remaining_lanes


# =====================================================================
# Hito 3: Concurrent Channel Locks & Hierarchy
# =====================================================================

def test_concurrent_channel_locks(tmp_path):
    """Distinct channels (moku and aelithia) can acquire locks concurrently without blocking."""
    lock_moku = ChannelLock("moku", lock_dir=tmp_path, timeout=0.5)
    lock_aelithia = ChannelLock("aelithia", lock_dir=tmp_path, timeout=0.5)

    with lock_moku:
        assert lock_moku.is_acquired
        with lock_aelithia:
            assert lock_aelithia.is_acquired
            assert os.path.exists(lock_moku.path)
            assert os.path.exists(lock_aelithia.path)
            assert lock_moku.path != lock_aelithia.path

    assert not lock_moku.is_acquired
    assert not lock_aelithia.is_acquired
    assert not os.path.exists(lock_moku.path)
    assert not os.path.exists(lock_aelithia.path)


def test_lock_hierarchy_all_vs_single(tmp_path):
    """ChannelLock enforces hierarchy: 'all' excludes single channels, and vice-versa."""
    lock_moku = ChannelLock("moku", lock_dir=tmp_path, timeout=0.2)
    lock_all = ChannelLock("all", lock_dir=tmp_path, timeout=0.2)

    # 1. When moku is held, 'all' cannot be acquired
    with lock_moku:
        with pytest.raises(ChannelLockError) as exc_info:
            lock_all.acquire(timeout=0.1)
        assert "moku" in str(exc_info.value)

    # 2. When 'all' is held, moku and aelithia cannot be acquired
    with lock_all:
        with pytest.raises(ChannelLockError) as exc_info:
            lock_moku.acquire(timeout=0.1)
        assert "all" in str(exc_info.value)

        lock_aelithia = ChannelLock("aelithia", lock_dir=tmp_path, timeout=0.1)
        with pytest.raises(ChannelLockError) as exc_info2:
            lock_aelithia.acquire(timeout=0.1)
        assert "all" in str(exc_info2.value)

    # 3. Once 'all' is released, single channels acquire successfully
    with lock_moku:
        assert lock_moku.is_acquired


def test_release_lock_specific_channel(tmp_path):
    """release_lock(channel) releases exclusively the specified channel."""
    _active_locks.clear()
    lock_moku = ChannelLock("moku", lock_dir=tmp_path)
    lock_aelithia = ChannelLock("aelithia", lock_dir=tmp_path)

    lock_moku.acquire()
    _active_locks["moku"] = lock_moku
    lock_aelithia.acquire()
    _active_locks["aelithia"] = lock_aelithia

    assert "moku" in _active_locks
    assert "aelithia" in _active_locks

    release_lock("moku")

    assert "moku" not in _active_locks
    assert "aelithia" in _active_locks
    assert not os.path.exists(lock_moku.path)
    assert os.path.exists(lock_aelithia.path)

    release_lock("aelithia")
    assert "aelithia" not in _active_locks
    assert not os.path.exists(lock_aelithia.path)


# =====================================================================
# Hito 4: Telegram Poller Singleton & Daemon Isolation
# =====================================================================

def test_telegram_poller_singleton_lock(tmp_path, monkeypatch):
    """Only one daemon instance can acquire the Telegram callback poller lock."""
    monkeypatch.setenv("YT_LOCK_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_TELEGRAM_CALLBACK_POLLING", "1")
    _release_telegram_poller_lock()

    # First acquisition succeeds
    assert _acquire_telegram_poller_lock() is True

    # Emulate another process attempting to lock the same file
    lock_file = tmp_path / "telegram_callback_poller.lock"
    assert lock_file.exists()

    # Subprocess attempting to lock should fail
    sub_code = (
        "import fcntl, sys\n"
        f"f = open(r'{lock_file}', 'a+')\n"
        "try:\n"
        "    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
        "    sys.exit(0)\n"
        "except (IOError, OSError):\n"
        "    sys.exit(42)\n"
    )
    result = subprocess.run([sys.executable, "-c", sub_code], capture_output=True)
    assert result.returncode == 42

    _release_telegram_poller_lock()


def test_scheduler_fair_rotation_with_paused_channel(tmp_path):
    """Scheduler skips paused channels and rotates through available ones."""
    db_path = str(tmp_path / "scheduler_fair.db")
    migrate_database(db_path)

    scheduler = PersistentScheduler(db_path, interval_seconds=10)

    # First turn should pick an active channel
    first = scheduler.take_due_turn(now=1000)
    assert first is not None
    first_ch = first.channel.value

    # Now pause that channel
    repo = QueueRepository(db_path)
    repo.pause(first_ch, reason="manual pause")

    # Next turn should pick the other channel, skipping the paused one
    second = scheduler.take_due_turn(now=1020)
    assert second is not None
    assert second.channel.value != first_ch

    # Resume the paused channel
    repo.resume(first_ch)
    third = scheduler.take_due_turn(now=1040)
    assert third is not None
    assert third.channel.value == first_ch


def test_start_daemon_continues_when_one_channel_disk_paused(tmp_path, monkeypatch):
    """start_daemon continues to next channel instead of breaking when disk guard triggers."""
    db_path = str(tmp_path / "daemon_disk_pause.db")
    migrate_database(db_path)

    runs = []

    def fake_run_pipeline_once(*args, **kwargs):
        runs.append(kwargs.get("channel"))
        return {"status": "SUCCESS"}

    monkeypatch.setattr("src.daemon.run_pipeline_once", fake_run_pipeline_once)
    monkeypatch.setattr("src.config.is_test_environment", lambda: False)
    monkeypatch.setattr("src.daemon._watchdog_tick_seconds", lambda: 0.05)
    monkeypatch.setattr("src.daemon._responsive_sleep", lambda sec: False)

    # First channel (moku/horror) fails disk check; second channel (aelithia/drama) passes
    disk_check_calls = []

    def fake_disk_check(database, channel_value):
        disk_check_calls.append(channel_value)
        if channel_value in ("moku", "horror"):
            return False  # disk pause
        return True

    monkeypatch.setattr("src.daemon._preflight_disk_or_pause", fake_disk_check)

    results = start_daemon(
        interval_seconds=1,
        max_runs=2,
        db_path=db_path,
        channels=["moku", "aelithia"],
    )

    assert len(results) == 2
    assert results[0]["status"] == "GUARD_DISK_PAUSED"
    assert results[0]["channel"] in ("moku", "horror")
    # Crucial invariant: start_daemon did NOT break! It continued to aelithia!
    assert any(c in runs for c in ("aelithia", "drama"))
    assert results[1]["status"] == "SUCCESS"


def test_lease_reaper_startup_preserves_alive_workers_without_channel_filter(tmp_path):
    """LeaseReaper(startup=True, channel=None) preserves alive workers across all channels."""
    db_file = tmp_path / "reaper_all_channels.db"
    cur_host = socket.gethostname()
    alive_pid = os.getpid()
    dead_pid = 999999
    now_ts = int(time.time())

    with sqlite3.connect(str(db_file)) as conn:
        conn.execute("CREATE TABLE stories (story_id TEXT PRIMARY KEY, status TEXT, run_id TEXT, error_msg TEXT)")
        conn.execute("CREATE TABLE runs (run_id TEXT PRIMARY KEY, status TEXT, finished_at TEXT, error_code TEXT)")
        conn.execute("CREATE TABLE leases (job_id TEXT PRIMARY KEY, channel TEXT, owner TEXT, run_id TEXT, acquired_at INTEGER, heartbeat_at INTEGER, expires_at INTEGER)")
        conn.execute("CREATE TABLE lane_leases (lane_id TEXT PRIMARY KEY, channel TEXT, owner TEXT, run_id TEXT, acquired_at INTEGER, heartbeat_at INTEGER, expires_at INTEGER)")

        # Alive workers on multiple distinct channels
        conn.execute("INSERT INTO stories VALUES ('s_moku_alive', 'PROCESSING', 'r_moku_alive', NULL), ('s_ael_alive', 'PROCESSING', 'r_ael_alive', NULL)")
        conn.execute("INSERT INTO runs VALUES ('r_moku_alive', 'PROCESSING', NULL, NULL), ('r_ael_alive', 'PROCESSING', NULL, NULL)")
        conn.execute(
            "INSERT INTO leases VALUES ('s_moku_alive', 'moku', ?, 'r_moku_alive', ?, ?, ?)",
            (f"worker:{cur_host}:{alive_pid}", now_ts - 10, now_ts - 2, now_ts + 900),
        )
        conn.execute(
            "INSERT INTO lane_leases VALUES ('ael-lane-1', 'aelithia', ?, 'r_ael_alive', ?, ?, ?)",
            (f"worker:{cur_host}:{alive_pid}", now_ts - 10, now_ts - 2, now_ts + 900),
        )

        # Dead worker on a third channel
        conn.execute("INSERT INTO stories VALUES ('s_scifi_dead', 'PROCESSING', 'r_scifi_dead', NULL)")
        conn.execute("INSERT INTO runs VALUES ('r_scifi_dead', 'PROCESSING', NULL, NULL)")
        conn.execute(
            "INSERT INTO leases VALUES ('s_scifi_dead', 'scifi', ?, 'r_scifi_dead', ?, ?, ?)",
            (f"worker:{cur_host}:{dead_pid}", now_ts - 60, now_ts - 10, now_ts + 900),
        )
        conn.commit()

    reaper = LeaseReaper(db_path=db_file)
    reaped = reaper.reap_once(startup=True, channel=None)
    assert reaped == 1  # Only dead scifi worker is reaped!

    with sqlite3.connect(str(db_file)) as conn:
        # Alive leases still exist
        assert conn.execute("SELECT 1 FROM leases WHERE channel = 'moku'").fetchone() is not None
        assert conn.execute("SELECT 1 FROM lane_leases WHERE channel = 'aelithia'").fetchone() is not None
        # Dead lease reaped
        assert conn.execute("SELECT 1 FROM leases WHERE channel = 'scifi'").fetchone() is None


def test_lock_hierarchy_detects_custom_channel_without_hardcoding(tmp_path):
    """ChannelLock('all') dynamically detects custom channels not in the default registry."""
    lock_custom = ChannelLock("custom_brand_unregistered", lock_dir=tmp_path, timeout=0.2)
    lock_all = ChannelLock("all", lock_dir=tmp_path, timeout=0.2)

    with lock_custom:
        assert lock_custom.is_acquired
        # 'all' must dynamically discover custom_brand_unregistered via lock dir inspection and raise ChannelLockError
        with pytest.raises(ChannelLockError) as exc_info:
            lock_all.acquire(timeout=0.1)
        assert "custom_brand_unregistered" in str(exc_info.value)

    # After custom lock is released, 'all' acquires cleanly
    with lock_all:
        assert lock_all.is_acquired


def test_start_reaper_daemon_channel_scoped(tmp_path):
    """start_reaper_daemon passes channel parameter correctly to background loop."""
    from src.core.lease_reaper import start_reaper_daemon

    sweeps = []
    with patch.object(LeaseReaper, "reap_once", side_effect=lambda **kw: sweeps.append(kw.get("channel")) or 0):
        th = start_reaper_daemon(interval_seconds=0.05, db_path=str(tmp_path / "dummy.db"), channel="moku")
        time.sleep(0.12)
        assert len(sweeps) >= 1
        assert sweeps[0] == "moku"

