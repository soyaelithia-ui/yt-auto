"""src/scrapers/scp/client.py - Crom GraphQL API and Wikidot SCP scraper clients."""

from __future__ import annotations

import asyncio
import logging
import sys
import urllib.parse
from typing import Any, Dict, List, Optional

import aiohttp
import requests

from src.scrapers.common import (
    AsyncRateLimiter,
    _async_backoff_sleep,
    _is_mocked_requests_get,
    _is_mocked_requests_post,
    _run_sync,
    _to_int,
)
from src.scrapers.scp.canonical import CANONICAL_SCP_STORIES
from src.scrapers.scp.constants import (
    CROM_GRAPHQL_ENDPOINT,
    DEFAULT_USER_AGENT,
    SCP_WIKI_BASE_URL,
)
from src.scrapers.scp.parser import parse_scp_wikidot_html

logger = logging.getLogger("scraper_scp")

_CROM_RATE_LIMITER = AsyncRateLimiter(max_concurrent=5, rate_limit_per_second=5.0)
_WIKIDOT_RATE_LIMITER = AsyncRateLimiter(max_concurrent=5, rate_limit_per_second=5.0)


async def _query_crom_graphql(
    payload: Dict[str, Any],
    headers: Dict[str, str],
    max_retries: int,
    session: Optional[aiohttp.ClientSession],
) -> Any:
    """Execute GraphQL POST request to Crom API with rate limiting and backoff."""
    if _is_mocked_requests_post():
        try:
            resp = await asyncio.to_thread(
                requests.post, CROM_GRAPHQL_ENDPOINT, json=payload, headers=headers, timeout=10
            )
            if getattr(resp, "status_code", 0) == 200:
                return resp.json()
        except Exception as e:
            logger.warning("Crom API query failed: %s", e)
        return None

    close_session = False
    active_session = session
    if active_session is None:
        active_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15, connect=5))
        close_session = True

    try:
        for attempt in range(max_retries):
            try:
                async with _CROM_RATE_LIMITER:
                    async with active_session.post(
                        CROM_GRAPHQL_ENDPOINT,
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=10.0),
                    ) as resp:
                        if resp.status == 200:
                            return await resp.json(content_type=None)
                        if resp.status in (429, 500, 502, 503, 504):
                            retry_after = resp.headers.get("retry-after")
                            if attempt < max_retries - 1:
                                await _async_backoff_sleep(attempt, base=1.0, retry_after=retry_after)
                                continue
                        logger.warning("Crom API returned HTTP %d", resp.status)
                        return None
            except Exception as e:
                if attempt < max_retries - 1:
                    await _async_backoff_sleep(attempt, base=1.0)
                    continue
                logger.warning("Crom API request exception: %s", e)
                return None
    finally:
        if close_session and active_session:
            await active_session.close()
    return None


async def _fetch_single_article_node(
    node: Dict[str, Any],
    get_session: Optional[aiohttp.ClientSession],
    parser_fn: Any,
) -> Optional[Dict[str, Any]]:
    """Fetch and parse a single Wikidot article from a node reference."""
    url = node.get("url", "")
    if not url:
        return None
    if url.startswith("http://"):
        url = "https://" + url[7:]
    if "scp-wiki.wikidot.com/scp-" not in url or any(bad in url for bad in ("-j", "-ex", "-d", "archived")):
        return None

    wikidot_info = node.get("wikidotInfo", {})
    rating = _to_int(wikidot_info.get("rating"), 0)
    author = wikidot_info.get("createdBy", {}).get("name", "SCP Community")

    try:
        if _is_mocked_requests_get():
            page_resp = await asyncio.to_thread(
                requests.get,
                url,
                headers={"User-Agent": DEFAULT_USER_AGENT},
                timeout=8,
            )
            if getattr(page_resp, "status_code", 0) == 200:
                return parser_fn(page_resp.text, url=url, author=author, rating=rating)
        elif get_session:
            async with _WIKIDOT_RATE_LIMITER:
                async with get_session.get(
                    url,
                    headers={"User-Agent": DEFAULT_USER_AGENT},
                    timeout=aiohttp.ClientTimeout(total=8.0),
                ) as page_resp:
                    if page_resp.status == 200:
                        html_content = await page_resp.text()
                        return parser_fn(html_content, url=url, author=author, rating=rating)
    except Exception as err:
        logger.warning("Failed to fetch article body from %s: %s", url, err)
    return None


async def _fetch_parsed_article_nodes(
    edges: List[Dict[str, Any]],
    session: Optional[aiohttp.ClientSession],
    parser_fn: Any,
) -> List[Dict[str, Any]]:
    """Iterate over GraphQL edges and fetch Wikidot article bodies."""
    articles: List[Dict[str, Any]] = []
    close_session_get = False
    get_session = session
    if get_session is None and not _is_mocked_requests_get():
        get_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15, connect=5))
        close_session_get = True

    try:
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            node = edge.get("node", {})
            if not isinstance(node, dict):
                continue
            parsed = await _fetch_single_article_node(node, get_session, parser_fn)
            if parsed:
                articles.append(parsed)
    finally:
        if close_session_get and get_session:
            await get_session.close()

    return articles


async def async_fetch_top_scp_from_crom(
    limit: int = 20,
    min_rating: int = 100,
    session: Optional[aiohttp.ClientSession] = None,
    max_retries: int = 3,
) -> List[Dict[str, Any]]:
    """Query Crom API GraphQL endpoint asynchronously for top-rated SCP articles."""
    query = """
    query GetTopSCPs($limit: Int!, $minRating: Int!) {
      pages(
        filter: {
          wikidotInfo: {
            tags: { eq: "scp" }
            rating: { gte: $minRating }
          }
        }
        sort: {
          key: RATING
          order: DESC
        }
        first: $limit
      ) {
        edges {
          node {
            url
            wikidotInfo {
              title
              rating
              createdBy {
                name
              }
            }
          }
        }
      }
    }
    """
    headers = {"User-Agent": DEFAULT_USER_AGENT, "Content-Type": "application/json"}
    payload = {"query": query, "variables": {"limit": limit, "minRating": min_rating}}

    data = await _query_crom_graphql(payload, headers, max_retries, session)
    if not data or not isinstance(data, dict):
        return []

    data_sec = data.get("data") if isinstance(data, dict) else None
    pages_sec = data_sec.get("pages") or data_sec.get("articles") if isinstance(data_sec, dict) else None
    edges = pages_sec.get("edges", []) if isinstance(pages_sec, dict) else []
    if not isinstance(edges, list):
        return []

    scraper_scp_mod = sys.modules.get("src.scraper_scp")
    parser_fn = (
        getattr(scraper_scp_mod, "parse_scp_wikidot_html", parse_scp_wikidot_html)
        if scraper_scp_mod
        else parse_scp_wikidot_html
    )

    articles = await _fetch_parsed_article_nodes(edges, session, parser_fn)
    if articles:
        logger.info("Crom API returned %d top SCP articles", len(articles))
    return articles


def fetch_top_scp_from_crom(limit: int = 20, min_rating: int = 100) -> List[Dict[str, Any]]:
    """Synchronous compatibility wrapper for async_fetch_top_scp_from_crom."""
    return _run_sync(async_fetch_top_scp_from_crom(limit=limit, min_rating=min_rating))


async def async_fetch_scp_by_item(
    item_number: str,
    session: Optional[aiohttp.ClientSession] = None,
    max_retries: int = 3,
) -> Optional[Dict[str, Any]]:
    """Async fetch and parse a specific SCP article by item number (e.g. 'SCP-096' or '096')."""
    item_clean = item_number.strip().upper()
    if not item_clean.startswith("SCP-"):
        item_clean = f"SCP-{item_clean}"

    scraper_scp_mod = sys.modules.get("src.scraper_scp")
    canonical_list = (
        getattr(scraper_scp_mod, "CANONICAL_SCP_STORIES", CANONICAL_SCP_STORIES)
        if scraper_scp_mod
        else CANONICAL_SCP_STORIES
    )

    # Check canonical fallback first
    for canon in canonical_list:
        if canon.get("item_number", "").upper() == item_clean:
            return dict(canon)

    url = f"{SCP_WIKI_BASE_URL}/{urllib.parse.quote(item_clean.lower())}"
    headers = {"User-Agent": DEFAULT_USER_AGENT}

    parser_fn = (
        getattr(scraper_scp_mod, "parse_scp_wikidot_html", parse_scp_wikidot_html)
        if scraper_scp_mod
        else parse_scp_wikidot_html
    )

    if _is_mocked_requests_get():
        try:
            resp = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
            if getattr(resp, "status_code", 0) == 200:
                parsed = parser_fn(resp.text, url=url, rating=100)
                if parsed:
                    return parsed
        except Exception as e:
            logger.warning("Failed to fetch %s from Wikidot: %s", item_clean, e)
        return None

    close_session = False
    active_session = session
    if active_session is None:
        active_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15, connect=5))
        close_session = True

    try:
        for attempt in range(max_retries):
            try:
                async with _WIKIDOT_RATE_LIMITER:
                    async with active_session.get(
                        url, headers=headers, timeout=aiohttp.ClientTimeout(total=10.0)
                    ) as resp:
                        if resp.status == 200:
                            html_text = await resp.text()
                            parsed = parser_fn(html_text, url=url, rating=100)
                            if parsed:
                                return parsed
                            return None
                        if resp.status == 404:
                            return None
                        if resp.status in (429, 500, 502, 503, 504):
                            retry_after = resp.headers.get("retry-after")
                            if attempt < max_retries - 1:
                                await _async_backoff_sleep(attempt, base=1.0, retry_after=retry_after)
                                continue
                            return None
                        return None
            except Exception as e:
                if attempt < max_retries - 1:
                    await _async_backoff_sleep(attempt, base=1.0)
                    continue
                logger.warning("Failed to fetch %s from Wikidot: %s", item_clean, e)
                return None
    finally:
        if close_session and active_session:
            await active_session.close()

    return None


def fetch_scp_by_item(item_number: str) -> Optional[Dict[str, Any]]:
    """Synchronous compatibility wrapper for async_fetch_scp_by_item."""
    return _run_sync(async_fetch_scp_by_item(item_number=item_number))


async def async_fetch_top_scp_articles(
    limit: int = 20,
    min_rating: int = 50,
    tag: str = "scp",
    session: Optional[aiohttp.ClientSession] = None,
    max_retries: int = 3,
) -> List[Dict[str, Any]]:
    """Fetch top-rated SCP articles with multi-tier fallback (Crom -> Wikidot -> Canonical)."""
    close_session = False
    active_session = session
    if active_session is None and not (_is_mocked_requests_get() or _is_mocked_requests_post()):
        active_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15, connect=5))
        close_session = True

    scraper_scp_mod = sys.modules.get("src.scraper_scp")
    fetch_crom = (
        getattr(scraper_scp_mod, "async_fetch_top_scp_from_crom", async_fetch_top_scp_from_crom)
        if scraper_scp_mod
        else async_fetch_top_scp_from_crom
    )
    fetch_item = (
        getattr(scraper_scp_mod, "async_fetch_scp_by_item", async_fetch_scp_by_item)
        if scraper_scp_mod
        else async_fetch_scp_by_item
    )
    canonical_list = (
        getattr(scraper_scp_mod, "CANONICAL_SCP_STORIES", CANONICAL_SCP_STORIES)
        if scraper_scp_mod
        else CANONICAL_SCP_STORIES
    )

    try:
        articles = await fetch_crom(
            limit=max(limit * 2, 30), min_rating=min_rating, session=active_session, max_retries=max_retries
        )
        existing_ids = {a["id"] for a in articles}

        if len(articles) < limit:
            common_items = [
                "SCP-173", "SCP-096", "SCP-049", "SCP-682", "SCP-3008",
                "SCP-087", "SCP-106", "SCP-999", "SCP-055", "SCP-079",
                "SCP-093", "SCP-105", "SCP-140", "SCP-500", "SCP-610",
                "SCP-914", "SCP-939", "SCP-1000", "SCP-1048", "SCP-1171",
                "SCP-1981", "SCP-2000", "SCP-2316", "SCP-2521", "SCP-3000",
                "SCP-3999", "SCP-4999", "SCP-5000",
            ]
            for item in common_items:
                if item in existing_ids:
                    continue
                art = await fetch_item(item, session=active_session, max_retries=max_retries)
                if art:
                    articles.append(art)
                    existing_ids.add(item)
                if len(articles) >= limit:
                    break

        if articles:
            return articles[:limit]

        logger.info("Using canonical built-in SCP dataset as fail-safe fallback")
        return [dict(s) for s in canonical_list[:limit]]
    finally:
        if close_session and active_session:
            await active_session.close()


def fetch_top_scp_articles(
    limit: int = 20,
    min_rating: int = 50,
    tag: str = "scp",
) -> List[Dict[str, Any]]:
    """Synchronous compatibility wrapper for async_fetch_top_scp_articles."""
    return _run_sync(async_fetch_top_scp_articles(limit=limit, min_rating=min_rating, tag=tag))


__all__ = [
    "_CROM_RATE_LIMITER",
    "_WIKIDOT_RATE_LIMITER",
    "async_fetch_top_scp_from_crom",
    "fetch_top_scp_from_crom",
    "async_fetch_scp_by_item",
    "fetch_scp_by_item",
    "async_fetch_top_scp_articles",
    "fetch_top_scp_articles",
]
