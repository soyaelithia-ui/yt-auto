"""Quota domain engine for LLM token burn and YouTube Data API v3 consumption.

Tracks multi-provider daily token budgets, YouTube 10,000 daily quota units
(resetting at 08:00 UTC / 00:00 PST), channel daily upload limits, and
quota saturation backoff recommendation states.
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import DEFAULT_DB_PATH
from src.core.domain import CanonicalChannel
from src.core.repository.queue import (
    TokenBurnSummary,
    connect,
)

logger = logging.getLogger(__name__)

# Canonical quota unit costs according to YouTube Data API v3
DEFAULT_YOUTUBE_DAILY_BUDGET: int = 10_000
YOUTUBE_UPLOAD_COST_UNITS: int = 1_600
YOUTUBE_THUMBNAIL_COST_UNITS: int = 50
YOUTUBE_METADATA_COST_UNITS: int = 50

# Rolling token budget heuristics per provider (tokens/day)
PROVIDER_DAILY_TOKEN_BUDGETS: dict[str, int] = {
    "antigravity_pro": 2_000_000,
    "gemini_rest": 1_000_000,
    "grok": 500_000,
    "edge_tts": 1_000_000,
    "elevenlabs": 100_000,
    "kokoro": 2_000_000,
}


@dataclass(frozen=True)
class YouTubeQuotaMetrics:
    daily_budget_units: int  # 10,000
    estimated_consumed_units: int
    remaining_quota_units: int
    estimated_remaining_uploads: int
    quota_cycle_reset_utc: str
    channel_daily_uploads: dict[str, int]
    staged_drafts_count: int
    staged_unlisted_count: int
    unconfirmed_uploads_count: int
    quota_status: str  # "OK" | "WARNING" | "EXHAUSTED"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)


def get_next_youtube_reset_utc(now: datetime | None = None) -> datetime:
    """Calculate the next 08:00 UTC YouTube Data API quota reset cycle."""
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    today_reset = now.replace(hour=8, minute=0, second=0, microsecond=0)
    if now < today_reset:
        return today_reset
    return today_reset + timedelta(days=1)


def get_current_youtube_cycle_start_utc(now: datetime | None = None) -> datetime:
    """Calculate the start timestamp of the active 08:00 UTC quota cycle."""
    next_reset = get_next_youtube_reset_utc(now)
    return next_reset - timedelta(days=1)


class QuotaMonitor:
    """Monitors token burn rates, YouTube quotas, and saturation conditions."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        env_db = os.environ.get("DEFAULT_DB_PATH")
        self.db_path = Path(db_path) if db_path is not None else (Path(env_db) if env_db else Path(DEFAULT_DB_PATH))
        from src.core.repository import QueueRepository

        self.repo = QueueRepository(self.db_path)

    def get_next_youtube_reset_utc(self) -> str:
        """Return ISO-8601 UTC string for next YouTube quota reset."""
        return get_next_youtube_reset_utc().isoformat()

    def get_youtube_quota_metrics(
        self, channel: str | CanonicalChannel | None = None
    ) -> YouTubeQuotaMetrics:
        """Calculate YouTube Data API v3 consumption for the current 08:00 UTC cycle."""
        channel_key = channel.value if isinstance(channel, CanonicalChannel) else channel
        now = datetime.now(timezone.utc)
        cycle_start = get_current_youtube_cycle_start_utc(now)
        cycle_start_iso = cycle_start.isoformat(timespec="seconds")
        next_reset_iso = get_next_youtube_reset_utc(now).isoformat()

        daily_budget = DEFAULT_YOUTUBE_DAILY_BUDGET
        consumed_units = 0
        channel_daily_uploads: dict[str, int] = {}
        staged_drafts = 0
        staged_unlisted = 0
        unconfirmed_uploads = 0
        quota_exceeded_events = 0

        try:
            with connect(self.db_path, read_only=True) as conn:
                # 1. Query publications since cycle start
                pub_clauses = ["verified_at >= ?"]
                pub_params: list[Any] = [cycle_start_iso]
                if channel_key:
                    pub_clauses.append("channel = ?")
                    pub_params.append(channel_key)

                rows = conn.execute(
                    f"""
                    SELECT channel, visibility, thumbnail_confirmed, COUNT(*) as cnt
                    FROM publications
                    WHERE {' AND '.join(pub_clauses)}
                    GROUP BY channel, visibility, thumbnail_confirmed
                    """,
                    tuple(pub_params),
                ).fetchall()

                for r in rows:
                    ch = str(r["channel"])
                    cnt = int(r["cnt"])
                    vis = str(r["visibility"]).lower()
                    thumb_conf = bool(r["thumbnail_confirmed"])

                    channel_daily_uploads[ch] = channel_daily_uploads.get(ch, 0) + cnt
                    # Upload (1600) + Metadata (50) + Optional Thumbnail (50)
                    units_per_pub = YOUTUBE_UPLOAD_COST_UNITS + YOUTUBE_METADATA_COST_UNITS
                    if thumb_conf:
                        units_per_pub += YOUTUBE_THUMBNAIL_COST_UNITS
                    consumed_units += cnt * units_per_pub

                    if vis == "draft":
                        staged_drafts += cnt
                    elif vis == "unlisted":
                        staged_unlisted += cnt

                # 2. Query stories for staged drafts or waiting statuses
                story_clauses = [
                    "status IN ('upload_unconfirmed', 'waiting_youtube_limit', 'UPLOAD_UNCONFIRMED', 'WAITING_YOUTUBE_LIMIT')"
                ]
                story_params: list[Any] = []
                if channel_key:
                    story_clauses.append("channel = ?")
                    story_params.append(channel_key)

                story_rows = conn.execute(
                    f"""
                    SELECT status, COUNT(*) as cnt
                    FROM stories
                    WHERE {' AND '.join(story_clauses)}
                    GROUP BY status
                    """,
                    tuple(story_params),
                ).fetchall()

                for sr in story_rows:
                    st = str(sr["status"]).upper()
                    cnt = int(sr["cnt"])
                    if st == "UPLOAD_UNCONFIRMED":
                        unconfirmed_uploads += cnt
                    elif st == "WAITING_YOUTUBE_LIMIT":
                        quota_exceeded_events += cnt

                # 3. Check for youtube_quota_limit events during the cycle
                ev_clauses = ["ts >= ?", "event_type = 'youtube_quota_limit'"]
                ev_params: list[Any] = [cycle_start_iso]
                if channel_key:
                    ev_clauses.append("channel = ?")
                    ev_params.append(channel_key)

                ev_row = conn.execute(
                    f"""
                    SELECT COUNT(*) as cnt
                    FROM system_events
                    WHERE {' AND '.join(ev_clauses)}
                    """,
                    tuple(ev_params),
                ).fetchone()
                if ev_row and ev_row["cnt"] > 0:
                    quota_exceeded_events += int(ev_row["cnt"])

        except Exception as exc:
            logger.debug("Failed to query YouTube quota metrics: %s", exc)

        remaining_units = max(0, daily_budget - consumed_units)
        remaining_uploads = remaining_units // YOUTUBE_UPLOAD_COST_UNITS

        if quota_exceeded_events > 0 or remaining_units <= 0:
            status = "EXHAUSTED"
        elif remaining_units <= 2000 or (remaining_units / daily_budget) <= 0.20:
            status = "WARNING"
        else:
            status = "OK"

        return YouTubeQuotaMetrics(
            daily_budget_units=daily_budget,
            estimated_consumed_units=consumed_units,
            remaining_quota_units=remaining_units,
            estimated_remaining_uploads=remaining_uploads,
            quota_cycle_reset_utc=next_reset_iso,
            channel_daily_uploads=channel_daily_uploads,
            staged_drafts_count=staged_drafts,
            staged_unlisted_count=staged_unlisted,
            unconfirmed_uploads_count=unconfirmed_uploads,
            quota_status=status,
        )

    def get_token_burn_summary(
        self,
        window_hours: int = 24,
        channel: str | CanonicalChannel | None = None,
        provider: str | None = None,
    ) -> TokenBurnSummary:
        """Aggregate token burn and USD cost metrics over the specified window."""
        return self.repo.query_token_burn_summary(
            window_hours=window_hours,
            channel=channel,
            provider=provider,
        )

    def detect_saturation_state(self) -> dict[str, Any]:
        """Detect quota saturation conditions across LLM, TTS, and YouTube publishing."""
        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(hours=2)).isoformat(timespec="seconds")

        waiting_llm = 0
        waiting_image = 0
        waiting_youtube = 0
        upload_unconfirmed = 0
        active_backoffs: list[dict[str, Any]] = []

        try:
            with connect(self.db_path, read_only=True) as conn:
                rows = conn.execute(
                    """
                    SELECT status, channel, story_id, next_attempt_at, last_error
                    FROM stories
                    WHERE status IN (
                        'waiting_llm_quota', 'waiting_image_quota', 'waiting_youtube_limit', 'upload_unconfirmed',
                        'WAITING_LLM_QUOTA', 'WAITING_IMAGE_QUOTA', 'WAITING_YOUTUBE_LIMIT', 'UPLOAD_UNCONFIRMED'
                    )
                    """
                ).fetchall()

                for r in rows:
                    st = r["status"]
                    st_upper = str(st).upper()
                    if st_upper == "WAITING_LLM_QUOTA":
                        waiting_llm += 1
                    elif st_upper == "WAITING_IMAGE_QUOTA":
                        waiting_image += 1
                    elif st_upper == "WAITING_YOUTUBE_LIMIT":
                        waiting_youtube += 1
                    elif st_upper == "UPLOAD_UNCONFIRMED":
                        upload_unconfirmed += 1

                    active_backoffs.append(
                        {
                            "channel": r["channel"],
                            "story_id": r["story_id"],
                            "status": st,
                            "next_attempt_at": r["next_attempt_at"],
                            "error": r["last_error"],
                        }
                    )

                # Check recent system_events for saturation
                sat_rows = conn.execute(
                    """
                    SELECT event_type, channel, details_json, ts
                    FROM system_events
                    WHERE ts >= ? AND event_type IN ('quota_saturation', 'youtube_quota_limit')
                    ORDER BY ts DESC LIMIT 10
                    """,
                    (cutoff,),
                ).fetchall()

                saturated = (
                    waiting_llm > 0
                    or waiting_image > 0
                    or waiting_youtube > 0
                    or len(sat_rows) > 0
                )

        except Exception as exc:
            logger.debug("Failed to detect saturation state: %s", exc)
            saturated = False

        return {
            "saturated": saturated,
            "waiting_llm_quota_count": waiting_llm,
            "waiting_image_quota_count": waiting_image,
            "waiting_youtube_limit_count": waiting_youtube,
            "upload_unconfirmed_count": upload_unconfirmed,
            "active_backoffs": active_backoffs,
        }
