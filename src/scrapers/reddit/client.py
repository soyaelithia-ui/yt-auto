"""src/scrapers/reddit/client.py - Async/sync Reddit and PullPush HTTP API client."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import requests

from src.scrapers.common import (
    AsyncRateLimiter,
    _async_backoff_sleep,
    _is_mocked_requests,
    _run_sync,
    _to_float,
    _to_int,
)
from src.scrapers.local.loader import _load_canonical_stories
from src.scrapers.reddit.constants import DEFAULT_USER_AGENT
from src.scrapers.reddit.quality import (
    _env_min_score,
    _env_min_upvote_ratio,
    _is_deleted_or_removed,
    is_high_quality_story,
)

logger = logging.getLogger("scraper")

_REDDIT_LIMITER = AsyncRateLimiter(max_concurrent=5, rate_limit_per_second=5.0)
_PULLPUSH_LIMITER = AsyncRateLimiter(max_concurrent=5, rate_limit_per_second=5.0)


def _extract_posts_from_json(data: Any) -> List[Dict[str, Any]]:
    """Extract post dicts from Reddit or PullPush JSON payloads."""
    if not data or not isinstance(data, dict):
        return []
    items: List[Dict[str, Any]] = []
    if "data" in data and isinstance(data["data"], dict) and "children" in data["data"]:
        children = data["data"].get("children", [])
        if isinstance(children, list):
            for child in children:
                if isinstance(child, dict) and "data" in child and isinstance(child["data"], dict):
                    items.append(child["data"])
    elif "data" in data and isinstance(data["data"], list):
        for item in data["data"]:
            if isinstance(item, dict):
                items.append(item)
    return items


async def _fetch_url_aiohttp(
    url: str,
    headers: Dict[str, str],
    session: aiohttp.ClientSession,
    timeout_sec: float = 10.0,
) -> Tuple[int, Any, Dict[str, str]]:
    """Fetch URL asynchronously via aiohttp, returning (status_code, data, headers)."""
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout_sec)) as resp:
            status = resp.status
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
            try:
                data = await resp.json(content_type=None)
            except Exception:
                text = await resp.text()
                try:
                    data = json.loads(text)
                except Exception:
                    data = text
            return status, data, resp_headers
    except Exception as err:
        logger.warning("aiohttp request error for %s: %s", url, err)
        return 0, None, {}


async def _fetch_url_mocked_requests(
    url: str,
    headers: Dict[str, str],
    timeout_sec: float = 10.0,
) -> Tuple[int, Any, Dict[str, str]]:
    """Execute via requests in threadpool when requests.get is mocked in tests."""
    try:
        resp = await asyncio.to_thread(requests.get, url, headers=headers, timeout=timeout_sec)
        status = getattr(resp, "status_code", 200)
        resp_headers = {k.lower(): v for k, v in getattr(resp, "headers", {}).items()}
        try:
            data = resp.json()
        except Exception:
            data = getattr(resp, "text", "")
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except Exception:
                    pass
        return status, data, resp_headers
    except Exception as err:
        logger.warning("requests exception for %s: %s", url, err)
        return 0, None, {}


async def _execute_reddit_direct(
    reddit_url: str,
    headers: Dict[str, str],
    active_session: Any,
    max_retries: int,
    subreddit: str,
) -> Tuple[Any, bool, bool]:
    """Execute Tier-1 direct Reddit API requests with retries and backoff.

    Returns (data, use_pullpush, reddit_failed).
    """
    scraper_mod = sys.modules.get("src.scraper")
    fetch_aio = getattr(scraper_mod, "_fetch_url_aiohttp", _fetch_url_aiohttp) if scraper_mod else _fetch_url_aiohttp
    backoff = getattr(scraper_mod, "_async_backoff_sleep", _async_backoff_sleep) if scraper_mod else _async_backoff_sleep

    data = None
    use_pullpush = False
    reddit_failed = False

    for attempt in range(max_retries):
        if _is_mocked_requests():
            status, resp_data, resp_headers = await _fetch_url_mocked_requests(reddit_url, headers=headers)
        else:
            async with _REDDIT_LIMITER:
                status, resp_data, resp_headers = await fetch_aio(
                    reddit_url, headers=headers, session=active_session, timeout_sec=10.0
                )

        if status == 200 and resp_data:
            data = resp_data
            break
        if status in (403, 404):
            logger.warning("Reddit API returned status %d for r/%s, activating PullPush fallback...", status, subreddit)
            reddit_failed = True
            use_pullpush = True
            break
        if status == 429:
            reddit_failed = True
            retry_after = resp_headers.get("retry-after")
            if attempt < max_retries - 1:
                logger.warning("Reddit API rate limited (429) on attempt %d, applying backoff...", attempt + 1)
                await backoff(attempt, base=1.0, retry_after=retry_after)
                continue
            logger.warning("Reddit API 429 retries exhausted, activating PullPush fallback...")
            use_pullpush = True
            break
        if status >= 500 or status == 0:
            reddit_failed = True
            if attempt < max_retries - 1:
                logger.warning("Reddit API error (%d) on attempt %d, retrying with backoff...", status, attempt + 1)
                await backoff(attempt, base=1.0)
                continue
            logger.warning("Reddit API request failed (%d), activating PullPush fallback...", status)
            use_pullpush = True
            break

        logger.warning("Reddit API returned unexpected status %d, activating PullPush fallback...", status)
        reddit_failed = True
        use_pullpush = True
        break

    return data, use_pullpush, reddit_failed


async def _execute_pullpush_fallback(
    pullpush_url: str,
    headers: Dict[str, str],
    active_session: Any,
    max_retries: int,
    subreddit: str,
) -> Tuple[Any, bool, bool]:
    """Execute Tier-2 PullPush fallback requests with retries.

    Returns (data, is_404, pullpush_failed).
    """
    scraper_mod = sys.modules.get("src.scraper")
    fetch_aio = getattr(scraper_mod, "_fetch_url_aiohttp", _fetch_url_aiohttp) if scraper_mod else _fetch_url_aiohttp
    backoff = getattr(scraper_mod, "_async_backoff_sleep", _async_backoff_sleep) if scraper_mod else _async_backoff_sleep

    data = None
    is_404 = False
    pullpush_failed = False

    for attempt in range(max_retries):
        if _is_mocked_requests():
            pp_status, pp_data, _ = await _fetch_url_mocked_requests(pullpush_url, headers=headers)
        else:
            async with _PULLPUSH_LIMITER:
                pp_status, pp_data, _ = await fetch_aio(
                    pullpush_url, headers=headers, session=active_session, timeout_sec=10.0
                )

        if pp_status == 200 and pp_data:
            data = pp_data
            logger.info("PullPush fallback fetch successful")
            break
        if pp_status == 404:
            logger.warning("PullPush API returned status 404 for r/%s", subreddit)
            is_404 = True
            pullpush_failed = True
            break
        if pp_status == 429:
            logger.warning("PullPush API rate limited (429) for r/%s, skipping retries...", subreddit)
            pullpush_failed = True
            break
        if pp_status in (500, 502, 503, 504, 0):
            if attempt < max_retries - 1:
                await backoff(attempt, base=1.0)
                continue
            logger.warning("PullPush API failed with status %d", pp_status)
            pullpush_failed = True
            break

        logger.warning("PullPush API returned status %d", pp_status)
        pullpush_failed = True
        break

    return data, is_404, pullpush_failed


def _parse_and_filter_stories(items: List[Dict[str, Any]], min_length: int) -> List[Dict[str, Any]]:
    """Parse raw post items, filtering deleted/low quality/low score items."""
    scraper_mod = sys.modules.get("src.scraper")
    quality_fn = getattr(scraper_mod, "is_high_quality_story", is_high_quality_story) if scraper_mod else is_high_quality_story

    stories: List[Dict[str, Any]] = []
    for post in items:
        if not isinstance(post, dict):
            continue
        if post.get("stickied") is True or post.get("pinned") is True:
            continue
        if post.get("over_18") is True or post.get("nsfw") is True:
            continue

        post_id = str(post.get("id", "") or "").strip()
        title = str(post.get("title", "") or "").strip()
        selftext = str(post.get("selftext", "") or post.get("body", "") or "").strip()
        author = str(post.get("author", "") or "").strip()
        score = _to_int(post.get("score"), 0)
        upvote_ratio = _to_float(post.get("upvote_ratio"), 0.0)
        num_comments = _to_int(post.get("num_comments"), 0)

        if not post_id or not title or not selftext:
            continue
        if _is_deleted_or_removed(selftext) or _is_deleted_or_removed(title) or _is_deleted_or_removed(author):
            continue
        if len(selftext) < min_length:
            continue
        if not quality_fn(title, selftext, min_length=min_length):
            continue
        if score < _env_min_score():
            logger.info("Skipping post '%s' (score %d < REDDIT_MIN_SCORE)", title[:50], score)
            continue
        if upvote_ratio < _env_min_upvote_ratio():
            logger.info("Skipping post '%s' (upvote_ratio %.2f < REDDIT_MIN_UPVOTE_RATIO)", title[:50], upvote_ratio)
            continue

        permalink = post.get("permalink", "")
        full_link = post.get("full_link", "") or post.get("url", "")
        if permalink and permalink.startswith("/"):
            url = f"https://www.reddit.com{permalink}"
        elif full_link and full_link.startswith("http"):
            url = full_link
        else:
            url = f"https://reddit.com/comments/{post_id}"

        stories.append({
            "id": post_id,
            "title": title,
            "content": selftext,
            "url": url,
            "score": score,
            "upvote_ratio": upvote_ratio,
            "num_comments": num_comments,
        })
    return stories


async def async_fetch_reddit_stories(
    subreddit: str = "nosleep",
    limit: int = 50,
    user_agent: str = DEFAULT_USER_AGENT,
    min_length: int = 10,
    sort: str = "hot",
    time_filter: str = "week",
    after: Optional[str] = None,
    session: Optional[aiohttp.ClientSession] = None,
    max_retries: int = 3,
) -> List[Dict[str, Any]]:
    """Asynchronously fetch posts from Reddit or PullPush with fallback to local canonical stories."""
    url_params = f"limit={limit}"
    if sort in ("top", "controversial"):
        url_params += f"&t={time_filter}"
    if after:
        url_params += f"&after={after}"

    sub_quoted = urllib.parse.quote(str(subreddit).strip())
    reddit_url = f"https://www.reddit.com/r/{sub_quoted}/{sort}.json?{url_params}"
    pullpush_url = f"https://api.pullpush.io/reddit/search/submission/?subreddit={sub_quoted}&size={limit}"
    headers = {"User-Agent": user_agent}

    logger.info("Fetching Reddit stories from r/%s (sort=%s, t=%s)...", subreddit, sort, time_filter)

    close_session = False
    active_session = session
    if active_session is None and not _is_mocked_requests():
        active_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15, connect=5))
        close_session = True

    try:
        data, use_pullpush, reddit_failed = await _execute_reddit_direct(
            reddit_url, headers, active_session, max_retries, subreddit
        )
        is_404 = False
        pullpush_failed = False
        if use_pullpush:
            data, is_404, pullpush_failed = await _execute_pullpush_fallback(
                pullpush_url, headers, active_session, max_retries, subreddit
            )
    finally:
        if close_session and active_session:
            await active_session.close()

    items = _extract_posts_from_json(data)
    stories = _parse_and_filter_stories(items, min_length)

    if not stories:
        reddit_failed = True

    if not stories and not is_404:
        if reddit_failed and (not use_pullpush or pullpush_failed):
            logger.warning(
                "Reddit and PullPush scrapers returned 0 valid stories for r/%s. Activating local canonical workset fallback...",
                subreddit,
            )
            scraper_mod = sys.modules.get("src.scraper")
            load_fn = (
                getattr(scraper_mod, "_load_canonical_stories", _load_canonical_stories)
                if scraper_mod
                else _load_canonical_stories
            )
            stories = load_fn(subreddit=subreddit, limit=limit, min_length=min_length)

    logger.info("Fetched and filtered %d high-quality stories from r/%s", len(stories), subreddit)
    return stories


def fetch_reddit_stories(
    subreddit: str = "nosleep",
    limit: int = 50,
    user_agent: str = DEFAULT_USER_AGENT,
    min_length: int = 10,
    sort: str = "hot",
    time_filter: str = "week",
    after: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Synchronous compatibility wrapper for async_fetch_reddit_stories."""
    return _run_sync(
        async_fetch_reddit_stories(
            subreddit=subreddit,
            limit=limit,
            user_agent=user_agent,
            min_length=min_length,
            sort=sort,
            time_filter=time_filter,
            after=after,
        )
    )


__all__ = [
    "_REDDIT_LIMITER",
    "_PULLPUSH_LIMITER",
    "_extract_posts_from_json",
    "_fetch_url_aiohttp",
    "_fetch_url_mocked_requests",
    "async_fetch_reddit_stories",
    "fetch_reddit_stories",
]
