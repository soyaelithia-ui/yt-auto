"""Compatibility facade over the safe SQLite repository."""

from __future__ import annotations

import asyncio
import functools
import hashlib
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
    validate_db_path,
    wal_checkpoint_passive as repo_wal_checkpoint_passive,
)
from src.log import get_logger


logger = get_logger("db")


@contextmanager
def get_db_connection(db_path: str = DEFAULT_DB_PATH) -> Iterator[sqlite3.Connection]:
    with connect(db_path) as conn:
        yield conn


def _get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Legacy helper; callers own the returned short-lived connection."""
    path_or_str = validate_db_path(db_path)
    if str(path_or_str) != ":memory:":
        parent = os.path.dirname(os.path.abspath(str(path_or_str)))
        if parent:
            os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(str(path_or_str), timeout=15.0)
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
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "UPDATE stories SET youtube_url = ? WHERE story_id = ?",
                    (youtube_url, story_id),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise


def is_story_processed(url_or_id: str, db_path: str = DEFAULT_DB_PATH) -> bool:
    if not os.path.exists(db_path):
        return False
    try:
        with connect(db_path, read_only=True) as conn:
            row = conn.execute(
                "SELECT 1 FROM stories WHERE story_id = ? OR url = ? LIMIT 1",
                (url_or_id, url_or_id),
            ).fetchone()
        return row is not None
    except sqlite3.OperationalError as exc:
        msg = str(exc).lower()
        if "no such table" in msg or "unable to open database" in msg:
            return False
        raise


def is_story_duplicate(
    channel: str,
    title_or_id: str,
    content: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> bool:
    """Strict 3-tier story deduplication checking stories and content_fingerprints.
    
    Tiers:
    1. Direct ID, Title, or URL exact match on specified channel.
    2. SHA-256 content digest match (combined and raw) on specified channel.
    3. 64-bit SimHash near-duplicate scan (Hamming distance <= 3) on specified channel.
    """
    if not os.path.exists(db_path):
        return False
    try:
        ch_key = canonical_channel(channel).value
    except (ValueError, KeyError):
        return False
    term = (title_or_id or "").strip()
    try:
        with connect(db_path, read_only=True) as conn:
            # 1. Direct story_id, title or URL match on specified channel
            if term:
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
                clean_content = content.strip()
                normalized = (term + "\n" + clean_content).lower() if term else clean_content.lower()
                digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
                content_raw_digest = hashlib.sha256(clean_content.encode("utf-8")).hexdigest()

                try:
                    fp_row = conn.execute(
                        """
                        SELECT 1 FROM content_fingerprints
                        WHERE channel = ? AND (sha256 = ? OR sha256 = ?)
                        LIMIT 1
                        """,
                        (ch_key, digest, content_raw_digest),
                    ).fetchone()
                    if fp_row is not None:
                        return True
                except sqlite3.OperationalError as exc:
                    logger.debug("Table or column absent during fingerprint check: %s", exc)

                # Also check exact content match in stories table
                try:
                    story_content_row = conn.execute(
                        """
                        SELECT 1 FROM stories
                        WHERE channel = ? AND content = ?
                        LIMIT 1
                        """,
                        (ch_key, clean_content),
                    ).fetchone()
                    if story_content_row is not None:
                        return True
                except sqlite3.OperationalError as exc:
                    logger.debug("Table or column absent during stories exact check: %s", exc)

                # 3. 64-bit SimHash near-duplicate check (Hamming distance <= 3)
                target_simhashes = [
                    compute_simhash_64(normalized),
                    compute_simhash_64(clean_content),
                ]
                target_simhashes = [tsh for tsh in target_simhashes if tsh != 0]

                if target_simhashes:
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
                                    if simhash_hamming_distance(tsh, existing_sh) <= 3:
                                        return True
                    except sqlite3.OperationalError as exc:
                        logger.debug("Table or column absent during simhash check: %s", exc)

                    # Also check against recent stories in stories table
                    try:
                        story_rows = conn.execute(
                            """
                            SELECT content FROM stories
                            WHERE channel = ? AND content IS NOT NULL
                            ORDER BY created_at DESC LIMIT 200
                            """,
                            (ch_key,),
                        ).fetchall()
                        for s_row in story_rows:
                            s_content = s_row["content"]
                            if s_content:
                                s_sh = compute_simhash_64(s_content)
                                if s_sh != 0:
                                    for tsh in target_simhashes:
                                        if simhash_hamming_distance(tsh, s_sh) <= 3:
                                            return True
                    except sqlite3.OperationalError as exc:
                        logger.debug("Table or column absent during recent stories check: %s", exc)
        return False
    except sqlite3.OperationalError as exc:
        msg = str(exc).lower()
        if "no such table" in msg or "unable to open database" in msg:
            return False
        raise


@auto_ensure_table
def reset_processing_stories(db_path: str = DEFAULT_DB_PATH) -> int:
    """Recover expired channel and lane leases safely without interrupting active work."""
    repo = QueueRepository(db_path)
    recovered_channel = repo.recover_expired_leases()
    recovered_lanes = repo.recover_expired_lane_leases()
    total_recovered = recovered_channel + recovered_lanes
    logger.info("Recovered %s expired leases (%s channel, %s lane)", total_recovered, recovered_channel, recovered_lanes)
    return total_recovered


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
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "UPDATE stories SET status = ?, error_msg = COALESCE(?, error_msg), updated_at = CURRENT_TIMESTAMP WHERE story_id = ?",
                (status, error_msg, video_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


# --- Asynchronous Non-Blocking Helpers for Concurrency ---

async def async_init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """Asynchronously run database migrations."""
    await asyncio.to_thread(init_db, db_path)


async def async_enqueue_story(
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
    """Asynchronously enqueue a story in SQLite without blocking the event loop."""
    return await asyncio.to_thread(
        enqueue_story,
        story_id,
        title,
        content,
        url,
        channel=channel,
        score=score,
        upvote_ratio=upvote_ratio,
        num_comments=num_comments,
        lane_id=lane_id,
        source_license=source_license,
        db_path=db_path,
    )


async def async_get_pending_story(
    db_path: str = DEFAULT_DB_PATH,
    claim: bool = False,
    channel: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Asynchronously get/claim a pending story from the queue."""
    return await asyncio.to_thread(
        get_pending_story,
        db_path=db_path,
        claim=claim,
        channel=channel,
    )


async def async_is_story_duplicate(
    channel: str,
    title_or_id: str,
    content: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> bool:
    """Asynchronously perform 3-tier story deduplication check."""
    return await asyncio.to_thread(
        is_story_duplicate,
        channel=channel,
        title_or_id=title_or_id,
        content=content,
        db_path=db_path,
    )


async def async_is_story_processed(
    url_or_id: str,
    db_path: str = DEFAULT_DB_PATH,
) -> bool:
    """Asynchronously check if story has been processed."""
    return await asyncio.to_thread(
        is_story_processed,
        url_or_id=url_or_id,
        db_path=db_path,
    )


async def async_update_story_status(
    story_id: str,
    status: str,
    error_msg: Optional[str] = None,
    youtube_url: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    """Asynchronously update story status."""
    await asyncio.to_thread(
        update_story_status,
        story_id=story_id,
        status=status,
        error_msg=error_msg,
        youtube_url=youtube_url,
        db_path=db_path,
    )


async def async_reset_processing_stories(db_path: str = DEFAULT_DB_PATH) -> int:
    """Asynchronously recover expired leases."""
    return await asyncio.to_thread(reset_processing_stories, db_path=db_path)


def wal_checkpoint_passive(db_path: str = DEFAULT_DB_PATH) -> tuple[int, int, int]:
    """Safely execute passive WAL checkpoint without blocking active readers or writers."""
    return repo_wal_checkpoint_passive(db_path)


async def async_wal_checkpoint_passive(db_path: str = DEFAULT_DB_PATH) -> tuple[int, int, int]:
    """Asynchronously execute passive WAL checkpoint on a background thread."""
    return await asyncio.to_thread(wal_checkpoint_passive, db_path=db_path)


