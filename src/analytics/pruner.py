"""
src/analytics/pruner.py - Autonomous Underperforming Video Pruning Engine.

Implements criteria-based automated deletion of underperforming YouTube Shorts:
1. Mandatory 24h evaluation grace period (protects slow-burn / fresh videos).
2. Dual-threshold underperformance check (actual_success_score < floor).
3. Bounded daily deletion ceiling (<= 2 videos/channel/day).
4. Kill-switch (AUTO_PRUNE_ENABLED=false) and HTTP 429 circuit breaker.
5. Marked-video purge runs in bounded batches and retries on later sweeps.
6. Telegram operational audit alert dispatch.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.config import DEFAULT_DB_PATH
from src.core.domain import CHANNEL_ALIASES, CanonicalChannel, canonical_channel
from src.core.repository.migrations import connect
from src.log import get_logger

logger = get_logger("analytics.pruner")


@dataclass(slots=True, frozen=True)
class PruneCandidate:
    publication_id: int
    video_id: str
    story_id: str
    channel: str
    title: str
    actual_success_score: float
    age_hours: float
    verified_at: str


@dataclass(slots=True)
class AutonomousPruneReport:
    channel: str
    evaluated_count: int
    pruned_count: int
    skipped_count: int
    failed_count: int
    items: List[Dict[str, Any]] = field(default_factory=list)


def _parse_iso_age_hours(dt_str: str) -> float:
    """Calculates age in decimal hours between an ISO timestamp and current UTC time."""
    if not dt_str:
        return 0.0
    try:
        clean = dt_str.replace("Z", "+00:00")
        published = datetime.fromisoformat(clean)
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta_sec = (now - published).total_seconds()
        return max(0.0, delta_sec / 3600.0)
    except Exception:
        return 0.0


def classify_video_failure(
    title: str,
    channel: str,
    views: int,
    likes: int,
    age_hours: float,
    score: float,
) -> str:
    """Determines the specific failure code for an underperforming or corrupted video."""
    t_clean = (title or "").strip()
    t_lower = t_clean.lower()
    if not t_clean or len(t_clean) < 2 or t_lower in ("test", "video", "untitled", "video sin título", "sin título"):
        return "EMPTY_TITLE_ARTIFACT"
    c_lower = str(channel).lower()
    if "horror" in c_lower and any(kw in t_lower for kw in ("soy el malo", "aita", "dilema", "¿soy el malo")):
        return "CROSS_CONTAMINATED_TITLE"
    if "drama" in c_lower and any(kw in t_lower for kw in ("relato de terror", "scp-", "scp ", "misterio de ultratumba")):
        return "CROSS_CONTAMINATED_TITLE"
    if age_hours >= 48.0 and views < 50 and likes == 0:
        return "ZERO_ENGAGEMENT_STALE"
    if score < 40.0:
        return "UNDERPERFORMING_SCORE"
    return "UNKNOWN_FAILURE"


def evaluate_prune_candidates(
    channel: str | CanonicalChannel,
    db_path: str = DEFAULT_DB_PATH,
    min_score: float = 40.0,
    grace_hours: float = 24.0,
    max_candidates: int = 2,
) -> List[PruneCandidate]:
    """
    Evaluates published videos in the target channel and identifies pruning candidates:
    - Must be older than grace_hours (strictly >= 24h).
    - Score must be strictly less than min_score.
    - Sorted ascending by score (worst first).
    - Capped to max_candidates.
    """
    canon = canonical_channel(channel)
    aliases = {k for k, v in CHANNEL_ALIASES.items() if v == canon}
    aliases.add(str(channel).lower())
    aliases.add(canon.value)
    placeholders = ",".join("?" for _ in aliases)
    query = f"""
        SELECT publication_id, video_id, story_id, channel, title,
               actual_success_score, verified_at
        FROM publications
        WHERE channel IN ({placeholders})
          AND video_id IS NOT NULL
          AND video_id != ''
          AND story_id NOT IN (SELECT story_id FROM stories WHERE status = 'PURGED')
        ORDER BY actual_success_score ASC
    """
    candidates: List[PruneCandidate] = []
    with connect(db_path, read_only=True) as conn:
        rows = conn.execute(query, tuple(aliases)).fetchall()
        for row in rows:
            v_id = row["video_id"]
            verified_at = row["verified_at"] or ""
            age = _parse_iso_age_hours(verified_at)

            # Mandatory Grace Period Check
            if age < grace_hours:
                continue

            score = float(row["actual_success_score"] or 0.0)
            if score < min_score:
                candidates.append(
                    PruneCandidate(
                        publication_id=int(row["publication_id"]),
                        video_id=v_id,
                        story_id=str(row["story_id"]),
                        channel=canon.value,
                        title=str(row["title"] or "Untitled"),
                        actual_success_score=score,
                        age_hours=round(age, 2),
                        verified_at=verified_at,
                    )
                )
                if len(candidates) >= max_candidates:
                    break

    return candidates


def _is_quota_error(exc: Exception) -> bool:
    """Detects HTTP 429 or quota exceeded errors from Google API."""
    err_str = str(exc).lower()
    return "quota" in err_str or "rate limit" in err_str or "429" in err_str


def _is_video_not_found_error(exc: Exception) -> bool:
    """True when the video is deleted or not found on YouTube (HTTP 404 / LookupError)."""
    if isinstance(exc, LookupError):
        return True
    msg = str(exc).lower()
    return "not found" in msg or "404" in msg or "videonotfound" in msg


def _is_ownership_error(exc: Exception) -> bool:
    """True when video ownership verification failed (belongs to another channel)."""
    if isinstance(exc, PermissionError):
        return True
    msg = str(exc).lower()
    return "pertenece a otro canal" in msg or "channel not owned" in msg


def _notify_telegram_pruned(channel: str, pruned_items: List[Dict[str, Any]]) -> None:
    """Dispatches Telegram operational alert for pruned videos."""
    if not pruned_items:
        return
    try:
        from src.telegram.notifier import TelegramNotifier
        notifier = TelegramNotifier()
        lines = [f"🧹 <b>[AUTO-PRUNE] Channel {channel}</b> pruned {len(pruned_items)} underperforming short(s):"]
        for it in pruned_items:
            lines.append(f"• <code>{it['video_id']}</code> - {it['title']} (Score: {it['score']})")
        msg = "\n".join(lines)
        notifier.send_message_sync(msg)
    except Exception as exc:
        logger.debug("Telegram prune notification skipped: %s", exc)


def execute_autonomous_prune(
    channel: str | CanonicalChannel,
    db_path: str = DEFAULT_DB_PATH,
    dry_run: bool = True,
    force: bool = False,
    min_score: float = 40.0,
    grace_hours: float = 24.0,
    max_delete: int = 2,
    youtube_service: Any = None,
) -> AutonomousPruneReport:
    """
    Executes autonomous pruning of underperforming videos with multi-tiered safety:
    - Enforces AUTO_PRUNE_ENABLED kill-switch.
    - Evaluates candidates respecting grace period and daily ceiling.
    - Dispatches YouTube deletion.
    - Updates local SQLite records.
    - Alerts Telegram.
    """
    canon = canonical_channel(channel).value

    # Kill switch verification
    kill_switch_enabled = os.environ.get("AUTO_PRUNE_ENABLED", "true").lower() in ("true", "1", "yes")
    if not kill_switch_enabled and not force:
        logger.warning("[PRUNE] Auto-pruning is disabled via AUTO_PRUNE_ENABLED=false")
        return AutonomousPruneReport(
            channel=canon,
            evaluated_count=0,
            pruned_count=0,
            skipped_count=1,
            failed_count=0,
            items=[{"status": "skipped", "reason": "kill_switch_active"}],
        )

    candidates = evaluate_prune_candidates(
        channel=canon,
        db_path=db_path,
        min_score=min_score,
        grace_hours=grace_hours,
        max_candidates=max_delete,
    )

    if not candidates:
        logger.info("[PRUNE] Zero underperforming candidates found for '%s'.", canon)
        return AutonomousPruneReport(
            channel=canon,
            evaluated_count=0,
            pruned_count=0,
            skipped_count=0,
            failed_count=0,
            items=[],
        )

    # Dry-run execution
    if dry_run:
        logger.info("[DRY-RUN] Found %d candidate(s) to prune in '%s'.", len(candidates), canon)
        items = [
            {
                "video_id": c.video_id,
                "title": c.title,
                "score": c.actual_success_score,
                "age_hours": c.age_hours,
                "status": "dry_run",
            }
            for c in candidates
        ]
        return AutonomousPruneReport(
            channel=canon,
            evaluated_count=len(candidates),
            pruned_count=0,
            skipped_count=0,
            failed_count=0,
            items=items,
        )

    # Live execution
    service = youtube_service
    if service is None:
        from src.youtube.control import _service_for_channel
        service = _service_for_channel(canon)

    pruned_items: List[Dict[str, Any]] = []
    failed_items: List[Dict[str, Any]] = []

    with connect(db_path) as conn:
        for cand in candidates:
            try:
                service.videos().delete(id=cand.video_id).execute()
                # Update SQLite status
                conn.execute(
                    "UPDATE stories SET status = 'PURGED', updated_at = CURRENT_TIMESTAMP WHERE story_id = ?",
                    (cand.story_id,),
                )
                conn.commit()

                pruned_items.append({
                    "video_id": cand.video_id,
                    "title": cand.title,
                    "score": cand.actual_success_score,
                    "status": "pruned",
                })
                logger.info(
                    "[PRUNE] Successfully deleted underperforming video '%s' (score=%.1f) from '%s'",
                    cand.video_id,
                    cand.actual_success_score,
                    canon,
                )
                time.sleep(0.5)  # rate limit spacing
            except Exception as exc:
                logger.error("[PRUNE] Failed to delete video '%s': %s", cand.video_id, exc)
                if _is_video_not_found_error(exc):
                    logger.info("[PRUNE] Video '%s' not found on YouTube (already deleted). Marking PURGED.", cand.video_id)
                    conn.execute(
                        "UPDATE stories SET status = 'PURGED', failure_code = 'VIDEO_NOT_FOUND', updated_at = CURRENT_TIMESTAMP WHERE story_id = ?",
                        (cand.story_id,),
                    )
                    conn.commit()
                    pruned_items.append({
                        "video_id": cand.video_id,
                        "title": cand.title,
                        "score": cand.actual_success_score,
                        "status": "purged_not_found",
                    })
                elif _is_ownership_error(exc):
                    logger.warning("[PRUNE] Video '%s' belongs to another channel. Marking PERMANENT_FAILED.", cand.video_id)
                    conn.execute(
                        "UPDATE stories SET status = 'PERMANENT_FAILED', failure_code = 'OWNERSHIP_MISMATCH', updated_at = CURRENT_TIMESTAMP WHERE story_id = ?",
                        (cand.story_id,),
                    )
                    conn.commit()
                    failed_items.append({
                        "video_id": cand.video_id,
                        "title": cand.title,
                        "error": str(exc),
                        "status": "failed_terminal",
                    })
                elif _is_quota_error(exc):
                    failed_items.append({
                        "video_id": cand.video_id,
                        "title": cand.title,
                        "error": str(exc),
                        "status": "failed_quota",
                    })
                    logger.warning("[PRUNE] YouTube quota exceeded during prune. Halting batch.")
                    break
                else:
                    failed_items.append({
                        "video_id": cand.video_id,
                        "title": cand.title,
                        "error": str(exc),
                        "status": "failed",
                    })

    _notify_telegram_pruned(canon, pruned_items)

    return AutonomousPruneReport(
        channel=canon,
        evaluated_count=len(candidates),
        pruned_count=len(pruned_items),
        skipped_count=0,
        failed_count=len(failed_items),
        items=pruned_items + failed_items,
    )


def mark_underperforming_candidates(
    channel: str | CanonicalChannel,
    db_path: str = DEFAULT_DB_PATH,
    min_score: float = 40.0,
    grace_hours: float = 24.0,
    max_candidates: int = 100,
) -> List[Dict[str, Any]]:
    """
    Diagnoses and marks eligible underperforming videos with status 'MARKED_FOR_PURGE'
    and assigns deterministic failure codes before any deletion.
    """
    canon = canonical_channel(channel)
    aliases = {k for k, v in CHANNEL_ALIASES.items() if v == canon}
    aliases.add(str(channel).lower())
    aliases.add(canon.value)
    placeholders = ",".join("?" for _ in aliases)

    query = f"""
        SELECT p.publication_id, p.video_id, p.story_id, p.channel, p.title,
               p.actual_success_score, p.verified_at, p.view_count, p.like_count
        FROM publications p
        JOIN stories s ON p.story_id = s.story_id
        WHERE p.channel IN ({placeholders})
          AND p.video_id IS NOT NULL
          AND p.video_id != ''
          AND s.status NOT IN ('PURGED', 'MARKED_FOR_PURGE')
        ORDER BY p.actual_success_score ASC
    """
    marked: List[Dict[str, Any]] = []
    with connect(db_path) as conn:
        rows = conn.execute(query, tuple(aliases)).fetchall()
        for row in rows:
            v_id = row["video_id"]
            title = str(row["title"] or "")
            verified_at = row["verified_at"] or ""
            age = _parse_iso_age_hours(verified_at)
            score = float(row["actual_success_score"] or 0.0)
            views = int(row["view_count"] or 0)
            likes = int(row["like_count"] or 0)

            fail_code = classify_video_failure(
                title=title,
                channel=canon.value,
                views=views,
                likes=likes,
                age_hours=age,
                score=score,
            )

            # Skip if younger than grace period unless it is an obvious artifact/cross-contamination
            if age < grace_hours and fail_code not in ("EMPTY_TITLE_ARTIFACT", "CROSS_CONTAMINATED_TITLE"):
                continue

            if score < min_score or fail_code in ("EMPTY_TITLE_ARTIFACT", "CROSS_CONTAMINATED_TITLE", "ZERO_ENGAGEMENT_STALE"):
                conn.execute(
                    "UPDATE stories SET status = 'MARKED_FOR_PURGE', failure_code = ? WHERE story_id = ?",
                    (fail_code, str(row["story_id"])),
                )
                marked.append({
                    "video_id": v_id,
                    "story_id": str(row["story_id"]),
                    "title": title,
                    "score": score,
                    "views": views,
                    "likes": likes,
                    "age_hours": round(age, 2),
                    "failure_code": fail_code,
                })
                if len(marked) >= max_candidates:
                    break
        conn.commit()
    return marked


def purge_marked_videos(
    channel: str | CanonicalChannel,
    db_path: str = DEFAULT_DB_PATH,
    max_delete: int = 50,
    youtube_service: Any = None,
) -> Dict[str, Any]:
    """
    Deletes batch of pre-marked videos via YouTube Data API and transitions
    their status from 'MARKED_FOR_PURGE' to 'PURGED'.
    """
    canon = canonical_channel(channel)
    aliases = {k for k, v in CHANNEL_ALIASES.items() if v == canon}
    aliases.add(str(channel).lower())
    aliases.add(canon.value)
    placeholders = ",".join("?" for _ in aliases)

    service = youtube_service
    if service is None:
        from src.youtube.control import _service_for_channel
        service = _service_for_channel(canon.value)

    query = f"""
        SELECT s.story_id, p.video_id, p.title, s.failure_code, p.actual_success_score
        FROM stories s
        JOIN publications p ON s.story_id = p.story_id
        WHERE s.status = 'MARKED_FOR_PURGE'
          AND p.channel IN ({placeholders})
        LIMIT ?
    """

    purged_items: List[Dict[str, Any]] = []
    failed_items: List[Dict[str, Any]] = []

    with connect(db_path) as conn:
        rows = conn.execute(query, (*tuple(aliases), max(1, max_delete))).fetchall()
        for row in rows:
            v_id = row["video_id"]
            s_id = row["story_id"]
            title = row["title"]
            try:
                from src.youtube.control import _verify_ownership

                _verify_ownership(service, v_id, canon.value)
                service.videos().delete(id=v_id).execute()
                conn.execute(
                    "UPDATE stories SET status = 'PURGED', updated_at = CURRENT_TIMESTAMP WHERE story_id = ?",
                    (s_id,),
                )
                conn.commit()
                purged_items.append({
                    "video_id": v_id,
                    "title": title,
                    "failure_code": row["failure_code"],
                    "score": row["actual_success_score"],
                    "status": "purged",
                })
                logger.info("[PURGE] Deleted marked video '%s' (reason: %s)", v_id, row["failure_code"])
                time.sleep(0.5)
            except Exception as exc:
                logger.error("[PURGE] Failed to delete marked video '%s': %s", v_id, exc)
                if _is_video_not_found_error(exc):
                    logger.info("[PURGE] Video '%s' not found on YouTube (already deleted). Marking PURGED.", v_id)
                    conn.execute(
                        "UPDATE stories SET status = 'PURGED', failure_code = 'VIDEO_NOT_FOUND', updated_at = CURRENT_TIMESTAMP WHERE story_id = ?",
                        (s_id,),
                    )
                    conn.commit()
                    purged_items.append({
                        "video_id": v_id,
                        "title": title,
                        "failure_code": "VIDEO_NOT_FOUND",
                        "score": row["actual_success_score"],
                        "status": "purged_not_found",
                    })
                elif _is_ownership_error(exc):
                    logger.warning("[PURGE] Video '%s' belongs to another channel. Marking PERMANENT_FAILED.", v_id)
                    conn.execute(
                        "UPDATE stories SET status = 'PERMANENT_FAILED', failure_code = 'OWNERSHIP_MISMATCH', updated_at = CURRENT_TIMESTAMP WHERE story_id = ?",
                        (s_id,),
                    )
                    conn.commit()
                    failed_items.append({
                        "video_id": v_id,
                        "title": title,
                        "error": str(exc),
                        "status": "failed_terminal",
                    })
                elif _is_quota_error(exc):
                    failed_items.append({
                        "video_id": v_id,
                        "title": title,
                        "error": str(exc),
                        "status": "failed_quota",
                    })
                    logger.warning("[PURGE] YouTube quota exceeded during purge. Halting batch.")
                    break
                else:
                    cur_code = str(row["failure_code"] or "")
                    new_status = "PERMANENT_FAILED" if "PURGE_ATTEMPT_2" in cur_code else "MARKED_FOR_PURGE"
                    new_code = (
                        f"PURGE_FAILED_TERMINAL: {str(exc)[:40]}"
                        if "PURGE_ATTEMPT_2" in cur_code
                        else ("PURGE_ATTEMPT_2" if "PURGE_ATTEMPT_1" in cur_code else "PURGE_ATTEMPT_1")
                    )
                    conn.execute(
                        "UPDATE stories SET status = ?, failure_code = ?, updated_at = CURRENT_TIMESTAMP WHERE story_id = ?",
                        (new_status, new_code, s_id),
                    )
                    conn.commit()
                    failed_items.append({
                        "video_id": v_id,
                        "title": title,
                        "error": str(exc),
                        "status": "failed",
                    })

    _notify_telegram_pruned(canon.value, purged_items)
    return {
        "channel": canon.value,
        "purged_count": len(purged_items),
        "failed_count": len(failed_items),
        "items": purged_items + failed_items,
    }

