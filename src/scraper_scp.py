"""src/scraper_scp.py - SCP Foundation Wiki & Crom API Scraper.

Backward-compatible facade delegating execution to the modular src.scrapers.scp package.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.scrapers import (
    CANONICAL_SCP_STORIES,
    CROM_GRAPHQL_ENDPOINT,
    DEFAULT_LICENSE,
    DEFAULT_USER_AGENT,
    SCP_WIKI_BASE_URL,
    SCP_WIKI_ES_BASE_URL,
    AsyncRateLimiter,
    ScrapedStory,
    _CROM_RATE_LIMITER,
    _WIKIDOT_RATE_LIMITER,
    _WikidotHTMLCleaner,
    _async_backoff_sleep,
    _run_sync,
    _to_int,
    async_fetch_scp_by_item,
    async_fetch_top_scp_articles,
    async_fetch_top_scp_from_crom,
    async_scrape_and_enqueue_scp,
    fetch_scp_by_item,
    fetch_top_scp_articles,
    fetch_top_scp_from_crom,
    parse_scp_text,
    parse_scp_wikidot_html,
    scrape_and_enqueue_scp,
)
from src.scrapers.common import (
    _is_mocked_requests_get,
    _is_mocked_requests_post,
)

logger = logging.getLogger("scraper_scp")

__all__ = [
    "DEFAULT_LICENSE",
    "DEFAULT_USER_AGENT",
    "CROM_GRAPHQL_ENDPOINT",
    "SCP_WIKI_BASE_URL",
    "SCP_WIKI_ES_BASE_URL",
    "CANONICAL_SCP_STORIES",
    "ScrapedStory",
    "_run_sync",
    "_to_int",
    "_is_mocked_requests_get",
    "_is_mocked_requests_post",
    "AsyncRateLimiter",
    "_CROM_RATE_LIMITER",
    "_WIKIDOT_RATE_LIMITER",
    "_async_backoff_sleep",
    "_WikidotHTMLCleaner",
    "parse_scp_text",
    "parse_scp_wikidot_html",
    "async_fetch_top_scp_from_crom",
    "fetch_top_scp_from_crom",
    "async_fetch_scp_by_item",
    "fetch_scp_by_item",
    "async_fetch_top_scp_articles",
    "fetch_top_scp_articles",
    "async_scrape_and_enqueue_scp",
    "scrape_and_enqueue_scp",
    "logger",
]
