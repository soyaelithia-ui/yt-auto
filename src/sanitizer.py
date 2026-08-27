"""
src/sanitizer.py - Script Sanitizer & System Prompt Leak Cleaner Engine for YTShort.

Filters system prompt instruction echoes, preambles, meta-commentary, markdown noise,
and legacy channel intros.
"""

import html
import logging
import re
from typing import Optional, Any, Dict, List

from lib.audio import (
    parse_dramatic_pauses,
    extract_dramatic_pauses,
    strip_dramatic_pauses,
)

logger = logging.getLogger("sanitizer")

class PromptLeakError(Exception):
    """Raised when a system prompt leak or taboo phrase is detected in script output."""
    pass


TABOO_BARRIER_PATTERNS = [
    r'(?i)El usuario (?:quiere|pide|solicita|busca|dio)',
    r'(?i)Aqu[íi] (?:tienes|est[áa]) (?:tu|el) guion',
    r'(?i)tono documental',
    r'(?i)sin etiquetas',
    r'(?i)sin headers',
    r'(?i)para el locutor',
    r'(?i)describir la criatura',
    r'(?i)reglas obligatorias',
    r'(?i)guion para locutor',
    r'(?i)texto del locutor',
    r'(?i)system prompt',
    r'(?i)espero que (?:te|les) (?:sirva|guste)',
    r'(?i)fin del (?:guion|relato|expediente)',
    r'(?i)Ahora,?\s+condensar(?:[ée]|\w*)?',
    r'(?i)condensar toda la historia',
    r'(?i)sin relleno',
    r'(?i)mantener la tensi[óo]n',
    r'(?i)primero la primera parte',
    r'(?i)luego la segunda parte',
    r'(?i)curaci[óo]n de guio?n',
    r'(?i)resumen de la historia',
    r'(?i)en resumen',
    r'(?i)vamos\s+a\s+redactar',
    r'(?i)voy\s+a\s+redactar',
    r'(?i)a\s+continuaci[óo]n',
]


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


def validate_semantic_barrier(text: str) -> bool:
    """
    Validates text against taboo semantic leak phrases.
    Raises PromptLeakError if any taboo phrase is found.
    Returns True if valid.
    """
    if not text:
        return True
    for pat in TABOO_BARRIER_PATTERNS:
        match = re.search(pat, text)
        if match:
            raise PromptLeakError(f"Semantic barrier violation: detected taboo phrase '{match.group(0)}'")
    return True


def validate_pre_tts_script(text: str) -> bool:
    """
    Deterministic pre-TTS barrier that checks script text before audio synthesis.
    Raises PromptLeakError if any instruction echo, preamble, meta-phrase, taboo pattern,
    or structural header / forbidden greeting is found.
    """
    if not text or not isinstance(text, str) or not text.strip():
        raise PromptLeakError("Pre-TTS barrier violation: script is empty, whitespace, or invalid")

    # Structural check on first lines & first sentences for explanatory/meta constructs
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if lines:
        first_line = lines[0]
        if re.match(r'(?i)^(?:vamos\s+a|voy\s+a|aqu[íi]|a\s+continuaci[óo]n|ahora\s+condensar|instrucciones|redacci[óo]n|adaptaci[óo]n)\b', first_line):
            raise PromptLeakError(f"Pre-TTS barrier violation: script starts with meta-introduction '{first_line[:40]}'")

    validate_semantic_barrier(text)

    # Check forbidden editorial elements (greetings, CTAs, farewells)
    forbidden_editorial = check_forbidden_editorial_elements(text)
    if forbidden_editorial:
        raise PromptLeakError(f"Pre-TTS barrier violation: detected forbidden editorial element '{forbidden_editorial}'")

    # Check legacy branding and cringe intro patterns
    for pat in LEGACY_BRANDING_PATTERNS + CRINGE_INTRO_PATTERNS:
        match = re.search(pat, text, flags=re.MULTILINE)
        if match:
            raise PromptLeakError(f"Pre-TTS barrier violation: detected legacy branding/cringe intro pattern '{match.group(0)}'")

    for pat in PROMPT_LEAK_PATTERNS:
        match = re.search(pat, text)
        if match:
            raise PromptLeakError(f"Pre-TTS barrier violation: detected prompt leak pattern '{match.group(0)}'")

    # Check structural header leaks (Sección Primera:, Capítulo 1:, Título: ..., etc.)
    structural_header_check_patterns = [
        r'(?i)^[>*\s]*#+\s+[^\n]+',
        r'(?i)^[>*\s#]*(?:secci[óo]n|cap[íi]tulo|parte|bloque|fase|paso)\s+' + ORDINAL_OR_ROMAN + r'[:.-]',
        r'(?i)\b(?:secci[óo]n|cap[íi]tulo)\s+\d+[:.-]?',
        r'(?i)^\s*(?:t[íi]tulo|title)\s*[:：]',
        r'(?i)\b(?:gancho\s+viral\s+inicial|remate\s+y\s+debate|remate\s+final|llamado\s+a\s+la\s+acci[óo]n)[:.-]',
    ]
    for pat in structural_header_check_patterns:
        match = re.search(pat, text, flags=re.MULTILINE)
        if match:
            raise PromptLeakError(f"Pre-TTS barrier violation: detected structural header '{match.group(0)}'")

    return True



# Comprehensive regex patterns for system prompt instruction echoes and model chatter
PROMPT_LEAK_PATTERNS = [
    # Explicit instruction lines / echoes
    r'(?i)MANTÉ?N EL 100%[^\n]*',
    r'(?i)prohibido resumir[^\n]*',
    r'(?i)resumir el texto[^\n]*',
    r'(?i)INSTRUCCION(?:ES)? DE ESTILO[^\n]*',
    r'(?i)INSTRUCCIÓ?N CRÍ?TICA[^\n]*',
    r'(?i)REGLAS ESTRUCTURALES[^\n]*',
    r'(?i)FORMATO DEL TEXTO[^\n]*',
    r'(?i)FORMATO DE ALTO IMPACTO[^\n]*',
    r'(?i)REGLAS DE ORO[^\n]*',
    r'(?i)DATOS DEL EXPEDIENTE[^\n]*',
    r'(?i)POSIBLE AMENAZA[^\n]*',
    r'(?i)CLASIFICACIÓN DE AMENAZA[^\n]*',
    r'(?i)^\s*contra-descripción[^\n]*',
    r'(?i)^\s*contra descripción[^\n]*',
    r'(?i)^\s*mecánica de la anomalía[^\n]*',
    r'(?i)^\s*nivel de amenaza[^\n]*',
    r'(?i)^\s*gancho de amenaza[^\n]*',
    r'(?i)cero historias ficticias[^\n]*',
    r'(?i)personajes inventados[^\n]*',
    r'(?i)^\s*reglas de contención[^\n]*',
    r'(?i)narración técnica oficial[^\n]*',
    r'(?i)guion para locutor[^\n]*',
    r'(?i)texto del locutor[^\n]*',
    r'(?i)Atención agentes[^\n]*',
    r'(?i)Atención personal[^\n]*',
    r'(?i)devuelve EXCLUSIVAMENTE[^\n]*',
    r'(?i)system prompt[^\n]*',
    r'(?i)el usuario (?:quiere|pide|solicita|busca|dio)[^\n]*',
    r'(?i)siguiendo las reglas[^\n]*',
    r'(?i)estilo oscuro[^\n]*',
    r'(?i)español neutro[^\n]*',
    r'(?i)solo el texto del relato[^\n]*',
    r'(?i)traducción fiel[^\n]*',
    r'(?i)mantener el sentido[^\n]*',
    r'(?i)^\s*(?:Wait,?\s*$|Wait,\s+|Oh,?\s*wait|Ah,?\s*wait|No,?\s*wait|No,?\s*no,\s+|Luego,?\s+seguir|Primero,?\s+aclara|Here is the script|Sure, here|Here\'s a script)[^\n]*',
    r'(?i)Inicia la narració?n INMEDIATAMENTE[^\n]*',
    r'(?i)Manté?n la tensió?n dramá?tica[^\n]*',
    r'(?i)Adapta la redacció?n a un españ?ol neutro[^\n]*',
    r'(?i)^\s*Está? estrictamente PROHIBIDO (?:resumir|inventar|modificar)[^\n]*',
    # Monologue / reasoning triggers
    r'(?i)perfecto,?\s*eso\s*es[^\n]*',
    r'(?i)primero\s+los\s+parámetros[^\n]*',
    r'(?i)revisar\s+que\s+el\s+español[^\n]*',
    r'(?i)se\s+logra\?[^\n]*',
    r'(?i)hook\s+es\s+impactante\?[^\n]*',
    r'(?i)vamos a ir parte por parte[^\n]*',
    r'(?i)primero,?\s+el\s+hook[^\n]*',
    r'(?i)revisar que el españ?ol[^\n]*',
    r'(?i)se nos olvida nada[^\n]*',
    r'(?i)luego,?\s+la\s+descripció?n[^\n]*',
    r'(?i)primero,?\s+la\s+mecá?nica[^\n]*',
    r'(?i)eso\s+es\s+(?:el|un)\s+gancho[^\n]*',
    r'(?i)gancho\s+de\s+0-1s[^\n]*',
    r'(?i)gancho\s+directo[^\n]*',
    r'(?i)descripció?n\s+té?cnica[^\n]*',
    r'(?i)luego la historia completa[^\n]*',
    r'(?i)luego la reacció?n[^\n]*',
    r'(?i)luego los pensamientos[^\n]*',
    r'(?i)luego\s+sigue:?[^\n]*',
    r'(?i)ahora\s+sigue:?[^\n]*',
    r'(?i)ahora,?\s+condensar[^\n]*',
    r'(?i)condensar toda la historia[^\n]*',
    r'(?i)primero la primera parte[^\n]*',
    r'(?i)luego la segunda parte[^\n]*',
    r'(?i)ahora\s+cuento\s+las\s+palabras[^\n]*',
    r'(?i)vamos\s+a\s+ver[^\n]*',
    r'(?i)vamos\s+a\s+contar:?[^\n]*',
    r'(?i)vamos\s+a\s+revisar:?[^\n]*',
    r'(?i)(?:\d+\.\s*[A-Za-záéíóúñÁÉÍÓÚÑ]+\s+){2,}[^\n]*',
]

# Legacy branding intros and intro greetings to strip
LEGACY_BRANDING_PATTERNS = [
    r'(?i)^\s*(?:[*#_\~\s]*)(?:¡|¿)?(?:Hola,?\s*|Bienvenidos a?\s*|Te damos la bienvenida a?\s*)?(?:está?s en|a)?\s*(?:Moku|Aelithia)\b\s*[,.\n!?:=\-\*\s]*',
    r'(?i)^\s*(?:[*#_\~\s]*)(?:¡|¿)?(?:Hola|Bienvenidos|Bienvenido|Te damos la bienvenida)\b[^\n!?:=]*[,.\n!?:=\-\*\s]*',
    r'(?i)Apaga las luces y escucha con atenció?n\.\.\.?',
]

# Cringe intro patterns and meta AI greetings to eliminate
CRINGE_INTRO_PATTERNS = [
    # "Atención, gente de la SCP...", "Atención personal de seguridad...", "Atención agentes...", "Atención a todo el personal..."
    r'(?i)^\s*(?:[*#_\~\s]*)(?:¡|¿)?Atenció?n\b'
    r'(?:\s*[,:\-]\s*|\s+)'
    r'(?:'
        r'(?:a\s+todo\s+el\s+personal|a\s+todos?\s+los(?:\s+(?:agentes|miembros|personal))?|gente|personal(?:\s+de\s+seguridad)?|agentes|miembros)'
        r'(?:\s*(?:de\s+(?:la\s+|el\s+)?|del\s+)?(?:Fundació?n(?:\s+SCP)?|SCP(?:[-\s]?\d+)?|SCP))?'
        r'|'
        r'(?:de\s+(?:la\s+|el\s+)?|del\s+)(?:Fundació?n(?:\s+SCP)?|SCP(?:[-\s]?\d+)?|SCP)'
    r')'
    r'\s*[,.\n!?:=\-\*\s]*',
    # "Bienvenidos a este expediente...", "Te damos la bienvenida a este archivo...", "¡Bienvenidos al expediente de SCP-173!"
    r'(?i)^\s*(?:[*#_\~\s]*)(?:¡|¿)?(?:Bienvenido|Bienvenidos|Hola|Te\s+damos\s+la\s+bienvenida)\b'
    r'\s+(?:a\s+(?:este|un|el|los)|al)\s+'
    r'(?:nuevo\s+)?(?:expediente|archivo|reporte|análisis|analisis|relato)\b'
    r'(?:\s*(?:de\s+(?:la\s+|el\s+)?|del\s+)?(?:Fundació?n(?:\s+SCP)?|SCP(?:[-\s]?\d+)?|SCP))?'
    r'\s*[,.\n!?:=\-\*\s]*',
    # "Lo que estás a punto de escuchar en este expediente..."
    r'(?i)^\s*(?:[*#_\~\s]*)(?:¡|¿)?Lo\s+que\s+está?s\s+a\s+punto\s+de\s+escuchar\s+en\s+este\s+(?:expediente|relato|archivo)\s*[,.\n!?:=\-\*\s]*',
    # Generic meta intro greetings
    r'(?i)^\s*(?:[*#_\~\s]*)(?:¡|¿)?Hola\s+(?:a\s+todos|fanáticos|fanaticos|seguidores|comunidad)\b\s*[,.\n!?:=\-\*\s]*',
]

# Strictly prohibited editorial elements (Greetings, CTAs, Farewells, Channel presentation)
FORBIDDEN_EDITORIAL_PATTERNS = [
    r'(?i)\b(?:hola|saludos|bienvenidos|bienvenido|te\s+damos\s+la\s+bienvenida)\b',
    r'(?i)\b(?:hoy\s+les\s+traigo|hoy\s+veremos|hoy\s+vamos\s+a\s+ver|hoy\s+hablaremos\s+de|esta\s+es\s+una\s+historia\s+de\s+terror)\b',
    r'(?i)\b(?:suscr[íi]bete|suscribirte|dale\s+a?\s+like|deja\s+tu\s+like|deja\s+un\s+comentario|comenta\s+abajo|s[íi]guenos)\b',
    r'(?i)\b(?:hasta\s+el\s+pr[óo]ximo|nos\s+vemos\s+en|hasta\s+la\s+pr[óo]xima|chao|adi[óo]s)\b',
    r'(?i)\b(?:HISTORIA\s+DE\s+TERROR|VIDEO\s+DE\s+MIEDO|ALGO\s+ATERRADOR)\b',
]

# Optional operator-extensible rules (config/editorial_rules.yaml). Falls back
# to the built-in list when the file is absent or invalid, so the barrier can
# never be weakened by a broken config.
_EXTRA_PATTERNS_CACHE: Optional[list] = None


def _editorial_patterns() -> list:
    global _EXTRA_PATTERNS_CACHE
    if _EXTRA_PATTERNS_CACHE is not None:
        return FORBIDDEN_EDITORIAL_PATTERNS + _EXTRA_PATTERNS_CACHE
    extra: list = []
    try:
        import json
        from pathlib import Path

        rules_path = Path(__file__).resolve().parent.parent / "config" / "editorial_rules.json"
        if rules_path.exists():
            data = json.loads(rules_path.read_text(encoding="utf-8")) or {}
            for item in data.get("forbidden_extra", []) or []:
                compiled = re.compile(str(item))
                extra.append(compiled.pattern)
    except Exception as exc:  # noqa: BLE001 - barrier must never break on config
        logging.getLogger(__name__).warning("editorial_rules.json ignorado: %s", exc)
    _EXTRA_PATTERNS_CACHE = extra
    return FORBIDDEN_EDITORIAL_PATTERNS + extra


def check_forbidden_editorial_elements(text: str) -> Optional[str]:
    """Checks if text contains forbidden greetings, CTAs, farewells, or generic horror phrases."""
    if not text:
        return None
    for pat in _editorial_patterns():
        match = re.search(pat, text)
        if match:
            return match.group(0)
    return None


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")


def repair_forbidden_editorial(text: str) -> tuple:
    """Deterministically drop every sentence containing a forbidden element.

    Returns ``(repaired_text, removed_sentences)``. Sentence boundaries are
    terminal punctuation followed by whitespace; the repair is surgical so the
    rest of the narration survives untouched.
    """
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


# LLM conversational response preambles
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

# Markdown header preambles like **Traducción:**, **Guion:**, etc.
MARKDOWN_HEADER_PREAMBLE = r"^\s*(?:\*\*)?(?:Traducción|Guion|Relato|Versión|Aquí tienes|Nota|Instrucciones)(?:\*\*)?\s*:\s*"

# LLM conversational response postambles
POSTAMBLE_PATTERNS = [
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
    """
    Sanitizes raw LLM script output by removing system prompt leaks, instruction echoes,
    preambles/postambles, markdown formatting clutter, and legacy branding intros.

    Args:
        raw_text: Raw text generated by LLM provider.
        mode: Curation mode - "long" for long videos, "short" for shorts/SCP format.

    Returns:
        Cleaned script string.
    """
    if not raw_text or not isinstance(raw_text, str):
        return ""

    cleaned = raw_text

    # 1. Strip legacy branding intros and cringe SCP greetings
    all_intro_patterns = LEGACY_BRANDING_PATTERNS + CRINGE_INTRO_PATTERNS
    for pattern in all_intro_patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.MULTILINE)

    # 3. Strip URLs, markdown links, and edit footnotes
    cleaned = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', cleaned)
    cleaned = re.sub(r'(?:https?://|www\.)\S+', '', cleaned)
    cleaned = re.sub(r'(?i)(?:\n\s*\n|\n|^|(?<=\.))\s*Edit\s*(?:[-:\d]+\s*:?|:)\s*[^.!?\n]*[.!?]?', '', cleaned)
    cleaned = re.sub(r'(?i)\bThanks for (?:the )?gold\b[^.!?\n]*[.!?]?', '', cleaned)

    # 4. Strip conversational preambles
    cleaned = re.sub(PREAMBLE_PATTERN, '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(MARKDOWN_HEADER_PREAMBLE, '', cleaned, flags=re.IGNORECASE)

    # 5. Strip conversational postambles
    for pattern in POSTAMBLE_PATTERNS:
        cleaned = re.sub(pattern, '', cleaned)

    # 6. Line-by-line filtering of system prompt instruction leaks & monologues
    lines = cleaned.split('\n')
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

        line_clean = re.sub(r'^(?:(?:Luego|Primero|Empieza por)\s+[^:]+:\s*)', '', line, flags=re.IGNORECASE)
        filtered_lines.append(line_clean)

    cleaned = '\n'.join(filtered_lines)

    # 7. Whitespace normalization
    cleaned = re.sub(r'[ \t]+', ' ', cleaned)
    cleaned = re.sub(r'\n\s*\n+', '\n\n', cleaned)
    return cleaned.strip()


def sanitize_html_entities(text: str) -> str:
    """
    Decodes HTML entities (&160;, &nbsp;, &amp;, &lt;, &gt;, &quot;, &#39;, &#160;, etc.)
    and replaces non-breaking space characters (\\xa0) with standard spaces.
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
    """
    Ensures single language guarantee (Spanish for 'moku' channel).
    Detects and removes orphaned English paragraphs, English section titles
    (e.g., 'Item #:', 'Object Class:', 'Special Containment Procedures:'),
    or raw English body blocks.
    """
    from src.config import is_test_environment
    if not text or channel.lower() not in ("moku", "spanish") or is_test_environment():
        return text

    # English header labels to strip
    english_headers = [
        r"(?i)^\s*Item\s*#?\s*:.*$",
        r"(?i)^\s*Object\s+Class\s*:.*$",
        r"(?i)^\s*Special\s+Containment\s+Procedures\s*:.*$",
        r"(?i)^\s*Description\s*:.*$",
        r"(?i)^\s*Addendum\s*\d*\s*:.*$",
    ]
    for pat in english_headers:
        text = re.sub(pat, "", text, flags=re.MULTILINE)

    # Common English words list for statistical block detection
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
        "give", "day", "most", "us"
    }

    paragraphs = text.split("\n")
    cleaned_paras = []
    for para in paragraphs:
        words = re.findall(r"\b[a-zA-Z]+\b", para.lower())
        if len(words) > 6:
            eng_count = sum(1 for w in words if w in english_stopwords)
            # If > 30% of words are English stopwords, reject as orphan English block
            if eng_count / len(words) > 0.30:
                logger.info(f"Filtered orphan English paragraph: '{para[:50]}...'")
                continue
        cleaned_paras.append(para)

    return "\n".join(cleaned_paras)


def sanitize_script_text(text: str, channel: str = "moku") -> str:
    """
    Complete Script Sanitizer Engine:
    1. Cleans HTML entities (&160;, &nbsp;, &amp;, <br/>) and unicode non-breaking spaces.
    2. Enforces single language guarantee (strips orphan English blocks for Spanish channels).
    3. Strips prompt leaks, system tags, markers ([BEAT 1], [0:22], line numbers) before TTS/subtitles.
    4. Strips structural section/chapter headers, markdown headers, and topic prefixes.
    5. Normalizes whitespace.
    """
    if not text or not isinstance(text, str):
        return ""

    # 1. HTML entities & unicode unescape
    cleaned = sanitize_html_entities(text)

    # 2. Filter orphan English blocks
    cleaned = filter_orphan_english_blocks(cleaned, channel=channel)

    # 3. Strip prompt leaks and monologues
    cleaned = strip_llm_prompt_leaks(cleaned)

    # 4. Strip leftover timecodes e.g. [0:22], [1:13], (00:22) while preserving timestamps like 03:45 horas
    cleaned = re.sub(r"\[\d{1,2}:\d{2}(?::\d{2})?\](?!\s*horas?\b|\s*hrs?\b)", "", cleaned)
    cleaned = re.sub(r"\(\d{1,2}:\d{2}(?::\d{2})?\)(?!\s*horas?\b|\s*hrs?\b)", "", cleaned)

    # 5. Fix split accented syllables (e.g. "regresarí a" -> "regresaría", "habí a" -> "había")
    cleaned = re.sub(r'(\b\w+í)\s+a\b', r'\1a', cleaned)
    cleaned = re.sub(r'(\b\w+í)\s+as\b', r'\1as', cleaned)
    cleaned = re.sub(r'(\b\w+í)\s+an\b', r'\1an', cleaned)
    cleaned = re.sub(r'(\b\w+í)\s+amos\b', r'\1amos', cleaned)
    cleaned = re.sub(r'(\b\w+ó)\s+n\b', r'\1n', cleaned)

    # 6. Strip markdown headers and unbracketed structural headers
    cleaned = re.sub(r"(?i)^[>*\s]*#+\s*[^\n]*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"(?i)^[>*\s#]*(?:secci[óo]n|cap[íi]tulo|parte|bloque|fase|paso)\s+" + ORDINAL_OR_ROMAN + r"(?:\s*[:.-]|\s+)", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"(?i)^[>*\s#]*(?:secci[óo]n|cap[íi]tulo|parte|bloque|fase|paso)\s+" + ORDINAL_OR_ROMAN + r"[:.-]?\s*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"(?i)###?\s*cap[íi]tulo\s*\d*[:.-]?[^\n]*", "", cleaned)
    cleaned = re.sub(r"(?i)\b(?:secci[óo]n|cap[íi]tulo)\s+" + ORDINAL_OR_ROMAN + r"[:.-]?", "", cleaned)

    # 7. Normalize spanglish loanwords
    cleaned = normalize_spanglish_terms(cleaned)

    # 8. Normalize whitespace
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned)
    return cleaned.strip()


SPANGLISH_REPLACEMENTS = [
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


def suppress_title_repetition(text: str, title: str, max_allowed: int = 2) -> str:
    """
    Suppresses mechanical repetition of the exact story title string across paragraphs.
    Preserves up to max_allowed occurrences; replaces subsequent occurrences with natural pronouns.
    """
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


class TextSanitizer:
    """Canonical single-entrypoint text sanitizer for TTS narration and script cleanup."""

    @classmethod
    def sanitize_for_tts(cls, text: str, channel: str = "moku") -> str:
        """
        Authoritative pre-TTS text sanitizer:
        1. Strips all structural headers (Sección primera, Capítulo 1, etc.).
        2. Strips markdown fences, hashes, asterisks, formatting tags.
        3. Normalizes timestamps and punctuation.
        4. Strips LLM reasoning, instruction leaks, and forbidden greetings.
        """
        return limpiar_texto_para_tts(text)

    @classmethod
    def sanitize_script(cls, text: str, channel: str = "moku", mode: str = "short") -> str:
        """Sanitizes script text removing prompts leaks and formatting."""
        return strip_llm_prompt_leaks(text)

    @classmethod
    def validate_pre_tts(cls, text: str) -> bool:
        """Validates that script text does not violate pre-TTS barriers."""
        return validate_pre_tts_script(text)

    @classmethod
    def parse_dramatic_pauses(cls, text: str) -> list[dict[str, Any]]:
        """Parses dramatic pause tags from script text."""
        return parse_dramatic_pauses(text)


def sanitize_text(text: str) -> str:
    """Compatibility facade delegating to sanitize_script_text."""
    return sanitize_script_text(text, channel="moku")


def standardize_timestamp_format(text: str) -> str:
    """Standardizes date and timestamp strings into TTS friendly format."""
    if not text:
        return ""
    # Pattern: 12 de noviembre [—] [19:45] hrs
    def _sub_time(match):
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
    cleaned = re.sub(r"```[\w]*\n?", "", cleaned)
    cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"(?:https?://|www\.)\S+", "", cleaned)

    # 1. Remove markdown headers and section titles like ### Capítulo 1:, Sección Primera:, etc.
    cleaned = re.sub(r"(?i)^[>*\s]*#+\s*[^\n]*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"(?i)^[>*\s#]*(?:secci[óo]n|cap[íi]tulo|parte|bloque|fase|paso)\s+" + ORDINAL_OR_ROMAN + r"(?:\s*[:.-]|\s+)", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"(?i)^[>*\s#]*(?:secci[óo]n|cap[íi]tulo|parte|bloque|fase|paso)\s+" + ORDINAL_OR_ROMAN + r"[:.-]?\s*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"(?i)###?\s*cap[íi]tulo\s*\d*[:.-]?[^\n]*", "", cleaned)
    cleaned = re.sub(r"(?i)\b(?:secci[óo]n|cap[íi]tulo)\s+" + ORDINAL_OR_ROMAN + r"[:.-]?", "", cleaned)

    # 2. Remove topic title markers (e.g. "Título: ...", "Title: ...")
    cleaned = re.sub(r"(?i)^\s*(?:t[íi]tulo|title)\s*[:：][^\n]*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"(?i)\b(?:t[íi]tulo|title)\s*[:：]\s*[^\n]*", "", cleaned)

    # 3. Remove legacy / forbidden conversational greetings
    for pattern in LEGACY_BRANDING_PATTERNS + CRINGE_INTRO_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"(?i)\b(?:hoy\s+les\s+traigo(?:\s+una\s+historia)?|hoy\s+veremos|hoy\s+vamos\s+a\s+ver|hoy\s+hablaremos\s+de|esta\s+es\s+una\s+historia\s+de\s+terror)\b[^\n.!?]*[.!?]?", "", cleaned)

    # 4. Remove editorial cues & stage directions
    cleaned = re.sub(r"(?i)\b(?:gancho\s+viral\s+inicial|remate\s+y\s+debate|remate\s+final|llamado\s+a\s+la\s+acci[óo]n)[:.-]?[^\n]*", "", cleaned)

    # 5. Remove SFX cues like [Sonido: ...] or Sonido 1: ...
    cleaned = re.sub(r"(?i)\[\s*(?:sonido|sfx|audio|m[uú]sica)[:\s][^\]]*\]", "", cleaned)
    cleaned = re.sub(r"(?i)^\s*(?:sonido|sfx)\s*(?:\d+\s*[:.-]|\s*[:.-])\s*[^\n]*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"(?i)\b(?:sonido|sfx)\s+(?:\d+\s*[:.-]|\s*[:.-])\s*[^\n]*", "", cleaned)

    # 6. Sanitize general script text
    cleaned = sanitize_script_text(cleaned, channel="moku")

    # 7. Clean trailing residual single characters like dangling 'm'
    cleaned = re.sub(r"\s+[a-zA-Z]\s*$", "", cleaned)
    # Strip markdown blockquote and stray hashes/backticks/tildes
    cleaned = re.sub(r"^[>\s]+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"[#>`~|]", "", cleaned)
    return cleaned.strip()


def validate_beat_format(script_text: str) -> bool:
    """Delegates beat format validation to src.curators.beats."""
    from src.curators.beats import validate_beat_format as _validate
    return _validate(script_text)
def extract_script_from_reasoning(text: str) -> str:
    """Extracts genuine narrative paragraphs and sentences from LLM responses containing reasoning monologues."""
    if not text:
        return ""
    # Strip <think>...</think> blocks
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)

    reasoning_patterns = [
        r'\bwait\b',
        r'\bno,?\s+espera\b',
        r'\bprimero,?\s+la clase',
        r'\bprimero,?\s+directamente',
        r'\bprimero,?\s+empiezo',
        r'\bprimero,?\s+abre',
        r'\basí que (?:empecemos|empiezo|tal vez)',
        r'por la primera frase',
        r'que nombre el objeto',
        r'amenaza letal inmediatamente',
        r'perfecto,?\s+eso es',
        r'primero los parámetros',
        r'parámetros físicos',
        r'lo puso el usuario',
        r'la dio el usuario',
        r'traducida correctamente',
        r'eso es correcto',
        r'apertura formal de la fundación',
        r'descripción física,?\s+tal cual',
        r'\bno (?:hay que )?agregar personajes',
        r'\bno inventar personajes',
        r'\bdramas secundarios',
        r'\bsolo lo oficial',
        r'^\s*sí,?\s+scp-',
        r'^\s*luego,?\s+(?:la|el|los|las)\s+(?:sección|parte|estructura|paso)\b',
        r'\bluego,?\s+el desencadenante',
        r'\bluego,?\s+el comportamiento',
        r'\bvamos a hacer que',
        r'\bhay que usar solo',
        r'\binformación canónica completa',
        r'el usuario (?:quiere|pide|solicita|busca|dio)',
        r'siguiendo las reglas',
        r'empiezo directo',
        r'primero,?\s+el segundo',
        r'regla \d',
        r'la historia tiene que ser',
        r'o sea,?\s+desde',
        r'por ejemplo,?\s+empieza',
        r'el guion es para un short',
        r'tono documental',
        r'sin etiquetas',
        r'sin headers',
        r'solo texto fluido',
        r'para el locutor',
        r'describir la criatura',
        r'espero que (?:te|les) (?:sirva|guste)',
        r'fin del (?:guion|relato|expediente)',
        r'nota:\s*',
        r'lista de reglas',
        r'reglas obligatorias',
        r':\s*(?:sí|ok|hecho)\.?$',
        r'\blo puse como\b',
        r'\bmantiene el sentido\b',
        r'\berror de (?:escritura|redacción)\b',
        r'\blee (?:bien|el contexto)\b',
        r'\bmira el contexto\b',
        r'^\s*(?:Luego,?\s+seguir|Primero,?\s+aclara|Oh,?\s*wait|Ah,?\s*wait|No,?\s*no)\b',
    ]

    lines = cleaned.split('\n')
    filtered_lines = []
    for line in lines:
        s_clean = line.strip()
        if not s_clean:
            filtered_lines.append("")
            continue
        is_reasoning = False
        for pat in reasoning_patterns:
            if re.search(pat, s_clean, re.IGNORECASE):
                is_reasoning = True
                break
        if not is_reasoning:
            filtered_lines.append(line)

    cleaned_str = '\n'.join(filtered_lines)
    cleaned_str = re.sub(r'\n\s*\n+', '\n\n', cleaned_str)
    return cleaned_str.strip()


def strip_llm_prompt_leaks(text: str) -> str:
    if not text:
        return ""
    # Strip <think>...</think> blocks
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    cleaned = re.sub(r'(?i)^(?:Luego,?\s+seguir|Primero,?\s+aclara|El usuario (?:quiere|pide)|INSTRUCCIONES?)[^:\n]*:\s*', '', cleaned, flags=re.MULTILINE)
    
    cleaned = extract_script_from_reasoning(cleaned)
    cleaned = sanitize_llm_script(cleaned, mode="short")
    # Strip prompt/beat bracket tags while preserving canonical SCP redactions ([DATOS BORRADOS], [REDACTADO])
    cleaned = re.sub(r'\[(?:BEAT|INTRO|HOOK|HEADER|PASO|REGLA|MÓDULO|SECCIÓN|PROMPT)[^\]]*\]', '', cleaned, flags=re.IGNORECASE)
    # Strip specific literal strings leaked from prompts
    cleaned = re.sub(r'(?i)SCP-\[N[uú]mero\]', '', cleaned)
    cleaned = re.sub(r'(?i)~?120-160\s*palabras?', '', cleaned)
    cleaned = re.sub(r'~?120-160', '', cleaned)
    cleaned = re.sub(r'(?i)REGLAS ESTRUCTURALES', '', cleaned)
    cleaned = re.sub(r'(?i)INSTRUCCI?ONES?', '', cleaned)
    cleaned = re.sub(r'(?i)FORMATO DE ALTO IMPACTO', '', cleaned)
    # Strip remaining intro meta phrases
    cleaned = re.sub(r'(?i)^[^\n.]*(?:el usuario quiere|tono documental|sin etiquetas|sin headers|texto fluido|para el locutor|describir la criatura:?)[^\n.]*[.\n]?', '', cleaned)
    cleaned = re.sub(r'(?i)(?:El usuario quiere|Luego seguir con|Primero describir|sin etiquetas|sin headers|solo texto fluido para el locutor)[^.\n]*[.\n]?', '', cleaned)
    # Strip concluding postambles and meta notes at the end of the text
    cleaned = re.sub(r'(?i)(?:espero que (?:te|les) (?:sirva|guste)|fin del (?:guion|relato|expediente)|nota:\s*.*|lista de reglas.*)$', '', cleaned)
    
    paragraphs = [p.strip() for p in cleaned.split('\n\n') if p.strip()]
    valid_paras = []
    for p in paragraphs:
        p_clean = re.sub(r'^[\"“](.*)[\"”]$', r'\1', p, flags=re.DOTALL).strip()
        p_clean = p_clean.strip('\"“’\'`')
        if p_clean:
            valid_paras.append(p_clean)

    if not valid_paras:
        valid_paras = paragraphs

    # If multiple explicit draft blocks exist (e.g. "Título: ...", "Versión 2: ..."), take the last draft block
    story_starts = [i for i, p in enumerate(valid_paras) if re.search(r'(?i)^\s*(?:Título:|Draft\s*\d|Borrador\s*\d|Versión\s*\d|Opción\s*\d)\b', p)]
    if len(story_starts) > 1:
        valid_paras = valid_paras[story_starts[-1]:]
    elif len(valid_paras) > 1:
        # Check if first paragraph is repeated later as a complete draft restart
        first_para_start = valid_paras[0][:30].lower()
        for idx in range(1, len(valid_paras)):
            if valid_paras[idx][:30].lower() == first_para_start:
                valid_paras = valid_paras[idx:]
                break

    unique_paras = []
    for p in valid_paras:
        if p not in unique_paras:
            unique_paras.append(p)

    final_script = '\n\n'.join(unique_paras).strip()

    # Strip any remaining taboo semantic leak phrases automatically
    for pat in TABOO_BARRIER_PATTERNS:
        final_script = re.sub(pat, '', final_script).strip()

    final_script = re.sub(r"[ \t]+", " ", final_script)
    final_script = re.sub(r"\n\s*\n+", "\n\n", final_script).strip()
    return final_script


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[^\w\-_]', '_', name)
    return cleaned[:100]

