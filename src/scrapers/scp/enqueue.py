"""src/scrapers/scp/enqueue.py - Ingest and enqueue SCP articles into the SQLite repository."""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Optional

import aiohttp

from src.scrapers.common import _run_sync
from src.scrapers.scp.client import async_fetch_top_scp_articles
from src.scrapers.scp.constants import DEFAULT_LICENSE

logger = logging.getLogger("scraper_scp")


async def async_scrape_and_enqueue_scp(
    limit: int = 10,
    db_path: Optional[str] = None,
    lane_id: str = "horror-scp-shorts",
    channel: str = "horror",
    session: Optional[aiohttp.ClientSession] = None,
) -> int:
    """Scrape SCP articles and enqueue them with CC BY-SA 3.0 license attribution asynchronously."""
    from src.config import DEFAULT_DB_PATH
    from src.db import enqueue_story, is_story_duplicate, is_story_processed

    path = db_path or DEFAULT_DB_PATH
    scraper_scp_mod = sys.modules.get("src.scraper_scp")
    fetch_top_fn = (
        getattr(scraper_scp_mod, "async_fetch_top_scp_articles", async_fetch_top_scp_articles)
        if scraper_scp_mod
        else async_fetch_top_scp_articles
    )

    articles = await fetch_top_fn(limit=max(limit * 4, 100), session=session)
    enqueued = 0

    for art in articles:
        if enqueued >= limit:
            break
        story_id = art["id"]
        title = art["title"]
        content = art["content"]
        url = art["url"]
        rating = int(art.get("score", 0) or 0)
        license_meta = art.get("source_license", DEFAULT_LICENSE)

        is_proc = await asyncio.to_thread(is_story_processed, story_id, db_path=path)
        if is_proc:
            continue
        is_dup = await asyncio.to_thread(is_story_duplicate, channel, title, content, db_path=path)
        if is_dup:
            continue

        ok = await asyncio.to_thread(
            enqueue_story,
            story_id=story_id,
            title=title,
            content=content,
            url=url,
            channel=channel,
            score=rating,
            lane_id=lane_id,
            source_license=license_meta,
            db_path=path,
        )
        if ok:
            enqueued += 1

    logger.info("Enqueued %d SCP stories into queue for lane [%s]", enqueued, lane_id)
    return enqueued


def scrape_and_enqueue_scp(
    limit: int = 10,
    db_path: Optional[str] = None,
    lane_id: str = "horror-scp-shorts",
    channel: str = "horror",
) -> int:
    """Synchronous compatibility wrapper for async_scrape_and_enqueue_scp."""
    return _run_sync(
        async_scrape_and_enqueue_scp(limit=limit, db_path=db_path, lane_id=lane_id, channel=channel)
    )


__all__ = [
    "async_scrape_and_enqueue_scp",
    "scrape_and_enqueue_scp",
]
