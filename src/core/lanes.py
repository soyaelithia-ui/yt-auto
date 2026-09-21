"""Production lanes: config-driven editorial units that replace format modes.

A lane (carril) bundles everything the pipeline needs to produce one kind of
video — channel, story type, canvas, duration targets, word budget, template,
voice rate, cadence ceiling, sources and QA profile — so no human flag decides
whether a piece is a "Short" or a longform video. The scheduler fires lanes by
cadence; the pipeline reads the lane of the story it claimed.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Final, Mapping

from src.core.domain import CanonicalChannel, canonical_channel
from src.core.resolution import LONGFORM_RESOLUTION, SHORT_RESOLUTION

logger = logging.getLogger(__name__)

DEFAULT_LANES_PATH = os.environ.get("LANES_CONFIG_PATH", "config/lanes.json")

ALLOWED_RESOLUTIONS: Final[dict[str, tuple[int, int]]] = {
    "vertical": SHORT_RESOLUTION,
    "horizontal": LONGFORM_RESOLUTION,
}
ALLOWED_VISUAL_PIPELINES: Final[frozenset[str]] = frozenset({"beats", "director"})
ALLOWED_STORY_TYPES: Final[frozenset[str]] = frozenset(
    {"scp", "horror", "reddit_aita", "reddit_generic", "scifi"}
)
ALLOWED_SOURCE_KINDS: Final[frozenset[str]] = frozenset({"reddit", "scp_wiki"})
MIN_GAP_SECONDS = 60

LANE_ALIASES: Final[dict[str, str]] = {
    # Thematic horror -> moku-scp-shorts / moku-horror-long
    "horror-scp-shorts": "moku-scp-shorts",
    "terror-scp-shorts": "moku-scp-shorts",
    "scp-shorts": "moku-scp-shorts",
    "horror-shorts": "moku-scp-shorts",
    "horror-long": "moku-horror-long",
    "horror-horror-long": "moku-horror-long",
    "terror-long": "moku-horror-long",
    "creepypasta-long": "moku-horror-long",
    # Thematic drama -> aelithia-drama-shorts / aelithia-aita-long
    "drama-shorts": "aelithia-drama-shorts",
    "drama-drama-shorts": "aelithia-drama-shorts",
    "relatos-shorts": "aelithia-drama-shorts",
    "drama-aita-long": "aelithia-aita-long",
    "drama-long": "aelithia-aita-long",
    "aita-long": "aelithia-aita-long",
    "relatos-long": "aelithia-aita-long",
    # Legacy aliases
    "scifi-chronicles-shorts": "scifi-singularity-shorts",
}

# Fail-safe fallback equivalent to today's three production formats. Used when
# config/lanes.json is missing or corrupt so the daemon never crashes on config.
FALLBACK_LANE_DOCUMENTS: Final[tuple[dict[str, Any], ...]] = (
    {
        "id": "moku-scp-shorts",
        "channel": "moku",
        "story_type": "scp",
        "orientation": "vertical",
        "duration": {"min_sec": 60, "target_sec": 150, "max_sec": 180},
        "words": {"min": 160, "max": 340, "recondense_max": 300},
        "template": "shorts_creepypasta",
        "voice_rate": "+0%",
        "voice_profile": "scp_documentary_es",
        "cadence": {"min_gap_seconds": 300, "initial_offset_seconds": 0},
        "sources": {
            "kind": "reddit",
            "subreddits": ["SCP", "SCPDeclassified", "nosleep"],
            "listing_categories": [["hot", "day"], ["top", "week"], ["new", "all"]],
        },
        "background_audio": {"enabled": True, "volume": 0.04, "mode": "auto", "theme": "scp"},
    },
    {
        "id": "moku-horror-long",
        "channel": "moku",
        "story_type": "horror",
        "orientation": "horizontal",
        "duration": {"min_sec": 600, "target_sec": 600, "max_sec": 1800},
        "words": {"min": 2600, "max": 4800, "recondense_max": 4500},
        "template": "creepypasta",
        "voice_rate": "+0%",
        "voice_profile": "moku_terror",
        "cadence": {"min_gap_seconds": 1800, "initial_offset_seconds": 0},
        "sources": {
            "kind": "reddit",
            "subreddits": ["nosleep", "scarystories", "darktales", "libraryofshadows"],
        },
        "multistory_collection": True,
        "visual_pipeline": "director",
        "background_audio": {"enabled": True, "volume": 0.04, "mode": "auto", "theme": "cosmic_horror"},
    },
    {
        "id": "aelithia-aita-long",
        "channel": "aelithia",
        "story_type": "reddit_aita",
        "orientation": "horizontal",
        "duration": {"min_sec": 600, "target_sec": 600, "max_sec": 1800},
        "words": {"min": 2600, "max": 4800, "recondense_max": 4500},
        "template": "aita",
        "voice_rate": "+6%",
        "voice_profile": "aelithia_reddit",
        "cadence": {"min_gap_seconds": 1800, "initial_offset_seconds": 0},
        "sources": {
            "kind": "reddit",
            "subreddits": [
                "AmItheAsshole",
                "TrueOffMyChest",
                "relationship_advice",
                "Confession",
            ],
        },
        "multistory_collection": True,
        "visual_pipeline": "director",
        "background_audio": {"enabled": True, "volume": 0.04, "mode": "auto", "theme": "drama"},
    },
)


@dataclass(frozen=True)
class LaneSources:
    kind: str = "reddit"
    subreddits: tuple[str, ...] = ()
    listing_categories: tuple[tuple[str, str], ...] = (("hot", "day"), ("top", "week"))
    limit_per_fetch: int = 25
    queue_target_pending: int = 25


@dataclass(frozen=True)
class LaneBackgroundAudioConfig:
    enabled: bool = True
    volume: float = 0.04
    mode: str = "auto"
    theme: str = "default"
    ducking_db: float = -18.0


@dataclass(frozen=True)
class LaneProfile:
    """Immutable editorial contract for one production lane."""

    id: str
    channel: CanonicalChannel | str
    story_type: str
    orientation: str
    duration_min_sec: int
    duration_target_sec: int
    duration_max_sec: int
    words_min: int
    words_max: int | None
    words_recondense_max: int
    template: str
    voice_rate: str
    cadence_min_gap_seconds: int
    cadence_initial_offset_seconds: int = 0
    sources: LaneSources = field(default_factory=LaneSources)
    background_audio: LaneBackgroundAudioConfig = field(default_factory=LaneBackgroundAudioConfig)
    enabled: bool = True
    multistory_collection: bool = False
    visual_pipeline: str = "beats"
    qa_profile: str = ""
    review_content_type: str = ""
    topic_filter_mode: str = "off"
    topic_filter_keywords: tuple[str, ...] = ()
    padding_themes: tuple[str, ...] = ()
    voice_profile: str | None = None
    fps: int = 30

    # -- derived properties -------------------------------------------------

    @property
    def expected_resolution(self) -> tuple[int, int]:
        return ALLOWED_RESOLUTIONS[self.orientation]

    @property
    def ass_playres(self) -> tuple[int, int]:
        return self.expected_resolution

    @property
    def word_budget(self) -> tuple[int, int | None]:
        return (self.words_min, self.words_max)

    @property
    def thumb_sizes(self) -> tuple[tuple[int, int], ...]:
        if self.orientation == "vertical":
            return ((1080, 1920), (720, 1280))
        return ((1920, 1080), (1280, 720))

    def with_overrides(self, overrides: Mapping[str, Any]) -> "LaneProfile":
        """Return a copy with top-level fields replaced (editorial overlay)."""
        allowed = {f for f in self.__dataclass_fields__ if not f.startswith("_")}
        clean = {k: v for k, v in dict(overrides).items() if k in allowed}
        return replace(self, **clean) if clean else self


def _require(mapping: Mapping[str, Any], key: str, lane_id: str) -> Any:
    if key not in mapping:
        raise ValueError(f"Lane '{lane_id}': falta el campo obligatorio '{key}'")
    return mapping[key]


def _positive_int(value: Any, lane_id: str, key: str) -> int:
    number = int(value)
    if number <= 0:
        raise ValueError(f"Lane '{lane_id}': '{key}' debe ser un entero positivo")
    return number


def parse_lane(raw: Mapping[str, Any]) -> LaneProfile:
    """Validate one raw lane document into a LaneProfile."""
    lane_id = str(_require(raw, "id", "")).strip()
    if not lane_id:
        raise ValueError("Lane sin 'id'")
    channel_raw = _require(raw, "channel", lane_id)
    ch = canonical_channel(str(channel_raw))
    channel_key = getattr(ch, "value", str(ch))

    orientation = str(_require(raw, "orientation", lane_id)).strip().lower()
    if orientation not in ALLOWED_RESOLUTIONS:
        raise ValueError(
            f"Lane '{lane_id}': orientación inválida {orientation!r} "
            f"(válidas: {sorted(ALLOWED_RESOLUTIONS)})"
        )

    duration = _require(raw, "duration", lane_id)
    min_sec = _positive_int(duration.get("min_sec", 60), lane_id, "duration.min_sec")
    target_sec = _positive_int(
        duration.get("target_sec", min_sec), lane_id, "duration.target_sec"
    )
    max_sec = _positive_int(
        duration.get("max_sec", target_sec), lane_id, "duration.max_sec"
    )
    if not (min_sec <= target_sec <= max_sec):
        raise ValueError(
            f"Lane '{lane_id}': duración incoherente "
            f"(min={min_sec}, target={target_sec}, max={max_sec})"
        )

    words = raw.get("words") or {}
    words_min = _positive_int(words.get("min", 160), lane_id, "words.min")
    words_max_raw = words.get("max")
    words_max = (
        None if words_max_raw is None else _positive_int(words_max_raw, lane_id, "words.max")
    )
    recondense_max = _positive_int(
        words.get("recondense_max", max(words_min, 300)), lane_id, "words.recondense_max"
    )
    if words_max is not None and words_max < words_min:
        raise ValueError(f"Lane '{lane_id}': words.max < words.min")

    cadence = raw.get("cadence") or {}
    gap = _positive_int(
        cadence.get("min_gap_seconds", 1800), lane_id, "cadence.min_gap_seconds"
    )
    if gap < MIN_GAP_SECONDS:
        raise ValueError(
            f"Lane '{lane_id}': min_gap_seconds ({gap}s) por debajo del mínimo operativo "
            f"({MIN_GAP_SECONDS}s)"
        )
    initial_offset_raw = cadence.get("initial_offset_seconds", 0)
    try:
        initial_offset = int(initial_offset_raw)
        if initial_offset < 0:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError(
            f"Lane '{lane_id}': 'cadence.initial_offset_seconds' debe ser un entero no negativo"
        )

    sources_raw = raw.get("sources") or {}
    kind = str(sources_raw.get("kind", "reddit")).strip().lower()
    if kind not in ALLOWED_SOURCE_KINDS:
        raise ValueError(f"Lane '{lane_id}': source kind inválida {kind!r}")
    categories_raw = sources_raw.get("listing_categories") or [("hot", "day"), ("top", "week")]
    listing_categories = tuple(
        (str(pair[0]).strip().lower(), str(pair[1]).strip().lower())
        for pair in categories_raw
        if isinstance(pair, (list, tuple)) and len(pair) == 2
    ) or (("hot", "day"), ("top", "week"))

    story_type = str(raw.get("story_type", "horror")).strip().lower()
    if story_type not in ALLOWED_STORY_TYPES:
        raise ValueError(f"Lane '{lane_id}': story_type inválida {story_type!r}")

    visual_pipeline = str(raw.get("visual_pipeline", "beats")).strip().lower()
    if visual_pipeline not in ALLOWED_VISUAL_PIPELINES:
        raise ValueError(f"Lane '{lane_id}': visual_pipeline inválido {visual_pipeline!r}")

    filter_raw = raw.get("topic_filter") or {}
    filter_mode = str(filter_raw.get("mode", "off")).strip().lower()
    if filter_mode not in {"off", "keyword"}:
        raise ValueError(f"Lane '{lane_id}': topic_filter.mode inválido {filter_mode!r}")

    qa_profile = str(raw.get("qa_profile", "")).strip() or (
        "short" if orientation == "vertical" else "longform"
    )
    review_content_type = str(raw.get("review_content_type", "")).strip() or (
        "short" if orientation == "vertical" else "long_video"
    )

    sources = LaneSources(
        kind=kind,
        subreddits=tuple(str(s).strip() for s in sources_raw.get("subreddits", ()) if str(s).strip()),
        listing_categories=listing_categories,
        limit_per_fetch=_positive_int(
            sources_raw.get("limit_per_fetch", 25), lane_id, "sources.limit_per_fetch"
        ),
        queue_target_pending=_positive_int(
            sources_raw.get("queue_target_pending", 25),
            lane_id,
            "sources.queue_target_pending",
        ),
    )

    bg_audio_raw = raw.get("background_audio") or {}
    bg_audio = LaneBackgroundAudioConfig(
        enabled=bool(bg_audio_raw.get("enabled", True)),
        volume=float(bg_audio_raw.get("volume", 0.04)),
        mode=str(bg_audio_raw.get("mode", "auto")).strip().lower(),
        theme=str(bg_audio_raw.get("theme", story_type)).strip().lower(),
        ducking_db=float(bg_audio_raw.get("ducking_db", -18.0)),
    )

    return LaneProfile(
        id=lane_id,
        channel=canonical_channel(channel_key),
        story_type=story_type,
        orientation=orientation,
        duration_min_sec=min_sec,
        duration_target_sec=target_sec,
        duration_max_sec=max_sec,
        words_min=words_min,
        words_max=words_max,
        words_recondense_max=recondense_max,
        template=str(_require(raw, "template", lane_id)).strip(),
        voice_rate=str(raw.get("voice_rate", "+0%")).strip(),
        cadence_min_gap_seconds=gap,
        cadence_initial_offset_seconds=initial_offset,
        sources=sources,
        background_audio=bg_audio,
        enabled=bool(raw.get("enabled", True)),
        multistory_collection=bool(raw.get("multistory_collection", False)),
        visual_pipeline=visual_pipeline,
        qa_profile=qa_profile,
        review_content_type=review_content_type,
        topic_filter_mode=filter_mode,
        topic_filter_keywords=tuple(
            str(k).strip() for k in filter_raw.get("keywords", ()) if str(k).strip()
        ),
        padding_themes=tuple(
            str(t).strip() for t in raw.get("padding_themes", ()) if str(t).strip()
        ),
        voice_profile=(str(raw["voice_profile"]).strip() or None) if raw.get("voice_profile") else None,
        fps=_positive_int(raw.get("fps", 30), lane_id, "fps"),
    )


def fallback_lanes() -> tuple[LaneProfile, ...]:
    """Build the built-in lanes matching today's production behaviour."""
    return tuple(parse_lane(doc) for doc in FALLBACK_LANE_DOCUMENTS)


def load_lanes(
    path: str | os.PathLike[str] | None = None,
    *,
    include_disabled: bool = False,
) -> tuple[LaneProfile, ...]:
    """Load and validate lanes from JSON; fall back to built-ins fail-safe.

    The result is cached per resolved path + mtime so daemon ticks stay cheap;
    a corrupt or absent file logs an ERROR and returns the embedded lanes
    instead of raising (the daemon must never die because of configuration).
    """
    global _LANES_CACHE
    resolved = Path(path or DEFAULT_LANES_PATH)

    try:
        stat = resolved.stat()
        # mtime alone is insufficient: two writes within one timestamp tick
        # (typical in tests) must not serve a stale document.
        cache_key = f"{resolved}|{stat.st_mtime_ns}|{stat.st_size}|{include_disabled}"
    except OSError:
        cache_key = f"{resolved}|missing|{include_disabled}"

    if _LANES_CACHE is not None and _LANES_CACHE[0] == cache_key:
        return _LANES_CACHE[1]

    try:
        document = json.loads(resolved.read_text(encoding="utf-8"))
        lanes_raw = document.get("lanes")
        if not isinstance(lanes_raw, list) or not lanes_raw:
            raise ValueError("El documento debe contener una lista 'lanes' no vacía")
        parsed: list[LaneProfile] = []
        seen_ids: set[str] = set()
        for item in lanes_raw:
            lane = parse_lane(item)
            if lane.id in seen_ids:
                raise ValueError(f"ID de lane duplicado: {lane.id}")
            seen_ids.add(lane.id)
            parsed.append(lane)
        if include_disabled:
            result = tuple(parsed)
        else:
            result = tuple(lane for lane in parsed if lane.enabled)
        disabled_count = len(parsed) - len(result)
        if disabled_count and not include_disabled:
            logger.info("Lanes deshabilitados por configuración: %d", disabled_count)
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.error(
            "config/lanes.json inválido o ausente (%s); usando carriles embebidos", exc
        )
        result = fallback_lanes()

    _LANES_CACHE = (cache_key, result)
    return result


_LANES_CACHE: tuple[str, tuple[LaneProfile, ...]] | None = None


def get_lane(lane_id: str, *, path: str | os.PathLike[str] | None = None) -> LaneProfile | None:
    wanted = str(lane_id or "").strip()
    canonical = LANE_ALIASES.get(wanted, wanted)
    for lane in load_lanes(path):
        if lane.id in (wanted, canonical):
            return lane
    return None


def lanes_for_channel(
    channel: str | CanonicalChannel, *, path: str | os.PathLike[str] | None = None
) -> tuple[LaneProfile, ...]:
    ch = canonical_channel(channel)
    channel_key = getattr(ch, "value", str(ch))
    return tuple(
        lane
        for lane in load_lanes(path)
        if getattr(lane.channel, "value", str(lane.channel)) == channel_key
    )


def resolve_lane_for_run(
    channel: str | CanonicalChannel,
    lane_id: str | None = None,
    *,
    story_row: Mapping[str, Any] | None = None,
    path: str | os.PathLike[str] | None = None,
) -> LaneProfile:
    """Resolve which lane governs this run.

    Priority: explicit ``lane_id`` → the story's persisted ``lane_id`` → the
    first enabled lane of the channel. Raises ValueError only when nothing
    compatible exists (misconfiguration), never silently picks a wrong format.
    """
    channel_key = canonical_channel(channel)
    channel_str = getattr(channel_key, "value", str(channel_key))
    wanted = str(lane_id or "").strip()

    available = lanes_for_channel(channel_key, path=path)
    if not available:
        disabled = tuple(
            lane
            for lane in load_lanes(path, include_disabled=True)
            if getattr(lane.channel, "value", str(lane.channel)) == channel_str
        )
        if wanted and disabled:
            available = disabled
        else:
            raise ValueError(f"Sin carriles configurados para el canal {channel_str!r}")

    if wanted:
        if any(char in wanted for char in (";", "&", "|", "`", "$", ">", "<", "\n", "\r")):
            raise ValueError(f"Identificador de carril inválido o sospechoso: {wanted!r}")
        canonical = LANE_ALIASES.get(wanted, wanted)
        for lane in available:
            if lane.id in (wanted, canonical):
                return lane
        raise ValueError(
            f"El carril {wanted!r} no existe o no pertenece al canal "
            f"{channel_str!r}; válidos: {[lane.id for lane in available]}"
        )

    story_lane = ""
    if story_row is not None:
        story_lane = str(story_row.get("lane_id") or "").strip()
    if story_lane:
        canonical_story = LANE_ALIASES.get(story_lane, story_lane)
        for lane in available:
            if lane.id in (story_lane, canonical_story):
                return lane
        logger.warning(
            "La historia guarda lane_id=%r pero ya no existe en la configuración; "
            "usando el carril por defecto del canal",
            story_lane,
        )

    return available[0]


DEFAULT_VOICE_PROFILES_PATH = os.environ.get(
    "VOICE_PROFILES_CONFIG_PATH", "config/voice_profiles.json"
)

_VOICE_PROFILES_CACHE: tuple[str, dict[str, Any]] | None = None


def load_voice_profiles(
    path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Load editorial voice profiles from config/voice_profiles.json."""
    global _VOICE_PROFILES_CACHE
    resolved = Path(path or DEFAULT_VOICE_PROFILES_PATH)
    try:
        stat = resolved.stat()
        cache_key = f"{resolved}|{stat.st_mtime_ns}|{stat.st_size}"
    except OSError:
        cache_key = f"{resolved}|missing"

    if _VOICE_PROFILES_CACHE is not None and _VOICE_PROFILES_CACHE[0] == cache_key:
        return _VOICE_PROFILES_CACHE[1]

    fallback = {
        "editorial_profiles": {
            "scp_documentary_es": {"approved_voices": [{"id": "es-ES-AlvaroNeural"}]},
            "moku_terror": {"approved_voices": [{"id": "es-ES-AlvaroNeural"}]},
            "aelithia_reddit": {"approved_voices": [{"id": "es-MX-DaliaNeural"}]},
        }
    }

    try:
        document = json.loads(resolved.read_text(encoding="utf-8"))
        result = document if isinstance(document, dict) else fallback
    except Exception as exc:
        logger.debug(
            "config/voice_profiles.json no cargado (%s); usando fallbacks", exc
        )
        result = fallback

    _VOICE_PROFILES_CACHE = (cache_key, result)
    return result


def resolve_voice_profile_for_lane(
    lane: LaneProfile | str | None = None,
    channel: str | CanonicalChannel | None = None,
    *,
    voice_profiles_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Resolve the full voice profile configuration dictionary for a lane or channel."""
    profiles = load_voice_profiles(voice_profiles_path).get("editorial_profiles", {})

    profile_name = None
    ch_key = None

    if isinstance(lane, LaneProfile):
        profile_name = lane.voice_profile
        ch_key = getattr(lane.channel, "value", str(lane.channel))
        if not profile_name:
            if lane.story_type == "scp":
                profile_name = "scp_documentary_es"
            elif ch_key == "aelithia" or lane.story_type == "reddit_aita":
                profile_name = "aelithia_reddit"
            elif ch_key == "scifi" or lane.story_type == "scifi":
                profile_name = "scifi_documentary_es"
            else:
                profile_name = "moku_terror"
    elif isinstance(lane, str) and lane.strip():
        if lane in profiles:
            profile_name = lane
        else:
            resolved_lane = get_lane(lane)
            if resolved_lane:
                return resolve_voice_profile_for_lane(
                    resolved_lane, channel, voice_profiles_path=voice_profiles_path
                )
            if "scp" in lane.lower():
                profile_name = "scp_documentary_es"
            elif "aelithia" in lane.lower() or "aita" in lane.lower():
                profile_name = "aelithia_reddit"
            elif "scifi" in lane.lower() or "singularity" in lane.lower():
                profile_name = "scifi_documentary_es"
            else:
                profile_name = "moku_terror"

    if not ch_key and channel is not None:
        ch = canonical_channel(channel)
        ch_key = getattr(ch, "value", str(ch))

    if not profile_name:
        if ch_key == "aelithia":
            profile_name = "aelithia_reddit"
        elif ch_key == "scifi":
            profile_name = "scifi_documentary_es"
        else:
            profile_name = "moku_terror"

    profile_data = profiles.get(profile_name) or {}
    approved = profile_data.get("approved_voices") or []
    if (
        approved
        and isinstance(approved, list)
        and isinstance(approved[0], dict)
        and approved[0].get("id")
    ):
        res = dict(approved[0])
        res["profile_name"] = profile_name
        return res

    if ch_key == "aelithia":
        fallback_voice = os.environ.get("AELITHIA_TTS_VOICE", "es-MX-DaliaNeural")
        return {
            "id": fallback_voice,
            "speed": "+6%",
            "pitch": "+0Hz",
            "volume": "+0%",
            "pauses": "conversational",
            "profile_name": profile_name,
        }
    fallback_voice = os.environ.get("MOKU_TTS_VOICE", "es-ES-AlvaroNeural")
    return {
        "id": fallback_voice,
        "speed": "+0%",
        "pitch": "-2Hz" if profile_name == "moku_terror" else "+0Hz",
        "volume": "+0%",
        "pauses": "clinical" if profile_name == "scp_documentary_es" else "dramatic",
        "profile_name": profile_name,
    }


def resolve_voice_for_lane(
    lane: LaneProfile | str | None = None,
    channel: str | CanonicalChannel | None = None,
    *,
    voice_profiles_path: str | os.PathLike[str] | None = None,
) -> str:
    """Resolve the preferred TTS voice ID for a lane or channel based on config/voice_profiles.json."""
    prof = resolve_voice_profile_for_lane(
        lane, channel, voice_profiles_path=voice_profiles_path
    )
    return str(prof.get("id") or "es-ES-AlvaroNeural")

