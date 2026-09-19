"""src/scrapers/scp - SCP Foundation Wiki & Crom API Scraper package."""

from __future__ import annotations

import logging

from src.scrapers.scp.canonical import CANONICAL_SCP_STORIES
from src.scrapers.scp.client import (
    _CROM_RATE_LIMITER,
    _WIKIDOT_RATE_LIMITER,
    async_fetch_scp_by_item,
    async_fetch_top_scp_articles,
    async_fetch_top_scp_from_crom,
    fetch_scp_by_item,
    fetch_top_scp_articles,
    fetch_top_scp_from_crom,
)
from src.scrapers.scp.constants import (
    CROM_GRAPHQL_ENDPOINT,
    DEFAULT_LICENSE,
    DEFAULT_USER_AGENT,
    SCP_WIKI_BASE_URL,
    SCP_WIKI_ES_BASE_URL,
)
from src.scrapers.scp.enqueue import (
    async_scrape_and_enqueue_scp,
    scrape_and_enqueue_scp,
)
from src.scrapers.scp.parser import (
    _WikidotHTMLCleaner,
    parse_scp_text,
    parse_scp_wikidot_html,
)

logger = logging.getLogger("scraper_scp")

__all__ = [
    "DEFAULT_LICENSE",
    "DEFAULT_USER_AGENT",
    "CROM_GRAPHQL_ENDPOINT",
    "SCP_WIKI_BASE_URL",
    "SCP_WIKI_ES_BASE_URL",
    "CANONICAL_SCP_STORIES",
    "_WikidotHTMLCleaner",
    "parse_scp_text",
    "parse_scp_wikidot_html",
    "_CROM_RATE_LIMITER",
    "_WIKIDOT_RATE_LIMITER",
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
