import json
import os
import re
import requests
from collections import Counter
from pathlib import Path
from typing import List, Dict, Any, Optional
from src.log import get_logger

logger = get_logger("scraper")

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) YoutubeAutomation/1.0"


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


def _parse_frontmatter(lines: List[str]) -> Dict[str, str]:
    """Parse an OPTIONAL leading '---' frontmatter block from pre-cleaned lines.

    Returns a metadata dict (possibly empty) and mutates nothing: the caller
    receives metadata plus must slice off the block itself when non-empty.
    """
    if not lines or lines[0] != "---":
        return {}
    closing = None
    for idx in range(1, len(lines)):
        if lines[idx] == "---":
            closing = idx
            break
    if closing is None:
        # Unterminated block: keep legacy behaviour (first line stays the title).
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

PRESET_CANONICAL_STORIES = [
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
        "url": "https://reddit.com/r/nosleep/comments/canonical001"
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
        "url": "https://reddit.com/r/AmItheAsshole/comments/canonical002"
    }
]




def _load_canonical_stories(
    subreddit: str = "nosleep",
    limit: int = 50,
    min_length: int = 10
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
                            "url": url
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
                        # Frontmatter present: title is the first non-frontmatter line.
                        title = body[0] if body else ""
                        content = "\n".join(body[1:]) if len(body) > 1 else title
                    else:
                        # No frontmatter: byte-identical to legacy parsing.
                        title = lines[0]
                        content = "\n".join(lines[1:]) if len(lines) > 1 else lines[0]
                    post_id = f"FILE-{text_file.stem}"
                    url = f"https://reddit.com/r/canonical/{post_id}"
                    if title and content and len(content) >= min_length:
                        story: Dict[str, Any] = {
                            "id": post_id,
                            "title": title,
                            "content": content,
                            "url": url
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

    return loaded_stories[:limit]


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
        "error 403", "error 502", "error 503", "error 504"
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


def fetch_reddit_stories(
    subreddit: str = "nosleep",
    limit: int = 50,
    user_agent: str = DEFAULT_USER_AGENT,
    min_length: int = 10,
    sort: str = "hot",
    time_filter: str = "week",
    after: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Fetch posts from Reddit using public JSON endpoint with category sort, time_filter, and pagination.
    Automatically falls back to PullPush API if direct Reddit returns non-200 or network error.
    Falls back to data/worksets/canonical/ local stories if scrapers return 0 usable stories.
    """
    url_params = f"limit={limit}"
    if sort in ("top", "controversial"):
        url_params += f"&t={time_filter}"
    if after:
        url_params += f"&after={after}"

    import urllib.parse
    sub_quoted = urllib.parse.quote(str(subreddit).strip())
    reddit_url = f"https://www.reddit.com/r/{sub_quoted}/{sort}.json?{url_params}"
    pullpush_url = f"https://api.pullpush.io/reddit/search/submission/?subreddit={sub_quoted}&size={limit}"
    headers = {"User-Agent": user_agent}

    use_pullpush = False
    data = None
    is_404 = False
    reddit_failed = False
    pullpush_failed = False

    logger.info(f"Fetching Reddit stories from r/{subreddit} (sort={sort}, t={time_filter})...")
    try:
        response = requests.get(reddit_url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
        elif response.status_code == 404:
            logger.warning(f"Reddit API returned status 404 for r/{subreddit}, activating PullPush fallback...")
            reddit_failed = True
            use_pullpush = True
        else:
            logger.warning(f"Reddit API returned status {response.status_code}, activating PullPush fallback...")
            reddit_failed = True
            use_pullpush = True
    except requests.RequestException as e:
        logger.warning(f"Reddit API request exception: {e}, activating PullPush fallback...")
        reddit_failed = True
        use_pullpush = True

    if use_pullpush:
        try:
            pp_response = requests.get(pullpush_url, headers=headers, timeout=10)
            if pp_response.status_code == 200:
                data = pp_response.json()
                logger.info("PullPush fallback fetch successful")
            elif pp_response.status_code == 404:
                logger.warning(f"PullPush API returned status 404 for r/{subreddit}")
                is_404 = True
                pullpush_failed = True
            else:
                logger.warning(f"PullPush API returned status {pp_response.status_code}")
                pullpush_failed = True
        except requests.RequestException as e:
            logger.warning(f"PullPush API request exception: {e}")
            pullpush_failed = True

    stories = []
    if data and isinstance(data, dict):
        items = []
        if "data" in data and isinstance(data["data"], dict) and "children" in data["data"]:
            for child in data["data"].get("children", []):
                if isinstance(child, dict) and "data" in child:
                    items.append(child["data"])
        elif "data" in data and isinstance(data["data"], list):
            items = data["data"]

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

            if _is_deleted_or_removed(selftext) or _is_deleted_or_removed(title) or _is_deleted_or_removed(author):
                continue

            if len(selftext) < min_length:
                continue

            if not is_high_quality_story(title, selftext, min_length=min_length):
                continue

            # Real-metadata quality knobs (env read at call time; 0/0.0 disables).
            if score < _env_min_score():
                logger.info(
                    "Skipping post '%s' (score %d < REDDIT_MIN_SCORE)",
                    title[:50], score
                )
                continue
            if upvote_ratio < _env_min_upvote_ratio():
                logger.info(
                    "Skipping post '%s' (upvote_ratio %.2f < REDDIT_MIN_UPVOTE_RATIO)",
                    title[:50], upvote_ratio
                )
                continue

            permalink = post.get("permalink", "")
            full_link = post.get("full_link", "") or post.get("url", "")
            if permalink and permalink.startswith("/"):
                url = f"https://www.reddit.com{permalink}"
            elif full_link and full_link.startswith("http"):
                url = full_link
            else:
                url = f"https://reddit.com/comments/{post_id}"

            if post_id and title and selftext:
                stories.append({
                    "id": post_id,
                    "title": title,
                    "content": selftext,
                    "url": url,
                    "score": score,
                    "upvote_ratio": upvote_ratio,
                    "num_comments": num_comments
                })

    if not stories:
        reddit_failed = True

    if not stories and not is_404:
        if reddit_failed and (not use_pullpush or pullpush_failed):
            logger.warning(f"Reddit and PullPush scrapers returned 0 valid stories for r/{subreddit}. Activating local canonical workset fallback...")
            stories = _load_canonical_stories(subreddit=subreddit, limit=limit, min_length=min_length)

    logger.info(f"Fetched and filtered {len(stories)} high-quality stories from r/{subreddit}")
    return stories

from src.branding import resolve_channel_key

USER_AGENTS = [DEFAULT_USER_AGENT]

CHANNEL_SUBREDDITS = {
    "terror": ["nosleep", "scarystories", "darktales", "creepypasta", "shortscarystories", "libraryofshadows"],
    "moku": ["nosleep", "scarystories", "darktales", "creepypasta", "shortscarystories", "libraryofshadows"],
    "aelithia": ["AmItheAsshole", "AITA", "TrueOffMyChest", "relationship_advice", "Confession", "badparents", "AskReddit", "ProRevenge", "NuclearRevenge", "PettyRevenge"]
}

def replenish_queue(channel: str = "terror", min_stories: int = 25, db_path: str = None) -> int:
    """
    Check current pending queue depth for channel and automatically scrape additional subreddits
    and listing categories (hot, top?t=week, top?t=month, new) to ensure at least `min_stories`
    pending stories are available for mass production.
    """
    from src.db import enqueue_story, get_pending_story
    from src.config import DEFAULT_DB_PATH
    from src.core.repository import connect

    c_key = resolve_channel_key(channel)
    path = db_path or DEFAULT_DB_PATH

    with connect(path, read_only=True) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM stories WHERE status = 'PENDING' AND (channel = ? OR channel = ?)", (c_key, channel))
        pending_count = cursor.fetchone()[0]

    if pending_count >= min_stories:
        return pending_count

    logger.info(f"Queue depth for [{c_key}] is {pending_count} (< target {min_stories}). Replenishing queue...")
    subreddits = CHANNEL_SUBREDDITS.get(c_key, ["nosleep" if c_key == "terror" else "AmItheAsshole"])
    categories = [
        ("hot", "week"),
        ("top", "week"),
        ("top", "month"),
        ("new", "all")
    ]

    for sub in subreddits:
        for sort_cat, t_filter in categories:
            with connect(path, read_only=True) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM stories WHERE status = 'PENDING' AND (channel = ? OR channel = ?)", (c_key, channel))
                curr_count = cursor.fetchone()[0]

            if curr_count >= min_stories:
                break

            try:
                fetched = fetch_reddit_stories(subreddit=sub, limit=50, sort=sort_cat, time_filter=t_filter)
                for s in fetched:
                    enqueue_story(
                        story_id=s["id"],
                        title=s["title"],
                        content=s["content"],
                        url=s["url"],
                        score=int(s.get("score", 0) or 0),
                        upvote_ratio=float(s.get("upvote_ratio", 0.0) or 0.0),
                        num_comments=int(s.get("num_comments", 0) or 0),
                        channel=channel,
                        db_path=path
                    )
            except Exception as e:
                logger.warning(f"Replenish queue error fetching from r/{sub} ({sort_cat}): {e}")

    with connect(path, read_only=True) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM stories WHERE status = 'PENDING' AND (channel = ? OR channel = ?)", (c_key, channel))
        updated_count = cursor.fetchone()[0]

    logger.info(f"Replenished queue for [{channel}]. Total pending stories now: {updated_count}")
    return updated_count


def ensure_queue_depth(lane: Any, db_path: Optional[str] = None) -> int:
    """Ensure the database has at least `lane.sources.queue_target_pending` pending stories for `lane`.

    Rotates across `lane.sources.subreddits` and category pairs (e.g. `[('hot', 'day'), ('top', 'week'), ('new', 'all')]`),
    filters stories with `filter_story_for_lane`, deduplicates, and enqueues matching items.
    If the lane source is SCP or if Reddit scraping is insufficient for an SCP lane, falls back to `scraper_scp`.
    """
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
        pending_count = cursor.fetchone()[0]

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
        from src.scraper_scp import scrape_and_enqueue_scp

        scrape_and_enqueue_scp(
            limit=max(5, target_depth - pending_count),
            db_path=path,
            lane_id=lane_id,
            channel=channel_key,
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
    words_min = getattr(lane, "words_min", 10)

    for sub in subreddits:
        for sort_cat, t_filter in categories:
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
                curr_count = cursor.fetchone()[0]

            if curr_count >= target_depth:
                break

            try:
                fetched = fetch_reddit_stories(
                    subreddit=sub,
                    limit=limit_per_fetch,
                    sort=sort_cat,
                    time_filter=t_filter,
                    min_length=words_min,
                )
                for s in fetched:
                    # Filter for topic/lane relevance
                    if not filter_story_for_lane(s["title"], s["content"], lane):
                        continue

                    # Check duplicate
                    if is_story_processed(s["id"], db_path=path) or is_story_duplicate(
                        channel_key, s["title"], s["content"], db_path=path
                    ):
                        continue

                    enqueue_story(
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
            except Exception as e:
                logger.warning(
                    "Error replenishing queue for lane [%s] from r/%s (%s): %s",
                    lane_id,
                    sub,
                    sort_cat,
                    e,
                )

    # 3. If still deficient and lane is SCP, fallback to SCP scraper
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
        curr_count = cursor.fetchone()[0]

    if curr_count < target_depth and story_type == "scp":
        from src.scraper_scp import scrape_and_enqueue_scp

        scrape_and_enqueue_scp(
            limit=max(5, target_depth - curr_count),
            db_path=path,
            lane_id=lane_id,
            channel=channel_key,
        )

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
        updated_count = cursor.fetchone()[0]

    logger.info(
        "Queue depth for lane [%s] replenished. Total pending: %d (target: %d)",
        lane_id,
        updated_count,
        target_depth,
    )
    return updated_count

