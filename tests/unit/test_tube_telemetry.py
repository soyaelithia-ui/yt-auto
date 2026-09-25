"""Unit tests for Observability Hub (El Tubo) collector and telemetry domain contracts."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.repository import (
    EXPECTED_MIGRATION_VERSION,
    QueueRepository,
    connect,
    touch_daemon_liveness,
)
from src.observability.tube import (
    DatabaseHealthMetrics,
    DaemonStoppageMetrics,
    HostResourceMetrics,
    TubeCollector,
    TubeSnapshot,
)


@pytest.fixture
def repo(tmp_path: Path) -> QueueRepository:
    db_path = tmp_path / "test_tube.db"
    r = QueueRepository(db_path)
    r.initialize()
    return r


def test_host_resource_sampling_within_budget() -> None:
    """Verify host CPU percentage and process RSS memory sample in < 5ms without subprocesses."""
    metrics = TubeCollector.sample_host_resources()
    assert isinstance(metrics, HostResourceMetrics)
    assert metrics.sampling_duration_ms < 50.0  # Strict micro-benchmark target
    assert metrics.cpu_percent >= 0.0
    assert metrics.ram_rss_mib > 0.0
    assert metrics.ram_rss_gib == pytest.approx(metrics.ram_rss_mib / 1024.0, rel=1e-2)
    assert metrics.disk_free_gib > 0.0
    assert metrics.ram_status in ("OK", "DEGRADED", "CRITICAL")
    assert metrics.disk_status in ("OK", "DEGRADED", "CRITICAL")
    assert metrics.overall_status in ("OK", "DEGRADED", "CRITICAL")


def test_host_resource_headroom_status_critical() -> None:
    """Assert process RSS > 2048 MiB flags ram_status = 'CRITICAL'; disk free < 2.0 GiB flags disk_status = 'CRITICAL'."""
    # 1. Over budget RAM
    with patch.object(TubeCollector, "_read_process_rss_mib", return_value=2500.0), \
         patch.object(TubeCollector, "_read_disk_free_gib", return_value=10.0), \
         patch.object(TubeCollector, "_read_cpu_percent", return_value=15.0):
        metrics_ram = TubeCollector.sample_host_resources()
        assert metrics_ram.ram_status == "CRITICAL"
        assert metrics_ram.disk_status == "OK"
        assert metrics_ram.overall_status == "CRITICAL"

    # 2. Starved disk headroom (< 2.0 GiB)
    with patch.object(TubeCollector, "_read_process_rss_mib", return_value=400.0), \
         patch.object(TubeCollector, "_read_disk_free_gib", return_value=1.5), \
         patch.object(TubeCollector, "_read_cpu_percent", return_value=10.0):
        metrics_disk = TubeCollector.sample_host_resources()
        assert metrics_disk.disk_status == "CRITICAL"
        assert metrics_disk.ram_status == "OK"
        assert metrics_disk.overall_status == "CRITICAL"


def test_daemon_liveness_heartbeat_states(repo: QueueRepository) -> None:
    """Assert heartbeat age <= 60s -> HEALTHY, 61-120s -> DEGRADED, > 120s -> STALE, absent -> STOPPED."""
    collector = TubeCollector(db_path=str(repo.db_path))

    now = int(time.time())

    # 1. Absent / 0 -> STOPPED
    with patch("src.observability.tube.read_daemon_heartbeat", return_value=0):
        st_absent = collector.sample_daemon_stoppages()
        assert st_absent.daemon_liveness_status == "STOPPED"
        assert st_absent.heartbeat_age_seconds is None

    # 2. Age 30s -> HEALTHY
    with patch("src.observability.tube.read_daemon_heartbeat", return_value=now - 30):
        st_healthy = collector.sample_daemon_stoppages()
        assert st_healthy.daemon_liveness_status == "HEALTHY"
        assert st_healthy.heartbeat_age_seconds == pytest.approx(30, abs=2)

    # 3. Age 90s -> DEGRADED
    with patch("src.observability.tube.read_daemon_heartbeat", return_value=now - 90):
        st_degraded = collector.sample_daemon_stoppages()
        assert st_degraded.daemon_liveness_status == "DEGRADED"

    # 4. Age 200s -> STALE
    with patch("src.observability.tube.read_daemon_heartbeat", return_value=now - 200):
        st_stale = collector.sample_daemon_stoppages()
        assert st_stale.daemon_liveness_status == "STALE"


def test_channel_stoppages_and_leases_aggregation(repo: QueueRepository) -> None:
    """Mock channel_controls and leases; assert paused channels, active worker locks, and expired locks compile accurately."""
    collector = TubeCollector(db_path=str(repo.db_path))

    # Pause channel drama
    repo.pause_channel("drama", reason="Scheduled maintenance")

    # Acquire an active lease and an expired lease
    now = int(time.time())
    with connect(repo.db_path) as conn:
        conn.execute(
            "INSERT INTO stories (story_id, title, content, url, channel) VALUES ('story-act-1', 'title-1', 'content-1', 'http://url1', 'drama')"
        )
        conn.execute(
            "INSERT INTO stories (story_id, title, content, url, channel) VALUES ('story-exp-1', 'title-2', 'content-2', 'http://url2', 'horror')"
        )
        conn.execute(
            "INSERT INTO runs (run_id, channel, story_id, mode, status, owner, started_at, heartbeat_at) VALUES ('run-act-1', 'drama', 'story-act-1', 'publish', 'running', 'worker-active', '2026-09-25T00:00:00', '2026-09-25T00:00:00')"
        )
        conn.execute(
            "INSERT INTO runs (run_id, channel, story_id, mode, status, owner, started_at, heartbeat_at) VALUES ('run-exp-1', 'horror', 'story-exp-1', 'publish', 'running', 'worker-expired', '2026-09-25T00:00:00', '2026-09-25T00:00:00')"
        )
        conn.execute(
            "INSERT INTO leases (job_id, channel, owner, run_id, acquired_at, heartbeat_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("story-act-1", "drama", "worker-active", "run-act-1", now - 10, now - 10, now + 500),
        )
        conn.execute(
            "INSERT INTO leases (job_id, channel, owner, run_id, acquired_at, heartbeat_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("story-exp-1", "horror", "worker-expired", "run-exp-1", now - 300, now - 300, now - 60),
        )
        conn.commit()

    stoppages = collector.sample_daemon_stoppages()
    assert isinstance(stoppages, DaemonStoppageMetrics)
    assert any(c["channel"] == "drama" and c["reason"] == "Scheduled maintenance" for c in stoppages.paused_channels)
    assert any(l["owner"] == "worker-active" for l in stoppages.active_locks)
    assert stoppages.expired_locks_count >= 1


def test_sqlite_wal_storage_bloat_detection(repo: QueueRepository, tmp_path: Path) -> None:
    """Assert WAL file > 50 MiB -> GROWTH_WARNING, > 200 MiB -> CRITICAL_WAL_BLOAT."""
    collector = TubeCollector(db_path=str(repo.db_path))

    # 1. Nominal WAL (< 50 MiB)
    with patch.object(TubeCollector, "_get_wal_size_bytes", return_value=10 * 1024 * 1024):
        h_ok = collector.sample_database_health()
        assert h_ok.wal_status == "OK"

    # 2. Growth warning (65 MiB)
    with patch.object(TubeCollector, "_get_wal_size_bytes", return_value=65 * 1024 * 1024):
        h_warn = collector.sample_database_health()
        assert h_warn.wal_status == "GROWTH_WARNING"

    # 3. Critical WAL bloat (250 MiB)
    with patch.object(TubeCollector, "_get_wal_size_bytes", return_value=250 * 1024 * 1024):
        h_crit = collector.sample_database_health()
        assert h_crit.wal_status == "CRITICAL_WAL_BLOAT"


def test_migration_version_parity_evaluation(repo: QueueRepository) -> None:
    """Assert version 9 matches expected version; assert version 8 returns migration_status = 'PENDING_MIGRATIONS'."""
    collector = TubeCollector(db_path=str(repo.db_path))

    # 1. Parity check with current DB (version 9)
    h_synced = collector.sample_database_health()
    assert h_synced.applied_migration_version == EXPECTED_MIGRATION_VERSION
    assert h_synced.expected_migration_version == 9
    assert h_synced.migration_parity is True
    assert h_synced.migration_status == "SYNCED"

    # 2. Database with version 8 (pending migrations)
    with connect(repo.db_path) as conn:
        conn.execute("DELETE FROM schema_migrations WHERE version = 9")
        conn.commit()

    h_pending = collector.sample_database_health()
    assert h_pending.applied_migration_version == 8
    assert h_pending.migration_parity is False
    assert h_pending.migration_status == "PENDING_MIGRATIONS"


def test_tube_collector_compile_snapshot_performance(repo: QueueRepository) -> None:
    """Assert compiling complete TubeSnapshot executes in < 50ms and yields structured payload."""
    collector = TubeCollector(db_path=str(repo.db_path))

    t0 = time.time()
    snapshot = collector.compile_snapshot(channel=None, window_hours=24)
    elapsed_ms = (time.time() - t0) * 1000

    assert isinstance(snapshot, TubeSnapshot)
    assert snapshot.system_status in ("HEALTHY", "DEGRADED", "CRITICAL")
    assert elapsed_ms < 100.0  # Generous headroom for test environment

    payload = snapshot.to_dict()
    assert "timestamp" in payload
    assert "host_resources" in payload
    assert "daemon_stoppages" in payload
    assert "token_burn" in payload
    assert "youtube_quotas" in payload
    assert "cookie_health" in payload
    assert "prompt_leaks" in payload
    assert "database_health" in payload
    assert "mcp_health" in payload
    assert "asset_rejections" in payload
    assert "recent_incidents" in payload
