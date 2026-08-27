"""
test_adversarial_m2_r2_stress.py - Empirical Challenger M2-R2 Stress Test Suite.

Comprehensive stress testing covering:
1. Single-line section headers with trailing narrative prose.
2. Upper and lower case Roman numerals (including V, XV, XXV, LV) & ordinals.
3. Preservation of legitimate Spanish vocabulary containing 'sonido' and Roman characters.
4. Timestamps & Timecode Preservation vs. Standalone Stripping.
5. Multi-story compilation matrix & channel alias routing.
6. Pre-TTS barrier verification & prompt leak rejection.
7. Single-beat & multi-beat tag extraction in extract_story_beats.
"""

import pytest
import re
from typing import List, Dict, Any

from src.sanitizer import (
    limpiar_texto_para_tts,
    validate_pre_tts_script,
    sanitize_script_text,
    sanitize_html_entities,
    PromptLeakError,
    ORDINAL_OR_ROMAN,
)
from src.curators.beats import (
    extract_story_beats,
    validate_beat_format,
    calculate_beat_shot_durations,
)
from src.llm import (
    compile_stories_to_target_words,
    curate_script,
    curate_batch_json,
    ORGANIC_CONNECTORS_HORROR,
    ORGANIC_CONNECTORS_DRAMA,
)
from src.branding import (
    get_channel_branding,
    resolve_channel_key,
    _CHANNEL_ALIASES,
)
from lib.tts import (
    strip_markdown_for_tts,
    sanitize_text_for_tts,
)


class TestSingleLineSectionHeaders:
    """Stress tests for single-line headers ensuring the following narrative text is preserved."""

    @pytest.mark.parametrize("header_prefix, expected_narrative", [
        ("Sección 1: ", "El agente avanzó por el pasillo oscuro con cautela."),
        ("Sección 12 - ", "Las compuertas del sector este se bloquearon de inmediato."),
        ("Sección XIV: ", "Los sensores acústicos detectaron un murmullo constante."),
        ("Sección Primera: ", "Nadie en el equipo de contención emitió ninguna palabra."),
        ("Sección Segunda - ", "La anomalía respondió a la presencia humana con agresividad."),
        ("Sección Décima: ", "El protocolo de emergencia fue declarado formalmente."),
        ("Capítulo 1: ", "Todo comenzó durante una guardia nocturna en el laboratorio."),
        ("Capítulo IV - ", "Los informes médicos confirmaron síntomas de parálisis."),
        ("Capítulo Primero: ", "La llamada de auxilio provino de un transmisor descontinuado."),
        ("Capítulo Duodécimo: ", "El desenlace fue sellado bajo estricto secreto militar."),
        ("Parte 1: ", "El primer síntoma fue una vibración continua en las paredes."),
        ("Parte 3 - ", "El personal técnico evacuó las instalaciones subterráneas."),
        ("Fase 2: ", "Iniciamos el monitoreo continuo de la criatura."),
        ("Bloque IV: ", "La estructura metálica colapsó por la presión del impacto."),
        ("Paso 5: ", "El cierre perimetral impidió la fuga del espécimen."),
    ])
    def test_single_line_headers_preserve_narrative_limpiar_tts(self, header_prefix: str, expected_narrative: str):
        raw_text = f"{header_prefix}{expected_narrative}"
        cleaned = limpiar_texto_para_tts(raw_text)

        # Header prefix must be stripped
        assert not re.search(r"(?i)\b(?:secci[óo]n|cap[íi]tulo|parte|fase|bloque|paso)\s+[a-záéíóú0-9IVXLCDMivxlcdm]+[:.-]?", cleaned)
        # Narrative must survive 100%
        assert expected_narrative in cleaned

    @pytest.mark.parametrize("header_prefix, expected_narrative", [
        ("Sección 1: ", "El agente avanzó por el pasillo oscuro con cautela."),
        ("Capítulo IV: ", "Los informes médicos confirmaron síntomas de parálisis."),
        ("Parte 2 - ", "El personal técnico evacuó las instalaciones subterráneas."),
    ])
    def test_single_line_headers_in_extract_story_beats(self, header_prefix: str, expected_narrative: str):
        raw_script = (
            f"[BEAT 1: HOOK]\n{header_prefix}{expected_narrative}\n\n"
            f"[BEAT 2: ESCALATION]\nSección 2: La criatura rompió el cristal de contención."
        )
        clean_script, beats = extract_story_beats(raw_script)

        assert len(beats) == 2
        assert expected_narrative in clean_script
        assert "La criatura rompió el cristal" in clean_script
        assert "Sección 1" not in clean_script
        assert "Sección 2" not in clean_script

    def test_multiple_inline_headers_in_continuous_prose(self):
        multi_line_text = (
            "Sección 1: Primera observación del sujeto.\n"
            "El espécimen permaneció quieto durante doce horas.\n"
            "Capítulo II: La primera interacción registrada.\n"
            "El investigador intentó comunicarse a través del intercomunicador.\n"
            "Parte 3: Desenlace de la prueba.\n"
            "La señal se interrumpió de forma definitiva."
        )
        cleaned = limpiar_texto_para_tts(multi_line_text)
        assert "Primera observación del sujeto." in cleaned
        assert "El espécimen permaneció quieto" in cleaned
        assert "La primera interacción registrada." in cleaned
        assert "El investigador intentó comunicarse" in cleaned
        assert "Desenlace de la prueba." in cleaned
        assert "La señal se interrumpió" in cleaned
        assert not re.search(r"(?i)\b(?:secci[óo]n|cap[íi]tulo|parte)\s+[a-záéíóú0-9IVXLCDMivxlcdm]+", cleaned)


class TestRomanNumeralsAndSpanishCollisions:
    """Stress tests for Roman numerals and collision avoidance with Spanish words."""

    @pytest.mark.parametrize("roman, name", [
        ("I", "uno"),
        ("II", "dos"),
        ("III", "tres"),
        ("IV", "cuatro"),
        ("V", "cinco"),
        ("VI", "seis"),
        ("VII", "siete"),
        ("VIII", "ocho"),
        ("IX", "nueve"),
        ("X", "diez"),
        ("XI", "once"),
        ("XIV", "catorce"),
        ("XV", "quince"),
        ("XIX", "diecinueve"),
        ("XX", "veinte"),
        ("XXIV", "veinticuatro"),
        ("XXV", "veinticinco"),
        ("XXIX", "veintinueve"),
        ("XL", "cuarenta"),
        ("XLII", "cuarenta y dos"),
        ("LV", "cincuenta y cinco"),
        ("L", "cincuenta"),
        ("i", "uno min"),
        ("iv", "cuatro min"),
        ("v", "cinco min"),
        ("viii", "ocho min"),
        ("xiv", "catorce min"),
        ("xv", "quince min"),
        ("xix", "diecinueve min"),
        ("xxv", "veinticinco min"),
    ])
    def test_roman_numeral_variants_stripped(self, roman: str, name: str):
        text_sec = f"Sección {roman}: El registro de la expedición número {name}."
        text_cap = f"Capítulo {roman}: La revelación sobre el origen {name}."

        cleaned_sec = limpiar_texto_para_tts(text_sec)
        cleaned_cap = limpiar_texto_para_tts(text_cap)

        assert not re.search(rf"(?i)\bsecci[óo]n\s+{roman}\b", cleaned_sec), f"Failed to strip 'Sección {roman}' in: {cleaned_sec}"
        assert not re.search(rf"(?i)\bcap[íi]tulo\s+{roman}\b", cleaned_cap), f"Failed to strip 'Capítulo {roman}' in: {cleaned_cap}"
        assert "El registro de la expedición" in cleaned_sec
        assert "La revelación sobre el origen" in cleaned_cap

    @pytest.mark.parametrize("sentence_with_spanish_words", [
        "En esta sección del bosque los árboles crecen completamente torcidos.",
        "La sección militar fue evacuada de inmediato tras la alerta roja.",
        "En la sección civil no hubo registros de anomalías térmicas.",
        "El capítulo de hoy terminó con una advertencia inquietante.",
        "En el capítulo inicial se describe el origen de la entidad.",
        "Esta es la sección delimitada por el personal de seguridad.",
        "El capítulo clave de la investigación fue archivado bajo llave.",
        "En la sección central del complejo se escucharon ruidos extraños.",
        "El capítulo médico detalla las lesiones del sujeto de prueba.",
        "La sección veterinaria atendió al espécimen antes del traslado.",
        "En la sección de operaciones nadie habló del incidente ocurrido.",
    ])
    def test_spanish_words_containing_roman_letters_preserved(self, sentence_with_spanish_words: str):
        cleaned = limpiar_texto_para_tts(sentence_with_spanish_words)
        # Verify grammar is undamaged
        assert "del bosque" in cleaned or "militar" in cleaned or "civil" in cleaned or "de hoy" in cleaned or "inicial" in cleaned or "delimitada" in cleaned or "clave" in cleaned or "central" in cleaned or "médico" in cleaned or "veterinaria" in cleaned or "de operaciones" in cleaned

    @pytest.mark.parametrize("sentence_with_sonido", [
        "Un sonido extraño resonó en la habitación.",
        "No escuchamos ningún sonido de fondo durante la expedición.",
        "El sonido del viento era aterrador en la colina.",
        "Nadie en el equipo de contención emitió un solo sonido.",
        "El sonido chirriante de raspado de piedra sobre hormigón continuó durante horas.",
    ])
    def test_legitimate_word_sonido_strictly_preserved(self, sentence_with_sonido: str):
        cleaned = limpiar_texto_para_tts(sentence_with_sonido)
        assert sentence_with_sonido.strip() == cleaned.strip(), f"Word 'sonido' caused destructive erasure: '{cleaned}'"


class TestExtractStoryBeatsSingleAndMultiBeat:
    """Stress tests extract_story_beats for single-beat and multi-beat scripts."""

    def test_single_beat_script_tag_stripped_and_text_preserved(self):
        single_beat_script = "[BEAT 1: HOOK]\nEl agente caminaba en silencio por el búnker abandonado."
        clean_script, beats = extract_story_beats(single_beat_script)

        assert "[BEAT" not in clean_script
        assert "HOOK]" not in clean_script
        assert "El agente caminaba en silencio por el búnker abandonado." in clean_script
        assert len(beats) == 1
        assert "[BEAT" not in beats[0]["text"]

    def test_multi_beat_with_dirty_html_entities(self):
        dirty_script = (
            "[BEAT 1: INTRO]\n&nbsp;&nbsp;Las cámaras térmicas detectaron movimiento.&lt;br&gt;\n\n"
            "[BEAT 2: DISCOVERY]\n&#160;Sección II: Confirmación visual del objetivo."
        )
        clean_script, beats = extract_story_beats(dirty_script)

        assert "&nbsp;" not in clean_script
        assert "&lt;" not in clean_script
        assert "&#160;" not in clean_script
        assert "Sección II:" not in clean_script
        assert "Las cámaras térmicas detectaron movimiento." in clean_script
        assert "Confirmación visual del objetivo." in clean_script


class TestTimestampsAndNarrativeTimes:
    """Stress tests verifying bracketed standalone timecodes are stripped while narrative timestamps survive."""

    @pytest.mark.parametrize("timecode_bracket", [
        "[0:22]",
        "[1:15]",
        "[12:45]",
        "[01:30:15]",
        "(00:22)",
        "(05:40)",
    ])
    def test_standalone_bracketed_timecodes_stripped(self, timecode_bracket: str):
        raw = f"El testigo relató lo sucedido {timecode_bracket} mientras las luces parpadeaban."
        cleaned = sanitize_script_text(raw)
        assert timecode_bracket not in cleaned
        assert "El testigo relató lo sucedido" in cleaned
        assert "mientras las luces parpadeaban." in cleaned

    @pytest.mark.parametrize("narrative_timestamp", [
        "03:45 horas",
        "02:15 horas",
        "19:45 horas",
        "14:30 hrs",
        "23:59 horas",
        "00:01 horas",
    ])
    def test_narrative_timestamps_strictly_preserved(self, narrative_timestamp: str):
        raw = f"El sujeto D-9023 ingresó al sector [DATOS BORRADOS] a las {narrative_timestamp}."
        cleaned = limpiar_texto_para_tts(raw)
        assert narrative_timestamp in cleaned
        assert "[DATOS BORRADOS]" in cleaned
        assert validate_pre_tts_script(cleaned) is True


class TestMultiStoryCompilationAndRouting:
    """Stress tests multi-story compilation across channels, aliases, and adversarial inputs."""

    @pytest.mark.parametrize("channel, is_drama", [
        ("moku", False),
        ("terror", False),
        ("moku_terror", False),
        ("moku-terror", False),
        ("scp", False),
        ("mokuredit", False),
        ("aelithia", True),
        ("aelithia-c1f", True),
        ("soy_el_malo", True),
        ("yo_soy_el_malo", True),
        ("aita", True),
        ("aita_drama", True),
        ("aita-drama", True),
    ])
    def test_compilation_genre_connector_isolation(self, channel: str, is_drama: bool):
        main_title = "Historia Principal de Prueba"
        main_content = "Un relato base inicial de unas cuantas palabras para comenzar la prueba."
        additional_stories = [
            {"title": "Anexo 1", "content": "Detalles del primer evento documentado en el registro."},
            {"title": "Anexo 2", "content": "Detalles del segundo evento complementario en el archivo."},
        ]

        compiled_title, compiled_content = compile_stories_to_target_words(
            main_title=main_title,
            main_content=main_content,
            additional_stories=additional_stories,
            min_words=500,
            channel=channel,
        )

        assert compiled_title == f"{main_title} | Compilación Completa"
        assert "# Capítulo" not in compiled_content
        assert "Capítulo " not in compiled_content or "Anexo 1" in compiled_content

        if is_drama:
            drama_indicators = ["escalando", "dinámica familiar", "fracturar la convivencia", "conflicto familiar", "situación decisiva"]
            assert any(ind in compiled_content for ind in drama_indicators), f"Channel {channel} failed to receive drama connectors"
        else:
            horror_indicators = ["inquietante", "testimonios", "anomalía", "segundo archivo", "nuevo testimonio"]
            assert any(ind in compiled_content for ind in horror_indicators), f"Channel {channel} failed to receive horror connectors"

    def test_compilation_with_adversarial_title_prefixes(self):
        main_title = "Expediente Central"
        main_content = "Informe inicial de situación."
        adversarial_stories = [
            {"title": "### Capítulo 1: El Inicio", "content": "Primera parte del reporte de campo."},
            {"title": "Sección 2 - La Criatura", "content": "Segunda parte con avistamiento directo."},
            {"title": "Parte III. La Huida", "content": "Tercera parte con evacuación exitosa."},
            {"title": "Relato Cuarto: El Fin", "content": "Cuarta parte con cierre de perímetro."},
        ]

        compiled_title, compiled_content = compile_stories_to_target_words(
            main_title=main_title,
            main_content=main_content,
            additional_stories=adversarial_stories,
            min_words=600,
            channel="moku",
        )

        cleaned = limpiar_texto_para_tts(compiled_content)
        assert "# Capítulo" not in cleaned
        assert not re.search(r"(?i)\bcap[íi]tulo\s+\d+", cleaned)
        assert not re.search(r"(?i)\bsecci[óo]n\s+\d+", cleaned)
        assert validate_pre_tts_script(cleaned) is True


class TestPreTTSBarrierDeterminism:
    """Stress tests validate_pre_tts_script barrier determinism against prompt leaks and taboo phrases."""

    @pytest.mark.parametrize("forbidden_phrase", [
        "Hoy les traigo una historia aterradora.",
        "Hola a todos bienvenidos a Moku.",
        "Te damos la bienvenida a Aelithia.",
        "Suscríbete al canal para no perderte ningún video.",
        "Deja tu like y comenta abajo qué opinas.",
        "Hasta la próxima amigos.",
        "Atención a todo el personal del Sitio 19:",
        "Bienvenidos a este nuevo expediente de la Fundación SCP.",
        "Lo que estás a punto de escuchar en este expediente...",
        "Atención agentes de la Fundación SCP:",
        "El usuario quiere un relato de terror.",
        "Aquí tienes el guion para locutor.",
        "Vamos a redactar una historia.",
        "Voy a redactar el expediente solicitado.",
        "A continuación el guion completo.",
        "Sección 1: La entrada al complejo.",
        "Capítulo IV: La noche oscura.",
        "Sección V: La revelación del misterio.",
        "Título: El Secreto del Abismo",
        "Gancho viral inicial: ¿Te atreves a entrar?",
        "Remate final: Nadie sobrevivió.",
        "Llamado a la acción: Comenta qué harías.",
    ])
    def test_pre_tts_barrier_rejects_forbidden_inputs(self, forbidden_phrase: str):
        with pytest.raises(PromptLeakError):
            validate_pre_tts_script(forbidden_phrase)

    @pytest.mark.parametrize("invalid_input", [
        "",
        "   ",
        "\n\t\n",
        None,
        12345,
        ["lista"],
        {"dict": 1},
    ])
    def test_pre_tts_barrier_rejects_empty_and_invalid_types(self, invalid_input):
        with pytest.raises(PromptLeakError):
            validate_pre_tts_script(invalid_input)

    def test_pre_tts_barrier_accepts_clean_narrative(self):
        clean_narrative = (
            "En la oscuridad de la noche, las luces del búnker parpadearon de forma intermitente. "
            "El equipo de contención aseguró el sector [DATOS BORRADOS] a las 03:45 horas. "
            "En esta sección del bosque los árboles parecían susurrar advertencias olvidadas. "
            "El informe clasificado permanece [REDACTADO] hasta nuevo aviso."
        )
        assert validate_pre_tts_script(clean_narrative) is True
