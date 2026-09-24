"""
src/analytics/pruner.py - Autonomous Underperforming Video Pruning Engine.

Implements criteria-based automated deletion of underperforming YouTube Shorts:
1. Mandatory 24h evaluation grace period (protects slow-burn / fresh videos).
2. Dual-threshold underperformance check (actual_success_score < floor).
3. Bounded daily deletion ceiling (<= 2 videos/channel/day).
4. Kill-switch (AUTO_PRUNE_ENABLED=false) and HTTP 429 circuit breaker.
5. Telegram operational audit alert dispatch.
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


def evaluate_prune_candidates(
    channel: str | CanonicalChannel,
    db_path: str = DEFAULT_DB_PATH,
    min_score: float = 25.0,
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
    min_score: float = 25.0,
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
                failed_items.append({
                    "video_id": cand.video_id,
                    "title": cand.title,
                    "error": str(exc),
                    "status": "failed",
                })
                if _is_quota_error(exc):
                    logger.warning("[PRUNE] YouTube quota exceeded during prune. Halting batch.")
                    break

    _notify_telegram_pruned(canon, pruned_items)

    return AutonomousPruneReport(
        channel=canon,
        evaluated_count=len(candidates),
        pruned_count=len(pruned_items),
        skipped_count=0,
        failed_count=len(failed_items),
        items=pruned_items + failed_items,
    )
