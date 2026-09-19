"""src/sanitizer/editorial.py - Editorial rule enforcement, brand/channel isolation, and repair."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from src.sanitizer.security import PROMPT_LEAK_PATTERNS

logger = logging.getLogger("sanitizer")

LEGACY_BRANDING_PATTERNS: list[str] = [
    r'(?i)^\s*(?:[*#_\~\s]*)(?:¡|¿)?(?:Hola,?\s*|Bienvenidos a?\s*|Te damos la bienvenida a?\s*)(?:está?s en|a)?\s*[\w\-.]+\b\s*[,.\n!?:=\-\*\s]*',
    r'(?i)^\s*(?:[*#_\~\s]*)(?:¡|¿)?(?:Hola|Bienvenidos|Bienvenido|Te damos la bienvenida)\b[^\n!?:=]*[,.\n!?:=\-\*\s]*',
    r'(?i)Apaga las luces y escucha con atenció?n\.\.\.?',
]

CRINGE_INTRO_PATTERNS: list[str] = [
    r'(?i)^\s*(?:[*#_\~\s]*)(?:¡|¿)?Atenció?n\b'
    r'(?:\s*[,:\-]\s*|\s+)'
    r'(?:'
        r'(?:a\s+todo\s+el\s+personal|a\s+todos?\s+los(?:\s+(?:agentes|miembros|personal))?|gente|personal(?:\s+de\s+seguridad)?|agentes|miembros)'
        r'(?:\s*(?:de\s+(?:la\s+|el\s+)?|del\s+)?(?:Fundació?n(?:\s+SCP)?|SCP(?:[-\s]?\d+)?|SCP))?'
        r'|'
        r'(?:de\s+(?:la\s+|el\s+)?|del\s+)(?:Fundació?n(?:\s+SCP)?|SCP(?:[-\s]?\d+)?|SCP)'
    r')'
    r'\s*[,.\n!?:=\-\*\s]*',
    r'(?i)^\s*(?:[*#_\~\s]*)(?:¡|¿)?(?:Bienvenido|Bienvenidos|Hola|Te\s+damos\s+la\s+bienvenida)\b'
    r'\s+(?:a\s+(?:este|un|el|los)|al)\s+'
    r'(?:nuevo\s+)?(?:expediente|archivo|reporte|análisis|analisis|relato)\b'
    r'(?:\s*(?:de\s+(?:la\s+|el\s+)?|del\s+)?(?:Fundació?n(?:\s+SCP)?|SCP(?:[-\s]?\d+)?|SCP))?'
    r'\s*[,.\n!?:=\-\*\s]*',
    r'(?i)^\s*(?:[*#_\~\s]*)(?:¡|¿)?Lo\s+que\s+está?s\s+a\s+punto\s+de\s+escuchar\s+en\s+este\s+(?:expediente|relato|archivo)\s*[,.\n!?:=\-\*\s]*',
    r'(?i)^\s*(?:[*#_\~\s]*)(?:¡|¿)?Hola\s+(?:a\s+todos|fanáticos|fanaticos|seguidores|comunidad)\b\s*[,.\n!?:=\-\*\s]*',
]

FORBIDDEN_EDITORIAL_PATTERNS: list[str] = [
    r'(?i)\b(?:hola|saludos|bienvenidos|bienvenido|te\s+damos\s+la\s+bienvenida)\b',
    r'(?i)\b(?:hoy\s+les\s+traigo|hoy\s+veremos|hoy\s+vamos\s+a\s+ver|hoy\s+hablaremos\s+de|esta\s+es\s+una\s+historia\s+de\s+terror)\b',
    r'(?i)\b(?:suscr[íi]bete|suscribirte|dale\s+a?\s+like|deja\s+tu\s+like|deja\s+un\s+comentario|comenta\s+abajo|s[íi]guenos)\b',
    r'(?i)\b(?:hasta\s+el\s+pr[óo]ximo|nos\s+vemos\s+en|hasta\s+la\s+pr[óo]xima|chao|adi[óo]s)\b',
    r'(?i)\b(?:HISTORIA\s+DE\s+TERROR|VIDEO\s+DE\s+MIEDO|ALGO\s+ATERRADOR)\b',
    r'(?i)\b(?:todos\s+los\s+)?(?:expedientes|archivos|relatos)\s+(?:y\s+(?:archivos|grabaciones)\s+)?(?:se\s+encuentran|permanecen\s+archivados)\s+(?:bajo\s+estricta\s+custodia\s+)?en\s+@?[\w\-.]+\b',
    r'(?i)\b(?:permanecen\s+archivados|se\s+encuentran\s+archivados)\s+bajo\s+estricta\s+custodia\b',
    r'(?i)\b(?:este|nuestro|mi|tu)\s+canal\b',
    r'(?i)\b(?:este|el|mi)\s+v[íi]deo\b',
    r'(?i)\bel\s+episodio\s+de\s+hoy\b',
    r'(?i)\bcanal\s+de\s+youtube\b',
    r'(?i)@[\w\-.]+\b',
    r'(?i)\b\w+\s+Reddit\b',
]

_FILE_RULES_CACHE: Optional[list] = None


def _editorial_patterns() -> list:
    global _FILE_RULES_CACHE
    if _FILE_RULES_CACHE is None:
        file_rules: list = []
        try:
            candidate_paths = [
                Path(__file__).resolve().parent.parent.parent / "config" / "editorial_rules.json",
                Path(__file__).resolve().parent.parent / "config" / "editorial_rules.json",
                Path("config/editorial_rules.json"),
            ]
            rules_path = next((p for p in candidate_paths if p.exists()), None)
            if rules_path and rules_path.exists():
                data = json.loads(rules_path.read_text(encoding="utf-8")) or {}
                for item in data.get("forbidden_extra", []) or []:
                    compiled = re.compile(str(item))
                    file_rules.append(compiled.pattern)
        except Exception as exc:  # noqa: BLE001 - barrier must never break on config
            logger.warning("editorial_rules.json ignorado: %s", exc)
        _FILE_RULES_CACHE = file_rules

    dynamic_channel_patterns: list = []
    distinctive_proper_nouns = {"moku", "aelithia", "singularidad sci-fi", "singularidad scifi", "singularidad sci fi"}
    try:
        from src.core.channel_profile import ChannelProfileRegistry

        ChannelProfileRegistry._ensure_loaded()
        channels = (
            list(ChannelProfileRegistry._cache.values())
            if hasattr(ChannelProfileRegistry, "_cache") and ChannelProfileRegistry._cache
            else ChannelProfileRegistry.list_active_channels()
        )
        for ch in channels:
            name = ch.editorial.public_name.strip() if ch.editorial and ch.editorial.public_name else ""
            handle = ch.editorial.handle.lstrip("@").strip() if ch.editorial and ch.editorial.handle else ""
            if name:
                dynamic_channel_patterns.append(rf"(?i)\b{re.escape(name)}\s*Reddit\b")
                dynamic_channel_patterns.append(rf"(?i)\b(?:en|de|del|por|canal|bienvenidos\s+a)\s+{re.escape(name)}\b")
                dynamic_channel_patterns.append(rf"(?i)\bsoy\s+{re.escape(name)}\b")
                if name.lower() in distinctive_proper_nouns:
                    dynamic_channel_patterns.append(rf"(?i)\b{re.escape(name)}\b")
            if handle:
                dynamic_channel_patterns.append(rf"(?i)@?{re.escape(handle)}\b")
    except Exception:
        pass

    for brand_pattern in (
        r"(?i)\bMoku\b",
        r"(?i)\bAelithia\b",
        r"(?i)\bSingularidad\s+Sci[-\s]?Fi\b",
        r"(?i)\b(?:bienvenidos\s+a|canal(?:\s+de)?|soy(?:\s+de)?)\s+Singularidad\b",
        r"(?i)@?SingularidadSciFi\b",
        r"(?i)@?MokuRedit\b",
        r"(?i)@?Aelithia-c1f\b",
    ):
        if brand_pattern not in dynamic_channel_patterns:
            dynamic_channel_patterns.append(brand_pattern)

    return FORBIDDEN_EDITORIAL_PATTERNS + _FILE_RULES_CACHE + dynamic_channel_patterns


_COMPILED_EDITORIAL_CACHE: Optional[list[re.Pattern]] = None


def _get_compiled_editorial_patterns() -> list[re.Pattern]:
    global _COMPILED_EDITORIAL_CACHE
    if _COMPILED_EDITORIAL_CACHE is not None:
        return _COMPILED_EDITORIAL_CACHE
    patterns = _editorial_patterns()
    compiled: list[re.Pattern] = []
    for pat in patterns:
        try:
            compiled.append(re.compile(pat))
        except re.error:
            pass
    _COMPILED_EDITORIAL_CACHE = compiled
    return _COMPILED_EDITORIAL_CACHE


def check_forbidden_editorial_elements(text: str) -> Optional[str]:
    """Checks if text contains forbidden greetings, CTAs, farewells, or generic horror phrases."""
    if not text:
        return None
    for pat in _get_compiled_editorial_patterns():
        match = pat.search(text)
        if match:
            return match.group(0)
    return None


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")


def repair_forbidden_editorial(text: str) -> tuple[str, list[str]]:
    """Deterministically drop every sentence containing a forbidden element."""
    if not text:
        return text, []
    sentences = _SENTENCE_SPLIT.split(text)
    kept: list[str] = []
    removed: list[str] = []
    for sentence in sentences:
        if check_forbidden_editorial_elements(sentence):
            removed.append(sentence.strip())
        else:
            kept.append(sentence)
    repaired = " ".join(part.strip() for part in kept if part.strip())
    return repaired, removed


PREAMBLE_PATTERN = (
    r"^(?:(?:luego|ahora),?\s*sigue:?\s*|"
    r"(?:vamos|voy)\s+a\s+redactar:?\s*|"
    r"se ha mantenido[^.\n!?:=]*[.\n!?:=]*|"
    r"a continuación[^.\n!?:=]*[.\n!?:=]*|"
    r"traducción completa[^.\n!?:=]*[.\n!?:=]*|"
    r"aquí (?:tienes|está)(?:\s+(?:un|una|la|el))?\s*(?:video|traducción|historia|relato|narración|guion|versión|con)?[^.\n!?:=]*[.\n!?:=]*|"
    r"claro,?\s*aquí[^.\n!?:=]*[.\n!?:=]*|"
    r"por supuesto,?[^.\n!?:=]*[.\n!?:=]*|"
    r"here is[^.\n!?:=]*[.\n!?:=]*|"
    r"here\'s[^.\n!?:=]*[.\n!?:=]*)\s*"
)

MARKDOWN_HEADER_PREAMBLE = r"^\s*(?:\*\*)?(?:Traducción|Guion|Relato|Versión|Aquí tienes|Nota|Instrucciones)(?:\*\*)?\s*:\s*"

POSTAMBLE_PATTERNS: list[str] = [
    r'(?i)\b¿?necesitas\s+(?:que\s+haga\s+)?algo\s+más\??',
    r'(?i)\b¿?necesitas\s+hacer\s+[^?.\n]+\??',
    r'(?i)\b¿?quieres\s+que\s+(?:modifique|ajuste|cambie)[^?.\n]+\??',
    r'(?i)\b¿?hay\s+algo\s+más\s+in\s+what\s+I\s+can\s+help\s+you\??',
    r'(?i)\b¿?hay\s+algo\s+más\s+en\s+lo\s+que\s+(?:pueda|te\s+pueda)\s+ayudar\??',
    r'(?i)\b¿?aví?same\s+si\s+necesitas\s+[^?.\n]+',
    r'(?i)\bespero\s+que\s+(?:esta\s+traducció?n|este\s+relato|el\s+guion)[^.\n!]*[.\n!]*',
    r'(?i)\bsi\s+tienes\s+alguna\s+(?:duda|pregunta)[^.\n!]*[.\n!]*',
]


def sanitize_llm_script(raw_text: str, mode: str = "short") -> str:
    """Sanitizes raw LLM script output by removing system prompt leaks, preambles, and clutter."""
    if not raw_text or not isinstance(raw_text, str):
        return ""

    cleaned = raw_text

    # 1. Strip legacy branding intros and cringe SCP greetings
    all_intro_patterns = LEGACY_BRANDING_PATTERNS + CRINGE_INTRO_PATTERNS
    for pattern in all_intro_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.MULTILINE)

    # 3. Strip URLs, markdown links, and edit footnotes
    cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"(?:https?://|www\.)\S+", "", cleaned)
    cleaned = re.sub(r"(?i)(?:\n\s*\n|\n|^|(?<=\.))\s*Edit\s*(?:[-:\d]+\s*:?|:)\s*[^.!?\n]*[.!?]?", "", cleaned)
    cleaned = re.sub(r"(?i)\bThanks for (?:the )?gold\b[^.!?\n]*[.!?]?", "", cleaned)

    # 4. Strip conversational preambles
    cleaned = re.sub(PREAMBLE_PATTERN, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(MARKDOWN_HEADER_PREAMBLE, "", cleaned, flags=re.IGNORECASE)

    # 5. Strip conversational postambles
    for pattern in POSTAMBLE_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned)

    # 6. Line-by-line filtering of system prompt instruction leaks & monologues
    lines = cleaned.split("\n")
    filtered_lines = []
    for line in lines:
        stripped_line = line.strip()
        skip_line = False
        for leak_pattern in PROMPT_LEAK_PATTERNS:
            if re.search(leak_pattern, stripped_line):
                skip_line = True
                break
        if skip_line:
            continue

        line_clean = re.sub(r"^(?:(?:Luego|Primero|Empieza por)\s+[^:]+:\s*)", "", line, flags=re.IGNORECASE)
        filtered_lines.append(line_clean)

    cleaned = "\n".join(filtered_lines)

    # 7. Whitespace normalization
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned)
    return cleaned.strip()


def suppress_title_repetition(text: str, title: str, max_allowed: int = 2) -> str:
    """Suppresses mechanical repetition of the exact story title string across paragraphs."""
    if not text or not title or len(title.strip()) < 5:
        return text

    pattern = re.compile(re.escape(title.strip()), re.IGNORECASE)
    matches = list(pattern.finditer(text))
    if len(matches) <= max_allowed:
        return text

    replacements = [
        "este suceso",
        "este conflicto",
        "esta situación",
        "los hechos narrados",
        "lo ocurrido",
    ]

    result = []
    last_idx = 0
    count = 0
    for match in matches:
        start, end = match.span()
        result.append(text[last_idx:start])
        count += 1
        if count <= max_allowed:
            result.append(text[start:end])
        else:
            rep = replacements[(count - max_allowed - 1) % len(replacements)]
            result.append(rep)
        last_idx = end
    result.append(text[last_idx:])
    return "".join(result)


def sanitize_script_text(text: str, channel: str = "moku") -> str:
    """Complete Script Sanitizer Engine."""
    if not text or not isinstance(text, str):
        return ""

    from src.sanitizer.linguistic import (
        filter_orphan_english_blocks,
        normalize_spanglish_terms,
        sanitize_html_entities,
    )
    from src.sanitizer.security import strip_llm_prompt_leaks
    from src.sanitizer.tts import (
        RE_CHAPTER_HEADER_LINE,
        RE_MARKDOWN_HEADERS,
        RE_STRUCTURAL_HEADERS_INLINE,
        RE_STRUCTURAL_HEADERS_LINE,
        RE_STRUCTURAL_HEADERS_PREFIX,
    )

    # 1. HTML entities & unicode unescape
    cleaned = sanitize_html_entities(text)

    # 2. Filter orphan English blocks
    cleaned = filter_orphan_english_blocks(cleaned, channel=channel)

    # 3. Strip prompt leaks and monologues
    cleaned = strip_llm_prompt_leaks(cleaned)

    # 4. Strip leftover timecodes while preserving timestamps
    cleaned = re.sub(r"\[\d{1,2}:\d{2}(?::\d{2})?\](?!\s*horas?\b|\s*hrs?\b)", "", cleaned)
    cleaned = re.sub(r"\(\d{1,2}:\d{2}(?::\d{2})?\)(?!\s*horas?\b|\s*hrs?\b)", "", cleaned)

    # 5. Fix split accented syllables
    cleaned = re.sub(r"(\b\w+í)\s+a\b", r"\1a", cleaned)
    cleaned = re.sub(r"(\b\w+í)\s+as\b", r"\1as", cleaned)
    cleaned = re.sub(r"(\b\w+í)\s+an\b", r"\1an", cleaned)
    cleaned = re.sub(r"(\b\w+í)\s+amos\b", r"\1amos", cleaned)
    cleaned = re.sub(r"(\b\w+ó)\s+n\b", r"\1n", cleaned)

    # 6. Strip markdown headers and unbracketed structural headers
    cleaned = RE_MARKDOWN_HEADERS.sub("", cleaned)
    cleaned = RE_STRUCTURAL_HEADERS_PREFIX.sub("", cleaned)
    cleaned = RE_STRUCTURAL_HEADERS_LINE.sub("", cleaned)
    cleaned = RE_CHAPTER_HEADER_LINE.sub("", cleaned)
    cleaned = RE_STRUCTURAL_HEADERS_INLINE.sub("", cleaned)

    # 7. Normalize spanglish loanwords
    cleaned = normalize_spanglish_terms(cleaned)

    # 8. Normalize whitespace
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned)
    return cleaned.strip()


__all__ = [
    "LEGACY_BRANDING_PATTERNS",
    "CRINGE_INTRO_PATTERNS",
    "FORBIDDEN_EDITORIAL_PATTERNS",
    "PREAMBLE_PATTERN",
    "MARKDOWN_HEADER_PREAMBLE",
    "POSTAMBLE_PATTERNS",
    "_FILE_RULES_CACHE",
    "_editorial_patterns",
    "_COMPILED_EDITORIAL_CACHE",
    "_get_compiled_editorial_patterns",
    "check_forbidden_editorial_elements",
    "_SENTENCE_SPLIT",
    "repair_forbidden_editorial",
    "sanitize_llm_script",
    "suppress_title_repetition",
    "sanitize_script_text",
]
