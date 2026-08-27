"""tests/unit/test_editorial_repair.py - Unit tests for editorial barrier and repair chain."""

from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from src.pipeline import _enforce_editorial_compliance
from src.sanitizer import (
    check_forbidden_editorial_elements,
    repair_forbidden_editorial,
)


def test_detect_forbidden_elements():
    """Detect forbidden greeting while clean narrative passes."""
    assert check_forbidden_editorial_elements("Hola a todos") is not None
    assert check_forbidden_editorial_elements("Historia limpia") is None


def test_repair_forbidden_editorial():
    """Deterministic repair drops forbidden sentence and retains valid ones."""
    good_prefix = "El bosque permanecía en absoluto silencio durante la medianoche."
    forbidden = "Saludos y bienvenidos al canal."
    good_suffix = "Nadie se atrevía a cruzar el río después de la puesta de sol."
    text = f"{good_prefix} {forbidden} {good_suffix}"

    repaired, removed = repair_forbidden_editorial(text)

    assert repaired == f"{good_prefix} {good_suffix}"
    assert removed == [forbidden]


def test_compliance_clean_script_passes_unchanged():
    """Clean script passes editorial compliance unchanged without alterations."""
    clean_script = (
        "El antiguo observatorio custodiaba registros de anomalías celestes "
        "detectadas a principios del siglo pasado. Los archivos siguen sellados."
    )
    result = _enforce_editorial_compliance(clean_script, stage="test", channel="moku")
    assert result == clean_script


def test_compliance_single_violation_deterministic_autorepair(monkeypatch):
    """Single violation is deterministically repaired without invoking AI."""
    good_prefix = "La criatura fue avistada en las inmediaciones del sector cuatro."
    forbidden = "Suscríbete y dale like al video."
    good_suffix = "El perímetro de contención fue reforzado de inmediato."
    text = f"{good_prefix} {forbidden} {good_suffix}"

    fake_ai = MagicMock(side_effect=RuntimeError("AI layer should not be called"))
    monkeypatch.setattr("src.llm._curate_with_gemini", fake_ai)

    result = _enforce_editorial_compliance(text, stage="test", channel="moku")

    assert result == f"{good_prefix} {good_suffix}"
    fake_ai.assert_not_called()


def test_compliance_irreparable_ai_fallback_success(monkeypatch):
    """Irreparable violation triggers AI fallback and accepts compliant rewrite."""
    clean_ai_script = (
        "En lo profundo del valle existía un refugio abandonado donde los "
        "investigadores registraron anomalías térmicas inexplicables. "
        "Las lecturas indicaban descensos bruscos de temperatura cada noche, "
        "coincidiendo con las observaciones del equipo de vigilancia nocturna."
    )

    fake_ai = MagicMock(return_value=clean_ai_script)
    monkeypatch.setattr("src.llm._curate_with_gemini", fake_ai)
    monkeypatch.setattr("src.sanitizer.repair_forbidden_editorial", lambda text: (text, []))

    irreparable_text = "Hola a todos en este relato misterioso sin solucion determinista"
    result = _enforce_editorial_compliance(irreparable_text, stage="test", channel="moku")

    assert result == clean_ai_script
    fake_ai.assert_called_once()


def test_compliance_irreparable_ai_failure_raises_value_error(monkeypatch):
    """Irreparable violation raises ValueError when AI fails or returns dirty text."""
    monkeypatch.setattr("src.sanitizer.repair_forbidden_editorial", lambda text: (text, []))
    irreparable_text = "Hola a todos en este relato misterioso sin solucion determinista"

    # Subcase: AI returns None
    monkeypatch.setattr("src.llm._curate_with_gemini", lambda prompt: None)
    with pytest.raises(ValueError, match="guion incumple barrera editorial"):
        _enforce_editorial_compliance(irreparable_text, stage="test", channel="moku")

    # Subcase: AI returns dirty text with forbidden element
    dirty_rewrite = (
        "Hola a todos y bienvenidos a este relato sobre los misterios ocultos "
        "en la estación de investigación polar durante el invierno de 1982."
    )
    monkeypatch.setattr("src.llm._curate_with_gemini", lambda prompt: dirty_rewrite)
    with pytest.raises(ValueError, match="guion incumple barrera editorial"):
        _enforce_editorial_compliance(irreparable_text, stage="test", channel="moku")


def test_extra_pattern_from_config_detected():
    """Extra pattern from config/editorial_rules.json triggers detection."""
    text_with_extra_pattern = (
        "El fenómeno fue documentado rigurosamente en este canal durante las expediciones."
    )
    violation = check_forbidden_editorial_elements(text_with_extra_pattern)
    assert violation is not None
    assert "este canal" in violation.lower()
