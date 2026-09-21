"""src/scraper.py - Reddit & Multi-Source Narrative Scraper.

Backward-compatible facade delegating execution to the modular src.scrapers package.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.branding import resolve_channel_key
from src.scrapers import (
    CHANNEL_SUBREDDITS,
    DEFAULT_USER_AGENT,
    PRESET_CANONICAL_STORIES,
    USER_AGENTS,
    _LANE_REPLENISH_BACKOFF,
    _PULLPUSH_LIMITER,
    _REDDIT_LIMITER,
    _async_backoff_sleep,
    _env_min_score,
    _env_min_upvote_ratio,
    _extract_posts_from_json,
    _fetch_url_aiohttp,
    _fetch_url_mocked_requests,
    _is_deleted_or_removed,
    _is_mocked_requests,
    _load_canonical_stories,
    _parse_frontmatter,
    _run_sync,
    _to_float,
    _to_int,
    async_ensure_queue_depth,
    async_fetch_reddit_stories,
    async_replenish_queue,
    ensure_queue_depth,
    fetch_reddit_stories,
    is_high_quality_story,
    replenish_queue,
)
from src.scrapers.common import AsyncRateLimiter
from src.scrapers.models import ScrapedStory

logger = logging.getLogger("scraper")

__all__ = [
    "DEFAULT_USER_AGENT",
    "USER_AGENTS",
    "CHANNEL_SUBREDDITS",
    "ScrapedStory",
    "_run_sync",
    "_to_int",
    "_to_float",
    "_env_min_score",
    "_env_min_upvote_ratio",
    "_is_mocked_requests",
    "AsyncRateLimiter",
    "_REDDIT_LIMITER",
    "_PULLPUSH_LIMITER",
    "_async_backoff_sleep",
    "_parse_frontmatter",
    "PRESET_CANONICAL_STORIES",
    "_load_canonical_stories",
    "_is_deleted_or_removed",
    "is_high_quality_story",
    "_extract_posts_from_json",
    "_fetch_url_aiohttp",
    "_fetch_url_mocked_requests",
    "async_fetch_reddit_stories",
    "fetch_reddit_stories",
    "async_replenish_queue",
    "replenish_queue",
    "_LANE_REPLENISH_BACKOFF",
    "async_ensure_queue_depth",
    "ensure_queue_depth",
    "resolve_channel_key",
    "Path",
    "logger",
]
