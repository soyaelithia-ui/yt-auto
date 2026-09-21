"""Topic filter engine for lane-based content ingestion and routing.

Evaluates story titles, contents, and metadata against lane criteria,
keyword lists, thematic archetypes, and negative filters.
"""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING, Sequence

from src.log import get_logger

if TYPE_CHECKING:
    from src.core.lanes import LaneProfile

logger = get_logger("topic_filter")

# Default keyword archetypes mapped by story_type
STORY_TYPE_DEFAULT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "scp": (
        "scp",
        "scp-",
        "anomal",
        "contención",
        "contencion",
        "containment",
        "fundación",
        "fundacion",
        "foundation",
        "keter",
        "euclid",
        "safe",
        "thaumiel",
        "apollyon",
        "objeto anómalo",
        "objeto analogo",
        "procedimiento especial",
        "clase de objeto",
        "d-class",
        "site-",
        "instalación",
    ),
    "reddit_aita": (
        "aita",
        "wibta",
        "soy el malo",
        "soy la mala",
        "am i the asshole",
        "asshole",
        "familia",
        "boda",
        "herencia",
        "hermano",
        "hermana",
        "esposo",
        "esposa",
        "novio",
        "novia",
        "suegra",
        "suegro",
        "divorcio",
        "infidelidad",
        "propiedad",
        "dinero",
        "traición",
    ),
    "horror": (
        "miedo",
        "terror",
        "monstruo",
        "bosque",
        "pesadilla",
        "muerte",
        "sangre",
        "oscuridad",
        "creepypasta",
        "paranormal",
        "fantasma",
        "criatura",
        "horror",
        "creepy",
        "dark",
        "woods",
        "demonio",
        "maldición",
        "aparición",
        "sombra",
        "entierro",
        "cementerio",
        "sótano",
        "ático",
    ),
    "reddit_generic": (
        "historia",
        "relato",
        "experiencia",
        "secreto",
        "anecdota",
        "vida",
    ),
}

# Negative spam / non-narrative filters
DISALLOWED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\b(?:crypto|bitcoin|nft|airdrop|giveaway|casino|promocode)\b"),
    re.compile(r"(?i)\b(?:onlyfans|fansly|escort|camgirl)\b"),
)


def remove_accents(text: str) -> str:
    """Normalize text removing diacritics / accents for robust matching."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_text_for_matching(text: str) -> str:
    """Lowercase and strip diacritics from text for case- and accent-insensitive matching."""
    if not text:
        return ""
    cleaned = remove_accents(text.lower().strip())
    replaced = re.sub(r"[^\w\s\-]", " ", cleaned)
    return re.sub(r"\s+", " ", replaced).strip()


def get_default_keywords_for_story_type(story_type: str) -> tuple[str, ...]:
    """Retrieve default keyword catalog for a given story_type."""
    st = str(story_type or "").strip().lower()
    return STORY_TYPE_DEFAULT_KEYWORDS.get(st, STORY_TYPE_DEFAULT_KEYWORDS["horror"])


def matches_keywords(text: str, keywords: Sequence[str]) -> bool:
    """Test whether text matches any of the provided keywords (case/accent-insensitive)."""
    if not text or not keywords:
        return False
    norm_text = normalize_text_for_matching(text)
    for kw in keywords:
        kw_norm = normalize_text_for_matching(kw)
        if not kw_norm:
            continue
        if " " in kw_norm or "-" in kw_norm:
            if kw_norm in norm_text:
                return True
        else:
            pattern = rf"\b{re.escape(kw_norm)}"
            if re.search(pattern, norm_text):
                return True
    return False


def count_keyword_matches(text: str, keywords: Sequence[str]) -> int:
    """Count how many distinct keywords appear in text."""
    if not text or not keywords:
        return 0
    norm_text = normalize_text_for_matching(text)
    count = 0
    for kw in keywords:
        kw_norm = normalize_text_for_matching(kw)
        if not kw_norm:
            continue
        if " " in kw_norm or "-" in kw_norm:
            if kw_norm in norm_text:
                count += 1
        else:
            if re.search(rf"\b{re.escape(kw_norm)}", norm_text):
                count += 1
    return count


def score_story_relevance(title: str, content: str, keywords: Sequence[str]) -> float:
    """Calculate story relevance score (title matches weighted 3x)."""
    if not keywords:
        return 1.0
    title_matches = count_keyword_matches(title, keywords)
    content_matches = count_keyword_matches(content, keywords)
    return float(title_matches * 3.0 + content_matches * 1.0)


def filter_story_by_keywords(
    title: str,
    content: str,
    keywords: Sequence[str],
    min_matches: int = 1,
) -> bool:
    """Return True if total keyword matches across title and content >= min_matches."""
    if not keywords:
        return True
    title_norm = normalize_text_for_matching(title)
    content_norm = normalize_text_for_matching(content)
    combined = f"{title_norm} {content_norm}"
    matches = count_keyword_matches(combined, keywords)
    return matches >= min_matches


def is_story_appropriate_for_theme(title: str, content: str, story_type: str) -> bool:
    """Check whether a story matches the default thematic keywords for story_type."""
    keywords = get_default_keywords_for_story_type(story_type)
    return filter_story_by_keywords(title, content, keywords, min_matches=1)


def is_spam_or_disallowed(title: str, content: str) -> bool:
    """Check if title or content contains spam/crypto/prohibited terms."""
    full_text = f"{title}\n{content}"
    for pat in DISALLOWED_PATTERNS:
        if pat.search(full_text):
            return True
    return False


def filter_story_for_lane(
    title: str,
    content: str,
    lane: LaneProfile,
) -> bool:
    """Main topic filter evaluator for a story under a specific LaneProfile.

    Rules:
    1. Rejects stories with empty title or empty content.
    2. Rejects stories containing spam/disallowed content.
    3. If `lane.topic_filter_mode == 'off'`, accepts the story.
    4. If `lane.topic_filter_mode == 'keyword'`, requires matching either
       `lane.topic_filter_keywords` (if configured) or default keywords for `lane.story_type`.
    """
    if not title or not title.strip() or not content or not content.strip():
        return False

    if is_spam_or_disallowed(title, content):
        logger.info("TopicFilter: Story '%s' rejected by spam/disallowed filter", title[:50])
        return False

    mode = str(getattr(lane, "topic_filter_mode", "off")).strip().lower()
    if mode == "off":
        return True

    keywords = getattr(lane, "topic_filter_keywords", ())
    if not keywords:
        keywords = get_default_keywords_for_story_type(getattr(lane, "story_type", "horror"))

    matches = filter_story_by_keywords(title, content, keywords, min_matches=1)
    if not matches:
        logger.info(
            "TopicFilter: Story '%s' rejected for lane '%s' (no keyword match against %s)",
            title[:50],
            getattr(lane, "id", "unknown"),
            keywords[:5],
        )
    return matches
