"""Centralized Observability Hub ('El Tubo') collector and telemetry domain engine.

Provides unified system snapshots spanning host CPU/RAM headroom, daemon heartbeat,
worker concurrency locks, multi-provider token burn, YouTube Data API quotas,
session cookie decay, audio prompt leak clusters, SQLite WAL storage health,
and MCP protocol parity.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from src.config import DEFAULT_DB_PATH
from src.core.domain import CanonicalChannel
from src.core.repository.migrations import EXPECTED_MIGRATION_VERSION
from src.core.repository.queue import (
    AssetRejectionSummary,
    DaemonStoppageMetrics,
    TokenBurnSummary,
    connect,
)
from src.core.repository.leases import read_daemon_heartbeat
from src.observability.alerts import send_operational_alert
from src.observability.mcp_health import MCPHealthChecker, MCPHealthMetrics
from src.observability.quota import QuotaMonitor, YouTubeQuotaMetrics

logger = logging.getLogger(__name__)


# ==============================================================================
# Domain Metrics Dataclasses
# ==============================================================================


@dataclass(frozen=True)
class HostResourceMetrics:
    cpu_percent: float
    ram_rss_mib: float
    ram_rss_gib: float
    ram_status: str  # "OK" | "DEGRADED" | "CRITICAL"
    disk_free_gib: float
    disk_status: str  # "OK" | "DEGRADED" | "CRITICAL"
    overall_status: str  # "OK" | "DEGRADED" | "CRITICAL"
    sampling_duration_ms: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)


@dataclass(frozen=True)
class CookieIncidentMetrics:
    channel_statuses: dict[str, str]
    recent_warnings_count: int
    recent_failures_count: int
    degraded_channels: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)


@dataclass(frozen=True)
class PromptLeakMetrics:
    window_hours: int
    total_leaks: int
    leaks_by_model: dict[str, int]
    leaks_by_channel: dict[str, int]
    recent_leaks: list[dict[str, Any]]
    alert_cluster_active: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)


@dataclass(frozen=True)
class DatabaseHealthMetrics:
    db_size_bytes: int
    db_size_mib: float
    wal_size_bytes: int
    wal_size_mib: float
    wal_status: str  # "OK" | "GROWTH_WARNING" | "CRITICAL_WAL_BLOAT"
    wal_checkpoint_info: tuple[int, int, int]
    applied_migration_version: int
    expected_migration_version: int  # 9
    migration_parity: bool
    migration_status: str  # "SYNCED" | "PENDING_MIGRATIONS" | "FUTURE_VERSION_DRIFT"
    last_backup_timestamp: str | None
    last_backup_age_hours: float | None
    last_backup_size_bytes: int | None
    backup_status: str  # "HEALTHY" | "BACKUP_STALE_WARNING" | "NO_BACKUP"
    integrity_check_result: str  # "HEALTHY" | "CORRUPTED"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)


@dataclass(frozen=True)
class TubeSnapshot:
    timestamp: str  # ISO-8601 UTC
    system_status: str  # "HEALTHY" | "DEGRADED" | "CRITICAL"
    host_resources: HostResourceMetrics
    daemon_stoppages: DaemonStoppageMetrics
    token_burn: TokenBurnSummary
    youtube_quotas: YouTubeQuotaMetrics
    cookie_health: CookieIncidentMetrics
    prompt_leaks: PromptLeakMetrics
    database_health: DatabaseHealthMetrics
    mcp_health: MCPHealthMetrics
    asset_rejections: AssetRejectionSummary
    recent_incidents: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "system_status": self.system_status,
            "host_resources": self.host_resources.to_dict(),
            "daemon_stoppages": self.daemon_stoppages.to_dict(),
            "token_burn": self.token_burn.to_dict(),
            "youtube_quotas": self.youtube_quotas.to_dict(),
            "cookie_health": self.cookie_health.to_dict(),
            "prompt_leaks": self.prompt_leaks.to_dict(),
            "database_health": self.database_health.to_dict(),
            "mcp_health": self.mcp_health.to_dict(),
            "asset_rejections": self.asset_rejections.to_dict(),
            "recent_incidents": self.recent_incidents,
        }

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)


# ==============================================================================
# Centralized Telemetry Collector Engine
# ==============================================================================


class TubeCollector:
    """Centralized collector aggregating all pipeline operational telemetry."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        repo_root: Path | None = None,
    ) -> None:
        if db_path is not None:
            self.db_path = Path(db_path)
        else:
            env_db = os.environ.get("DEFAULT_DB_PATH")
            self.db_path = Path(env_db) if env_db else Path(DEFAULT_DB_PATH)

        self.repo_root = (
            Path(repo_root).resolve()
            if repo_root is not None
            else Path(__file__).resolve().parent.parent.parent
        )
        from src.core.repository import QueueRepository

        self.repo = QueueRepository(self.db_path)
        self.quota_monitor = QuotaMonitor(self.db_path)
        self.mcp_checker = MCPHealthChecker(self.db_path, repo_root=self.repo_root)
        self.mcp_checker.evaluate_health()

    # --------------------------------------------------------------------------
    # Host Resource Sampling Subsystem (< 2ms, zero subprocesses)
    # --------------------------------------------------------------------------

    @staticmethod
    def _read_process_rss_mib() -> float:
        """Sample resident memory size of the current process without spawning subprocesses."""
        try:
            # High-speed Linux procfs read
            with open("/proc/self/status", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        parts = line.split()
                        if len(parts) >= 2:
                            return round(float(parts[1]) / 1024.0, 2)
        except Exception:
            pass

        try:
            import resource

            usage = resource.getrusage(resource.RUSAGE_SELF)
            return round(float(usage.ru_maxrss) / 1024.0, 2)
        except Exception:
            return 0.0

    @staticmethod
    def _read_disk_free_gib(mount_path: str | Path | None = None) -> float:
        """Measure available disk space on database mount via statvfs."""
        path = str(mount_path) if mount_path else os.getcwd()
        try:
            st = os.statvfs(path)
            free_bytes = st.f_bavail * st.f_frsize
            return round(free_bytes / (1024.0**3), 2)
        except Exception:
            return 0.0

    @staticmethod
    def _read_cpu_percent() -> float:
        """Read system CPU utilization from /proc/loadavg instantaneously."""
        try:
            with open("/proc/loadavg", "r", encoding="utf-8") as f:
                line = f.readline()
                parts = line.split()
                if parts:
                    core_count = os.cpu_count() or 1
                    load1 = float(parts[0])
                    return round(min(100.0, (load1 / core_count) * 100.0), 2)
        except Exception:
            pass
        return 0.0

    @classmethod
    def sample_host_resources(
        cls, mount_path: str | Path | None = None
    ) -> HostResourceMetrics:
        """Sample host CPU %, RSS RAM, and disk free headroom in < 2ms."""
        t0 = time.perf_counter()

        rss_mib = cls._read_process_rss_mib()
        rss_gib = round(rss_mib / 1024.0, 6)
        disk_gib = cls._read_disk_free_gib(mount_path)
        cpu_pct = cls._read_cpu_percent()

        duration_ms = round((time.perf_counter() - t0) * 1000.0, 3)

        # Evaluate RAM headroom (budget: 2048 MiB)
        if rss_mib > 2048.0:
            ram_status = "CRITICAL"
        elif rss_mib > 1536.0:
            ram_status = "DEGRADED"
        else:
            ram_status = "OK"

        # Evaluate Disk headroom (minimum: 2.0 GiB)
        if disk_gib < 2.0:
            disk_status = "CRITICAL"
        elif disk_gib < 5.0:
            disk_status = "DEGRADED"
        else:
            disk_status = "OK"

        # Overall host resource status
        if ram_status == "CRITICAL" or disk_status == "CRITICAL":
            overall_status = "CRITICAL"
        elif ram_status == "DEGRADED" or disk_status == "DEGRADED":
            overall_status = "DEGRADED"
        else:
            overall_status = "OK"

        return HostResourceMetrics(
            cpu_percent=cpu_pct,
            ram_rss_mib=rss_mib,
            ram_rss_gib=rss_gib,
            ram_status=ram_status,
            disk_free_gib=disk_gib,
            disk_status=disk_status,
            overall_status=overall_status,
            sampling_duration_ms=duration_ms,
        )

    # --------------------------------------------------------------------------
    # Daemon Heartbeat & Worker Stoppages Subsystem
    # --------------------------------------------------------------------------

    def sample_daemon_stoppages(self) -> DaemonStoppageMetrics:
        """Compile daemon liveness heartbeat age, paused channels, and concurrency leases."""
        # Query base stoppages & worker leases from repository
        base_stoppages = self.repo.query_channel_stoppages()

        # Check heartbeat using module-level read_daemon_heartbeat for patchability
        hb = read_daemon_heartbeat(self.db_path)
        current_epoch = int(time.time())

        if hb is None or hb <= 0:
            heartbeat_age = None
            daemon_status = "STOPPED"
        else:
            heartbeat_age = max(0, current_epoch - int(hb))
            if heartbeat_age <= 60:
                daemon_status = "HEALTHY"
            elif heartbeat_age <= 120:
                daemon_status = "DEGRADED"
            else:
                daemon_status = "STALE"

        return DaemonStoppageMetrics(
            heartbeat_age_seconds=heartbeat_age,
            daemon_liveness_status=daemon_status,
            paused_channels=base_stoppages.paused_channels,
            active_locks=base_stoppages.active_locks,
            expired_locks_count=base_stoppages.expired_locks_count,
            circuit_breakers=base_stoppages.circuit_breakers,
            tripped_breakers_count=base_stoppages.tripped_breakers_count,
        )

    # --------------------------------------------------------------------------
    # Database Health & WAL Storage Subsystem
    # --------------------------------------------------------------------------

    def _get_wal_size_bytes(self, db_path: Path | str | None = None) -> int:
        """Return size in bytes of the SQLite WAL file."""
        target = Path(db_path or self.db_path)
        wal_path = Path(f"{target}-wal")
        try:
            return wal_path.stat().st_size if wal_path.is_file() else 0
        except Exception:
            return 0

    def sample_database_health(self) -> DatabaseHealthMetrics:
        """Measure database size, WAL bloat, migration parity, and backup recency."""
        target = Path(self.db_path)
        db_size_bytes = 0
        try:
            if target.is_file():
                db_size_bytes = target.stat().st_size
        except Exception:
            pass
        db_size_mib = round(db_size_bytes / (1024.0 * 1024.0), 2)

        wal_size_bytes = self._get_wal_size_bytes(target)
        wal_size_mib = round(wal_size_bytes / (1024.0 * 1024.0), 2)

        if wal_size_bytes > 200 * 1024 * 1024:
            wal_status = "CRITICAL_WAL_BLOAT"
        elif wal_size_bytes > 50 * 1024 * 1024:
            wal_status = "GROWTH_WARNING"
        else:
            wal_status = "OK"

        applied_version = 0
        checkpoint_info = (0, 0, 0)
        integrity_result = "HEALTHY"
        last_backup_ts = None
        last_backup_age = None
        last_backup_size = None
        backup_status = "NO_BACKUP"

        try:
            with connect(self.db_path, read_only=True) as conn:
                # 1. Migration version parity
                try:
                    row_mig = conn.execute(
                        "SELECT MAX(version) FROM schema_migrations"
                    ).fetchone()
                    if row_mig and row_mig[0] is not None:
                        applied_version = int(row_mig[0])
                except Exception:
                    applied_version = 0

                # 2. WAL passive checkpoint inspect
                try:
                    cp_row = conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
                    if cp_row:
                        checkpoint_info = (int(cp_row[0]), int(cp_row[1]), int(cp_row[2]))
                except Exception:
                    checkpoint_info = (0, 0, 0)

                # 3. Integrity check
                try:
                    chk_row = conn.execute("PRAGMA quick_check(1)").fetchone()
                    if chk_row and str(chk_row[0]).lower() == "ok":
                        integrity_result = "HEALTHY"
                    else:
                        integrity_result = "CORRUPTED"
                except Exception:
                    integrity_result = "CORRUPTED"

                # 4. Backup status from system_events
                try:
                    b_row = conn.execute(
                        """
                        SELECT ts, details_json FROM system_events
                        WHERE event_type = 'database_backup_completed'
                        ORDER BY ts DESC, event_id DESC LIMIT 1
                        """
                    ).fetchone()
                    if b_row and b_row["ts"]:
                        last_backup_ts = b_row["ts"]
                        try:
                            dt = datetime.fromisoformat(last_backup_ts)
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                            age_s = (datetime.now(timezone.utc) - dt).total_seconds()
                            last_backup_age = round(max(0.0, age_s / 3600.0), 2)
                        except Exception:
                            last_backup_age = None

                        if b_row["details_json"]:
                            try:
                                d_json = json.loads(b_row["details_json"])
                                last_backup_size = d_json.get("size_bytes") or d_json.get("file_size_bytes")
                            except Exception:
                                pass

                        if last_backup_age is not None and last_backup_age > 36.0:
                            backup_status = "BACKUP_STALE_WARNING"
                        else:
                            backup_status = "HEALTHY"
                except Exception:
                    pass

        except Exception as exc:
            logger.debug("Database health sampling failure: %s", exc)
            integrity_result = "CORRUPTED"

        expected_version = EXPECTED_MIGRATION_VERSION
        parity = applied_version == expected_version
        if parity:
            mig_status = "SYNCED"
        elif applied_version < expected_version:
            mig_status = "PENDING_MIGRATIONS"
        else:
            mig_status = "FUTURE_VERSION_DRIFT"

        return DatabaseHealthMetrics(
            db_size_bytes=db_size_bytes,
            db_size_mib=db_size_mib,
            wal_size_bytes=wal_size_bytes,
            wal_size_mib=wal_size_mib,
            wal_status=wal_status,
            wal_checkpoint_info=checkpoint_info,
            applied_migration_version=applied_version,
            expected_migration_version=expected_version,
            migration_parity=parity,
            migration_status=mig_status,
            last_backup_timestamp=last_backup_ts,
            last_backup_age_hours=last_backup_age,
            last_backup_size_bytes=last_backup_size,
            backup_status=backup_status,
            integrity_check_result=integrity_result,
        )

    # --------------------------------------------------------------------------
    # Cookie Lifecycle & Session Health Subsystem
    # --------------------------------------------------------------------------

    def sample_cookie_health(
        self,
        window_hours: int = 24,
        channel: str | CanonicalChannel | None = None,
    ) -> CookieIncidentMetrics:
        """Sample YouTube session cookie status and decay warnings across channels."""
        hours = max(1, int(window_hours))
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
        channel_key = channel.value if isinstance(channel, CanonicalChannel) else channel

        channel_statuses: dict[str, str] = {}
        recent_warnings = 0
        recent_failures = 0
        degraded: list[str] = []

        # 1. Query recent cookie events
        try:
            with connect(self.db_path, read_only=True) as conn:
                clauses = ["ts >= ?", "event_type IN ('cookie_warning', 'cookie_failure')"]
                params: list[Any] = [cutoff]
                if channel_key:
                    clauses.append("channel = ?")
                    params.append(channel_key)

                rows = conn.execute(
                    f"""
                    SELECT event_type, channel, COUNT(*) as cnt
                    FROM system_events
                    WHERE {' AND '.join(clauses)}
                    GROUP BY event_type, channel
                    """,
                    tuple(params),
                ).fetchall()

                for r in rows:
                    ev = r["event_type"]
                    cnt = int(r["cnt"])
                    ch = str(r["channel"] or "unknown")
                    if ev == "cookie_warning":
                        recent_warnings += cnt
                        channel_statuses.setdefault(ch, "EXPIRING_SOON")
                    elif ev == "cookie_failure":
                        recent_failures += cnt
                        channel_statuses[ch] = "EXPIRED"
        except Exception as exc:
            logger.debug("Failed querying cookie events: %s", exc)

        # 2. Check channel cookie files on disk
        target_channels = (
            [channel_key]
            if channel_key
            else [c.value for c in CanonicalChannel]
        )

        try:
            from src.api_health import check_cookies

            for ch in target_channels:
                if ch not in channel_statuses:
                    try:
                        res = check_cookies(ch)
                        if res.get("ok"):
                            channel_statuses[ch] = "HEALTHY"
                        else:
                            detail = str(res.get("detail", "")).lower()
                            if "expiring" in detail:
                                channel_statuses[ch] = "EXPIRING_SOON"
                            elif "faltan" in detail or "vacías" in detail:
                                channel_statuses[ch] = "MISSING"
                            else:
                                channel_statuses[ch] = "INVALID"
                    except Exception:
                        channel_statuses[ch] = "UNKNOWN"
        except Exception:
            for ch in target_channels:
                channel_statuses.setdefault(ch, "HEALTHY")

        for ch, st in channel_statuses.items():
            if st != "HEALTHY":
                degraded.append(ch)

        return CookieIncidentMetrics(
            channel_statuses=channel_statuses,
            recent_warnings_count=recent_warnings,
            recent_failures_count=recent_failures,
            degraded_channels=degraded,
        )

    # --------------------------------------------------------------------------
    # Pre-TTS Audio Prompt Leak Telemetry Subsystem
    # --------------------------------------------------------------------------

    def sample_prompt_leaks(
        self,
        window_hours: int = 24,
        channel: str | CanonicalChannel | None = None,
    ) -> PromptLeakMetrics:
        """Sample pre-TTS taboo meta-cue and prompt leak interception events."""
        hours = max(1, int(window_hours))
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
        cluster_cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(timespec="seconds")
        channel_key = channel.value if isinstance(channel, CanonicalChannel) else channel

        total_leaks = 0
        leaks_by_model: dict[str, int] = {}
        leaks_by_channel: dict[str, int] = {}
        recent_leaks: list[dict[str, Any]] = []
        cluster_counts: dict[tuple[str, str], int] = {}
        alert_cluster_active = False

        try:
            with connect(self.db_path, read_only=True) as conn:
                clauses = ["ts >= ?", "event_type = 'audio_prompt_leak'"]
                params: list[Any] = [cutoff]
                if channel_key:
                    clauses.append("channel = ?")
                    params.append(channel_key)

                rows = conn.execute(
                    f"""
                    SELECT event_id, ts, channel, details_json
                    FROM system_events
                    WHERE {' AND '.join(clauses)}
                    ORDER BY ts DESC, event_id DESC
                    LIMIT 20
                    """,
                    tuple(params),
                ).fetchall()

                for r in rows:
                    total_leaks += 1
                    ch = str(r["channel"] or "unknown")
                    leaks_by_channel[ch] = leaks_by_channel.get(ch, 0) + 1

                    details: dict[str, Any] = {}
                    if r["details_json"]:
                        try:
                            details = json.loads(r["details_json"])
                        except Exception:
                            details = {}

                    model = str(details.get("model") or "unknown")
                    leaks_by_model[model] = leaks_by_model.get(model, 0) + 1

                    recent_leaks.append(
                        {
                            "event_id": r["event_id"],
                            "ts": r["ts"],
                            "channel": ch,
                            "model": model,
                            "pattern": details.get("pattern"),
                            "snippet": details.get("snippet"),
                        }
                    )

                    if r["ts"] >= cluster_cutoff:
                        key = (model, ch)
                        cluster_counts[key] = cluster_counts.get(key, 0) + 1
                        if cluster_counts[key] > 3:
                            alert_cluster_active = True

        except Exception as exc:
            logger.debug("Prompt leaks sampling failure: %s", exc)

        return PromptLeakMetrics(
            window_hours=hours,
            total_leaks=total_leaks,
            leaks_by_model=leaks_by_model,
            leaks_by_channel=leaks_by_channel,
            recent_leaks=recent_leaks[:10],
            alert_cluster_active=alert_cluster_active,
        )

    # --------------------------------------------------------------------------
    # Snapshot Consolidation
    # --------------------------------------------------------------------------

    def compile_snapshot(
        self,
        channel: str | CanonicalChannel | None = None,
        window_hours: int = 24,
    ) -> TubeSnapshot:
        """Consolidate pipeline operational telemetry into an immutable TubeSnapshot."""
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Sample Host Resources
        host_resources = self.sample_host_resources()

        # 2. Sample Daemon Stoppages
        daemon_stoppages = self.sample_daemon_stoppages()

        # 3. Sample Multi-Provider Token Burn
        token_burn = self.quota_monitor.get_token_burn_summary(
            window_hours=window_hours, channel=channel
        )

        # 4. Sample YouTube Data API Quotas
        youtube_quotas = self.quota_monitor.get_youtube_quota_metrics(channel=channel)

        # 5. Sample Cookie Lifecycle Health
        cookie_health = self.sample_cookie_health(
            window_hours=window_hours, channel=channel
        )

        # 6. Sample Pre-TTS Prompt Leaks
        prompt_leaks = self.sample_prompt_leaks(
            window_hours=window_hours, channel=channel
        )

        # 7. Sample SQLite Database & WAL Storage Health
        database_health = self.sample_database_health()

        # 8. Sample MCP Health
        mcp_health = self.mcp_checker.evaluate_health(window_hours=window_hours)

        # 9. Sample Asset Rejections & Quality Assurance
        asset_rejections = self.repo.query_asset_rejection_counts(
            window_hours=window_hours, channel=channel
        )

        # 10. Sample Recent Operational Incidents
        recent_incidents = self.repo.query_tube_incidents(
            window_hours=window_hours, limit=20
        )

        # Evaluate Consolidated System Status Tri-State
        if (
            host_resources.overall_status == "CRITICAL"
            or database_health.wal_status == "CRITICAL_WAL_BLOAT"
            or database_health.integrity_check_result == "CORRUPTED"
            or database_health.migration_status == "PENDING_MIGRATIONS"
            or youtube_quotas.quota_status == "EXHAUSTED"
            or mcp_health.overall_status == "BROKEN"
        ):
            system_status = "CRITICAL"
        elif (
            host_resources.overall_status == "DEGRADED"
            or daemon_stoppages.daemon_liveness_status in ("DEGRADED", "STALE", "STOPPED")
            or database_health.wal_status == "GROWTH_WARNING"
            or database_health.backup_status == "BACKUP_STALE_WARNING"
            or youtube_quotas.quota_status == "WARNING"
            or len(cookie_health.degraded_channels) > 0
            or prompt_leaks.alert_cluster_active
            or mcp_health.overall_status == "DEGRADED"
        ):
            system_status = "DEGRADED"
        else:
            system_status = "HEALTHY"

        # Trigger operational alerts if critical clusters are detected
        if prompt_leaks.alert_cluster_active:
            try:
                send_operational_alert(
                    "Audio Prompt Leak Cluster Detected",
                    f"Over 3 prompt leaks detected in 30 minutes! Window total: {prompt_leaks.total_leaks}.",
                )
            except Exception:
                pass

        return TubeSnapshot(
            timestamp=now_iso,
            system_status=system_status,
            host_resources=host_resources,
            daemon_stoppages=daemon_stoppages,
            token_burn=token_burn,
            youtube_quotas=youtube_quotas,
            cookie_health=cookie_health,
            prompt_leaks=prompt_leaks,
            database_health=database_health,
            mcp_health=mcp_health,
            asset_rejections=asset_rejections,
            recent_incidents=recent_incidents,
        )
