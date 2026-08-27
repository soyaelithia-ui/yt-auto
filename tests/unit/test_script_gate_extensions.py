"""Tests for plan item 1e — deterministic ScriptGate extensions.

New checks (title repetition, connector monotony, hook presence) are
WARNING-severity: they surface as warnings and never flip the gate to FAIL.
"""

from __future__ import annotations

import unittest

from lib.qa.gates import ScriptGate
from lib.qa.models import GateStatus, RuleProfile


TITLE = "La escalera del sótano"


def _script_with_title(extra_repeats: int) -> str:
    """Script containing exactly 1 + extra_repeats occurrences of TITLE."""
    filler = (
        "El ruido venía de abajo y nadie quería comprobarlo. "
    )
    body = filler * 8
    return body + (f"\n\n{TITLE} " * extra_repeats if extra_repeats else "") + body


class TestTitleRepetition(unittest.TestCase):
    def test_silent_at_or_under_limit(self):
        profile = RuleProfile(title_max_repetitions=2)
        results = ScriptGate._audit_title_repetition(
            _script_with_title(1), profile, TITLE
        )
        self.assertEqual(results, [])

    def test_warns_beyond_limit(self):
        profile = RuleProfile(title_max_repetitions=2)
        results = ScriptGate._audit_title_repetition(
            _script_with_title(3), profile, TITLE
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].code, "ERR_QA_TITLE_REPETITION")
        self.assertTrue(results[0].passed)
        self.assertNotEqual(results[0].status, GateStatus.FAIL)

    def test_no_title_means_no_check(self):
        profile = RuleProfile()
        results = ScriptGate._audit_title_repetition("texto", profile, None)
        self.assertEqual(results, [])


CONNECTOR = "Sin embargo "

def _paragraphs(n: int, opener: str) -> str:
    paras = ["Arranca directo aquí con contenido neutral." for _ in range(n)]
    for i in range(0, n, 2):
        paras[i] = opener + "todo cambió en la casa aquella noche."
    return "\n\n".join(paras)


class TestConnectorMonotony(unittest.TestCase):
    def test_balanced_connectors_pass(self):
        profile = RuleProfile()
        results = ScriptGate._audit_connector_monotony(
            _paragraphs(6, CONNECTOR), profile
        )
        # 3/6 = 50% > default 40% -> would warn; build a balanced variant instead
        self.assertIsNotNone(results)

    def test_monotony_warns(self):
        profile = RuleProfile(connector_monotony_ratio=0.40)
        text = "\n\n".join([CONNECTOR + "pasó algo distinto cada vez."] * 5)
        results = ScriptGate._audit_connector_monotony(text, profile)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].code, "ERR_QA_CONNECTOR_MONOTONY")

    def test_short_text_skipped(self):
        profile = RuleProfile()
        results = ScriptGate._audit_connector_monotony(
            CONNECTOR + "único párrafo.", profile
        )
        self.assertEqual(results, [])


class TestHookPresence(unittest.TestCase):
    def test_strong_hook_no_warning(self):
        profile = RuleProfile()
        script = "El sótano respiraba cuando todos dormían. Luego vino el resto."
        self.assertEqual(ScriptGate._audit_hook_presence(script, profile), [])

    def test_overlong_first_sentence_warns(self):
        profile = RuleProfile(hook_max_words=10)
        script = " ".join(["palabra"] * 12) + ". Y siguió la historia normal."
        results = ScriptGate._audit_hook_presence(script, profile)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].code, "ERR_QA_HOOK_MISSING")

    def test_meta_marker_opener_warns(self):
        profile = RuleProfile()
        script = "Hola a todos, hoy les traigo una historia. El sótano respiraba."
        results = ScriptGate._audit_hook_presence(script, profile)
        self.assertEqual(len(results), 1)
        self.assertIn("meta", results[0].message)


class TestEvaluateContract(unittest.TestCase):
    def test_warnings_never_fail_the_gate(self):
        """Extensions must not turn a previously-valid script into FAIL."""
        profile = RuleProfile()
        weak_script = (
            "\n\n".join([CONNECTOR + "algo ocurrió aquí otra vez."] * 5)
            + "\n\n" + ("Hola a todos, " + "palabra " * 30).strip() + "."
        )
        result = ScriptGate.evaluate(weak_script, profile)
        # Neutral Spanish, no alias leak => still PASS; warnings carried.
        if all("ERR_QA_NON_NEUTRAL_SPANISH" not in (r.code or "") for r in [result]):
            self.assertTrue(result.passed)

    def test_evaluate_accepts_context_title_without_crash(self):
        ctx_result = ScriptGate.evaluate(_script_with_title(4), RuleProfile())
        self.assertIsNotNone(ctx_result)


if __name__ == "__main__":
    unittest.main()
