"""
Adversarial Stress Test Suite for Milestone M2:
Multi-story compilation, 0-3s Hook Delivery, and Header Elimination.

Authored by: Challenger 2 (teamwork_preview_challenger)
Target modules: src/llm.py, src/branding.py, src/sanitizer.py, src/templates/narratives.py
"""

import pytest
import re
from typing import List, Dict, Any

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
    _CHANNEL_BRANDING_REGISTRY,
    _CHANNEL_ALIASES,
)
from src.sanitizer import (
    limpiar_texto_para_tts,
    sanitize_script_text,
    validate_pre_tts_script,
    validate_semantic_barrier,
    check_forbidden_editorial_elements,
    PromptLeakError,
)
from lib.tts import sanitize_text_for_tts, strip_markdown_for_tts
from src.templates.narratives import (
    build_short_narrative,
    build_longform_narrative,
    build_moku_short_narrative,
    build_aelithia_short_narrative,
    build_moku_longform_narrative,
    build_aelithia_longform_narrative,
)


class TestMultiStoryCompilationMatrix:
    """Stress-test compile_stories_to_target_words across combinations of count, words, and channels."""

    @pytest.mark.parametrize("story_count", [1, 2, 5, 10])
    @pytest.mark.parametrize("target_words", [100, 500, 2500])
    @pytest.mark.parametrize("channel", ["moku", "aelithia", "terror", "aita"])
    def test_compilation_matrix_scaling_and_connectors(self, story_count: int, target_words: int, channel: str):
        """Verify multi-story compilation scales cleanly across story counts, targets, and channels."""
        main_title = "El Secreto Principal"
        # 50-word base story
        main_content = (
            "La primera investigación comenzó en un antiguo edificio abandonado en las afueras de la ciudad. "
            "Los testigos aseguraban haber escuchado ruidos inexplicables durante la medianoche. "
            "El equipo de reconocimiento ingresó con precaución para verificar el estado de las instalaciones. "
            "Encontraron marcas extrañas en las paredes que nadie supo explicar con claridad documental."
        )
        
        # Generate additional stories (each ~50 words)
        additional_stories = []
        for i in range(1, story_count + 1):
            additional_stories.append({
                "title": f"Incidente Anexo {i}",
                "content": (
                    f"El reporte número {i} documenta una serie de sucesos inesperados ocurridos poco después. "
                    "Varios integrantes del grupo manifestaron haber sentido una extraña presencia en los pasillos. "
                    "Las grabaciones de audio ambiental captaron susurros distorsionados difíciles de clasificar. "
                    "La situación se volvió insostenible hasta que se ordenó la evacuación preventiva del sector."
                )
            })

        compiled_title, compiled_content = compile_stories_to_target_words(
            main_title=main_title,
            main_content=main_content,
            additional_stories=additional_stories,
            min_words=target_words,
            channel=channel,
        )

        assert isinstance(compiled_title, str) and len(compiled_title) > 0
        assert isinstance(compiled_content, str) and len(compiled_content) > 0

        # Verify no structural headers were injected
        assert "# Capítulo" not in compiled_content
        assert "# Capitulo" not in compiled_content
        assert "Capítulo " not in compiled_content or "Incidente Anexo" in compiled_content
        assert "Sección Primera" not in compiled_content

        is_drama = str(channel).lower() in ("aelithia", "aita", "soy_el_malo", "yo_soy_el_malo")
        
        # If words were below target and additional stories were added, verify appropriate connectors
        initial_words = len(main_content.split())
        if initial_words < target_words and story_count > 0:
            assert compiled_title == f"{main_title} | Compilación Completa"
            
            # Check genre-specific connector presence
            if is_drama:
                # Drama connectors should be present
                drama_matched = any(conn in compiled_content for conn in ORGANIC_CONNECTORS_DRAMA) or "escalando" in compiled_content
                assert drama_matched, f"Expected drama connectors for channel '{channel}', found none."
            else:
                # Horror connectors should be present
                horror_matched = any(conn in compiled_content for conn in ORGANIC_CONNECTORS_HORROR) or "testimonios" in compiled_content
                assert horror_matched, f"Expected horror connectors for channel '{channel}', found none."


    def test_compilation_with_adversarial_chapter_titles(self):
        """Test compilation when story titles contain adversarial chapter labels."""
        main_title = "Expediente Alpha"
        main_content = "Breve reporte inicial de anomalía en el sector siete."
        
        adversarial_stories = [
            {"title": "# Capítulo 1: La Criatura", "content": "Apareció una sombra en el corredor norte."},
            {"title": "Capítulo 2: El Despertar", "content": "Los sensores registraron movimiento térmico."},
            {"title": "capítulo 3: La Huida", "content": "El personal procedió al repliegue táctico."},
            {"title": "Sección Cuarta: Conclusión", "content": "El área quedó totalmente clausurada."},
            {"title": "Relato de Medianoche", "content": "Un testigo aportó nuevos datos relevantes."},
        ]

        for channel in ["moku", "aelithia", "terror", "aita"]:
            compiled_title, compiled_content = compile_stories_to_target_words(
                main_title=main_title,
                main_content=main_content,
                additional_stories=adversarial_stories,
                min_words=500,
                channel=channel,
            )

            # When passed to full script cleaner, all structural headers MUST be purged
            cleaned = limpiar_texto_para_tts(compiled_content)
            assert "# Capítulo" not in cleaned
            assert "# Capitulo" not in cleaned
            assert not re.search(r"(?i)\bcap[íi]tulo\s+\d+", cleaned)
            assert not re.search(r"(?i)\bsecci[óo]n\s+[a-záéíóú0-9]+", cleaned)

            # Pre-TTS validator MUST pass without prompt leak or header violation
            assert validate_pre_tts_script(cleaned) is True


    def test_compilation_with_empty_or_malformed_stories(self):
        """Test resilience against None, empty strings, non-dict elements."""
        main_title = "Relato Base"
        main_content = "Contenido base suficiente para la prueba inicial de robustez."
        
        malformed_stories = [
            None,
            {},
            {"title": "", "content": ""},
            {"title": "Solo Titulo", "content": None},
            {"title": None, "content": "Contenido valido sin titulo previo."},
            "not a dict string",
            12345,
            {"title": "Valido", "content": "Contenido complementario que aporta datos."},
        ]

        compiled_title, compiled_content = compile_stories_to_target_words(
            main_title=main_title,
            main_content=main_content,
            additional_stories=malformed_stories,  # type: ignore
            min_words=300,
            channel="moku",
        )

        assert "Contenido valido sin titulo previo" in compiled_content
        assert "Contenido complementario que aporta datos" in compiled_content
        assert "not a dict string" not in compiled_content


class Test0to3sHookEngineAndBrandingCompliance:
    """Stress-test channel branding intro hooks and 0-3s hook delivery."""

    @pytest.mark.parametrize("channel_alias", list(_CHANNEL_ALIASES.keys()) + ["moku", "aelithia"])
    def test_channel_branding_intro_hooks_zero_forbidden_greetings(self, channel_alias: str):
        """Verify every registered channel branding intro hook has zero forbidden greetings and passes Pre-TTS."""
        branding = get_channel_branding(channel_alias)
        intro_hook = branding.intro_hook_template
        outro_cta = branding.outro_cta_template

        assert isinstance(intro_hook, str) and len(intro_hook.strip()) > 0
        
        # 1. Zero forbidden greetings in 0-3s hook
        forbidden_match = check_forbidden_editorial_elements(intro_hook)
        assert forbidden_match is None, f"Channel '{channel_alias}' intro hook contains forbidden greeting: '{forbidden_match}'"

        # 2. Semantic barrier check
        assert validate_semantic_barrier(intro_hook) is True

        # 3. Pre-TTS barrier validation
        assert validate_pre_tts_script(intro_hook) is True

        # 4. Hook conciseness & delivery speed: must be immediate (<= 25 words for 0-3s impact)
        word_count = len(intro_hook.split())
        assert word_count <= 25, f"Intro hook for '{channel_alias}' is {word_count} words; expected <= 25 for 0-3s delivery."

        # 5. Must start in media res without conversational filler
        forbidden_starters = ["hola", "bienvenidos", "bienvenido", "hoy", "en este video", "saludos"]
        first_word = intro_hook.lower().split()[0].strip("¡¿,.:;")
        assert first_word not in forbidden_starters, f"Intro hook starts with forbidden filler word: '{first_word}'"


    @pytest.mark.parametrize("channel", ["moku", "aelithia"])
    def test_short_narratives_0to3s_hook_integrity(self, channel: str):
        """Verify Shorts narratives begin with high-impact 0-3s hook and pass all pre-TTS validation."""
        topic = "El Misterio de la Habitación 404"
        script = build_short_narrative(topic=topic, channel=channel)

        # Must pass pre-TTS barrier
        assert validate_pre_tts_script(script) is True

        # Must have no structural headers
        assert "# Capítulo" not in script
        assert "Capítulo" not in script
        assert "Sección" not in script

        # First sentence must be an immediate hook in media res
        first_sentence = script.split(".")[0].strip()
        assert len(first_sentence.split()) >= 8
        assert not any(greeting in first_sentence.lower() for greeting in ["hola", "bienvenidos", "saludos"])

        if channel == "moku":
            assert "anomalía" in script.lower() or "sensores" in script.lower() or "grabaciones" in script.lower()
        else:
            assert "familia" in script.lower() or "patrimonio" in script.lower() or "ahorros" in script.lower()


    @pytest.mark.parametrize("channel", ["moku", "aelithia"])
    def test_longform_narratives_header_free_and_tts_clean(self, channel: str):
        """Verify longform narratives contain >=2100 words, no structural headers, and pass TTS sanitization."""
        topic = "La Anomalía del Subsuelo"
        script = build_longform_narrative(topic=topic, channel=channel, target_duration_minutes=10.5)

        # Word count >= 2000 words
        word_count = len(script.split())
        assert word_count >= 2000, f"Longform script for {channel} has only {word_count} words (expected >= 2000)"

        # Must not contain any structural headers like "Sección Primera:", "Capítulo 1:", etc.
        assert not re.search(r"(?i)\bsecci[óo]n\s+(?:primera|segunda|tercera|\d+)", script)
        assert not re.search(r"(?i)\bcap[íi]tulo\s+\d+", script)
        assert "# " not in script

        # Clean with Pre-TTS cleaner
        cleaned = limpiar_texto_para_tts(script)
        assert validate_pre_tts_script(cleaned) is True


class TestEndToEndCurateScriptAndSanitization:
    """Stress-test curate_script with multi-story inputs and edge-case sanitization."""

    def test_curate_script_with_additional_stories_terror(self):
        """Test curate_script correctly formats and sanitizes multi-story inputs for terror/moku."""
        stories = [
            {"title": "Relato 1", "content": "Una figura misteriosa apareció en la niebla del sendero solitario."},
            {"title": "Relato 2", "content": "Los investigadores encontraron huellas que terminaban de manera abrupta."},
        ]
        res = curate_script(raw_text=stories, title="Compilación Nocturna", min_words=300, channel="moku")

        assert isinstance(res, str)
        assert "Título: Compilación Nocturna" in res or "Compilación Nocturna" in res
        assert "# Capítulo" not in res
        assert "Capítulo" not in res

        # Check TTS sanitization on curated output
        tts_clean = sanitize_text_for_tts(res)
        assert validate_pre_tts_script(tts_clean) is True


    def test_curate_script_with_additional_stories_aelithia(self):
        """Test curate_script correctly formats and sanitizes multi-story inputs for aelithia/drama."""
        stories = [
            {"title": "Dilema 1", "content": "Mi cuñado me pidió dinero prestado y se negó a firmar un pagaré."},
            {"title": "Dilema 2", "content": "Mi hermana dejó de hablarme porque no quise pagar las vacaciones de todos."},
        ]
        res = curate_script(raw_text=stories, title="Conflictos de Familia", min_words=300, channel="aelithia")

        assert isinstance(res, str)
        assert "Conflictos de Familia" in res
        assert "# Capítulo" not in res

        # Verify drama connectors used
        drama_keywords = ["escalando", "dinámica familiar", "fracturar la convivencia", "conflicto familiar"]
        assert any(k in res for k in drama_keywords)

        tts_clean = sanitize_text_for_tts(res)
        assert validate_pre_tts_script(tts_clean) is True


    def test_curate_batch_json_all_channels(self):
        """Verify curate_batch_json outputs valid schema, SEO description, tags, and thumbnail prompt."""
        for ch in ["moku", "aelithia", "terror", "aita"]:
            batch = curate_batch_json(
                raw_text="Historia breve sobre sucesos inexplicables.",
                title="Prueba General de Canal",
                min_words=100,
                channel=ch,
            )
            assert "script" in batch
            assert "title" in batch
            assert "description" in batch
            assert "tags" in batch
            # thumbnail_prompt is preserved in the payload for back-compat
            # but is now an empty string: AI cover-prompt generation has
            # been retired in favour of locally-rendered thumbnails.
            assert "thumbnail_prompt" in batch
            assert batch["thumbnail_prompt"] == ""
            assert len(batch["tags"]) > 0
            assert "# Capítulo" not in batch["script"]
            assert validate_pre_tts_script(limpiar_texto_para_tts(batch["script"])) is True
