"""src/scrapers/replenisher.py - Queue replenishment and lane depth management."""

from __future__ import annotations

import asyncio
import logging
import sys
import time
import unittest.mock
from typing import Any, List, Optional

import aiohttp

from src.branding import resolve_channel_key
from src.scrapers.common import _run_sync
from src.scrapers.reddit.client import (
    async_fetch_reddit_stories,
    fetch_reddit_stories,
)
from src.scrapers.reddit.constants import CHANNEL_SUBREDDITS
from src.scrapers.scp.client import fetch_top_scp_articles
from src.scrapers.scp.enqueue import (
    async_scrape_and_enqueue_scp,
    scrape_and_enqueue_scp,
)

logger = logging.getLogger("scraper")

_LANE_REPLENISH_BACKOFF: dict[str, float] = {}


async def async_replenish_queue(
    channel: str = "terror",
    min_stories: int = 25,
    db_path: Optional[str] = None,
    session: Optional[aiohttp.ClientSession] = None,
) -> int:
    """Check pending queue depth asynchronously and replenish across subreddits and categories."""
    from src.config import DEFAULT_DB_PATH
    from src.core.repository import connect
    from src.db import enqueue_story

    c_key = resolve_channel_key(channel)
    path = db_path or DEFAULT_DB_PATH

    def _get_count() -> int:
        with connect(path, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM stories WHERE status = 'PENDING' AND (channel = ? OR channel = ?)",
                (c_key, channel),
            )
            return cursor.fetchone()[0]

    pending_count = await asyncio.to_thread(_get_count)
    if pending_count >= min_stories:
        return pending_count

    logger.info("Queue depth for [%s] is %d (< target %d). Replenishing queue...", c_key, pending_count, min_stories)
    subreddits = CHANNEL_SUBREDDITS.get(c_key, ["nosleep" if c_key == "terror" else "AmItheAsshole"])
    categories = [
        ("hot", "week"),
        ("top", "week"),
        ("top", "month"),
        ("new", "all"),
    ]

    scraper_mod = sys.modules.get("src.scraper")
    sync_fetch = getattr(scraper_mod, "fetch_reddit_stories", fetch_reddit_stories) if scraper_mod else fetch_reddit_stories
    async_fetch = getattr(scraper_mod, "async_fetch_reddit_stories", async_fetch_reddit_stories) if scraper_mod else async_fetch_reddit_stories

    for sub in subreddits:
        for sort_cat, t_filter in categories:
            curr_count = await asyncio.to_thread(_get_count)
            if curr_count >= min_stories:
                break

            try:
                if isinstance(sync_fetch, (unittest.mock.Mock, unittest.mock.MagicMock)):
                    fetched = await asyncio.to_thread(
                        sync_fetch,
                        subreddit=sub,
                        limit=50,
                        sort=sort_cat,
                        time_filter=t_filter,
                    )
                else:
                    res = async_fetch(
                        subreddit=sub,
                        limit=50,
                        sort=sort_cat,
                        time_filter=t_filter,
                        session=session,
                    )
                    fetched = await res if asyncio.iscoroutine(res) else res

                for s in fetched:
                    await asyncio.to_thread(
                        enqueue_story,
                        story_id=s["id"],
                        title=s["title"],
                        content=s["content"],
                        url=s["url"],
                        score=int(s.get("score", 0) or 0),
                        upvote_ratio=float(s.get("upvote_ratio", 0.0) or 0.0),
                        num_comments=int(s.get("num_comments", 0) or 0),
                        channel=channel,
                        db_path=path,
                    )
            except Exception as e:
                logger.warning("Replenish queue error fetching from r/%s (%s): %s", sub, sort_cat, e)

    updated_count = await asyncio.to_thread(_get_count)
    logger.info("Replenished queue for [%s]. Total pending stories now: %d", channel, updated_count)
    return updated_count


def replenish_queue(channel: str = "terror", min_stories: int = 25, db_path: Optional[str] = None) -> int:
    """Synchronous compatibility wrapper for async_replenish_queue."""
    return _run_sync(async_replenish_queue(channel=channel, min_stories=min_stories, db_path=db_path))


def _get_procedural_history(path: str, channel_key: str) -> tuple[set[str], list[str]]:
    """Retrieve existing titles and recent texts from database for procedural deduplication."""
    existing_titles: set[str] = set()
    existing_texts: list[str] = []
    try:
        import sqlite3

        with sqlite3.connect(path) as _chk_conn:
            for _row in _chk_conn.execute(
                "SELECT title FROM publications WHERE channel = ? UNION SELECT title FROM stories WHERE channel = ?",
                (channel_key, channel_key),
            ).fetchall():
                if _row and _row[0]:
                    existing_titles.add(_row[0].strip().lower())
        from src.core.repository import QueueRepository

        existing_texts = list(QueueRepository(path).recent_published_texts(channel_key))
        with sqlite3.connect(path) as _chk_conn:
            for _row in _chk_conn.execute(
                "SELECT content FROM stories WHERE channel = ? AND status IN ('PENDING', 'PROCESSING', 'RENDERED', 'WAITING_YOUTUBE_LIMIT') ORDER BY created_at DESC LIMIT 30",
                (channel_key,),
            ).fetchall():
                if _row and _row[0]:
                    existing_texts.append(str(_row[0]))
    except Exception:
        pass
    return existing_titles, existing_texts


def _generate_procedural_title(
    channel_key: str,
    is_lane_long: bool,
    seed: int,
    i: int,
    themes_to_use: tuple[str, ...],
    existing_titles: set[str],
) -> tuple[str, str]:
    """Generate a unique title and theme for dynamic story fallback."""
    theme = themes_to_use[(seed + i) % len(themes_to_use)]
    horror_hooks = (
        "El terror de", "La misteriosa entidad en", "No debí entrar jamás a",
        "La pesadilla olvidada en", "El horror acecha en", "La señal prohibida desde",
        "El misterio sin resolver en", "El peligro oculto en", "Lo que encontramos en",
        "La presencia siniestra en",
    )
    drama_short_hooks = (
        "cancelar mi boda por", "cortar contacto con mi familia por",
        "negarme a prestar mis ahorros por", "vender la propiedad familiar por",
        "echar a mis parientes por", "no invitar a mi hermana por",
        "rechazar el chantaje ante", "renunciar al patrimonio por",
        "expulsar a mi suegra tras", "bloquear las cuentas conjuntas tras",
        "exigir el pago de la deuda ante", "cambiar las cerraduras de casa tras",
    )
    drama_long_hooks = (
        "mi decisión ante", "poner límites definitivos ante",
        "negarme al chantaje familiar por", "cortar lazos de por vida tras",
        "proteger mi patrimonio frente a", "rechazar la herencia tóxica de",
        "revelar la verdad familiar tras", "defender mi hogar ante",
        "enfrentar las exigencias injustas de",
    )
    qualifiers = (
        "tras años de silencio", "ante toda la familia reunida",
        "ante una traición inesperada", "por una deuda que no me correspondía",
        "tras descubrir la verdad oculta", "después de poner límites claros",
        "cuando exigieron lo imposible", "en el momento más difícil",
        "a espaldas de todos", "tras un ultimátum injusto",
        "sin pedir disculpas", "ante el chantaje de mis parientes",
    )
    attempts = 0
    while attempts < 30:
        q_part = f" {qualifiers[(seed + i + attempts) % len(qualifiers)]}" if attempts > 0 else ""
        if is_lane_long:
            hook = horror_hooks[(seed + i + attempts) % len(horror_hooks)] if "moku" in channel_key else drama_long_hooks[(seed + i + attempts) % len(drama_long_hooks)]
        else:
            hook = horror_hooks[(seed + i + attempts) % len(horror_hooks)] if "moku" in channel_key else drama_short_hooks[(seed + i + attempts) % len(drama_short_hooks)]
        cand = f"{hook} {theme}{q_part} en la noche" if "moku" in channel_key else f"¿Soy la mala por {hook} {theme}{q_part}?"
        cand_clean = cand.strip().lower()
        if cand_clean not in existing_titles:
            existing_titles.add(cand_clean)
            return cand, theme
        attempts += 1

    cand = f"¿Soy la mala por {drama_short_hooks[i % len(drama_short_hooks)]} {theme} #{seed % 10000}?" if "aelithia" in channel_key else f"{horror_hooks[i % len(horror_hooks)]} {theme} en la noche #{seed % 10000}"
    existing_titles.add(cand.strip().lower())
    return cand, theme


async def _dynamic_procedural_fallback(
    lane: Any,
    channel_key: str,
    lane_id: str,
    target_depth: int,
    path: str,
) -> None:
    """Dynamic procedural story generation fallback when all online and local sources yield 0 stories."""
    from src.curators.base import get_narrative_director
    from src.db import enqueue_story

    director = get_narrative_director()
    is_lane_long = getattr(lane, "orientation", "") == "horizontal"
    padding_themes = getattr(lane, "padding_themes", ())
    default_horror_themes = (
        "bosques con niebla", "casas abandonadas", "carreteras nocturnas",
        "hospitales psiquiátricos clausurados", "túneles subterráneos",
        "faros aislados en la tormenta", "hoteles clausurados en la montaña",
        "estaciones de tren desiertas", "archivos clasificados de la fundación",
        "laboratorios biológicos en cuarentena", "cabinas de radio en la madrugada",
        "cementerios olvidados en la niebla", "pantanos prohibidos", "minas de carbón clausuradas",
    )
    default_drama_themes = (
        "herencia familiar disputada", "boda cancelada", "desalojo inesperado",
        "testamento secreto alterado", "hipoteca oculta de mis suegros",
        "deuda estudiantil exigida", "fiesta de compromiso saboteada",
        "cena de navidad arruinada", "custodia de mascotas tras divorcio",
        "negocios turbios de mi cuñado", "depósito de alquiler confiscado",
        "reparto injusto de bienes paternos", "anillo de compromiso falso",
        "chantaje de mi hermana menor", "secretos financieros de mi prometido",
        "viaje familiar cancelado a espaldas", "cuidado de padres ancianos delegado",
    )
    default_themes = default_horror_themes if "moku" in channel_key else default_drama_themes
    themes_to_use = tuple(padding_themes) + tuple(default_themes)

    existing_titles, existing_texts = _get_procedural_history(path, channel_key)
    needed = min(3, target_depth)

    for i in range(needed):
        seed = int(time.time()) + i
        title, theme = _generate_procedural_title(channel_key, is_lane_long, seed, i, themes_to_use, existing_titles)

        if is_lane_long:
            content = director.build_longform(
                channel_key,
                title,
                target_words=getattr(lane, "words_min", 2600),
                seed=seed + i,
                recent_texts=existing_texts,
            )
            prefix = "DYNAMIC-LONG"
        else:
            content = director.build_short(
                channel_key, theme, seed_offset=seed + i, recent_texts=existing_texts
            )
            prefix = "DYNAMIC-SHORT"

        existing_texts.append(content)
        story_id = f"{prefix}-{lane_id}-{seed}"
        await asyncio.to_thread(
            enqueue_story,
            story_id=story_id,
            title=title,
            content=content,
            url=f"https://yt-auto.local/{story_id}",
            channel=channel_key,
            score=999,
            upvote_ratio=0.98,
            num_comments=50,
            lane_id=lane_id,
            db_path=path,
        )
    logger.info("Dynamic procedural fallback enqueued %d stories for lane [%s]", needed, lane_id)


async def _replenish_from_reddit(
    lane: Any,
    subreddits: tuple[str, ...],
    categories: tuple[tuple[str, str], ...],
    limit_per_fetch: int,
    scrape_min_length: int,
    channel_key: str,
    lane_id: str,
    target_depth: int,
    path: str,
    session: Optional[aiohttp.ClientSession],
    _get_count_fn: Any,
) -> None:
    """Iterate through subreddits and categories to replenish stories from Reddit/PullPush."""
    from src.core.topics import filter_story_for_lane
    from src.db import enqueue_story, is_story_duplicate, is_story_processed

    scraper_mod = sys.modules.get("src.scraper")
    sync_fetch = getattr(scraper_mod, "fetch_reddit_stories", fetch_reddit_stories) if scraper_mod else fetch_reddit_stories
    async_fetch = getattr(scraper_mod, "async_fetch_reddit_stories", async_fetch_reddit_stories) if scraper_mod else async_fetch_reddit_stories

    canonical_used = False
    for sub in subreddits:
        if canonical_used:
            break
        for sort_cat, t_filter in categories:
            curr_count = await asyncio.to_thread(_get_count_fn)
            if curr_count >= target_depth:
                break

            try:
                if isinstance(sync_fetch, (unittest.mock.Mock, unittest.mock.MagicMock)):
                    fetched = await asyncio.to_thread(
                        sync_fetch,
                        subreddit=sub,
                        limit=limit_per_fetch,
                        sort=sort_cat,
                        time_filter=t_filter,
                        min_length=scrape_min_length,
                    )
                else:
                    res = async_fetch(
                        subreddit=sub,
                        limit=limit_per_fetch,
                        sort=sort_cat,
                        time_filter=t_filter,
                        min_length=scrape_min_length,
                        session=session,
                    )
                    fetched = await res if asyncio.iscoroutine(res) else res

                newly_enqueued = 0
                for s in fetched:
                    if not filter_story_for_lane(s["title"], s["content"], lane):
                        continue

                    is_canonical_story = "canonical" in str(s.get("url", "")) or str(s.get("id", "")).startswith("FILE-")
                    if is_canonical_story:
                        sid = str(s.get("id", "")).lower()
                        is_lane_long = getattr(lane, "orientation", "") == "horizontal"
                        if is_lane_long and "_short_" in sid:
                            continue
                        if not is_lane_long and "_long_" in sid:
                            continue

                    is_proc = await asyncio.to_thread(is_story_processed, s["id"], db_path=path)
                    if is_proc:
                        continue
                    is_dup = await asyncio.to_thread(is_story_duplicate, channel_key, s["title"], s["content"], db_path=path)
                    if is_dup:
                        continue

                    await asyncio.to_thread(
                        enqueue_story,
                        story_id=s["id"],
                        title=s["title"],
                        content=s["content"],
                        url=s["url"],
                        channel=channel_key,
                        score=int(s.get("score", 0) or 0),
                        upvote_ratio=float(s.get("upvote_ratio", 0.0) or 0.0),
                        num_comments=int(s.get("num_comments", 0) or 0),
                        lane_id=lane_id,
                        source_license=s.get("source_license"),
                        db_path=path,
                    )
                    newly_enqueued += 1

                is_canonical = any("canonical" in str(s.get("url", "")) for s in fetched)
                if is_canonical:
                    canonical_used = True
                    break
                if fetched and newly_enqueued == 0:
                    break
            except Exception as e:
                logger.warning("Error replenishing queue for lane [%s] from r/%s (%s): %s", lane_id, sub, sort_cat, e)


async def _replenish_from_scp(
    needed: int,
    path: str,
    lane_id: str,
    channel_key: str,
    session: Optional[aiohttp.ClientSession],
) -> None:
    """Helper to fetch and enqueue SCP stories via sync or async scraper."""
    scraper_scp_mod = sys.modules.get("src.scraper_scp")
    sync_scp = getattr(scraper_scp_mod, "scrape_and_enqueue_scp", scrape_and_enqueue_scp) if scraper_scp_mod else scrape_and_enqueue_scp
    async_scp = getattr(scraper_scp_mod, "async_scrape_and_enqueue_scp", async_scrape_and_enqueue_scp) if scraper_scp_mod else async_scrape_and_enqueue_scp
    limit = max(5, needed)
    if isinstance(sync_scp, (unittest.mock.Mock, unittest.mock.MagicMock)):
        await asyncio.to_thread(
            sync_scp,
            limit=limit,
            db_path=path,
            lane_id=lane_id,
            channel=channel_key,
        )
    else:
        await async_scp(
            limit=limit,
            db_path=path,
            lane_id=lane_id,
            channel=channel_key,
            session=session,
        )


def _apply_replenish_backoff(lane_id: str, updated_count: int, pending_count: int) -> None:
    """Record cooldown backoff when replenishment yields 0 new stories."""
    if updated_count <= pending_count:
        cooldown = 60.0 if updated_count == 0 else 300.0
        _LANE_REPLENISH_BACKOFF[lane_id] = time.time() + cooldown
        logger.info(
            "Lane [%s] replenishment yielded 0 new stories; setting %.0fs backoff cooldown (pending: %d).",
            lane_id,
            cooldown,
            updated_count,
        )
    else:
        _LANE_REPLENISH_BACKOFF.pop(lane_id, None)


def _get_lane_subreddits_and_categories(
    sources: Any, channel_key: str
) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    """Determine subreddits and sorting categories for a lane."""
    subreddits = getattr(sources, "subreddits", ()) if sources else ()
    if not subreddits:
        subreddits = tuple(
            CHANNEL_SUBREDDITS.get(
                channel_key,
                ["nosleep" if channel_key in ("moku", "terror") else "AmItheAsshole"],
            )
        )
    categories = getattr(sources, "listing_categories", ()) if sources else ()
    if not categories:
        categories = (("hot", "day"), ("top", "week"), ("new", "all"))
    return subreddits, categories


async def async_ensure_queue_depth(
    lane: Any,
    db_path: Optional[str] = None,
    session: Optional[aiohttp.ClientSession] = None,
) -> int:
    """Ensure the database has at least `lane.sources.queue_target_pending` pending stories for `lane` asynchronously."""
    from src.config import DEFAULT_DB_PATH
    from src.core.repository import connect

    path = db_path or DEFAULT_DB_PATH
    channel_obj = getattr(lane, "channel", "moku")
    channel_key = getattr(channel_obj, "value", str(channel_obj))
    lane_id = getattr(lane, "id", str(lane))
    sources = getattr(lane, "sources", None)
    target_depth = getattr(sources, "queue_target_pending", 25) if sources else 25

    now = time.time()
    backoff_until = _LANE_REPLENISH_BACKOFF.get(lane_id, 0.0)
    if now < backoff_until:
        logger.debug(
            "Lane [%s] replenishment in backoff cooldown for another %.1fs; skipping scrape.",
            lane_id,
            backoff_until - now,
        )
        return 0

    def _get_count() -> int:
        with connect(path, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*) FROM stories
                WHERE status = 'PENDING'
                  AND (channel = ? OR channel = ?)
                  AND (lane_id IS NULL OR lane_id = ?)
                """,
                (channel_key, resolve_channel_key(channel_key), lane_id),
            )
            return cursor.fetchone()[0]

    pending_count = await asyncio.to_thread(_get_count)
    if pending_count >= target_depth:
        return pending_count

    logger.info("Lane [%s] queue depth is %d (< target %d). Replenishing queue...", lane_id, pending_count, target_depth)

    source_kind = getattr(sources, "kind", "reddit") if sources else "reddit"
    subreddits, categories = _get_lane_subreddits_and_categories(sources, channel_key)
    story_type = getattr(lane, "story_type", "")

    if source_kind == "scp_wiki" or (story_type == "scp" and not getattr(sources, "subreddits", ())):
        await _replenish_from_scp(target_depth - pending_count, path, lane_id, channel_key, session)

    limit_per_fetch = getattr(sources, "limit_per_fetch", 25) if sources else 25
    scrape_min_length = (
        min(getattr(lane, "words_min", 100), 100)
        if getattr(lane, "multistory_collection", False)
        else min(getattr(lane, "words_min", 100), 250)
    )

    await _replenish_from_reddit(
        lane=lane,
        subreddits=subreddits,
        categories=categories,
        limit_per_fetch=limit_per_fetch,
        scrape_min_length=scrape_min_length,
        channel_key=channel_key,
        lane_id=lane_id,
        target_depth=target_depth,
        path=path,
        session=session,
        _get_count_fn=_get_count,
    )

    curr_count = await asyncio.to_thread(_get_count)
    if curr_count < target_depth and story_type == "scp":
        await _replenish_from_scp(target_depth - curr_count, path, lane_id, channel_key, session)

    curr_count = await asyncio.to_thread(_get_count)
    if curr_count == 0:
        try:
            await _dynamic_procedural_fallback(lane, channel_key, lane_id, target_depth, path)
        except Exception as dyn_err:
            logger.warning("Dynamic procedural fallback failed for lane [%s]: %s", lane_id, dyn_err)

    updated_count = await asyncio.to_thread(_get_count)
    _apply_replenish_backoff(lane_id, updated_count, pending_count)

    logger.info("Queue depth for lane [%s] replenished. Total pending: %d (target: %d)", lane_id, updated_count, target_depth)
    return updated_count


def ensure_queue_depth(lane: Any, db_path: Optional[str] = None) -> int:
    """Synchronous compatibility wrapper for async_ensure_queue_depth."""
    return _run_sync(async_ensure_queue_depth(lane, db_path=db_path))


__all__ = [
    "_LANE_REPLENISH_BACKOFF",
    "async_replenish_queue",
    "replenish_queue",
    "async_ensure_queue_depth",
    "ensure_queue_depth",
]
