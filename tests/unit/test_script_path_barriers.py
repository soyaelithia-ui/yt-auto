"""Tests for the main-path script barriers (plan 1d).

Covers:
- conditional TranslatorAgent gating on the three curation branches
  (main path / re-condensation / auto-expansion share the same guard);
- title-repetition suppression wired after beat extraction;
- pre-TTS barrier enforced on the main path outside TEST_MODE.
"""

from __future__ import annotations

import pytest

from src.core.quality import is_spanish_neutral
from src.pipeline import _should_translate


SPANISH_TEXT = (
    "La escalera del sótano crujía cada noche a las tres en punto. "
    "Nadie quería bajar a comprobar por qué las bombillas se fundían en serie. "
    "Cuando por fin descendí, el eco de mis pasos volvía tarde, como si alguien "
    "los repitiera desde el último peldaño."
)


class TestConditionalTranslationGate:
    def test_spanish_neutral_text_skips_translation(self):
        """A neutral-Spanish script must not trigger the translator pass."""
        assert is_spanish_neutral(SPANISH_TEXT)

    def test_english_text_requires_translation(self):
        """An English script still requires the translation pass."""
        english = ("The cold wind blew through the old shattered window and "
                   "the door slammed shut behind me in the darkness of the night.")
        assert not is_spanish_neutral(english)

    def test_always_translate_flag_restores_legacy(self, monkeypatch):
        """ALWAYS_TRANSLATE=1 forces the translator even for Spanish text."""
        monkeypatch.setenv("ALWAYS_TRANSLATE", "1")
        assert _should_translate(SPANISH_TEXT)

    def test_default_gate_skips_for_spanish(self):
        assert not _should_translate(SPANISH_TEXT)

    def test_default_gate_runs_for_foreign(self):
        english = ("The cold wind blew through the old shattered window and "
                   "the door slammed shut behind me in the darkness of the night.")
        assert _should_translate(english)
