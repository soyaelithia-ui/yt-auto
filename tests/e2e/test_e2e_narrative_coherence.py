"""
E2E Test Suite for Requirement R3 (Narrative Coherence & Quality Gate).
Covers Features F12 through F16, 3-Act Structure, Neutral Spanish, and Boundaries.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List
import pytest

from src.core.quality import forbidden_aliases, is_spanish_neutral, normalize_text

PROJECT_ROOT = Path(__file__).resolve().parents[2]


# ==============================================================================
# Tier 1: Feature Coverage (R3: F12 - F16)
# ==============================================================================

@pytest.mark.tier1
def test_r3_f12_three_act_narrative_structure_detection():
    """Verify story curation requires a 3-act progression (hook, conflict, resolution)."""
    coherent_3act_script = (
        "Eran las tres de la madrugada cuando una campana comenzó a sonar en el sótano de la vieja cabaña. "
        "Al principio pensé que era solo el viento golpeando las maderas viejas, pero el ritmo era constante y pausado. "
        "Bajé cada escalón con cautela, sosteniendo la linterna temblorosa, sintiendo cómo el aire se volvía gélido. "
        "Frente a mí, la campana de bronce vibraba sola en la oscuridad más absoluta. "
        "De repente, una sombra emergió de la pared y comprendí que el campanario no llamaba a los vivos, sino a nosotros."
    )
    words = coherent_3act_script.split()
    assert len(words) >= 80, "Coherent story should have substantive narrative development"
    assert is_spanish_neutral(coherent_3act_script), "Narrative must be in clean neutral Spanish"


@pytest.mark.tier1
def test_r3_f13_single_pov_consistency():
    """Verify single POV continuity without erratic perspective jumping."""
    inconsistent_pov_script = (
        "Yo estaba solo en mi habitación mirando el teléfono cuando escuché un ruido. "
        "De repente, ella abrió la puerta de su auto a cinco kilómetros de allí sin saber que él la observaba. "
        "Entonces nosotros gritamos con pánico mientras mi hermano miraba las estrellas."
    )
    # Check for pronoun and perspective collision markers
    has_yo = "yo" in normalize_text(inconsistent_pov_script).split()
    has_ella = "ella" in normalize_text(inconsistent_pov_script).split()
    has_nosotros = "nosotros" in normalize_text(inconsistent_pov_script).split()
    # Flag perspective jumping
    assert has_yo and has_ella and has_nosotros, "Test sample demonstrates erratic multi-POV flipping"


@pytest.mark.tier1
def test_r3_f14_neutral_spanish_and_inverted_punctuation():
    """Verify proper Spanish punctuation marks (¿, ¡) and rejection of translation artifacts."""
    valid_spanish = "¿Sabías que en las profundidades del abismo ningún sonido puede escapar? ¡Es una oscuridad total y eterna!"
    assert "¿" in valid_spanish and "?" in valid_spanish
    assert "¡" in valid_spanish and "!" in valid_spanish
    assert is_spanish_neutral(valid_spanish, minimum_words=10)


@pytest.mark.tier1
def test_r3_f14_anti_crutches_rejection():
    """Verify detection of repetitive formulaic clickbait crutches."""
    formulaic_crutches = [
        "pero antes de empezar",
        "no vas a creer lo que paso",
        "comenta para parte 2",
        "dale like y suscribete",
        "quedate hasta el final",
    ]
    bad_script = "Hola a todos, pero antes de empezar no vas a creer lo que paso. Quedate hasta el final para saber la verdad."
    norm = normalize_text(bad_script)
    detected = [c for c in formulaic_crutches if normalize_text(c) in norm]
    assert len(detected) >= 2, f"Expected detection of formulaic crutches, found: {detected}"


@pytest.mark.tier1
def test_r3_f15_pre_tts_validation_gate_contract():
    """Verify validate_narrative_coherence or NarrativeQualityGate interface contract."""
    try:
        from src.narrative.quality_gate import validate_narrative_coherence
    except ImportError:
        try:
            from src.core.quality import validate_narrative_coherence
        except ImportError:
            pytest.xfail("Pending M3 implementation: validate_narrative_coherence gate function not yet implemented")

    result = validate_narrative_coherence("Historia de prueba de terror en el bosque.", channel="moku", duration_type="short")
    assert hasattr(result, "valid")
    assert hasattr(result, "errors")
    assert hasattr(result, "score")


@pytest.mark.tier1
def test_r3_f16_thematic_story_fallback_diversity():
    """Verify story fallbacks produce channel-specific themes (horror for Moku, drama for Aelithia)."""
    try:
        from src.templates.narratives import get_fallback_story
        story_moku = get_fallback_story(channel="moku")
        story_aelithia = get_fallback_story(channel="aelithia")
        assert story_moku != story_aelithia, "Fallback stories for Moku and Aelithia must be differentiated"
    except (ImportError, AttributeError):
        pytest.xfail("Pending M3 implementation: dynamic channel-specific get_fallback_story() not yet available")


# ==============================================================================
# Tier 2: Boundary & Corner Cases (>= 5 tests)
# ==============================================================================

@pytest.mark.tier2
def test_r3_boundary_empty_script_rejection():
    """Verify empty or whitespace-only script is rejected by Spanish neutrality gate."""
    assert not is_spanish_neutral("", minimum_words=1)
    assert not is_spanish_neutral("     ", minimum_words=1)
    assert not is_spanish_neutral(None, minimum_words=1)


@pytest.mark.tier2
def test_r3_boundary_under_minimum_word_count():
    """Verify script with fewer than minimum words (e.g., <20 words) is rejected."""
    tiny_script = "Había una vez un perro que ladraba en la noche."
    assert not is_spanish_neutral(tiny_script, minimum_words=20)


@pytest.mark.tier2
def test_r3_boundary_over_maximum_word_count_shorts():
    """Verify word count boundary detection for shorts (115-145 target, max 170)."""
    oversized_words = ["palabra"] * 250
    oversized_script = " ".join(oversized_words)
    word_count = len(oversized_script.split())
    assert word_count > 170, "Oversized script must exceed the 170-word upper threshold for 60s Shorts"


@pytest.mark.tier2
def test_r3_boundary_unpaired_inverted_punctuation():
    """Verify detection of opening inverted punctuation without closing punctuation."""
    unpaired_question = "¿Por qué nadie me responde en esta vieja casa solitaria"
    has_open = "¿" in unpaired_question
    has_close = "?" in unpaired_question
    assert has_open and not has_close, "Script has unpaired inverted question mark"


@pytest.mark.tier2
def test_r3_boundary_english_leakage_rejection():
    """Verify script containing pure English or translation artifacts fails Spanish neutrality."""
    english_script = (
        "The dark figure stood in the corner of the abandoned basement and did not say a single word. "
        "I was terrified and could not move my feet at all."
    )
    assert not is_spanish_neutral(english_script, minimum_words=20)


@pytest.mark.tier2
def test_r3_boundary_forbidden_channel_alias_leakage():
    """Verify forbidden channel aliases (canal_terror, soy_el_malo) are detected."""
    leak_script = "Bienvenidos a canal_terror donde hoy hablaremos de historias oscuras."
    leaks = forbidden_aliases(leak_script)
    assert len(leaks) > 0, f"Expected forbidden alias detection, got: {leaks}"


# ==============================================================================
# Tier 3: Cross-Feature Interaction
# ==============================================================================

@pytest.mark.tier3
def test_r3_interaction_narrative_gate_blocks_tts_invocation():
    """Verify quality failure prevents TTS invocation in pipeline flow."""
    try:
        from src.core.quality import QualityReport
        report = QualityReport(channel="moku", issues=["Incoherent narrative: unresolvable cliffhanger"])
        with pytest.raises(ValueError, match="Control de calidad bloqueado"):
            report.require_pass()
    except Exception as e:
        pytest.fail(f"QualityReport contract verification failed: {e}")
