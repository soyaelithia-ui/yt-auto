"""Telegram approval timeout and auto-publication for long-pending reviews.

The system is fully automatic: videos wait in the review store up to
AUTO_PUBLISH_TIMEOUT_HOURS and, without further action, are auto-published
to YouTube through the canonical ReviewJobManager publication flow.

The sweep now honours the code-based review verdict: rows whose
``metadata.code_verdict`` is present (i.e. the deterministic verdict ran
and either approved or rejected the job) are skipped — the verdict path is
authoritative. Legacy rows without a verdict fall back to the timeout window.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("telegram_approval")

# Env-driven so operators can tune the review window without a code change.
# Default raised to 24h so transient infrastructure blips do not auto-publish
# a job that the deterministic verdict is still evaluating.
try:
    AUTO_PUBLISH_TIMEOUT_HOURS: int = max(1, int(os.environ.get("AUTO_PUBLISH_TIMEOUT_HOURS", "24")))
except ValueError:
    logger.warning(
        "AUTO_PUBLISH_TIMEOUT_HOURS inválido (%r); usando default 24",
        os.environ.get("AUTO_PUBLISH_TIMEOUT_HOURS"),
    )
    AUTO_PUBLISH_TIMEOUT_HOURS = 24


def _cutoff_time(max_age_seconds: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)


def get_expired_pending_videos(
    cutoff_time: Optional[datetime] = None, db_conn: Optional[Any] = None
) -> List[Dict[str, Any]]:
    """Return pending-review videos older than the auto-publish cutoff.

    The canonical source is ``review.ReviewStateStore``, which owns
    the atomic publication gate; no secondary queue scan is required.

    Rows whose ``metadata.code_verdict`` is already set are filtered out —
    the deterministic code-based review is the authoritative verdict and the
    auto-publish sweep must not race against it.
    """
    if db_conn and hasattr(db_conn, "get_expired_pending_videos"):
        try:
            return list(db_conn.get_expired_pending_videos(cutoff_time))
        except Exception as exc:
            logger.warning("db_conn.get_expired_pending_videos failed: %s", exc)

    max_age = int(AUTO_PUBLISH_TIMEOUT_HOURS * 3600)
    if cutoff_time is not None:
        max_age = max(0, int((datetime.now(timezone.utc) - cutoff_time).total_seconds()))

    from review.db import ReviewStateStore

    store = ReviewStateStore()
    out: List[Dict[str, Any]] = []
    cooldown = int(os.environ.get("APPROVED_RETRY_COOLDOWN_SECONDS", "900"))
    for job in store.get_stale_pending_jobs(max_age_seconds=max_age, approved_retry_cooldown_seconds=cooldown):
        metadata = job.metadata if isinstance(job.metadata, dict) else {}
        if isinstance(metadata.get("code_verdict"), dict) and metadata["code_verdict"]:
            logger.info(
                "Sweep skipping %s v%s — code verdict already set",
                job.job_id, job.version,
            )
            continue
        out.append(
            {
                "id": job.job_id,
                "job_id": job.job_id,
                "title": job.title,
                "description": job.description,
                "original_video_path": job.original_video_path,
                "video_path": job.original_video_path,
                "version": job.version,
                "channel": job.channel,
                "created_at": job.created_at,
                "status": job.status,
                "metadata": metadata,
            }
        )
    return out


def update_video_status(
    video_id: str, status: str = "auto_published", db_conn: Optional[Any] = None
) -> bool:
    """Persist a publication marker on the local stories queue.

    ``status`` defaults to ``PUBLISHED`` — the canonical terminal state. The
    legacy ``'auto_published'`` value was an illegal status outside the state
    machine; auto-publication must travel the same path as human approval.
    """
    if status == "auto_published":
        status = "PUBLISHED"
    if db_conn and hasattr(db_conn, "update_video_status"):
        try:
            db_conn.update_video_status(video_id, status=status)
            return True
        except Exception as exc:
            logger.warning("db_conn.update_video_status failed: %s", exc)

    try:
        from src.config import DEFAULT_DB_PATH
        from src.core.repository import connect

        with connect(DEFAULT_DB_PATH) as conn:
            conn.execute(
                "UPDATE stories SET status = ?, youtube_url = COALESCE(youtube_url, ?), updated_at = CURRENT_TIMESTAMP WHERE story_id = ?",
                (
                    status,
                    f"https://www.youtube.com/watch?v={video_id}",
                    video_id,
                ),
            )
            conn.commit()
        return True
    except Exception as exc:
        logger.warning("Local queue DB status update failed: %s", exc)
        return False


def _trigger_youtube_upload_sync(video: Dict[str, Any]) -> Dict[str, Any]:
    """Auto-publish an expired video through the canonical ReviewJobManager flow."""
    video_id = str(video.get("id") or video.get("job_id"))
    version = int(video.get("version") or 1)

    try:
        from review import ReviewJobManager

        manager = ReviewJobManager()
        from src.review_adapter import publish

        manager.register_publish_handler(
            "YTShort",
            lambda job: publish(
                {
                    "job_id": job.job_id,
                    "version": job.version,
                    "original_video_path": job.original_video_path,
                    "thumbnail_path": str(Path(job.original_video_path).parent / "thumbnail.jpg"),
                    "title": job.title,
                    "description": job.description,
                    "channel": job.channel,
                }
            ),
        )
        res = manager.action_publish(job_id=video_id, version=version, user_id=0)
        logger.info("Auto-published %s v%s: %s", video_id, version, res)
        return res
    except Exception as exc:
        logger.warning("ReviewJobManager auto-publish failed for %s: %s", video_id, exc)

    try:
        from src.review_adapter import publish

        res = publish(
            {
                "job_id": video_id,
                "version": version,
                "original_video_path": video.get("original_video_path") or video.get("video_path", ""),
                "title": video.get("title", ""),
                "description": video.get("description", ""),
                "channel": video.get("channel", "moku"),
            }
        )
        logger.info("Auto-published via publication adapter for %s: %s", video_id, res)
        return res
    except Exception as exc:
        logger.error("YouTube auto-upload failed for video %s: %s", video_id, exc)
        return {"ok": False, "error": str(exc)}


async def trigger_youtube_upload(video: Dict[str, Any]) -> Dict[str, Any]:
    """Async-compatible alias kept for external callers."""
    return _trigger_youtube_upload_sync(video)


def _run_sweep(max_age_seconds: int, db_conn: Optional[Any] = None) -> List[str]:
    """Core auto-publish sweep. Returns ids published in this pass."""
    expired = get_expired_pending_videos(
        cutoff_time=_cutoff_time(max_age_seconds), db_conn=db_conn
    )
    published_ids: List[str] = []
    for video in expired:
        v_id = str(video.get("id") or video.get("job_id"))
        try:
            result = _trigger_youtube_upload_sync(video)
        except Exception as exc:
            logger.error("Auto-publication exception for %s: %s", v_id, exc)
            continue
        if result.get("ok"):
            published_ids.append(v_id)
            update_video_status(v_id, status="auto_published", db_conn=db_conn)
    if published_ids:
        logger.info(
            "Auto-published %d expired review(s): %s", len(published_ids), published_ids
        )
    return published_ids


async def process_approval_timeout(db_conn: Optional[Any] = None) -> List[str]:
    """Async entrypoint running the AUTO_PUBLISH_TIMEOUT_HOURS auto-publish sweep."""
    return _run_sweep(int(AUTO_PUBLISH_TIMEOUT_HOURS * 3600), db_conn=db_conn)


def check_pending_approvals(
    db_conn: Optional[Any] = None, timeout_hours: int = AUTO_PUBLISH_TIMEOUT_HOURS
) -> List[str]:
    """Synchronously auto-publish pending reviews older than ``timeout_hours``."""
    return _run_sweep(int(timeout_hours) * 3600, db_conn=db_conn)
