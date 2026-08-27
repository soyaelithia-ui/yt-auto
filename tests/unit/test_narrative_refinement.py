"""
tests/unit/test_narrative_refinement.py - Unit test suite for narrative refinement,
anti-spanglish sanitization, title repetition suppression, and audio tail buffering.
"""

import pytest
from src.templates.narratives import (
    build_moku_longform_narrative,
    build_aelithia_longform_narrative,
    build_moku_short_narrative,
    build_aelithia_short_narrative,
    build_channel_narrative,
)
from src.sanitizer import (
    normalize_spanglish_terms,
    suppress_title_repetition,
    limpiar_texto_para_tts,
)


def test_moku_longform_first_person_no_headers():
    topic = "La Estación de Radio Olvidada"
    script = build_moku_longform_narrative(topic, channel="moku")
    
    # Assert rich length and first-person perspective
    assert len(script.split()) >= 1000
    assert "mi memoria" in script or "mi labor" in script or "mi puesto" in script
    # Assert absence of robotic section headers
    assert "Sección Primera" not in script
    assert "Capítulo 1" not in script
    # Assert topic is not mechanically repeated in every single paragraph
    assert script.count(topic) <= 2


def test_aelithia_longform_multi_case_with_dialogue():
    topic = "El Testamento de la Abuela"
    script = build_aelithia_longform_narrative(topic, channel="aelithia")
    
    # Assert multi-case structure
    assert len(script.split()) >= 900
    assert "primer caso" in script.lower()
    assert "segundo caso" in script.lower()
    assert "tercer" in script.lower()
    # Assert direct dialogue quotes
    assert "'" in script or '"' in script or "'Dado que" in script
    # Assert absence of military or radiation tropes
    assert "búnker" not in script.lower()
    assert "radiación" not in script.lower()
    # Assert topic is not repeated excessively
    assert script.count(topic) <= 2


def test_moku_short_scp_087_canonical_lore():
    topic = "SCP-087: El Pozo de las Escaleras"
    script = build_moku_short_narrative(topic, channel="moku")
    
    assert "escalera" in script.lower()
    assert "oscuridad" in script.lower()
    assert "rostro" in script.lower()
    assert "llanto" in script.lower() or "sollozos" in script.lower()
    assert "087" in script


def test_aelithia_short_aita_structure():
    topic = "Vender la casa de mi infancia"
    script = build_aelithia_short_narrative(topic, channel="aelithia")
    
    assert "¿Soy yo el malo" in script or "¿Soy la mala" in script or "límites" in script
    assert "@Aelithia" in script or "comentarios" in script


def test_normalize_spanglish_terms():
    raw_text = "El muro de concreto reinforced dentro de la security facility fue sellado."
    clean_text = normalize_spanglish_terms(raw_text)
    assert "concreto reforzado" in clean_text
    assert "instalación de seguridad" in clean_text
    assert "reinforced" not in clean_text


def test_suppress_title_repetition():
    title = "La Gran Disputa Familiar"
    repeated_text = (
        f"Párrafo uno sobre {title}. "
        f"Párrafo dos hablando de {title}. "
        f"Párrafo tres acerca de {title}. "
        f"Párrafo cuatro recordando {title}."
    )
    suppressed = suppress_title_repetition(repeated_text, title, max_allowed=2)
    assert suppressed.count(title) == 2
    assert "este conflicto" in suppressed or "este suceso" in suppressed or "esta situación" in suppressed
