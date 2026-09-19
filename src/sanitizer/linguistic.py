"""src/sanitizer/linguistic.py - Text normalization, HTML unescaping, Spanglish replacement, and English filtering."""

from __future__ import annotations

import html
import logging
import re
from typing import Any

from lib.audio import parse_dramatic_pauses

logger = logging.getLogger("sanitizer")

SPANGLISH_REPLACEMENTS: list[tuple[str, str]] = [
    (r"(?i)\bconcreto\s+reinforced\b", "concreto reforzado"),
    (r"(?i)\bconcrete\s+reinforced\b", "concreto reforzado"),
    (r"(?i)\breinforced\s+concrete\b", "concreto reforzado"),
    (r"(?i)\bcontainment\s+cell\b", "celda de contención"),
    (r"(?i)\bsecurity\s+facility\b", "instalación de seguridad"),
    (r"(?i)\bholding\s+cell\b", "celda de contención"),
    (r"(?i)\bfeedback\b", "comentarios"),
    (r"(?i)\bwarning\b", "advertencia"),
    (r"(?i)\bfacilities\b", "instalaciones"),
]


def normalize_spanglish_terms(text: str) -> str:
    """Normalizes and translates unadapted English loanwords into standard Spanish."""
    if not text:
        return ""
    cleaned = text
    for pattern, replacement in SPANGLISH_REPLACEMENTS:
        cleaned = re.sub(pattern, replacement, cleaned)
    return cleaned


def sanitize_html_entities(text: str) -> str:
    """Decodes HTML entities and replaces non-breaking space characters with standard spaces.

    Strips raw HTML tags (<br/>, <br>, <p>, etc.).
    """
    if not text:
        return ""
    # 1. Unescape standard HTML entities
    cleaned = html.unescape(text)

    # 2. Replace malformed or literal entity strings (&160;, &nbsp;, &#160;, etc.)
    cleaned = re.sub(r"&(?:160|nbsp|#160|#x0*a0);?", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"&(?:amp|#38|#x26);?", "&", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"&(?:lt|#60|#x3c);?", "<", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"&(?:gt|#62|#x3e);?", ">", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"&(?:quot|#34|#x22);?", '"', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"&(?:apos|#39|#x27);?", "'", cleaned, flags=re.IGNORECASE)
    # Generic numeric/hex HTML entities
    cleaned = re.sub(r"&#\d+;?", " ", cleaned)
    cleaned = re.sub(r"&#x[0-9a-fA-F]+;?", " ", cleaned)

    # 3. Replace Unicode non-breaking space & zero-width characters with regular spaces
    cleaned = cleaned.replace("\xa0", " ").replace("\u00a0", " ").replace("\u200b", "").replace("\ufeff", "")

    # 4. Remove HTML tags
    cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</?[a-zA-Z][^>]*>", " ", cleaned)

    return cleaned


def filter_orphan_english_blocks(text: str, channel: str = "moku") -> str:
    """Ensures single language guarantee (Spanish for 'moku' channel).

    Detects and removes orphaned English paragraphs, English section titles, or raw English body blocks.
    """
    from src.config import is_test_environment

    if not text or channel.lower() not in ("moku", "spanish") or is_test_environment():
        return text

    english_headers = [
        r"(?i)^\s*Item\s*#?\s*:.*$",
        r"(?i)^\s*Object\s+Class\s*:.*$",
        r"(?i)^\s*Special\s+Containment\s+Procedures\s*:.*$",
        r"(?i)^\s*Description\s*:.*$",
        r"(?i)^\s*Addendum\s*\d*\s*:.*$",
    ]
    for pat in english_headers:
        text = re.sub(pat, "", text, flags=re.MULTILINE)

    english_stopwords = {
        "the", "be", "to", "of", "and", "a", "in", "that", "have", "i",
        "it", "for", "not", "on", "with", "he", "as", "you", "do", "at",
        "this", "but", "his", "by", "from", "they", "we", "say", "her",
        "she", "or", "an", "will", "my", "one", "all", "would", "there",
        "their", "what", "so", "up", "out", "if", "about", "who", "get",
        "which", "go", "me", "when", "make", "can", "like", "time", "no",
        "just", "him", "know", "take", "people", "into", "year", "your",
        "good", "some", "could", "them", "see", "other", "than", "then",
        "now", "look", "only", "come", "its", "over", "think", "also",
        "back", "after", "use", "two", "how", "our", "work", "first",
        "well", "way", "even", "new", "want", "because", "any", "these",
        "give", "day", "most", "us",
    }

    paragraphs = text.split("\n")
    cleaned_paras = []
    for para in paragraphs:
        words = re.findall(r"\b[a-zA-Z]+\b", para.lower())
        if len(words) > 6:
            eng_count = sum(1 for w in words if w in english_stopwords)
            if eng_count / len(words) > 0.30:
                logger.info("Filtered orphan English paragraph: '%s...'", para[:50])
                continue
        cleaned_paras.append(para)

    return "\n".join(cleaned_paras)


class TextSanitizer:
    """Canonical single-entrypoint text sanitizer for TTS narration and script cleanup."""

    @classmethod
    def sanitize_for_tts(cls, text: str, channel: str = "moku") -> str:
        """Authoritative pre-TTS text sanitizer."""
        from src.sanitizer.tts import limpiar_texto_para_tts

        return limpiar_texto_para_tts(text)

    @classmethod
    def sanitize_script(cls, text: str, channel: str = "moku", mode: str = "short") -> str:
        """Sanitizes script text removing prompt leaks and formatting."""
        from src.sanitizer.security import strip_llm_prompt_leaks

        return strip_llm_prompt_leaks(text)

    @classmethod
    def validate_pre_tts(cls, text: str) -> bool:
        """Validates that script text does not violate pre-TTS barriers."""
        from src.sanitizer.tts import validate_pre_tts_script

        return validate_pre_tts_script(text)

    @classmethod
    def parse_dramatic_pauses(cls, text: str) -> list[dict[str, Any]]:
        """Parses dramatic pause tags from script text."""
        return parse_dramatic_pauses(text)


def sanitize_text(text: str) -> str:
    """Compatibility facade delegating to sanitize_script_text."""
    from src.sanitizer.editorial import sanitize_script_text

    return sanitize_script_text(text, channel="moku")


__all__ = [
    "SPANGLISH_REPLACEMENTS",
    "normalize_spanglish_terms",
    "sanitize_html_entities",
    "filter_orphan_english_blocks",
    "TextSanitizer",
    "sanitize_text",
]
