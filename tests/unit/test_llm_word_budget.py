"""Unit tests for the Shorts word-budget contract in src/llm.py.

Regression context (2026-08-23): provider A/B ignored ``max_words``; an
881-word script produced 292s of TTS audio against the 180s Short cap and the
re-condensation retry overshot again, failing production runs with
RETRYABLE_FAILED. The chain must now honor the budget: prompt instruction for
LLM providers plus a deterministic sentence-boundary trim as a hard guarantee.
"""

import unittest
from unittest.mock import patch, MagicMock

from src.llm import (
    _trim_script_to_max_words,
    _word_budget_instruction,
    curate_script,
)


class TestTrimScriptToMaxWords(unittest.TestCase):
    def test_returns_script_unchanged_when_within_budget(self):
        script = "Primera frase corta. Segunda frase también corta."
        self.assertEqual(_trim_script_to_max_words(script, 50), script)

    def test_noop_without_budget(self):
        script = "palabra " * 500
        self.assertEqual(_trim_script_to_max_words(script, None), script)
        self.assertEqual(_trim_script_to_max_words(script, 0), script)
        self.assertEqual(_trim_script_to_max_words("", 100), "")

    def test_trims_at_sentence_boundary_inside_budget(self):
        sentences = [f"Frase número {i} sigue aquí." for i in range(1, 60)]
        script = " ".join(sentences)  # ~7 words per sentence → >300 words
        trimmed = _trim_script_to_max_words(script, 100)
        word_count = len(trimmed.split())
        self.assertLessEqual(word_count, 100)
        # Cut lands on a complete sentence, never mid-word.
        self.assertTrue(trimmed.endswith("."))
        self.assertGreaterEqual(word_count, int(100 * 0.6))

    def test_falls_back_to_hard_cut_without_sentence_boundary(self):
        script = " ".join(["palabra"] * 150)  # no '.' '!' '?' anywhere
        trimmed = _trim_script_to_max_words(script, 100)
        self.assertEqual(len(trimmed.split()), 100)


class TestWordBudgetInstruction(unittest.TestCase):
    def test_instruction_contains_limit(self):
        text = _word_budget_instruction(340)
        self.assertIn("340", text)
        self.assertIn("máximo", text)

    def test_empty_without_budget(self):
        self.assertEqual(_word_budget_instruction(None), "")
        self.assertEqual(_word_budget_instruction(0), "")


class TestCurateScriptHonorsMaxWords(unittest.TestCase):
    def test_provider_a_overshoot_is_trimmed_to_budget(self):
        long_story = " ".join(
            f"La noche del turno {i} pasó lenta en el túnel B." for i in range(200)
        )
        scripted = "Guion. " + " ".join(
            f"Escena {i} del relato termina aquí." for i in range(120)
        )

        class FakeAgent:
            def __init__(self, *args, **kwargs):
                pass

            def run(self, prompt):
                self.prompt = prompt
                return "/tmp/fake"

            def consume(self, path):
                assert "máximo 340 palabras" in self.prompt
                return {"output": {"reply": f"<script>{scripted}</script>"}}

        with (
            patch("src.agents.base_agent.ProgrammaticAgent", FakeAgent),
            patch("src.agents.base_agent.CANONICAL_MODEL", "fake-model"),
        ):
            result = curate_script(
                long_story,
                title="El túnel B",
                min_words=160,
                max_words=340,
            )
        self.assertIsNotNone(result)
        self.assertLessEqual(len(result.split()), 340)

    def test_short_path_regex_provider_truncates(self):
        long_story = " ".join(f"Palabra{i}" for i in range(900))
        result = curate_script(
            long_story,
            title="Historia",
            min_words=160,
            max_words=340,
            provider="C",
        )
        self.assertLessEqual(len(result.split()), 340)


if __name__ == "__main__":
    unittest.main()
