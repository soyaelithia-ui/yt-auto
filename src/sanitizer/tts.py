"""src/sanitizer/tts.py - Pre-TTS cleaning, ASS subtitle stripping, and audio speech readiness."""

from __future__ import annotations

import re
from typing import Optional

from src.sanitizer.security import (
    PromptLeakError,
    PROMPT_LEAK_PATTERNS,
    validate_semantic_barrier,
)

ORDINAL_OR_ROMAN = (
    r"(?:"
    r"\d+"
    r"|primero|primera|segundo|segunda|tercero|tercera|cuarto|cuarta|quinto|quinta|"
    r"sexto|sexta|s[eé]ptimo|s[eé]ptima|septimo|septima|octavo|octava|noveno|novena|"
    r"d[eé]cimo|d[eé]cima|decimo|decima|und[eé]cimo|und[eé]cima|undecimo|undecima|"
    r"duod[eé]cimo|duod[eé]cima|duodecimo|duodecima"
    r"|\b(?:(?:[xX][cC]|[xX][lL]|[lL]?[xX]{1,3})(?:[iI][vVxX]|[vV]?[iI]{0,3})|[lL](?:[iI][vVxX]|[vV]?[iI]{0,3})|[iI][vVxX]|[vV]?[iI]{1,3}|[vV])\b"
    r")"
)

# Centralized compiled module-level regex patterns
RE_ASS_TAGS = re.compile(r"\{\\[^}]*\}")
RE_CODE_BLOCKS = re.compile(r"```[\w]*\n?")
RE_MARKDOWN_LINKS = re.compile(r"\[([^\]]+)\]\([^\)]+\)")
RE_URLS = re.compile(r"(?:https?://|www\.)\S+")
RE_MARKDOWN_HEADERS = re.compile(r"(?i)^[>*\s]*#+\s*[^\n]*", flags=re.MULTILINE)
RE_MARKDOWN_BOLD = re.compile(r"\*\*(.+?)\*\*")
RE_MARKDOWN_ITALIC = re.compile(r"\*(.+?)\*")
RE_MARKDOWN_CHARS = re.compile(r"[#>`~|]")
RE_MARKDOWN_CHARS_ALL = re.compile(r"[#>{}\[\]~`|]")
RE_STRUCTURAL_HEADERS_PREFIX = re.compile(
    r"(?i)^[>*\s#]*(?:secci[óo]n|cap[íi]tulo|parte|bloque|fase|paso)\s+" + ORDINAL_OR_ROMAN + r"(?:\s*[:.-]|\s+)",
    flags=re.MULTILINE,
)
RE_STRUCTURAL_HEADERS_LINE = re.compile(
    r"(?i)^[>*\s#]*(?:secci[óo]n|cap[íi]tulo|parte|bloque|fase|paso)\s+" + ORDINAL_OR_ROMAN + r"[:.-]?\s*$",
    flags=re.MULTILINE,
)
RE_STRUCTURAL_HEADERS_INLINE = re.compile(
    r"(?i)\b(?:secci[óo]n|cap[íi]tulo)\s+" + ORDINAL_OR_ROMAN + r"[:.-]?"
)
RE_CHAPTER_HEADER_LINE = re.compile(r"(?i)###?\s*cap[íi]tulo\s*\d*[:.-]?[^\n]*")
RE_TITLE_PREFIX = re.compile(r"(?i)^\s*(?:t[íi]tulo|title)\s*[:：][^\n]*", flags=re.MULTILINE)
RE_TITLE_INLINE = re.compile(r"(?i)\b(?:t[íi]tulo|title)\s*[:：]\s*[^\n]*")
RE_ACT_CHAPTER_LABELS = re.compile(
    r"(?i)\b(?:acto|cap[ií]tulo|secci[oó]n|parte)\s+[a-záéíóú0-9IVXLCDMivxlcdm]+[:\.\-–—]\s*"
)
RE_ACT_CHAPTER_LINE = re.compile(
    r"(?im)^\s*(?:acto|cap[ií]tulo|secci[oó]n|parte)\s+[a-záéíóú0-9IVXLCDMivxlcdm]+[:\.\-–—]\s*"
)
RE_EDITORIAL_CUES = re.compile(
    r"(?i)\b(?:gancho\s+viral\s+inicial|remate\s+y\s+debate|remate\s+final|llamado\s+a\s+la\s+acci[óo]n)[:.-]?[^\n]*"
)
RE_SFX_CUES = re.compile(
    r"(?i)\[\s*(?:sonido|sfx|audio|m[uú]sica)[:\s][^\]]*\]"
)
RE_SFX_LINE = re.compile(
    r"(?i)^\s*(?:sonido|sfx)\s*(?:\d+\s*[:.-]|\s*[:.-])\s*[^\n]*",
    flags=re.MULTILINE,
)
RE_SFX_INLINE = re.compile(
    r"(?i)\b(?:sonido|sfx)\s+(?:\d+\s*[:.-]|\s*[:.-])\s*[^\n]*"
)


def strip_ass_tags(text: str | None) -> str:
    """Strip Advanced SubStation Alpha (ASS) formatting override tags (e.g. {\\k50}, {\\pos(x,y)})."""
    if not text:
        return ""
    return RE_ASS_TAGS.sub("", str(text))


def strip_act_chapter_headers(text: str | None) -> str:
    """Strip chapter, section, act, and title headers from text."""
    if not text:
        return ""
    cleaned = str(text)
    cleaned = RE_TITLE_PREFIX.sub("", cleaned)
    cleaned = RE_TITLE_INLINE.sub("", cleaned)
    cleaned = RE_MARKDOWN_HEADERS.sub("", cleaned)
    cleaned = RE_STRUCTURAL_HEADERS_PREFIX.sub("", cleaned)
    cleaned = RE_STRUCTURAL_HEADERS_LINE.sub("", cleaned)
    cleaned = RE_CHAPTER_HEADER_LINE.sub("", cleaned)
    cleaned = RE_STRUCTURAL_HEADERS_INLINE.sub("", cleaned)
    cleaned = RE_ACT_CHAPTER_LABELS.sub("", cleaned)
    cleaned = RE_ACT_CHAPTER_LINE.sub("", cleaned)
    return cleaned.strip()


def sanitize_scp_acronyms_for_tts(text: str | None) -> str:
    """Format technical SCP acronyms phonetically for clean neutral Spanish TTS."""
    if not text:
        return ""
    cleaned = str(text)
    cleaned = re.sub(r"\bSCP-(\d+)\b", r"S-C-P \1", cleaned)
    cleaned = re.sub(r"\bSCP\b", r"S-C-P", cleaned)
    cleaned = re.sub(r"\bBZHR\b", r"B-Z-H-R", cleaned)
    cleaned = re.sub(r"\bXACTS\b", r"X-ACTS", cleaned)
    cleaned = re.sub(r"\bO5\b", r"O-5", cleaned)
    cleaned = re.sub(r"\bXK\b", r"X-K", cleaned)
    return cleaned


def validate_pre_tts_script(text: str) -> bool:
    """Deterministic pre-TTS barrier checking script text before audio synthesis.

    Raises PromptLeakError if any instruction echo, preamble, meta-phrase, taboo pattern,
    or structural header / forbidden greeting is found.
    """
    if not text or not isinstance(text, str) or not text.strip():
        raise PromptLeakError("Pre-TTS barrier violation: script is empty, whitespace, or invalid")

    # Structural check on first lines & first sentences for explanatory/meta constructs
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if lines:
        first_line = lines[0]
        if re.match(
            r"(?i)^(?:vamos\s+a|voy\s+a|aqu[íi]|a\s+continuaci[óo]n|ahora\s+condensar|instrucciones|redacci[óo]n|adaptaci[óo]n)\b",
            first_line,
        ):
            raise PromptLeakError(f"Pre-TTS barrier violation: script starts with meta-introduction '{first_line[:40]}'")

    validate_semantic_barrier(text)

    # Check forbidden editorial elements (greetings, CTAs, farewells)
    from src.sanitizer.editorial import (
        CRINGE_INTRO_PATTERNS,
        LEGACY_BRANDING_PATTERNS,
        check_forbidden_editorial_elements,
    )

    forbidden_editorial = check_forbidden_editorial_elements(text)
    if forbidden_editorial:
        raise PromptLeakError(f"Pre-TTS barrier violation: detected forbidden editorial element '{forbidden_editorial}'")

    # Check legacy branding and cringe intro patterns
    for pat in LEGACY_BRANDING_PATTERNS + CRINGE_INTRO_PATTERNS:
        match = re.search(pat, text, flags=re.MULTILINE)
        if match:
            raise PromptLeakError(
                f"Pre-TTS barrier violation: detected legacy branding/cringe intro pattern '{match.group(0)}'"
            )

    for pat in PROMPT_LEAK_PATTERNS:
        match = re.search(pat, text)
        if match:
            raise PromptLeakError(f"Pre-TTS barrier violation: detected prompt leak pattern '{match.group(0)}'")

    # Check structural header leaks (Sección Primera:, Capítulo 1:, Título: ..., etc.)
    structural_header_check_patterns = [
        r"(?i)^[>*\s]*#+\s+[^\n]+",
        r"(?i)^[>*\s#]*(?:secci[óo]n|cap[íi]tulo|parte|bloque|fase|paso)\s+" + ORDINAL_OR_ROMAN + r"[:.-]",
        r"(?i)\b(?:secci[óo]n|cap[íi]tulo)\s+\d+[:.-]?",
        r"(?i)^\s*(?:t[íi]tulo|title)\s*[:：]",
        r"(?i)\b(?:gancho\s+viral\s+inicial|remate\s+y\s+debate|remate\s+final|llamado\s+a\s+la\s+acci[óo]n)[:.-]",
    ]
    for pat in structural_header_check_patterns:
        match = re.search(pat, text, flags=re.MULTILINE)
        if match:
            raise PromptLeakError(f"Pre-TTS barrier violation: detected structural header '{match.group(0)}'")

    return True


def standardize_timestamp_format(text: str) -> str:
    """Standardizes date and timestamp strings into TTS friendly format."""
    if not text:
        return ""

    def _sub_time(match: re.Match) -> str:
        date_part = match.group(1).strip()
        time_part = match.group(2)
        if time_part:
            return f"{date_part}, {time_part.strip()} horas"
        return f"{date_part}, 03:45 horas"

    pattern = r"(?i)\b(\d{1,2}\s+de\s+[a-záéíóúñ]+)(?:\s*[—–-]\s*|\s+)(?:(\d{1,2}:\d{2})\s*)?hrs\b"
    return re.sub(pattern, _sub_time, text)


def limpiar_texto_para_tts(text: str) -> str:
    """Cleans editorial tags, headers, SFX labels, and residual tokens for TTS."""
    if not text:
        return ""
    cleaned = str(text or "")

    # 0. Strip code blocks & fences and links
    cleaned = RE_CODE_BLOCKS.sub("", cleaned)
    cleaned = RE_MARKDOWN_LINKS.sub(r"\1", cleaned)
    cleaned = RE_URLS.sub("", cleaned)

    # 1. Remove markdown headers and section titles like ### Capítulo 1:, Sección Primera:, etc.
    cleaned = RE_MARKDOWN_HEADERS.sub("", cleaned)
    cleaned = RE_STRUCTURAL_HEADERS_PREFIX.sub("", cleaned)
    cleaned = RE_STRUCTURAL_HEADERS_LINE.sub("", cleaned)
    cleaned = RE_CHAPTER_HEADER_LINE.sub("", cleaned)
    cleaned = RE_STRUCTURAL_HEADERS_INLINE.sub("", cleaned)

    # 2. Remove topic title markers (e.g. "Título: ...", "Title: ...")
    cleaned = RE_TITLE_PREFIX.sub("", cleaned)
    cleaned = RE_TITLE_INLINE.sub("", cleaned)

    # 3. Remove legacy / forbidden conversational greetings
    from src.sanitizer.editorial import (
        CRINGE_INTRO_PATTERNS,
        LEGACY_BRANDING_PATTERNS,
        sanitize_script_text,
    )

    for pattern in LEGACY_BRANDING_PATTERNS + CRINGE_INTRO_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(
        r"(?i)\b(?:hoy\s+les\s+traigo(?:\s+una\s+historia)?|hoy\s+veremos|hoy\s+vamos\s+a\s+ver|hoy\s+hablaremos\s+de|esta\s+es\s+una\s+historia\s+de\s+terror)\b[^\n.!?]*[.!?]?",
        "",
        cleaned,
    )

    # 4. Remove editorial cues & stage directions
    cleaned = RE_EDITORIAL_CUES.sub("", cleaned)

    # 5. Remove SFX cues like [Sonido: ...] or Sonido 1: ...
    cleaned = RE_SFX_CUES.sub("", cleaned)
    cleaned = RE_SFX_LINE.sub("", cleaned)
    cleaned = RE_SFX_INLINE.sub("", cleaned)

    # 6. Sanitize general script text
    cleaned = sanitize_script_text(cleaned, channel="moku")

    # 7. Clean trailing residual single characters like dangling 'm'
    cleaned = re.sub(r"\s+[a-zA-Z]\s*$", "", cleaned)
    # Strip markdown blockquote and stray hashes/backticks/tildes
    cleaned = re.sub(r"^[>\s]+", "", cleaned, flags=re.MULTILINE)
    cleaned = RE_MARKDOWN_CHARS.sub("", cleaned)
    return cleaned.strip()


def validate_beat_format(script_text: str) -> bool:
    """Delegates beat format validation to src.curators.beats."""
    from src.curators.beats import validate_beat_format as _validate

    return _validate(script_text)


__all__ = [
    "ORDINAL_OR_ROMAN",
    "RE_ASS_TAGS",
    "RE_CODE_BLOCKS",
    "RE_MARKDOWN_LINKS",
    "RE_URLS",
    "RE_MARKDOWN_HEADERS",
    "RE_MARKDOWN_BOLD",
    "RE_MARKDOWN_ITALIC",
    "RE_MARKDOWN_CHARS",
    "RE_MARKDOWN_CHARS_ALL",
    "RE_STRUCTURAL_HEADERS_PREFIX",
    "RE_STRUCTURAL_HEADERS_LINE",
    "RE_STRUCTURAL_HEADERS_INLINE",
    "RE_CHAPTER_HEADER_LINE",
    "RE_TITLE_PREFIX",
    "RE_TITLE_INLINE",
    "RE_ACT_CHAPTER_LABELS",
    "RE_ACT_CHAPTER_LINE",
    "RE_EDITORIAL_CUES",
    "RE_SFX_CUES",
    "RE_SFX_LINE",
    "RE_SFX_INLINE",
    "strip_ass_tags",
    "strip_act_chapter_headers",
    "sanitize_scp_acronyms_for_tts",
    "validate_pre_tts_script",
    "standardize_timestamp_format",
    "limpiar_texto_para_tts",
    "validate_beat_format",
]
