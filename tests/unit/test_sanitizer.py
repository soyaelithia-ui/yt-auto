"""
Unit tests for YTShort src/sanitizer.py: sanitize_llm_script, sanitize_text, and validate_beat_format.
Verifies prompt leak filtering, legacy branding removal, preamble stripping, and SCP format validation.
"""

import pytest
from src.sanitizer import sanitize_llm_script, sanitize_text, validate_beat_format
from src.curators.beats import extract_story_beats


def test_sanitize_llm_script_short_mode_discards_pre_beat_preamble():
    raw = (
        "Aquí está el guion SCP solicitado por el usuario:\n"
        "INSTRUCCIÓN CRÍTICA DE FORMATO: prohibido resumir el texto.\n\n"
        "[BEAT 1: CLASIFICACION Y HOOK]\n"
        "Archivo SCP Clasificado. SCP-096. Clasificación: Euclídeo.\n\n"
        "[BEAT 2: PROCEDIMIENTOS DE CONTENCION]\n"
        "SCP-096 debe ser mantenido en una celda sellada de 5x5 metros."
    )
    cleaned = sanitize_llm_script(raw, mode="short")
    assert "Aquí está el guion" not in cleaned
    assert "INSTRUCCIÓN CRÍTICA" not in cleaned
    assert "prohibido resumir" not in cleaned
    assert cleaned.startswith("[BEAT 1: CLASIFICACION Y HOOK]")
    assert "Archivo SCP Clasificado" in cleaned


def test_validate_scp_format_valid_script():
    valid_scp = (
        "[BEAT 1: CLASIFICACION Y HOOK]\n"
        "Archivo SCP Clasificado. SCP-173. Clasificación: Euclídeo.\n\n"
        "[BEAT 2: PROCEDIMIENTOS DE CONTENCION]\n"
        "Debe estar bajo vigilancia constante de dos personas."
    )
    assert validate_beat_format(valid_scp) is True


def test_validate_scp_format_invalid_cases():
    # Empty script
    assert validate_beat_format("") is False
    assert validate_beat_format(None) is False

    # Missing beat tags
    no_tags = "Archivo SCP Clasificado. SCP-173 sin etiquetas."
    assert validate_beat_format(no_tags) is False

    # Valid beat format without SCP hook is accepted (generic channels)
    no_hook = (
        "[BEAT 1: HOOK]\n"
        "Hola a todos, hoy veremos una historia de miedo.\n\n"
        "[BEAT 2: CONTENCION]\n"
        "Instrucciones de contención."
    )
    assert validate_beat_format(no_hook) is True

    # Contains system prompt leak
    prompt_leak = (
        "INSTRUCCIÓN CRÍTICA: prohibido resumir.\n"
        "[BEAT 1: CLASIFICACION Y HOOK]\n"
        "Archivo SCP Clasificado. SCP-173."
    )
    assert validate_beat_format(prompt_leak) is False


def test_extract_scp_beats_discards_preambles():
    raw_with_chatter = (
        "Se ha mantenido la traducción completa.\n"
        "[BEAT 1: CLASIFICACION Y HOOK]\n"
        "Archivo SCP Clasificado. SCP-682.\n\n"
        "[BEAT 2: DESCRIPCION]\n"
        "Es un reptil gigante indestructible."
    )
    clean_text, beats = extract_story_beats(raw_with_chatter)
    assert "Se ha mantenido" not in clean_text
    assert len(beats) == 2
    assert beats[0]["label"] == "CLASIFICACION Y HOOK"
    assert beats[0]["text"] == "Archivo SCP Clasificado. SCP-682."

def test_strip_llm_prompt_leaks():
    from src.sanitizer import strip_llm_prompt_leaks
    text = "REGLAS ESTRUCTURALES\n[BEAT 1: HOOK] SCP-[Número] 120-160 palabras"
    res = strip_llm_prompt_leaks(text)
    assert "REGLAS ESTRUCTURALES" not in res
    assert "[BEAT" not in res
    assert "SCP-[Número]" not in res
    assert "120-160 palabras" not in res


def test_strip_llm_prompt_leaks_comprehensive_purge():
    from src.sanitizer import strip_llm_prompt_leaks, sanitize_llm_script
    raw_output = (
        "Aquí está el guion en formato contra-descripción:\n"
        "REGLAS DE ORO: NARRACIÓN 100% EN ESPAÑOL PURO.\n"
        "mecánica de la anomalía y nivel de amenaza.\n"
        "Atención agentes de la Fundación SCP.\n"
        "Si te encuentras cara a cara con SCP-173 no parpadees.\n"
        "espero que te sirva este guion."
    )
    cleaned = strip_llm_prompt_leaks(raw_output)
    assert "Aquí está el guion" not in cleaned
    assert "REGLAS DE ORO" not in cleaned
    assert "mecánica de la anomalía" not in cleaned
    assert "Atención agentes" not in cleaned
    assert "espero que te sirva" not in cleaned
    assert "Si te encuentras cara a cara con SCP-173 no parpadees" in cleaned


def test_purge_reasoning_monologue_artifacts():
    from src.sanitizer import strip_llm_prompt_leaks, sanitize_llm_script, extract_script_from_reasoning

    raw_monologue = (
        "perfecto, eso es... primero los parámetros físicos de la anomalía.\n"
        "revisar que el español sea 100% puro sin marcas de agua.\n"
        "se logra? el hook es impactante?\n"
        "Si te encuentras cara a cara con el SCP-173, no rompas el contacto visual."
    )

    cleaned = strip_llm_prompt_leaks(raw_monologue)
    assert "perfecto, eso es" not in cleaned.lower()
    assert "primero los parámetros" not in cleaned.lower()
    assert "revisar que el español" not in cleaned.lower()
    assert "se logra?" not in cleaned.lower()
    assert "hook es impactante?" not in cleaned.lower()
    assert "Si te encuentras cara a cara con el SCP-173" in cleaned


def test_purge_word_counting_monologue_trails():
    from src.sanitizer import strip_llm_prompt_leaks
    raw_text = (
        "Amenaza de extinción biológica activa.\n"
        "Ahora cuento las palabras: vamos a ver, son alrededor de 160?\n"
        "1.Amenaza 2.de 3.extinción 4.biológica 5.activa"
    )
    cleaned = strip_llm_prompt_leaks(raw_text)
    assert "Ahora cuento las palabras" not in cleaned
    assert "1.Amenaza 2.de 3.extinción" not in cleaned
    assert "Amenaza de extinción biológica activa." in cleaned


def test_validate_semantic_barrier_valid_and_leaks():
    from src.sanitizer import validate_semantic_barrier, PromptLeakError

    valid_script = "Archivo SCP Clasificado. SCP-096 debe ser mantenido en una celda sellada de 5x5 metros."
    assert validate_semantic_barrier(valid_script) is True

    leaked_scripts = [
        "El usuario quiere un relato escalofriante de SCP-173.",
        "Aquí tienes tu guion para la locución.",
        "Aquí está el guion que solicitaste.",
        "Guion con tono documental sin etiquetas.",
        "Texto optimizado para el locutor oficial.",
        "Primero vamos a describir la criatura.",
        "Siguiendo las reglas obligatorias de contención.",
    ]

    for leaked in leaked_scripts:
        with pytest.raises(PromptLeakError):
            validate_semantic_barrier(leaked)


def test_limpiar_texto_para_tts_initialization_and_header_removal():
    from src.sanitizer import limpiar_texto_para_tts

    # Handles None and empty inputs without error
    assert limpiar_texto_para_tts(None) == ""
    assert limpiar_texto_para_tts("") == ""

    # Complex script with markdown, section labels, title prefixes, greetings, and SFX
    raw_script = (
        "Título: El Archivo Maldito.\n\n"
        "### Capítulo 1: La Revelación\n\n"
        "Sección Primera: El Descubrimiento Inicial y los Primeros Registros.\n\n"
        "Bienvenidos a Moku. Hoy les traigo una historia aterradora.\n\n"
        "[Sonido: viento aullando]\n"
        "Gancho viral inicial: Atención a todos.\n\n"
        "El guardia de seguridad observó las cámaras y notó una figura inmóvil en el pasillo norte. "
        "Sección 2: La Anomalía.\n\n"
        "Ninguna persona tenía autorización para acceder a ese sector después de la medianoche."
    )

    cleaned = limpiar_texto_para_tts(raw_script)

    assert "Título:" not in cleaned
    assert "Capítulo" not in cleaned
    assert "Sección" not in cleaned
    assert "Bienvenidos" not in cleaned
    assert "Hoy les traigo" not in cleaned
    assert "[Sonido:" not in cleaned
    assert "Gancho viral" not in cleaned
    assert "El guardia de seguridad observó las cámaras" in cleaned
    assert "Ninguna persona tenía autorización" in cleaned


def test_validate_pre_tts_script_detects_structural_headers():
    from src.sanitizer import validate_pre_tts_script, PromptLeakError

    clean_narrative = (
        "La puerta de la celda de contención permaneció sellada durante cuatro semanas consecutivas. "
        "Ningún sonido escapaba del interior del recinto subterráneo."
    )
    assert validate_pre_tts_script(clean_narrative) is True

    # Violations with structural markers
    structural_violations = [
        "Sección Primera: El Descubrimiento Inicial.\n\nTodo comenzó en la base militar.",
        "Sección 1: Primeros Reportes.\n\nLos sensores registraron movimiento.",
        "# Capítulo 1: La Llegada.\n\nEl convoy arribó a las doce.",
        "Título: La Sombra del Pasillo.\n\nCaminé despacio.",
        "Gancho viral inicial: Lo que viene te asustará.\n\nLa criatura atacó.",
    ]

    for violation in structural_violations:
        with pytest.raises(PromptLeakError):
            validate_pre_tts_script(violation)


def test_validate_pre_tts_script_preserves_dramatic_pauses():
    from src.sanitizer import validate_pre_tts_script, TextSanitizer, limpiar_texto_para_tts

    script_with_pauses = (
        "El guardia de seguridad abrió la puerta blindada con temor. [PAUSA: 1.5s]\n\n"
        "Al fondo del pasillo, la entidad permanecía inmóvil. [PAUSE: 800ms]\n\n"
        "De repente, las luces parpadearon y se apagaron por completo. [PAUSA]"
    )

    # Pre-TTS barrier must accept dramatic pauses as valid narrative timing elements
    assert validate_pre_tts_script(script_with_pauses) is True

    # TextSanitizer.parse_dramatic_pauses parses tags properly
    segments = TextSanitizer.parse_dramatic_pauses(script_with_pauses)
    assert len(segments) == 3
    assert segments[0]["pause_after"] == 1.5
    assert segments[1]["pause_after"] == 0.8
    assert segments[2]["pause_after"] == 1.2

    # limpiar_texto_para_tts preserves dramatic pauses
    cleaned = limpiar_texto_para_tts(script_with_pauses)
    assert "[PAUSA: 1.5s]" in cleaned
    assert "[PAUSE: 800ms]" in cleaned
    assert "[PAUSA]" in cleaned


def test_strip_ass_tags_centralized():
    from src.sanitizer import strip_ass_tags
    assert strip_ass_tags(None) == ""
    assert strip_ass_tags("") == ""
    ass_sample = "{\\k50}Hola {\\pos(192,200)\\c&H0000FF&}mundo{\\r}"
    assert strip_ass_tags(ass_sample) == "Hola mundo"


def test_strip_act_chapter_headers_centralized():
    from src.sanitizer import strip_act_chapter_headers
    assert strip_act_chapter_headers(None) == ""
    assert strip_act_chapter_headers("") == ""
    raw = (
        "Título: El Despertar\n"
        "### Capítulo 1: La Llegada\n"
        "Acto I: Inicio del relato\n"
        "La noche estaba fría y silenciosa."
    )
    cleaned = strip_act_chapter_headers(raw)
    assert "Título:" not in cleaned
    assert "Capítulo" not in cleaned
    assert "Acto I:" not in cleaned
    assert "La noche estaba fría y silenciosa." in cleaned


def test_sanitize_scp_acronyms_for_tts_centralized():
    from src.sanitizer import sanitize_scp_acronyms_for_tts
    assert sanitize_scp_acronyms_for_tts(None) == ""
    assert sanitize_scp_acronyms_for_tts("") == ""
    raw = "El SCP-173 fue investigado por el consejo O5 ante un escenario XK con tecnología BZHR y XACTS de SCP."
    res = sanitize_scp_acronyms_for_tts(raw)
    assert "S-C-P 173" in res
    assert "O-5" in res
    assert "X-K" in res
    assert "B-Z-H-R" in res
    assert "X-ACTS" in res
    assert "S-C-P" in res






