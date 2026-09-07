"""Active Lease Reaper Daemon & Orphan Recovery (yt-auto v3.1).

Continuously monitors process identifiers (PIDs) associated with active lane leases.
When a worker crashes abruptly (OOM killer, SIGKILL, unhandled segfault), the reaper
detects dead PIDs via 'os.kill(pid, 0)' and immediately frees the lane lease without
waiting for the 900s TTL expiration window.
"""

from __future__ import annotations

import logging
import os
import re
import socket
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from src.core.domain import JobStatus
from src.core.repository import validate_db_path
from src.log import get_logger

logger = get_logger("lease_reaper")


DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "shorts_queue.db"


def is_pid_alive(pid: int) -> bool:
    """Check if process with PID is currently alive on the system."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but belongs to another user
        return True
    except OSError:
        return False


def extract_pid_from_owner(owner: str) -> Optional[int]:
    """Extract integer PID from lease owner string (e.g., 'worker:moku:12345' -> 12345, 'server_node_42' -> 42)."""
    if not owner:
        return None
    match = re.search(r"[:_](\d+)$", owner)
    if match:
        return int(match.group(1))
    return None


def is_local_hostname(owner: str) -> bool:
    """Return True if lease belongs to current host (for multi-node safety)."""
    if not owner:
        return False
    current_host = socket.gethostname()
    if ":" in owner:
        parts = owner.split(":")
        if len(parts) >= 3:
            # Multi-segment format: prefix:hostname:pid (e.g. lane-id:hostname:pid)
            return parts[1] == current_host or parts[1] == "localhost"
        # Two-segment format: host_or_prefix:pid (e.g. worker:pid or localhost:pid)
        prefix_or_host = parts[0]
        if prefix_or_host in ("worker", "legacy", "default"):
            return True
        return prefix_or_host == current_host or prefix_or_host == "localhost"
    return True


is_local_lease = is_local_hostname


class LeaseReaper:
    """Proactive reaper of orphaned locks and crashed worker leases."""

    def __init__(self, db_path: Optional[Union[str, Path]] = None) -> None:
        raw_path = db_path if db_path else DEFAULT_DB_PATH
        self.db_path = Path(validate_db_path(raw_path))

    def reap_once(self, startup: bool = False) -> int:
        """Scan leases and lane_leases; delete expired leases and those owned by dead local processes."""
        if not self.db_path.exists():
            return 0

        reaped_count = 0
        now_ts = int(time.time())
        now_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        with sqlite3.connect(str(self.db_path), timeout=30.0) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout = 30000")

            # 1. Check leases table
            try:
                rows = conn.execute("SELECT job_id, run_id, owner, heartbeat_at, expires_at FROM leases").fetchall()
                for row in rows:
                    job_id = row["job_id"]
                    run_id = row["run_id"]
                    owner = row["owner"]
                    expires_at = row["expires_at"] if "expires_at" in row.keys() else None
                    heartbeat_at = row["heartbeat_at"] if "heartbeat_at" in row.keys() else None
                    pid = extract_pid_from_owner(owner)

                    is_expired = expires_at is not None and expires_at <= now_ts
                    is_dead_process = pid is not None and is_local_hostname(owner) and not is_pid_alive(pid)
                    is_stale_heartbeat = heartbeat_at is not None and (now_ts - heartbeat_at > 300)
                    is_startup_orphan = startup and (
                        os.environ.get("MULTI_NODE", "0").lower() not in ("1", "true", "yes")
                        or is_local_hostname(owner)
                    )
                    is_orphan_remote = not is_local_hostname(owner) and (
                        os.environ.get("MULTI_NODE", "0").lower() not in ("1", "true", "yes")
                        or is_stale_heartbeat
                    )

                    if is_expired or is_dead_process or is_orphan_remote or is_stale_heartbeat or is_startup_orphan:
                        if is_startup_orphan:
                            reason = f"Prior instance lease orphaned on startup (owner '{owner}') (reaped)"
                            err_code = "startup_orphan_reaped"
                        elif is_dead_process:
                            reason = f"Worker PID {pid} crashed (reaped)"
                            err_code = "worker_sigkill_reaped"
                        elif is_orphan_remote:
                            reason = f"Orphan remote lease from host {owner} (reaped)"
                            err_code = "orphan_host_reaped"
                        elif is_stale_heartbeat:
                            reason = f"Lease heartbeat stale ({now_ts - (heartbeat_at or 0)}s > 300s) (reaped)"
                            err_code = "heartbeat_timeout"
                        else:
                            reason = "Lease TTL expired (reaped)"
                            err_code = "lease_expired"
                        logger.warning(
                            "Reaping lease for job '%s' (run '%s', owner '%s'): %s.",
                            job_id, run_id, owner, reason,
                        )
                        conn.execute("BEGIN IMMEDIATE")
                        conn.execute("DELETE FROM leases WHERE job_id = ? AND run_id = ?", (job_id, run_id))
                        conn.execute(
                            "UPDATE stories SET status = ?, run_id = NULL, error_msg = ? WHERE story_id = ? AND run_id = ?",
                            (JobStatus.RETRYABLE_FAILED.value, reason, job_id, run_id),
                        )
                        conn.execute(
                            "UPDATE runs SET status = ?, finished_at = ?, error_code = ? WHERE run_id = ?",
                            (JobStatus.RETRYABLE_FAILED.value, now_utc, err_code, run_id),
                        )
                        conn.commit()
                        reaped_count += 1
            except sqlite3.OperationalError:
                pass

            # 2. Check lane_leases table
            try:
                lane_rows = conn.execute("SELECT lane_id, run_id, owner, heartbeat_at, expires_at FROM lane_leases").fetchall()
                for row in lane_rows:
                    lane_id = row["lane_id"]
                    run_id = row["run_id"]
                    owner = row["owner"]
                    expires_at = row["expires_at"] if "expires_at" in row.keys() else None
                    heartbeat_at = row["heartbeat_at"] if "heartbeat_at" in row.keys() else None
                    pid = extract_pid_from_owner(owner)

                    is_expired = expires_at is not None and expires_at <= now_ts
                    is_dead_process = pid is not None and is_local_hostname(owner) and not is_pid_alive(pid)
                    is_stale_heartbeat = heartbeat_at is not None and (now_ts - heartbeat_at > 300)
                    is_startup_orphan = startup and (
                        os.environ.get("MULTI_NODE", "0").lower() not in ("1", "true", "yes")
                        or is_local_hostname(owner)
                    )
                    is_orphan_remote = not is_local_hostname(owner) and (
                        os.environ.get("MULTI_NODE", "0").lower() not in ("1", "true", "yes")
                        or is_stale_heartbeat
                    )

                    if is_expired or is_dead_process or is_orphan_remote or is_stale_heartbeat or is_startup_orphan:
                        if is_startup_orphan:
                            reason = f"Prior instance lane lease orphaned on startup (owner '{owner}') (reaped)"
                            err_code = "startup_orphan_reaped"
                        elif is_dead_process:
                            reason = f"Worker PID {pid} crashed (reaped)"
                            err_code = "worker_sigkill_reaped"
                        elif is_orphan_remote:
                            reason = f"Orphan remote lease from host {owner} (reaped)"
                            err_code = "orphan_host_reaped"
                        elif is_stale_heartbeat:
                            reason = f"Lane lease heartbeat stale ({now_ts - (heartbeat_at or 0)}s > 300s) (reaped)"
                            err_code = "heartbeat_timeout"
                        else:
                            reason = "Lane lease TTL expired (reaped)"
                            err_code = "lease_expired"
                        logger.warning(
                            "Reaping lane lease '%s' (run '%s', owner '%s'): %s.",
                            lane_id, run_id, owner, reason,
                        )
                        conn.execute("BEGIN IMMEDIATE")
                        conn.execute("DELETE FROM lane_leases WHERE lane_id = ? AND run_id = ?", (lane_id, run_id))
                        conn.execute(
                            "UPDATE stories SET status = ?, run_id = NULL, error_msg = ? WHERE run_id = ? AND status IN ('CLAIMED', 'PROCESSING')",
                            (JobStatus.RETRYABLE_FAILED.value, reason, run_id),
                        )
                        conn.execute(
                            "UPDATE runs SET status = ?, finished_at = ?, error_code = ? WHERE run_id = ?",
                            (JobStatus.RETRYABLE_FAILED.value, now_utc, err_code, run_id),
                        )
                        conn.commit()
                        reaped_count += 1
            except sqlite3.OperationalError:
                pass

        return reaped_count


def start_reaper_daemon(interval_seconds: float = 30.0, db_path: Optional[Union[str, Path]] = None) -> threading.Thread:
    """Start background daemon thread executing periodic reaper sweeps."""
    reaper = LeaseReaper(db_path=db_path)

    def _loop():
        while True:
            try:
                reaper.reap_once()
            except Exception as exc:
                logger.error("Error in lease reaper sweep: %s", exc)
            time.sleep(interval_seconds)

    thread = threading.Thread(target=_loop, name="AutoLeaseReaper", daemon=True)
    thread.start()
    return thread
