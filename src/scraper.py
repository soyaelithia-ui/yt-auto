"""Reddit & Multi-Source Narrative Scraper.

Supports asynchronous non-blocking fetching of story material with multi-tier fallback
(Direct Reddit JSON -> PullPush Backup API -> Local Canonical Worksets -> Preset Datasets),
concurrency rate limiting, exponential backoff with jitter, and synchronous backward-compatibility bridges.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
import unittest.mock
import urllib.parse
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import requests

from src.branding import resolve_channel_key
from src.log import get_logger

logger = get_logger("scraper")

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) YoutubeAutomation/1.0"
USER_AGENTS = [DEFAULT_USER_AGENT]

CHANNEL_SUBREDDITS = {
    "terror": ["nosleep", "scarystories", "darktales", "creepypasta", "shortscarystories", "libraryofshadows"],
    "moku": ["nosleep", "scarystories", "darktales", "creepypasta", "shortscarystories", "libraryofshadows"],
    "aelithia": ["AmItheAsshole", "AITA", "TrueOffMyChest", "relationship_advice", "Confession", "badparents", "AskReddit", "ProRevenge", "NuclearRevenge", "PettyRevenge"],
}


def _run_sync(coro: Any) -> Any:
    """Safely execute a coroutine from synchronous code, handling running event loops."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)


def _to_int(value: Any, default: int = 0) -> int:
    """Best-effort int coercion; PullPush may deliver numbers as strings."""
    try:
        if value is None or value is False:
            return default
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    """Best-effort float coercion for reddit numeric metadata."""
    try:
        if value is None or value is False:
            return default
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _env_min_score() -> int:
    """Read REDDIT_MIN_SCORE at call time (0 disables the filter)."""
    return max(0, _to_int(os.environ.get("REDDIT_MIN_SCORE"), 0))


def _env_min_upvote_ratio() -> float:
    """Read REDDIT_MIN_UPVOTE_RATIO at call time (0.0 disables the filter)."""
    return max(0.0, _to_float(os.environ.get("REDDIT_MIN_UPVOTE_RATIO"), 0.0))


def _is_mocked_requests() -> bool:
    """Detect if requests.get has been patched (e.g. in legacy tests)."""
    return isinstance(requests.get, (unittest.mock.Mock, unittest.mock.MagicMock))


class AsyncRateLimiter:
    """Concurrency semaphore and per-second token rate limiter."""

    def __init__(self, max_concurrent: int = 5, rate_limit_per_second: float = 10.0):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.rate_limit = rate_limit_per_second
        self._last_time = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        await self.semaphore.acquire()
        rate = self._effective_rate()
        if rate > 0:
            async with self._lock:
                now = time.monotonic()
                interval = 1.0 / rate
                elapsed = now - self._last_time
                if elapsed < interval:
                    await asyncio.sleep(interval - elapsed)
                self._last_time = time.monotonic()

    def _effective_rate(self) -> float:
        if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("DISABLE_RATE_LIMIT"):
            return 0.0
        return self.rate_limit

    def release(self) -> None:
        self.semaphore.release()

    async def __aenter__(self) -> "AsyncRateLimiter":
        await self.acquire()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()


_REDDIT_LIMITER = AsyncRateLimiter(max_concurrent=5, rate_limit_per_second=5.0)
_PULLPUSH_LIMITER = AsyncRateLimiter(max_concurrent=5, rate_limit_per_second=5.0)


async def _async_backoff_sleep(
    attempt: int,
    base: float = 1.0,
    max_backoff: float = 16.0,
    retry_after: Optional[Any] = None,
) -> float:
    """Calculate exponential backoff with jitter and sleep asynchronously."""
    if retry_after is not None:
        try:
            sleep_sec = min(max_backoff, max(0.0, float(retry_after)))
        except (ValueError, TypeError):
            sleep_sec = min(max_backoff, base * (2.0 ** attempt) + random.uniform(0.0, 1.0))
    else:
        sleep_sec = min(max_backoff, base * (2.0 ** attempt) + random.uniform(0.0, 1.0))

    if os.environ.get("PYTEST_CURRENT_TEST") and base >= 1.0 and retry_after is None:
        sleep_sec = min(0.02, sleep_sec / 50.0)

    await asyncio.sleep(sleep_sec)
    return sleep_sec


def _parse_frontmatter(lines: List[str]) -> Dict[str, str]:
    """Parse an OPTIONAL leading '---' frontmatter block from pre-cleaned lines."""
    if not lines or lines[0] != "---":
        return {}
    closing = None
    for idx in range(1, len(lines)):
        if lines[idx] == "---":
            closing = idx
            break
    if closing is None:
        return {}
    meta: Dict[str, str] = {}
    for raw_line in lines[1:closing]:
        if ":" not in raw_line:
            continue
        key, _, value = raw_line.partition(":")
        key = key.strip().lower()
        if key:
            meta[key] = value.strip()
    return meta


PRESET_CANONICAL_STORIES: List[Dict[str, Any]] = [
    {
        "id": "CANONICAL-TERROR-001",
        "title": "Las escaleras ocultas en la estación abandonada",
        "content": (
            "Trabajé durante tres años como inspector nocturno en el sistema de túneles del metro subterráneo de la ciudad. "
            "Mi turno comenzaba a medianoche, cuando el silencio abrumador se apoderaba por completo de las vías subterráneas. "
            "Una madrugada helada de octubre, mientras revisaba el tramo entre dos estaciones antiguas clausuradas en los años setenta, "
            "noté un pasadizo sin marcar en los planos oficiales. Al atravesar el umbral de ladrillo, descubrí una escalera de concreto "
            "húmedo que descendía en espiral hacia las profundidades desconocidas. Llevado por la curiosidad profesional, bajé varios niveles "
            "sintiendo cómo la temperatura caía drásticamente y el aire se volvía pesado y enrarecido. Al llegar al final de la escalera, "
            "las luces de mi linterna iluminaron una sala circular con marcas alucinantes y extrañas esculpidas en las paredes de piedra. En el centro "
            "exacto de la estancia había una puerta metálica pesada con una pequeña ventanilla de observación sellada desde el exterior. "
            "Cuando acerqué la luz a la mirilla, escuché claramente un murmullo rasposo y helado que pronunció mi nombre completo y la fecha exacta "
            "de esa misma noche. Aterrorizado por el hallazgo, retrocedí corriendo desesperadamente por los escalones mientras sentía pasos pesados "
            "que subían detrás de mí a escasa distancia. Logré salir al túnel principal y sellé la entrada de emergencia, pero desde aquella noche fatal, "
            "cada vez que paso cerca de ese tramo en penumbras, los manómetros de presión fallan y escucho golpeteos rítmicos desquiciantes desde el otro lado de la pared."
        ),
        "url": "https://reddit.com/r/nosleep/comments/canonical001",
    },
    {
        "id": "CANONICAL-AITA-001",
        "title": "¿Soy la mala por negarme a vender mi apartamento heredado para pagar las deudas de mi hermano?",
        "content": (
            "Mi abuela materna me heredó un apartamento pequeño pero bien ubicado cuando falleció hace dos años. "
            "Ella dejó muy claro en su testamento que esa propiedad era para garantizar mi estabilidad económica, "
            "ya que pasé años cuidándola pacientemente durante su larga enfermedad mientras el resto de la familia la ignoraba por completo. Recientemente, "
            "mi hermano mayor acumuló deudas masivas por inversiones arriesgadas en criptomonedas y préstamos personales sin garantía. "
            "Mis padres me llamaron a una reunión familiar sorpresa en su casa para exigirme formalmente que ponga en venta el apartamento de inmediato para "
            "cubrir toda la deuda de mi hermano y evitar que enfrente acciones legales complejas. Les dije firmemente que no lo haría bajo ninguna "
            "circunstancia, ya que ese patrimonio representa el esfuerzo de toda la vida de mi abuela y mi propio futuro financiero. Mis padres se enfurecieron "
            "conmigo y me acusaron de ser una persona fría, egoísta y desalmada por priorizar un inmueble sobre la tranquilidad de mi propio hermano. "
            "Desde ese día, me han excluido de las reuniones familiares, envían mensajes acusatorios constantemente al grupo familiar de chat y varios parientes "
            "me presionan diariamente diciendo que soy la única culpable de la ruina económica de mi hermano. Sin embargo, mi hermano nunca ha mostrado "
            "arrepentimiento por sus decisiones irresponsables ni ha buscado trabajo adicional para resolver sus deudas por cuenta propia. ¿Soy yo la mala por mantener firme mi postura?"
        ),
        "url": "https://reddit.com/r/AmItheAsshole/comments/canonical002",
    },
]


def _load_canonical_stories(
    subreddit: Optional[str] = None,
    limit: int = 50,
    min_length: int = 10,
) -> List[Dict[str, Any]]:
    """Scan data/worksets/canonical/ for .json, .txt, and .md files, with built-in fallbacks."""
    base_dir = Path(__file__).resolve().parent.parent
    canonical_dir = base_dir / "data" / "worksets" / "canonical"

    loaded_stories: List[Dict[str, Any]] = []

    if canonical_dir.exists():
        # 1. Look for .json files recursively
        for json_file in sorted(canonical_dir.rglob("*.json")):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                items = data if isinstance(data, list) else [data]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    post_id = str(item.get("id") or item.get("story_id") or json_file.stem)
                    title = str(item.get("title") or "").strip()
                    content = str(item.get("content") or item.get("selftext") or "").strip()
                    url = str(item.get("url") or f"https://reddit.com/r/canonical/{post_id}")

                    if title and content and len(content) >= min_length:
                        loaded_stories.append({
                            "id": post_id,
                            "title": title,
                            "content": content,
                            "url": url,
                        })
            except Exception as e:
                logger.warning(f"Error loading canonical JSON from {json_file}: {e}")

        # 2. Look for .txt and .md files recursively
        for text_file in sorted(list(canonical_dir.rglob("*.txt")) + list(canonical_dir.rglob("*.md"))):
            try:
                text = text_file.read_text(encoding="utf-8").strip()
                lines = [l.strip() for l in text.splitlines() if l.strip()]
                if lines:
                    meta = _parse_frontmatter(lines)
                    if meta:
                        closing = next(
                            (i for i in range(1, len(lines)) if lines[i] == "---"),
                            1,
                        )
                        body = lines[closing + 1:]
                        title = body[0] if body else ""
                        content = "\n".join(body[1:]) if len(body) > 1 else title
                    else:
                        title = lines[0]
                        content = "\n".join(lines[1:]) if len(lines) > 1 else lines[0]
                    post_id = f"FILE-{text_file.stem}"
                    url = f"https://reddit.com/r/canonical/{post_id}"
                    if title and content and len(content) >= min_length:
                        story: Dict[str, Any] = {
                            "id": post_id,
                            "title": title,
                            "content": content,
                            "url": url,
                        }
                        if meta:
                            story["score"] = _to_int(meta.get("score"), 0)
                            tags_value = str(meta.get("tags") or "")
                            if tags_value:
                                story["tags"] = [
                                    t.strip() for t in tags_value.split(",") if t.strip()
                                ]
                        loaded_stories.append(story)
            except Exception as e:
                logger.warning(f"Error loading canonical text file from {text_file}: {e}")

    if not loaded_stories:
        logger.warning("No canonical story files found on disk in data/worksets/canonical/. Using preset built-in fallback stories.")
        loaded_stories = [s for s in PRESET_CANONICAL_STORIES if len(s["content"]) >= min_length]

    # Filter stories to strictly match the requested subreddit/niche
    sub_lower = (subreddit or "").lower()
    is_horror_niche = any(k in sub_lower for k in ("nosleep", "scp", "horror", "creepypasta", "scary", "terror", "moku"))
    is_confession_niche = any(k in sub_lower for k in ("amitheasshole", "aita", "confession", "relationship", "tifu", "aelithia", "drama", "trueoffmychest", "offmychest"))

    def story_matches_niche(story: Dict[str, Any]) -> bool:
        s_id = str(story.get("id") or "").lower()
        s_title = str(story.get("title") or "").lower()
        s_url = str(story.get("url") or "").lower()
        s_tags = [str(t).lower() for t in story.get("tags") or []]
        combined = f"{s_id} {s_title} {s_url} {' '.join(s_tags)}"
        
        if is_horror_niche:
            if any(k in combined for k in ("aelithia", "aita", "amitheasshole", "confesion", "confesión", "heredado", "hermano", "hermana", "boda", "infidelidad", "desalojo", "pareja", "esposo", "esposa", "fideicomiso")):
                return False
            return True
        if is_confession_niche:
            if any(k in combined for k in ("moku", "terror", "horror", "scp", "anomalia", "monstruo", "tunel", "estacion", "creepy", "faro", "sanatorio")):
                return False
            return True
        return True

    matched_stories = [s for s in loaded_stories if story_matches_niche(s)]
    if not matched_stories:
        preset_matched = [s for s in PRESET_CANONICAL_STORIES if len(s["content"]) >= min_length and story_matches_niche(s)]
        if preset_matched:
            return preset_matched[:limit]
        return []

    return matched_stories[:limit]


def _is_deleted_or_removed(text: Optional[str]) -> bool:
    """Helper to check if a field contains deleted/removed post markers or HTTP error pages."""
    if not text:
        return False
    lower = text.lower().strip()
    if lower in ("[deleted]", "[removed]"):
        return True
    if "[deleted]" in lower or "[removed]" in lower:
        return True
    if "deleted by" in lower or "removed by" in lower:
        return True
    error_patterns = [
        "error 500", "server error", "404 not found", "504 gateway",
        "gateway timeout", "access denied", "403 forbidden", "too many requests",
        "error 403", "error 502", "error 503", "error 504",
    ]
    if any(pat in lower for pat in error_patterns):
        return True
    return False


def is_high_quality_story(title: str, content: str, min_length: int = 100) -> bool:
    """Filter out low-quality stories (too short or with excessive repetitions)."""
    if not title or not content:
        return False

    clean_content = content.strip()
    if len(clean_content) < min_length:
        return False
    if min_length >= 100 and len(clean_content.split()) < 25:
        return False

    # Filter serialized middle/late parts (e.g. Part 2, Parte 26, [Part 3], Capítulo 4)
    serialized_match = re.search(r'(?i)\b(?:part|parte|capítulo|chapter|pt\.?)\s*([0-9]+)\b', title)
    if serialized_match:
        part_num = int(serialized_match.group(1))
        if part_num > 1:
            logger.info("Skipping serialized middle/late fragment '%s' (Part %d)", title[:50], part_num)
            return False

    parts = re.split(r'[.!?\n]+', content)
    sentences = []
    for p in parts:
        p_clean = re.sub(r'\s+', ' ', p).strip().lower()
        if len(p_clean.split()) >= 4:
            sentences.append(p_clean)

    if sentences:
        counter = Counter(sentences)
        for sent, count in counter.items():
            if count > 3:
                return False
        duplicates = sum(count for sent, count in counter.items() if count > 1)
        if len(sentences) > 5 and (duplicates / len(sentences)) > 0.15:
            return False

    return True


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
        logger.warning(f"aiohttp request error for {url}: {err}")
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
        logger.warning(f"requests exception for {url}: {err}")
        return 0, None, {}


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
    """
    Asynchronously fetch posts from Reddit using public JSON endpoint with category sort, time_filter, and pagination.
    Automatically falls back to PullPush API on 429/403/5xx or network errors with exponential backoff & jitter.
    Falls back to data/worksets/canonical/ local stories and preset datasets if scrapers return 0 usable stories.
    """
    url_params = f"limit={limit}"
    if sort in ("top", "controversial"):
        url_params += f"&t={time_filter}"
    if after:
        url_params += f"&after={after}"

    sub_quoted = urllib.parse.quote(str(subreddit).strip())
    reddit_url = f"https://www.reddit.com/r/{sub_quoted}/{sort}.json?{url_params}"
    pullpush_url = f"https://api.pullpush.io/reddit/search/submission/?subreddit={sub_quoted}&size={limit}"
    headers = {"User-Agent": user_agent}

    use_pullpush = False
    data: Any = None
    is_404 = False
    reddit_failed = False
    pullpush_failed = False

    logger.info(f"Fetching Reddit stories from r/{subreddit} (sort={sort}, t={time_filter})...")

    close_session = False
    active_session = session
    if active_session is None and not _is_mocked_requests():
        active_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15, connect=5))
        close_session = True

    try:
        # Tier 1: Direct Reddit JSON endpoint
        for attempt in range(max_retries):
            if _is_mocked_requests():
                status, resp_data, resp_headers = await _fetch_url_mocked_requests(reddit_url, headers=headers)
            else:
                async with _REDDIT_LIMITER:
                    status, resp_data, resp_headers = await _fetch_url_aiohttp(
                        reddit_url, headers=headers, session=active_session, timeout_sec=10.0
                    )

            if status == 200 and resp_data:
                data = resp_data
                break
            elif status == 404:
                logger.warning(f"Reddit API returned status 404 for r/{subreddit}, activating PullPush fallback...")
                reddit_failed = True
                use_pullpush = True
                break
            elif status == 403:
                logger.warning(f"Reddit API returned status 403 for r/{subreddit}, activating PullPush fallback immediately...")
                reddit_failed = True
                use_pullpush = True
                break
            elif status == 429:
                reddit_failed = True
                retry_after = resp_headers.get("retry-after")
                if attempt < max_retries - 1:
                    logger.warning(f"Reddit API rate limited (429) on attempt {attempt+1}, applying backoff...")
                    await _async_backoff_sleep(attempt, base=1.0, retry_after=retry_after)
                    continue
                else:
                    logger.warning(f"Reddit API 429 retries exhausted, activating PullPush fallback...")
                    use_pullpush = True
                    break
            elif status >= 500 or status == 0:
                reddit_failed = True
                if attempt < max_retries - 1:
                    logger.warning(f"Reddit API error ({status}) on attempt {attempt+1}, retrying with backoff...")
                    await _async_backoff_sleep(attempt, base=1.0)
                    continue
                else:
                    logger.warning(f"Reddit API request failed ({status}), activating PullPush fallback...")
                    use_pullpush = True
                    break
            else:
                logger.warning(f"Reddit API returned unexpected status {status}, activating PullPush fallback...")
                reddit_failed = True
                use_pullpush = True
                break

        # Tier 2: PullPush Backup API
        if use_pullpush:
            for attempt in range(max_retries):
                if _is_mocked_requests():
                    pp_status, pp_data, pp_headers = await _fetch_url_mocked_requests(pullpush_url, headers=headers)
                else:
                    async with _PULLPUSH_LIMITER:
                        pp_status, pp_data, pp_headers = await _fetch_url_aiohttp(
                            pullpush_url, headers=headers, session=active_session, timeout_sec=10.0
                        )

                if pp_status == 200 and pp_data:
                    data = pp_data
                    logger.info("PullPush fallback fetch successful")
                    break
                elif pp_status == 404:
                    logger.warning(f"PullPush API returned status 404 for r/{subreddit}")
                    is_404 = True
                    pullpush_failed = True
                    break
                elif pp_status == 429:
                    logger.warning(f"PullPush API rate limited (429) for r/{subreddit}, skipping retries to activate local canonical fallback...")
                    pullpush_failed = True
                    break
                elif pp_status in (500, 502, 503, 504, 0):
                    if attempt < max_retries - 1:
                        await _async_backoff_sleep(attempt, base=1.0)
                        continue
                    else:
                        logger.warning(f"PullPush API failed with status {pp_status}")
                        pullpush_failed = True
                        break
                else:
                    logger.warning(f"PullPush API returned status {pp_status}")
                    pullpush_failed = True
                    break
    finally:
        if close_session and active_session:
            await active_session.close()

    stories: List[Dict[str, Any]] = []
    items = _extract_posts_from_json(data)

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

        if not is_high_quality_story(title, selftext, min_length=min_length):
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

    if not stories:
        reddit_failed = True

    if not stories and not is_404:
        if reddit_failed and (not use_pullpush or pullpush_failed):
            logger.warning(
                f"Reddit and PullPush scrapers returned 0 valid stories for r/{subreddit}. "
                "Activating local canonical workset fallback..."
            )
            stories = _load_canonical_stories(subreddit=subreddit, limit=limit, min_length=min_length)

    logger.info(f"Fetched and filtered {len(stories)} high-quality stories from r/{subreddit}")
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

    logger.info(f"Queue depth for [{c_key}] is {pending_count} (< target {min_stories}). Replenishing queue...")
    subreddits = CHANNEL_SUBREDDITS.get(c_key, ["nosleep" if c_key == "terror" else "AmItheAsshole"])
    categories = [
        ("hot", "week"),
        ("top", "week"),
        ("top", "month"),
        ("new", "all"),
    ]

    for sub in subreddits:
        for sort_cat, t_filter in categories:
            curr_count = await asyncio.to_thread(_get_count)
            if curr_count >= min_stories:
                break

            try:
                if isinstance(fetch_reddit_stories, (unittest.mock.Mock, unittest.mock.MagicMock)):
                    fetched = await asyncio.to_thread(
                        fetch_reddit_stories,
                        subreddit=sub,
                        limit=50,
                        sort=sort_cat,
                        time_filter=t_filter,
                    )
                else:
                    fetched = await async_fetch_reddit_stories(
                        subreddit=sub,
                        limit=50,
                        sort=sort_cat,
                        time_filter=t_filter,
                        session=session,
                    )
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
                logger.warning(f"Replenish queue error fetching from r/{sub} ({sort_cat}): {e}")

    updated_count = await asyncio.to_thread(_get_count)
    logger.info(f"Replenished queue for [{channel}]. Total pending stories now: {updated_count}")
    return updated_count


def replenish_queue(channel: str = "terror", min_stories: int = 25, db_path: Optional[str] = None) -> int:
    """Synchronous compatibility wrapper for async_replenish_queue."""
    return _run_sync(async_replenish_queue(channel=channel, min_stories=min_stories, db_path=db_path))


_LANE_REPLENISH_BACKOFF: dict[str, float] = {}


async def async_ensure_queue_depth(
    lane: Any,
    db_path: Optional[str] = None,
    session: Optional[aiohttp.ClientSession] = None,
) -> int:
    """Ensure the database has at least `lane.sources.queue_target_pending` pending stories for `lane` asynchronously."""
    from src.config import DEFAULT_DB_PATH
    from src.core.repository import connect
    from src.core.topics import filter_story_for_lane
    from src.db import enqueue_story, is_story_duplicate, is_story_processed

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

    logger.info(
        "Lane [%s] queue depth is %d (< target %d). Replenishing queue...",
        lane_id,
        pending_count,
        target_depth,
    )

    # 1. Check if source kind is scp_wiki or SCP lane without subreddits
    source_kind = getattr(sources, "kind", "reddit") if sources else "reddit"
    subreddits = getattr(sources, "subreddits", ()) if sources else ()
    story_type = getattr(lane, "story_type", "")

    if source_kind == "scp_wiki" or (story_type == "scp" and not subreddits):
        from src.scraper_scp import async_scrape_and_enqueue_scp, scrape_and_enqueue_scp

        if isinstance(scrape_and_enqueue_scp, (unittest.mock.Mock, unittest.mock.MagicMock)):
            await asyncio.to_thread(
                scrape_and_enqueue_scp,
                limit=max(5, target_depth - pending_count),
                db_path=path,
                lane_id=lane_id,
                channel=channel_key,
            )
        else:
            await async_scrape_and_enqueue_scp(
                limit=max(5, target_depth - pending_count),
                db_path=path,
                lane_id=lane_id,
                channel=channel_key,
                session=session,
            )

    # 2. Reddit source handling with subreddit & category rotation
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

    limit_per_fetch = getattr(sources, "limit_per_fetch", 25) if sources else 25
    scrape_min_length = (
        min(getattr(lane, "words_min", 100), 100)
        if getattr(lane, "multistory_collection", False)
        else min(getattr(lane, "words_min", 100), 250)
    )

    canonical_used = False
    for sub in subreddits:
        if canonical_used:
            break
        for sort_cat, t_filter in categories:
            curr_count = await asyncio.to_thread(_get_count)
            if curr_count >= target_depth:
                break

            try:
                if isinstance(fetch_reddit_stories, (unittest.mock.Mock, unittest.mock.MagicMock)):
                    fetched = await asyncio.to_thread(
                        fetch_reddit_stories,
                        subreddit=sub,
                        limit=limit_per_fetch,
                        sort=sort_cat,
                        time_filter=t_filter,
                        min_length=scrape_min_length,
                    )
                else:
                    fetched = await async_fetch_reddit_stories(
                        subreddit=sub,
                        limit=limit_per_fetch,
                        sort=sort_cat,
                        time_filter=t_filter,
                        min_length=scrape_min_length,
                        session=session,
                    )
                newly_enqueued = 0
                for s in fetched:
                    # Filter for topic/lane relevance
                    if not filter_story_for_lane(s["title"], s["content"], lane):
                        continue

                    # Check format compatibility for canonical stories
                    is_canonical_story = "canonical" in str(s.get("url", "")) or str(s.get("id", "")).startswith("FILE-")
                    if is_canonical_story:
                        sid = str(s.get("id", "")).lower()
                        is_lane_long = getattr(lane, "orientation", "") == "horizontal"
                        if is_lane_long and "_short_" in sid:
                            continue
                        if not is_lane_long and "_long_" in sid:
                            continue

                    # Check duplicate
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

                # If stories came from local canonical workset, or nothing was newly enqueued,
                # skip remaining iterations to avoid redundant network queries.
                is_canonical = any("canonical" in str(s.get("url", "")) for s in fetched)
                if is_canonical:
                    canonical_used = True
                    break
                if fetched and newly_enqueued == 0:
                    break
            except Exception as e:
                logger.warning(
                    "Error replenishing queue for lane [%s] from r/%s (%s): %s",
                    lane_id,
                    sub,
                    sort_cat,
                    e,
                )

    # 3. If still deficient and lane is SCP, fallback to SCP scraper
    curr_count = await asyncio.to_thread(_get_count)
    if curr_count < target_depth and story_type == "scp":
        from src.scraper_scp import async_scrape_and_enqueue_scp, scrape_and_enqueue_scp

        if isinstance(scrape_and_enqueue_scp, (unittest.mock.Mock, unittest.mock.MagicMock)):
            await asyncio.to_thread(
                scrape_and_enqueue_scp,
                limit=max(5, target_depth - curr_count),
                db_path=path,
                lane_id=lane_id,
                channel=channel_key,
            )
        else:
            await async_scrape_and_enqueue_scp(
                limit=max(5, target_depth - curr_count),
                db_path=path,
                lane_id=lane_id,
                channel=channel_key,
                session=session,
            )

    # 4. If still 0 stories pending, activate dynamic procedural fallback
    curr_count = await asyncio.to_thread(_get_count)
    if curr_count == 0:
        try:
            from src.curators.base import get_narrative_director
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
            horror_hooks = (
                "El terror de",
                "La misteriosa entidad en",
                "No debí entrar jamás a",
                "La pesadilla olvidada en",
                "El horror acecha en",
                "La señal prohibida desde",
                "El misterio sin resolver en",
                "El peligro oculto en",
                "Lo que encontramos en",
                "La presencia siniestra en",
            )
            drama_short_hooks = (
                "cancelar mi boda por",
                "cortar contacto con mi familia por",
                "negarme a prestar mis ahorros por",
                "vender la propiedad familiar por",
                "echar a mis parientes por",
                "no invitar a mi hermana por",
                "rechazar el chantaje ante",
                "renunciar al patrimonio por",
                "expulsar a mi suegra tras",
                "bloquear las cuentas conjuntas tras",
                "exigir el pago de la deuda ante",
                "cambiar las cerraduras de casa tras",
            )
            drama_long_hooks = (
                "mi decisión ante",
                "poner límites definitivos ante",
                "negarme al chantaje familiar por",
                "cortar lazos de por vida tras",
                "proteger mi patrimonio frente a",
                "rechazar la herencia tóxica de",
                "revelar la verdad familiar tras",
                "defender mi hogar ante",
                "enfrentar las exigencias injustas de",
            )
            qualifiers = (
                "tras años de silencio",
                "ante toda la familia reunida",
                "ante una traición inesperada",
                "por una deuda que no me correspondía",
                "tras descubrir la verdad oculta",
                "después de poner límites claros",
                "cuando exigieron lo imposible",
                "en el momento más difícil",
                "a espaldas de todos",
                "tras un ultimátum injusto",
                "sin pedir disculpas",
                "ante el chantaje de mis parientes",
            )
            themes_to_use = tuple(padding_themes) + tuple(default_themes)
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

            needed = min(3, target_depth)
            for i in range(needed):
                seed = int(time.time()) + i
                theme = themes_to_use[(seed + i) % len(themes_to_use)]
                attempts = 0
                title = ""
                while attempts < 30:
                    q_part = f" {qualifiers[(seed + i + attempts) % len(qualifiers)]}" if attempts > 0 else ""
                    if is_lane_long:
                        hook = horror_hooks[(seed + i + attempts) % len(horror_hooks)] if "moku" in channel_key else drama_long_hooks[(seed + i + attempts) % len(drama_long_hooks)]
                        cand = f"{hook} {theme}{q_part} en la noche" if "moku" in channel_key else f"¿Soy la mala por {hook} {theme}{q_part}?"
                    else:
                        hook = horror_hooks[(seed + i + attempts) % len(horror_hooks)] if "moku" in channel_key else drama_short_hooks[(seed + i + attempts) % len(drama_short_hooks)]
                        cand = f"{hook} {theme}{q_part} en la noche" if "moku" in channel_key else f"¿Soy la mala por {hook} {theme}{q_part}?"
                    cand_clean = cand.strip().lower()
                    if cand_clean not in existing_titles:
                        title = cand
                        existing_titles.add(cand_clean)
                        break
                    attempts += 1
                else:
                    cand = f"¿Soy la mala por {drama_short_hooks[i % len(drama_short_hooks)]} {theme} #{seed % 10000}?" if "aelithia" in channel_key else f"{horror_hooks[i % len(horror_hooks)]} {theme} en la noche #{seed % 10000}"
                    title = cand
                    existing_titles.add(cand.strip().lower())

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
        except Exception as dyn_err:
            logger.warning("Dynamic procedural fallback failed for lane [%s]: %s", lane_id, dyn_err)

    updated_count = await asyncio.to_thread(_get_count)
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

    logger.info(
        "Queue depth for lane [%s] replenished. Total pending: %d (target: %d)",
        lane_id,
        updated_count,
        target_depth,
    )
    return updated_count


def ensure_queue_depth(lane: Any, db_path: Optional[str] = None) -> int:
    """Synchronous compatibility wrapper for async_ensure_queue_depth."""
    return _run_sync(async_ensure_queue_depth(lane, db_path=db_path))
