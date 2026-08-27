"""
Unit tests for Milestone M2: Header Elimination, Sanitizer & 3s Hook Engine.
Verifies:
1. Complete elimination of structural section/chapter headers across sanitizer, beats, and TTS.
2. Zero vocalization leakage of 'Sección Primera...', 'Capítulo 1...', 'Título: ...', and forbidden greetings.
3. Organic genre-specific narrative connectors in multi-story compilation for Moku and Aelithia.
4. Compliance of channel branding opening hooks with editorial and pre-TTS rules.
"""

import pytest
from src.sanitizer import (
    limpiar_texto_para_tts,
    sanitize_script_text,
    validate_pre_tts_script,
    PromptLeakError,
)
from src.curators.beats import extract_story_beats
from src.llm import (
    compile_stories_to_target_words,
    ORGANIC_CONNECTORS_HORROR,
    ORGANIC_CONNECTORS_DRAMA,
)
from lib.tts import (
    sanitize_text_for_tts,
    strip_markdown_for_tts,
)
from src.branding import get_channel_branding


class TestM2HeaderEliminationAndSanitizer:
    """Test pre-TTS sanitizer and header elimination engines."""

    @pytest.mark.parametrize("section_header", [
        "Sección Primera: El Descubrimiento Inicial y los Primeros Registros de la Anomalía.",
        "Sección Segunda: Las Primeras Anomalías y la Alteración del Entorno.",
        "Sección Tercera: Los Testimonios de los Guardias de Turno.",
        "Sección Cuarta: La Llegada del Equipo Especial de Análisis.",
        "Sección Quinta: Archivos Perdidos y Precedentes Históricos.",
        "Sección Sexta: La Pérdida de Comunicaciones.",
        "Sección Séptima: El Encuentro Directo y las Grabaciones.",
        "Sección Octava: El Protocolo Extraordinario de Contención.",
        "Sección Novena: Las Secuelas y los Secretos.",
        "Sección Décima: Nuevas Evidencias Desclasificadas.",
        "Sección Undécima: El Impacto en la Comunidad.",
        "Sección Duodécima: Reflexión Final y Preguntas Abiertas.",
        "Sección 1: Primer reporte oficial.",
        "Sección 12: Informe de cierre.",
        "Capítulo 1: El Inicio del Caso.",
        "Capítulo 2: La Confrontación.",
        "# Capítulo 1: Revelaciones Ocultas.",
        "### Capítulo 3: El Veredicto.",
        "Parte 1: Antecedentes del Incidente.",
    ])
    def test_limpiar_texto_para_tts_eliminates_all_structural_headers(self, section_header):
        raw = f"{section_header}\n\nEl silencio inundó la sala mientras las luces parpadeaban de forma intermitente."
        cleaned = limpiar_texto_para_tts(raw)
        assert "Sección" not in cleaned
        assert "Capítulo" not in cleaned
        assert "Parte 1" not in cleaned
        assert "#" not in cleaned
        assert "El silencio inundó la sala" in cleaned

    def test_limpiar_texto_para_tts_eliminates_title_and_forbidden_greetings(self):
        raw = (
            "Título: El Enigma de la Habitación 404.\n\n"
            "Bienvenidos a Moku. Hoy les traigo una historia aterradora que los dejará sin aliento.\n\n"
            "Gancho viral inicial: Nadie sobrevivió al experimento.\n\n"
            "[Sonido: estática intensa]\n\n"
            "El doctor Ramírez revisó los monitores y confirmó que los signos vitales del sujeto se habían estabilizado."
        )
        cleaned = limpiar_texto_para_tts(raw)
        assert "Título:" not in cleaned
        assert "Bienvenidos" not in cleaned
        assert "Hoy les traigo" not in cleaned
        assert "Gancho viral" not in cleaned
        assert "[Sonido:" not in cleaned
        assert "El doctor Ramírez revisó los monitores" in cleaned

    def test_validate_pre_tts_script_barrier_enforcement(self):
        # Valid clean script passes
        clean_text = (
            "Los registros de la cámara de seguridad confirman que la compuerta blindada "
            "se abrió sin intervención del operador a las tres de la madrugada."
        )
        assert validate_pre_tts_script(clean_text) is True

        # Header leaks are strictly rejected
        invalid_texts = [
            "Sección Primera: Inicio del evento.\n\nLos sensores detectaron presencia.",
            "Capítulo 1: La Llegada.\n\nEl equipo táctico descendió del helicóptero.",
            "# Capítulo 2: El Contacto.\n\nLa criatura abrió los ojos.",
            "Título: Crónicas del Abismo.\n\nNadie pudo explicar lo ocurrido.",
            "Gancho viral inicial: Lo que verás a continuación cambiará tu percepción.",
            "Hoy les traigo una historia fascinante sobre lo ocurrido en el bosque.",
            "Por favor suscríbete al canal para más historias aterradoras.",
        ]
        for inv in invalid_texts:
            with pytest.raises(PromptLeakError):
                validate_pre_tts_script(inv)

        # Empty and whitespace scripts are rejected with PromptLeakError
        with pytest.raises(PromptLeakError):
            validate_pre_tts_script("")
        with pytest.raises(PromptLeakError):
            validate_pre_tts_script("   \n\t  ")

    def test_inline_section_headers_preserve_narrative_sentence_on_same_line(self):
        """Remediates Challenger 1 data-loss bug: prefix-only section removal must keep narrative text."""
        raw = (
            "Sección 1: El agente avanzó por el pasillo oscuro y escuchó un ruido metálico.\n"
            "Capítulo IV: Los testigos confirmaron que la puerta nunca se abrió desde adentro.\n"
            "Parte 2: Nadie pudo anticipar el desenlace del experimento.\n"
            "Bloque 3: El perímetro exterior quedó completamente acordonado."
        )
        cleaned = limpiar_texto_para_tts(raw)
        assert "Sección 1" not in cleaned
        assert "Capítulo IV" not in cleaned
        assert "Parte 2" not in cleaned
        assert "Bloque 3" not in cleaned
        assert "El agente avanzó por el pasillo oscuro" in cleaned
        assert "Los testigos confirmaron que la puerta nunca se abrió" in cleaned
        assert "Nadie pudo anticipar el desenlace del experimento" in cleaned
        assert "El perímetro exterior quedó completamente acordonado" in cleaned

    def test_spanish_words_with_roman_letters_are_never_corrupted(self):
        """Remediates Challenger 1 regex bug: strict Roman numeral boundaries must not match Spanish words."""
        text = (
            "El informe del comandante militar confirmó que el personal civil "
            "comenzó la fase de investigación inicial en el sector delimitado."
        )
        cleaned = sanitize_script_text(text)
        assert "del" in cleaned
        assert "militar" in cleaned
        assert "civil" in cleaned
        assert "inicial" in cleaned
        assert "delimitado" in cleaned
        assert cleaned.strip() == text.strip()

    def test_legitimate_timestamps_with_horas_preserved(self):
        """Remediates Challenger 1 timestamp bug: 03:45 horas must not be stripped."""
        text = "El registro del sensor se activó a las 03:45 horas en el laboratorio secundario."
        cleaned = sanitize_script_text(text)
        assert "03:45 horas" in cleaned



class TestM2BeatsAndStoryCompilation:
    """Test beat extraction and multi-story compilation with organic connectors."""

    def test_extract_story_beats_eliminates_unbracketed_structural_headers(self):
        script_with_headers = (
            "Título: El Experimento Prohibido.\n\n"
            "Sección Primera: Las Primeras Pruebas de Laboratorio.\n\n"
            "Durante las primeras semanas de investigación, el equipo mantuvo un control absoluto sobre el compuesto. "
            "Sin embargo, las lecturas térmicas comenzaron a elevarse sin causa aparente.\n\n"
            "Sección Segunda: La Falla en el Sistema de Enfriamiento.\n\n"
            "A medianoche, los generadores auxiliares colapsaron de manera simultánea. "
            "La temperatura del núcleo alcanzó niveles críticos en menos de diez segundos."
        )
        clean_script, beats = extract_story_beats(script_with_headers)

        assert "Título:" not in clean_script
        assert "Sección Primera" not in clean_script
        assert "Sección Segunda" not in clean_script
        assert "Durante las primeras semanas de investigación" in clean_script
        assert "A medianoche, los generadores auxiliares" in clean_script
        for b in beats:
            assert "Sección" not in b["text"]
            assert "Título:" not in b["text"]

    def test_compile_stories_moku_uses_horror_connectors_without_chapter_injections(self):
        main_content = "El expediente inicial describió un fenómeno lumínico en el bosque."
        additional = [
            {"title": "El Refugio Abandonado", "content": "Los exploradores encontraron marcas profundas en las paredes de concreto."},
            {"title": "Las Voces en la Frecuencia", "content": "La radio comenzó a emitir susurros ininteligibles a las tres de la mañana."},
        ]

        title, compiled = compile_stories_to_target_words(
            main_title="Expedientes de la Noche",
            main_content=main_content,
            additional_stories=additional,
            min_words=200,
            channel="moku",
        )

        assert "# Capítulo" not in compiled
        assert "Capítulo 1" not in compiled
        assert "Capítulo 2" not in compiled
        assert "Sección" not in compiled

        # Verifies organic connectors for horror genre
        has_horror_connector = any(conn[:30] in compiled for conn in ORGANIC_CONNECTORS_HORROR)
        assert has_horror_connector is True
        assert "marcas profundas en las paredes" in compiled
        assert "susurros ininteligibles" in compiled
        assert "Expedientes de la Noche | Compilación Completa" == title

    def test_compile_stories_aelithia_uses_drama_connectors_without_chapter_injections(self):
        main_content = "Mi hermana decidió cancelar la boda dos días antes de la ceremonia familiar."
        additional = [
            {"title": "La Discusión por la Herencia", "content": "Nuestros padres convocaron una reunión de emergencia para repartir los bienes."},
            {"title": "El Mensaje Revelador", "content": "Recibí una captura de pantalla que confirmaba la traición de mi cuñado."},
        ]

        title, compiled = compile_stories_to_target_words(
            main_title="Secretos de Familia",
            main_content=main_content,
            additional_stories=additional,
            min_words=200,
            channel="aelithia",
        )

        assert "# Capítulo" not in compiled
        assert "Capítulo 1" not in compiled
        assert "Capítulo 2" not in compiled
        assert "Sección" not in compiled

        # Verifies organic connectors for drama genre
        has_drama_connector = any(conn[:30] in compiled for conn in ORGANIC_CONNECTORS_DRAMA)
        assert has_drama_connector is True
        assert "reunión de emergencia para repartir" in compiled
        assert "confirmaba la traición" in compiled
        assert "Secretos de Familia | Compilación Completa" == title

    def test_compile_stories_aita_alias_uses_drama_connectors_and_sanitizes_titles(self):
        """Remediates Challenger 2 bug: 'aita' alias must receive drama connectors and strip # Capítulo."""
        main_content = "Descubrí que mi prometido mantenía una cuenta secreta de ahorros."
        additional = [
            {"title": "### Capítulo 2: La Revelación", "content": "Su mejor amigo me confesó toda la verdad durante el almuerzo."},
            {"title": "Sección 3: El Desenlace", "content": "Decidí cancelar la boda inmediatamente y devolver el anillo de compromiso."},
        ]

        title, compiled = compile_stories_to_target_words(
            main_title="El Gran Secreto",
            main_content=main_content,
            additional_stories=additional,
            min_words=200,
            channel="aita",
        )

        assert "# Capítulo" not in compiled
        assert "Capítulo 2" not in compiled
        assert "Sección 3" not in compiled
        assert "###" not in compiled
        # Verifies drama connectors are selected for 'aita' alias
        has_drama_connector = any(conn[:30] in compiled for conn in ORGANIC_CONNECTORS_DRAMA)
        assert has_drama_connector is True
        assert "Su mejor amigo me confesó toda la verdad" in compiled
        assert "cancelar la boda inmediatamente" in compiled
        assert "El Gran Secreto | Compilación Completa" == title


class TestM2TTSAndBrandingHarmony:
    """Test TTS markdown stripping and channel branding opening hook compliance."""

    def test_lib_tts_sanitization_strips_structural_headers(self):
        raw_script = (
            "Título: Caso 89.\n\n"
            "# Capítulo 1: El Descenso\n\n"
            "Sección Primera: Los Hechos.\n\n"
            "La expedición ingresó al complejo abandonado a las ocho de la mañana. "
            "**Advertencia**: no tocar las paredes cubiertas de musgo."
        )
        tts_ready = sanitize_text_for_tts(raw_script)

        assert "Título:" not in tts_ready
        assert "Capítulo" not in tts_ready
        assert "Sección" not in tts_ready
        assert "#" not in tts_ready
        assert "**" not in tts_ready
        assert "La expedición ingresó al complejo abandonado" in tts_ready
        assert "Advertencia: no tocar las paredes" in tts_ready

    def test_strip_markdown_for_tts_comprehensive(self):
        text = "# Capítulo 1\n\n**Texto en negrita**, *texto en cursiva*, [enlace](http://test.com), ## Sección 2"
        res = strip_markdown_for_tts(text)
        assert "#" not in res
        assert "Capítulo" not in res
        assert "Sección" not in res
        assert "**" not in res
        assert "*" not in res
        assert "Texto en negrita, texto en cursiva, enlace" in res

    def test_channel_branding_intro_hooks_compliance(self):
        moku_branding = get_channel_branding("moku")
        aelithia_branding = get_channel_branding("aelithia")

        for b in [moku_branding, aelithia_branding]:
            hook = b.intro_hook_template
            assert hook, f"Channel {b.channel_key} intro_hook_template must not be empty"
            hook_lower = hook.lower()
            assert "bienvenidos" not in hook_lower
            assert "hola" not in hook_lower
            assert "saludos" not in hook_lower
            assert "hoy les traigo" not in hook_lower
            assert "hoy veremos" not in hook_lower
            assert "apaga las luces" not in hook_lower
            # Must pass pre-TTS barrier as a valid clean statement
            assert validate_pre_tts_script(hook) is True
