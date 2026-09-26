"""Database store for video review state and atomic publication flow."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

from review.domain import (
    ALLOWED_TRANSITIONS,
    ReviewJob,
    ReviewStatus,
    validate_status_name,
)
from src.core.repository import validate_db_path

REVIEW_SCHEMA = """
CREATE TABLE IF NOT EXISTS review_jobs (
    job_id TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    project TEXT NOT NULL DEFAULT 'YTShort',
    channel TEXT NOT NULL DEFAULT 'moku',
    content_type TEXT NOT NULL DEFAULT 'short',
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    original_video_path TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    reviewed_at TEXT,
    telegram_chat_id INTEGER,
    telegram_message_id INTEGER,
    published_id TEXT,
    published_url TEXT,
    publication_consumed INTEGER NOT NULL DEFAULT 0,
    delivery_error TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (job_id, version)
)
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _migrate_legacy_schema(db_path: str) -> None:
    """Migrate the legacy single-version table (no version column) in place."""
    with get_db_connection(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(review_jobs)").fetchall()}
        if "version" in columns:
            return
        conn.execute("ALTER TABLE review_jobs RENAME TO review_jobs_legacy")
        conn.execute(REVIEW_SCHEMA)
        conn.execute(
            """
            INSERT INTO review_jobs
                (job_id, version, channel, title, original_video_path, status,
                 created_at, reviewed_at, telegram_message_id)
            SELECT job_id, 1, channel, title, video_path, status,
                   created_at, reviewed_at, telegram_message_id
            FROM review_jobs_legacy
            """
        )
        conn.execute("DROP TABLE review_jobs_legacy")


def _migrate_add_metadata(db_path: str) -> None:
    """Add the metadata TEXT column (default '{}') to legacy review_jobs tables
    that pre-date the code-based review verdict payload."""
    with get_db_connection(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(review_jobs)").fetchall()}
        if "metadata" in columns:
            return
        conn.execute("ALTER TABLE review_jobs ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'")


REVIEW_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_review_jobs_status ON review_jobs(status)",
    "CREATE INDEX IF NOT EXISTS idx_review_jobs_msg ON review_jobs(telegram_message_id)",
    "CREATE INDEX IF NOT EXISTS idx_review_jobs_created ON review_jobs(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_review_jobs_job_status ON review_jobs(job_id, status)",
)


def _ensure_review_indexes(db_path: str) -> None:
    with get_db_connection(db_path) as conn:
        for idx in REVIEW_INDEXES:
            conn.execute(idx)


def init_review_db(db_path: str | os.PathLike[str]) -> None:
    path_or_str = validate_db_path(db_path)
    if str(path_or_str) != ":memory:":
        parent = os.path.dirname(os.path.abspath(str(path_or_str)))
        if parent:
            os.makedirs(parent, exist_ok=True)
    with sqlite3.connect(str(path_or_str), timeout=30.0) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=15000;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA temp_store=MEMORY;")
        conn.execute("PRAGMA cache_size=-8000;")
        conn.execute(REVIEW_SCHEMA)
        for idx in REVIEW_INDEXES:
            conn.execute(idx)
        conn.commit()
    _migrate_legacy_schema(str(path_or_str))
    _migrate_add_metadata(str(path_or_str))
    _ensure_review_indexes(str(path_or_str))


@contextmanager
def get_db_connection(db_path: str | os.PathLike[str]) -> Iterator[sqlite3.Connection]:
    """Yield a row-factory connection inside an autocommit transaction."""
    path_or_str = validate_db_path(db_path)
    conn = sqlite3.connect(str(path_or_str), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=15000;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA cache_size=-8000;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _default_review_db() -> str:
    """Profile-aware default; keeps the standalone legacy fallback intact."""
    try:
        from src.config import default_review_db_path

        return str(default_review_db_path())
    except Exception:
        return os.environ.get("VIDEO_REVIEW_DB_PATH", "data/review_state.db")


class ReviewStateStore:
    def __init__(self, db_path: str | os.PathLike[str] | None = None):
        raw_path = db_path or os.environ.get(
            "VIDEO_REVIEW_DB_PATH"
        ) or _default_review_db()
        self.db_path = str(validate_db_path(raw_path))
        init_review_db(self.db_path)


    def create_job(self, job: ReviewJob) -> ReviewJob:
        now = _now_iso()
        metadata_json = json.dumps(job.metadata or {}, ensure_ascii=False)
        created_at = job.created_at or now
        with get_db_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO review_jobs (
                    job_id, version, project, channel, content_type, title,
                    description, original_video_path, status, created_at,
                    reviewed_at, telegram_chat_id, telegram_message_id,
                    published_id, published_url, publication_consumed,
                    delivery_error, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id, version) DO UPDATE SET
                    project=excluded.project,
                    channel=excluded.channel,
                    content_type=excluded.content_type,
                    title=excluded.title,
                    description=excluded.description,
                    original_video_path=excluded.original_video_path,
                    status=excluded.status,
                    reviewed_at=excluded.reviewed_at,
                    telegram_chat_id=excluded.telegram_chat_id,
                    telegram_message_id=excluded.telegram_message_id,
                    delivery_error=excluded.delivery_error,
                    metadata=excluded.metadata
                """,
                (
                    job.job_id,
                    job.version,
                    job.project,
                    job.channel,
                    job.content_type,
                    job.title,
                    job.description,
                    job.original_video_path,
                    job.status if isinstance(job.status, str) else job.status.value,
                    created_at,
                    job.reviewed_at,
                    job.telegram_chat_id,
                    job.telegram_message_id,
                    # Un re-submit nunca puede borrar la publicación ya lograda:
                    # preserva published_id/url/publication_consumed existentes.
                    job.published_id,
                    job.published_url,
                    job.publication_consumed,
                    job.delivery_error,
                    metadata_json,
                ),
            )
        return self.get_job(job.job_id, job.version) or job

    def save_job(self, job: ReviewJob) -> ReviewJob:
        """Backward-compatible alias for create_job."""
        return self.create_job(job)

    def get_job(self, job_id: str, version: int = 1) -> Optional[ReviewJob]:
        with get_db_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM review_jobs WHERE job_id = ? AND version = ?",
                (job_id, version),
            ).fetchone()
            if row:
                return ReviewJob.from_row(row)
        return None

    def get_latest_job(self, job_id: str) -> Optional[ReviewJob]:
        """Return the newest version for a callback that omits version."""
        with get_db_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM review_jobs WHERE job_id = ? ORDER BY version DESC LIMIT 1",
                (job_id,),
            ).fetchone()
            if row:
                return ReviewJob.from_row(row)
        return None

    def get_pending_jobs(self) -> List[ReviewJob]:
        with get_db_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM review_jobs WHERE status IN (?, ?)",
                (ReviewStatus.PENDING_REVIEW.value, ReviewStatus.APPROVED.value),
            ).fetchall()
            return [ReviewJob.from_row(r) for r in rows]

    def get_stale_pending_jobs(
        self,
        max_age_seconds: int = 21600,
        approved_retry_cooldown_seconds: int = 0,
    ) -> List[ReviewJob]:
        """Pending jobs whose created_at is older than max_age_seconds.

        If approved_retry_cooldown_seconds > 0 and a job is in APPROVED status,
        it will be excluded if its reviewed_at was updated less than
        approved_retry_cooldown_seconds ago (cooldown after failed publish attempt).
        """
        pending = self.get_pending_jobs()
        now_ts = datetime.now(timezone.utc).timestamp()
        cutoff = now_ts - max_age_seconds
        stale: List[ReviewJob] = []
        for job in pending:
            if approved_retry_cooldown_seconds > 0 and job.status == ReviewStatus.APPROVED.value:
                if job.reviewed_at:
                    try:
                        reviewed = datetime.fromisoformat(job.reviewed_at)
                        if (now_ts - reviewed.timestamp()) < approved_retry_cooldown_seconds:
                            continue
                    except (TypeError, ValueError):
                        pass
            try:
                created = datetime.fromisoformat(job.created_at)
            except (TypeError, ValueError):
                continue
            if created.timestamp() < cutoff:
                stale.append(job)
        return stale

    def _transition(self, job_id: str, version: int, current: str, target: str) -> None:
        target = validate_status_name(target)
        if target not in ALLOWED_TRANSITIONS.get(current, frozenset()):
            raise ValueError(
                f"Invalid review status transition: {current!r} -> {target!r}"
            )

    def update_job_status(
        self,
        job_id: str,
        version: int = 1,
        status: str | ReviewStatus = ReviewStatus.PENDING_REVIEW,
    ) -> ReviewJob:
        """Validated status update; raises ValueError on invalid name/transition."""
        target = validate_status_name(status)
        with get_db_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM review_jobs WHERE job_id = ? AND version = ?",
                (job_id, version),
            ).fetchone()
            if row is None:
                raise ValueError(f"Review job not found: {job_id} v{version}")
            current = str(row["status"])
            self._transition(job_id, version, current, target)
            conn.execute(
                "UPDATE review_jobs SET status = ?, reviewed_at = ? WHERE job_id = ? AND version = ?",
                (target, _now_iso(), job_id, version),
            )

        if target == "REJECTED":
            try:
                from src.observability.events import emit_event

                emit_event(
                    "asset_rejection",
                    level="WARNING",
                    message=f"Editorial rejection for review job {job_id} v{version}",
                    details={
                        "defect_category": "editorial",
                        "job_id": job_id,
                        "version": version,
                    },
                    story_id=job_id,
                )
            except Exception:
                pass

        return self.get_job(job_id, version)  # type: ignore[return-value]

    def transition_review_action(
        self,
        job_id: str,
        version: int = 1,
        target_status: str | ReviewStatus = ReviewStatus.APPROVED,
    ) -> ReviewJob:
        return self.update_job_status(job_id, version, target_status)

    def approve_job(
        self, job_id: str, version: int = 1, user_id: Optional[int] = None
    ) -> ReviewJob:
        return self.update_job_status(job_id, version, ReviewStatus.APPROVED)

    def reject_job(self, job_id: str, version: int = 1) -> ReviewJob:
        return self.update_job_status(job_id, version, ReviewStatus.REJECTED)

    def update_job_metadata(
        self,
        job_id: str,
        version: int,
        metadata: Dict[str, Any],
    ) -> ReviewJob:
        """Replace the metadata JSON blob for a job. Returns the refreshed row.

        Used by the code-based review path to persist the verdict payload alongside
        the status transition without overwriting unrelated fields.
        """
        payload = json.dumps(metadata or {}, ensure_ascii=False)
        with get_db_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM review_jobs WHERE job_id = ? AND version = ?",
                (job_id, version),
            ).fetchone()
            if row is None:
                raise ValueError(f"Review job not found for metadata update: {job_id} v{version}")
            conn.execute(
                "UPDATE review_jobs SET metadata = ? WHERE job_id = ? AND version = ?",
                (payload, job_id, version),
            )
        refreshed = self.get_job(job_id, version)
        if refreshed is None:
            raise RuntimeError(f"Review job vanished after metadata update: {job_id} v{version}")
        return refreshed

    def claim_for_publication(
        self, job_id: str, version: int, video_path: str = ""
    ) -> ReviewJob:
        """Atomically move an APPROVED job to PUBLISHING, returning the claimed job.

        Raises RuntimeError when the job is not approvable or the path does not
        match, leaving the persisted state untouched.
        """
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout=15000;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA temp_store=MEMORY;")
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM review_jobs WHERE job_id = ? AND version = ?",
                (job_id, version),
            ).fetchone()
            if row is None:
                raise RuntimeError(f"Publication claim job not found: {job_id} v{version}")
            current = str(row["status"])
            if current not in (
                ReviewStatus.APPROVED.value,
                ReviewStatus.WAITING_HUMAN_VERIFICATION.value,
            ):
                raise RuntimeError(
                    f"Publication gate is not approved for {job_id} v{version}: {current}"
                )
            if video_path:
                stored_path = str(row["original_video_path"] or "")
                if (
                    stored_path
                    and os.path.realpath(stored_path) != os.path.realpath(video_path)
                ):
                    raise RuntimeError(
                        f"Publication gate path mismatch for {job_id} v{version}"
                    )
            conn.execute(
                "UPDATE review_jobs SET status = ?, reviewed_at = ? "
                "WHERE job_id = ? AND version = ?",
                (ReviewStatus.PUBLISHING.value, _now_iso(), job_id, version),
            )
            conn.commit()
            claimed = ReviewJob.from_row(
                conn.execute(
                    "SELECT * FROM review_jobs WHERE job_id = ? AND version = ?",
                    (job_id, version),
                ).fetchone()
            )
            return claimed
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def confirm_publication(
        self,
        job_id: str,
        version: int,
        published_id: str,
        published_url: str = "",
    ) -> ReviewJob:
        """Persist a verified publication and mark the job PUBLISHED."""
        with get_db_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM review_jobs WHERE job_id = ? AND version = ?",
                (job_id, version),
            ).fetchone()
            if row is None:
                raise ValueError(f"Review job not found: {job_id} v{version}")
            current = str(row["status"])
            if current not in (
                ReviewStatus.PUBLISHING.value,
                ReviewStatus.PUBLISHED.value,
            ):
                raise ValueError(
                    f"Cannot confirm publication from status {current!r}"
                )
            conn.execute(
                """
                UPDATE review_jobs SET status = ?, published_id = ?, published_url = ?,
                    publication_consumed = 1, reviewed_at = ?
                WHERE job_id = ? AND version = ?
                """,
                (
                    ReviewStatus.PUBLISHED.value,
                    published_id,
                    published_url,
                    _now_iso(),
                    job_id,
                    version,
                ),
            )
        return self.get_job(job_id, version)  # type: ignore[return-value]
