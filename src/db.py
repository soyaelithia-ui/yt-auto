"""Compatibility facade over the safe SQLite repository."""

from __future__ import annotations

import functools
import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

from src.config import DEFAULT_DB_PATH
from src.core.domain import ALL_STATUSES, JobStatus, canonical_channel
from src.core.repository import (
    QueueRepository,
    compute_simhash_64,
    connect,
    migrate_database,
    simhash_hamming_distance,
)
from src.log import get_logger


logger = get_logger("db")


@contextmanager
def get_db_connection(db_path: str = DEFAULT_DB_PATH) -> Iterator[sqlite3.Connection]:
    with connect(db_path) as conn:
        yield conn


def _get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Legacy helper; callers own the returned short-lived connection."""
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=15000;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    migrate_database(db_path)


def auto_ensure_table(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        db_path = kwargs.get("db_path", DEFAULT_DB_PATH)
        try:
            return func(*args, **kwargs)
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower() or "no such column" in str(exc).lower():
                init_db(db_path)
                return func(*args, **kwargs)
            raise

    return wrapper


@auto_ensure_table
def enqueue_story(
    story_id: str,
    title: str,
    content: str,
    url: str,
    channel: str = "moku",
    score: int = 0,
    upvote_ratio: float = 0.0,
    num_comments: int = 0,
    lane_id: Optional[str] = None,
    source_license: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> bool:
    return QueueRepository(db_path).enqueue(
        story_id,
        title,
        content,
        url,
        canonical_channel(channel),
        score=score,
        upvote_ratio=upvote_ratio,
        num_comments=num_comments,
        lane_id=lane_id,
        source_license=source_license,
    )


@auto_ensure_table
def get_pending_story(
    db_path: str = DEFAULT_DB_PATH,
    claim: bool = False,
    channel: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if claim:
        if channel is None:
            raise ValueError("channel es obligatorio al reclamar un trabajo")
        return QueueRepository(db_path).claim(
            channel,
            owner=f"legacy-pipeline:{os.getpid()}",
        )
    with connect(db_path, read_only=True) as conn:
        if channel is None:
            row = conn.execute(
                "SELECT * FROM stories WHERE status = ? ORDER BY created_at LIMIT 1",
                (JobStatus.PENDING.value,),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT * FROM stories
                WHERE status = ? AND channel = ?
                ORDER BY created_at LIMIT 1
                """,
                (JobStatus.PENDING.value, canonical_channel(channel).value),
            ).fetchone()
    return dict(row) if row else None


@auto_ensure_table
def update_story_status(
    story_id: str,
    status: str,
    error_msg: Optional[str] = None,
    youtube_url: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    if status not in ALL_STATUSES:
        raise ValueError(f"Estado inválido: {status}")
    repository = QueueRepository(db_path)
    try:
        repository.set_status(
            story_id,
            status,
            error_code="legacy_failure" if error_msg else None,
            error_detail=error_msg,
        )
    except RuntimeError:
        raise
    if youtube_url is not None:
        # Historical COMPLETED records may retain a URL, but are not publication proof.
        with connect(db_path) as conn:
            conn.execute(
                "UPDATE stories SET youtube_url = ? WHERE story_id = ?",
                (youtube_url, story_id),
            )
            conn.commit()


def is_story_processed(url_or_id: str, db_path: str = DEFAULT_DB_PATH) -> bool:
    try:
        with connect(db_path, read_only=True) as conn:
            row = conn.execute(
                "SELECT 1 FROM stories WHERE story_id = ? OR url = ? LIMIT 1",
                (url_or_id, url_or_id),
            ).fetchone()
        return row is not None
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return False
        raise


def is_story_duplicate(
    channel: str,
    title_or_id: str,
    content: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> bool:
    """Strict 3-channel story deduplication checking stories and content_fingerprints."""
    ch_key = canonical_channel(channel).value
    term = title_or_id.strip()
    try:
        with connect(db_path, read_only=True) as conn:
            # 1. Direct story_id, title or URL match on specified channel
            row = conn.execute(
                """
                SELECT 1 FROM stories
                WHERE channel = ? AND (story_id = ? OR title = ? OR url = ?)
                LIMIT 1
                """,
                (ch_key, term, term, term),
            ).fetchone()
            if row is not None:
                return True

            # 2. Fingerprint match if content is provided
            if content and content.strip():
                import hashlib
                normalized = (term + "\n" + content.strip()).lower()
                digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
                fp_row = conn.execute(
                    """
                    SELECT 1 FROM content_fingerprints
                    WHERE channel = ? AND sha256 = ?
                    LIMIT 1
                    """,
                    (ch_key, digest),
                ).fetchone()
                if fp_row is not None:
                    return True

                # 3. 64-bit SimHash near-duplicate check (Hamming distance <= 3)
                target_simhashes = [
                    compute_simhash_64(normalized),
                    compute_simhash_64(content.strip()),
                ]
                try:
                    sh_rows = conn.execute(
                        """
                        SELECT simhash FROM content_fingerprints
                        WHERE channel = ? AND simhash IS NOT NULL
                        """,
                        (ch_key,),
                    ).fetchall()
                    for sh_row in sh_rows:
                        existing_sh = sh_row["simhash"]
                        if existing_sh is not None:
                            for tsh in target_simhashes:
                                if tsh != 0 and simhash_hamming_distance(tsh, existing_sh) <= 3:
                                    return True
                except sqlite3.OperationalError:
                    pass
        return False
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return False
        raise


@auto_ensure_table
def reset_processing_stories(db_path: str = DEFAULT_DB_PATH) -> int:
    """Legacy name: only expired leases are recovered; live work is never reset."""
    recovered = QueueRepository(db_path).recover_expired_leases()
    logger.info("Recovered %s expired leases", recovered)
    return recovered


@auto_ensure_table
def get_expired_pending_videos(
    cutoff_time: Any, db_path: str = DEFAULT_DB_PATH
) -> list[dict[str, Any]]:
    """Retrieve pending_approval stories created before cutoff_time."""
    from datetime import datetime
    cutoff_str = cutoff_time.isoformat() if isinstance(cutoff_time, datetime) else str(cutoff_time)
    with connect(db_path, read_only=True) as conn:
        rows = conn.execute(
            """
            SELECT * FROM stories
            WHERE status IN ('pending_approval', 'PENDING_REVIEW', 'WAITING_HUMAN_VERIFICATION')
              AND created_at <= ?
            ORDER BY created_at ASC
            """,
            (cutoff_str,),
        ).fetchall()
        return [
            {
                "id": str(r["story_id"]),
                "job_id": str(r["story_id"]),
                "title": str(r["title"]),
                "description": str(r["content"]),
                "video_path": str(r["url"]),
                "created_at": str(r["created_at"]),
                "status": str(r["status"]),
            }
            for r in rows
        ]


@auto_ensure_table
def update_video_status(
    video_id: str,
    status: str,
    error_msg: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    """Update status of a video/story record."""
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE stories SET status = ?, error_msg = COALESCE(?, error_msg), updated_at = CURRENT_TIMESTAMP WHERE story_id = ?",
            (status, error_msg, video_id),
        )
        conn.commit()
