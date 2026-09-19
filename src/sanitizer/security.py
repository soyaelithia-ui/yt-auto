"""src/sanitizer/security.py - Prompt leak barrier, taboo phrases, and reasoning monologue eradication."""

from __future__ import annotations

import re


class PromptLeakError(Exception):
    """Raised when a system prompt leak or taboo phrase is detected in script output."""
    pass


TABOO_BARRIER_PATTERNS: list[str] = [
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
    r'(?i)como\s+modelo\s+de\s+lenguaje',
    r'(?i)como\s+una?\s+ia\b',
    r'(?i)como\s+inteligencia\s+artificial',
    r'(?i)</?script>',
    r'(?i)claro,?\s+aqu[íi]\s+(?:tienes|est[áa])',
    r'(?i)a\s+continuaci[óo]n\s+presento',
    r'(?i)adaptaci[óo]n\s+narrativa',
    r'(?i)instrucciones\s+recibidas',
    r'(?i)seg[úu]n\s+las\s+instrucciones',
    r'(?i)\bprompt\s*:',
]

# Comprehensive regex patterns for system prompt instruction echoes and model chatter
PROMPT_LEAK_PATTERNS: list[str] = [
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


def validate_semantic_barrier(text: str) -> bool:
    """Validates text against taboo semantic leak phrases.

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


def extract_script_from_reasoning(text: str) -> str:
    """Extracts genuine narrative paragraphs and sentences from LLM responses containing reasoning monologues."""
    if not text:
        return ""
    # Strip <think>...</think> blocks
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

    reasoning_patterns = [
        r"\bwait\b",
        r"\bno,?\s+espera\b",
        r"\bprimero,?\s+la clase",
        r"\bprimero,?\s+directamente",
        r"\bprimero,?\s+empiezo",
        r"\bprimero,?\s+abre",
        r"\basí que (?:empecemos|empiezo|tal vez)",
        r"por la primera frase",
        r"que nombre el objeto",
        r"amenaza letal inmediatamente",
        r"perfecto,?\s+eso es",
        r"primero los parámetros",
        r"parámetros físicos",
        r"lo puso el usuario",
        r"la dio el usuario",
        r"traducida correctamente",
        r"eso es correcto",
        r"apertura formal de la fundación",
        r"descripción física,?\s+tal cual",
        r"\bno (?:hay que )?agregar personajes",
        r"\bno inventar personajes",
        r"\bdramas secundarios",
        r"\bsolo lo oficial",
        r"^\s*sí,?\s+scp-",
        r"^\s*luego,?\s+(?:la|el|los|las)\s+(?:sección|parte|estructura|paso)\b",
        r"\bluego,?\s+el desencadenante",
        r"\bluego,?\s+el comportamiento",
        r"\bvamos a hacer que",
        r"\bhay que usar solo",
        r"\binformación canónica completa",
        r"el usuario (?:quiere|pide|solicita|busca|dio)",
        r"siguiendo las reglas",
        r"empiezo directo",
        r"primero,?\s+el segundo",
        r"regla \d",
        r"la historia tiene que ser",
        r"o sea,?\s+desde",
        r"por ejemplo,?\s+empieza",
        r"el guion es para un short",
        r"tono documental",
        r"sin etiquetas",
        r"sin headers",
        r"solo texto fluido",
        r"para el locutor",
        r"describir la criatura",
        r"espero que (?:te|les) (?:sirva|guste)",
        r"fin del (?:guion|relato|expediente)",
        r"nota:\s*",
        r"lista de reglas",
        r"reglas obligatorias",
        r":\s*(?:sí|ok|hecho)\.?$",
        r"\blo puse como\b",
        r"\bmantiene el sentido\b",
        r"\berror de (?:escritura|redacción)\b",
        r"\blee (?:bien|el contexto)\b",
        r"\bmira el contexto\b",
        r"^\s*(?:Luego,?\s+seguir|Primero,?\s+aclara|Oh,?\s*wait|Ah,?\s*wait|No,?\s*no)\b",
    ]

    lines = cleaned.split("\n")
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

    cleaned_str = "\n".join(filtered_lines)
    cleaned_str = re.sub(r"\n\s*\n+", "\n\n", cleaned_str)
    return cleaned_str.strip()


def strip_llm_prompt_leaks(text: str) -> str:
    """Strips LLM instruction echoes, system tags, reasoning monologues, and draft restarts."""
    if not text:
        return ""
    # Strip <think>...</think> blocks
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(
        r"(?i)^(?:Luego,?\s+seguir|Primero,?\s+aclara|El usuario (?:quiere|pide)|INSTRUCCIONES?)[^:\n]*:\s*",
        "",
        cleaned,
        flags=re.MULTILINE,
    )

    cleaned = extract_script_from_reasoning(cleaned)
    from src.sanitizer.editorial import sanitize_llm_script

    cleaned = sanitize_llm_script(cleaned, mode="short")
    # Strip prompt/beat bracket tags while preserving canonical SCP redactions ([DATOS BORRADOS], [REDACTADO])
    cleaned = re.sub(
        r"\[(?:BEAT|INTRO|HOOK|HEADER|PASO|REGLA|MÓDULO|SECCIÓN|PROMPT)[^\]]*\]",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    # Strip specific literal strings leaked from prompts
    cleaned = re.sub(r"(?i)SCP-\[N[uú]mero\]", "", cleaned)
    cleaned = re.sub(r"(?i)~?120-160\s*palabras?", "", cleaned)
    cleaned = re.sub(r"~?120-160", "", cleaned)
    cleaned = re.sub(r"(?i)REGLAS ESTRUCTURALES", "", cleaned)
    cleaned = re.sub(r"(?i)INSTRUCCI?ONES?", "", cleaned)
    cleaned = re.sub(r"(?i)FORMATO DE ALTO IMPACTO", "", cleaned)
    # Strip remaining intro meta phrases
    cleaned = re.sub(
        r"(?i)^[^\n.]*(?:el usuario quiere|tono documental|sin etiquetas|sin headers|texto fluido|para el locutor|describir la criatura:?)[^\n.]*[.\n]?",
        "",
        cleaned,
    )
    cleaned = re.sub(
        r"(?i)(?:El usuario quiere|Luego seguir con|Primero describir|sin etiquetas|sin headers|solo texto fluido para el locutor)[^.\n]*[.\n]?",
        "",
        cleaned,
    )
    # Strip concluding postambles and meta notes at the end of the text
    cleaned = re.sub(
        r"(?i)(?:espero que (?:te|les) (?:sirva|guste)|fin del (?:guion|relato|expediente)|nota:\s*.*|lista de reglas.*)$",
        "",
        cleaned,
    )

    paragraphs = [p.strip() for p in cleaned.split("\n\n") if p.strip()]
    valid_paras = []
    for p in paragraphs:
        p_clean = re.sub(r'^["“](.*)["”]$', r"\1", p, flags=re.DOTALL).strip()
        p_clean = p_clean.strip("\"“’'`")
        if p_clean:
            valid_paras.append(p_clean)

    if not valid_paras:
        valid_paras = paragraphs

    # If multiple explicit draft blocks exist (e.g. "Título: ...", "Versión 2: ..."), take the last draft block
    story_starts = [
        i
        for i, p in enumerate(valid_paras)
        if re.search(r"(?i)^\s*(?:Título:|Draft\s*\d|Borrador\s*\d|Versión\s*\d|Opción\s*\d)\b", p)
    ]
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

    final_script = "\n\n".join(unique_paras).strip()

    # Strip any remaining taboo semantic leak phrases automatically
    for pat in TABOO_BARRIER_PATTERNS:
        final_script = re.sub(pat, "", final_script).strip()

    final_script = re.sub(r"[ \t]+", " ", final_script)
    final_script = re.sub(r"\n\s*\n+", "\n\n", final_script).strip()
    return final_script


__all__ = [
    "PromptLeakError",
    "TABOO_BARRIER_PATTERNS",
    "PROMPT_LEAK_PATTERNS",
    "validate_semantic_barrier",
    "extract_script_from_reasoning",
    "strip_llm_prompt_leaks",
]
