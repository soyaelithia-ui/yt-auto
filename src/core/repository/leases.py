"""Worker lease management, heartbeat renewals, orphan lease recovery, and checkpoints."""

from __future__ import annotations

import sqlite3
import time
from typing import Any

from src.core.domain import ALL_STATUSES, CanonicalChannel, JobStatus, canonical_channel
from src.core.repository.migrations import _utc_now, connect, wal_checkpoint_passive


class LeaseOperationsMixin:
    """Operations related to worker leases, heartbeats, expiry recovery, and WAL checkpoints."""

    db_path: str

    def wal_checkpoint_passive(self) -> tuple[int, int, int]:
        """Safely run PRAGMA wal_checkpoint(PASSIVE) for this repository's database."""
        return wal_checkpoint_passive(self.db_path)

    def checkpoint_wal(self, mode: str = "PASSIVE") -> tuple[int, int, int]:
        """Safely checkpoint WAL frames back to the database file without blocking writers."""
        valid_modes = {"PASSIVE", "FULL", "RESTART", "TRUNCATE"}
        selected_mode = mode.upper() if mode.upper() in valid_modes else "PASSIVE"
        with connect(self.db_path) as conn:
            row = conn.execute(f"PRAGMA wal_checkpoint({selected_mode});").fetchone()
            if row is None:
                return (0, 0, 0)
            return (int(row[0]), int(row[1]), int(row[2]))

    @staticmethod
    def _holds_lease(
        conn: sqlite3.Connection,
        story_id: str,
        run_id: str,
        owner: str,
        *,
        now: int | None = None,
    ) -> bool:
        """True when a live lease for (story, run, owner) exists in either table."""
        current = int(time.time() if now is None else now)
        for table in ("leases", "lane_leases"):
            if conn.execute(
                f"SELECT 1 FROM {table} "
                "WHERE job_id = ? AND run_id = ? AND owner = ? AND expires_at > ?",
                (story_id, run_id, owner, current),
            ).fetchone():
                return True
        return False

    @staticmethod
    def _bind_channel_lease_locked(
        conn: sqlite3.Connection,
        run_id: str,
        channel_key: str,
        story_id: str,
        mode: str,
        owner: str,
        current: int,
        lease_seconds: int,
    ) -> None:
        now_ts = _utc_now()
        conn.execute(
            """
            INSERT INTO runs(
                run_id, channel, story_id, mode, status, owner,
                started_at, heartbeat_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, channel_key, story_id, mode, JobStatus.PROCESSING.value, owner, now_ts, now_ts),
        )
        conn.execute(
            """
            INSERT INTO leases(
                job_id, channel, owner, run_id, acquired_at,
                heartbeat_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                channel = excluded.channel,
                owner = excluded.owner,
                run_id = excluded.run_id,
                acquired_at = excluded.acquired_at,
                heartbeat_at = excluded.heartbeat_at,
                expires_at = excluded.expires_at
            """,
            (story_id, channel_key, owner, run_id, current, current, current + lease_seconds),
        )
        conn.execute(
            "INSERT OR IGNORE INTO run_stories(run_id, story_id, position) VALUES (?, ?, 0)",
            (run_id, story_id),
        )

    @staticmethod
    def _bind_lane_lease_locked(
        conn: sqlite3.Connection,
        run_id: str,
        channel_key: str,
        story_id: str,
        mode: str,
        owner: str,
        lane_key: str,
        current: int,
        lease_seconds: int,
    ) -> None:
        now_ts = _utc_now()
        conn.execute(
            """
            INSERT INTO runs(
                run_id, channel, story_id, mode, status, owner,
                started_at, heartbeat_at, lane_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, channel_key, story_id, mode, JobStatus.PROCESSING.value, owner, now_ts, now_ts, lane_key),
        )
        conn.execute(
            """
            INSERT INTO lane_leases(
                job_id, lane_id, channel, owner, run_id, acquired_at,
                heartbeat_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                lane_id = excluded.lane_id,
                channel = excluded.channel,
                owner = excluded.owner,
                run_id = excluded.run_id,
                acquired_at = excluded.acquired_at,
                heartbeat_at = excluded.heartbeat_at,
                expires_at = excluded.expires_at
            """,
            (story_id, lane_key, channel_key, owner, run_id, current, current, current + lease_seconds),
        )
        conn.execute(
            "INSERT OR IGNORE INTO run_stories(run_id, story_id, position) VALUES (?, ?, 0)",
            (run_id, story_id),
        )

    def _recover_expired_exact_locked(
        self,
        conn: sqlite3.Connection,
        story_id: str,
        channel: str,
        now: int,
    ) -> int:
        expired = conn.execute(
            """
            SELECT job_id, run_id FROM leases
            WHERE job_id = ? AND channel = ? AND expires_at <= ?
            """,
            (story_id, channel, now),
        ).fetchall()
        for lease in expired:
            conn.execute(
                """
                UPDATE stories
                SET status = ?, run_id = NULL, failure_code = 'lease_expired',
                    error_msg = 'Lease dirigido expirado; trabajo reconciliado',
                    next_attempt_at = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE story_id = ? AND run_id = ? AND status = ?
                """,
                (
                    JobStatus.RETRYABLE_FAILED.value,
                    lease["job_id"],
                    lease["run_id"],
                    JobStatus.PROCESSING.value,
                ),
            )
            conn.execute(
                """
                UPDATE runs
                SET status = ?, finished_at = ?, error_code = 'lease_expired'
                WHERE run_id = ? AND status = ?
                """,
                (
                    JobStatus.RETRYABLE_FAILED.value,
                    _utc_now(),
                    lease["run_id"],
                    JobStatus.PROCESSING.value,
                ),
            )
            conn.execute(
                "DELETE FROM leases WHERE job_id = ? AND run_id = ? AND expires_at <= ?",
                (lease["job_id"], lease["run_id"], now),
            )
        return len(expired)

    def recover_expired_exact(
        self,
        story_id: str,
        channel: str | CanonicalChannel,
        *,
        now: int | None = None,
    ) -> int:
        current = int(time.time() if now is None else now)
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            count = self._recover_expired_exact_locked(
                conn,
                str(story_id or "").strip(),
                canonical_channel(channel).value,
                current,
            )
            conn.commit()
            return count

    def _recover_expired_locked(self, conn: sqlite3.Connection, now: int) -> int:
        expired = conn.execute(
            "SELECT job_id, run_id FROM leases WHERE expires_at <= ?", (now,)
        ).fetchall()
        for lease in expired:
            conn.execute(
                """
                UPDATE stories
                SET status = ?, run_id = NULL, failure_code = 'lease_expired',
                    error_msg = 'Lease expirado; trabajo recuperado de forma segura',
                    updated_at = CURRENT_TIMESTAMP
                WHERE story_id = ? AND run_id = ? AND status = ?
                """,
                (
                    JobStatus.RETRYABLE_FAILED.value,
                    lease["job_id"],
                    lease["run_id"],
                    JobStatus.PROCESSING.value,
                ),
            )
            conn.execute(
                """
                UPDATE runs
                SET status = ?, finished_at = ?, error_code = 'lease_expired'
                WHERE run_id = ?
                """,
                (JobStatus.RETRYABLE_FAILED.value, _utc_now(), lease["run_id"]),
            )
        conn.execute("DELETE FROM leases WHERE expires_at <= ?", (now,))
        return len(expired)

    def recover_expired_leases(self, *, now: int | None = None) -> int:
        current = int(time.time() if now is None else now)
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            count = self._recover_expired_locked(conn, current)
            conn.commit()
            return count

    def heartbeat(
        self,
        run_id: str,
        owner: str,
        *,
        lease_seconds: int = 900,
        now: int | None = None,
    ) -> bool:
        current = int(time.time() if now is None else now)
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                """
                UPDATE leases SET heartbeat_at = ?, expires_at = ?
                WHERE run_id = ? AND owner = ? AND expires_at > ?
                """,
                (current, current + lease_seconds, run_id, owner, current),
            )
            if not cursor.rowcount:
                cursor = conn.execute(
                    """
                    UPDATE lane_leases SET heartbeat_at = ?, expires_at = ?
                    WHERE run_id = ? AND owner = ? AND expires_at > ?
                    """,
                    (current, current + lease_seconds, run_id, owner, current),
                )
            if cursor.rowcount:
                conn.execute(
                    "UPDATE runs SET heartbeat_at = ? WHERE run_id = ? AND owner = ?",
                    (_utc_now(), run_id, owner),
                )
            conn.commit()
            return bool(cursor.rowcount)

    def _recover_expired_lanes_locked(self, conn: sqlite3.Connection, now: int) -> int:
        """Expire lane leases back to RETRYABLE_FAILED (mirrors legacy recovery)."""
        expired = conn.execute(
            "SELECT job_id, lane_id, run_id FROM lane_leases WHERE expires_at <= ?", (now,)
        ).fetchall()
        for lease in expired:
            conn.execute(
                """
                UPDATE stories
                SET status = ?, run_id = NULL, failure_code = 'lease_expired',
                    error_msg = 'Lease de carril expirado; trabajo recuperado de forma segura',
                    updated_at = CURRENT_TIMESTAMP
                WHERE story_id = ? AND run_id = ? AND status = ?
                """,
                (
                    JobStatus.RETRYABLE_FAILED.value,
                    lease["job_id"],
                    lease["run_id"],
                    JobStatus.PROCESSING.value,
                ),
            )
            conn.execute(
                """
                UPDATE runs
                SET status = ?, finished_at = ?, error_code = 'lease_expired'
                WHERE run_id = ?
                """,
                (JobStatus.RETRYABLE_FAILED.value, _utc_now(), lease["run_id"]),
            )
        conn.execute("DELETE FROM lane_leases WHERE expires_at <= ?", (now,))
        return len(expired)

    def recover_expired_lane_leases(self, *, now: int | None = None) -> int:
        current = int(time.time() if now is None else now)
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            count = self._recover_expired_lanes_locked(conn, current)
            conn.commit()
            return count

    def heartbeat_lane_lease(
        self,
        run_id: str,
        owner: str,
        *,
        lease_seconds: int = 900,
        now: int | None = None,
    ) -> bool:
        current = int(time.time() if now is None else now)
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                """
                UPDATE lane_leases SET heartbeat_at = ?, expires_at = ?
                WHERE run_id = ? AND owner = ? AND expires_at > ?
                """,
                (current, current + lease_seconds, run_id, owner, current),
            )
            if cursor.rowcount:
                conn.execute(
                    "UPDATE runs SET heartbeat_at = ? WHERE run_id = ? AND owner = ?",
                    (_utc_now(), run_id, owner),
                )
            conn.commit()
            return bool(cursor.rowcount)

    def finish_lane_run(self, run_id: str, status: str | JobStatus, *, owner: str | None = None) -> bool:
        value = status.value if isinstance(status, JobStatus) else str(status)
        if value not in ALL_STATUSES:
            raise ValueError(f"Estado operativo inválido: {value}")
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            if owner is not None and not conn.execute(
                "SELECT 1 FROM lane_leases WHERE run_id = ? AND owner = ? AND expires_at > ?",
                (run_id, owner, int(time.time())),
            ).fetchone():
                conn.rollback()
                return False
            cursor = conn.execute(
                "UPDATE runs SET status = ?, finished_at = ? WHERE run_id = ? AND status != ?",
                (value, _utc_now(), run_id, JobStatus.PUBLISHED.value),
            )
            if not cursor.rowcount:
                conn.rollback()
                return False
            conn.execute("DELETE FROM lane_leases WHERE run_id = ?", (run_id,))
            conn.commit()
            return True


def touch_daemon_liveness(db_path: Any, *, now: int | float | None = None) -> None:
    """Record the daemon liveness heartbeat consumed by healthcheck.py (AUD-08)."""
    stamp = int(now) if now is not None else int(time.time())
    with connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "INSERT INTO daemon_liveness(id, heartbeat_at) VALUES (1, ?) "
                "ON CONFLICT(id) DO UPDATE SET heartbeat_at = excluded.heartbeat_at",
                (stamp,),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def read_daemon_heartbeat(db_path: Any) -> int | None:
    """Return the last daemon liveness epoch, or None when absent/never set."""
    with connect(db_path, read_only=True) as conn:
        row = conn.execute(
            "SELECT heartbeat_at FROM daemon_liveness WHERE id = 1"
        ).fetchone()
    return int(row[0]) if row and row[0] else None
