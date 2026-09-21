"""WP2 / AUD-02 — AI-first curation chain is fail-closed."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src import llm
from src.core.domain import AIProviderChainExhausted


def _raw() -> str:
    return "Historia de terror suficiente para curar. " * 20


def test_regex_only_when_explicit_C():
    out = llm.curate_script(_raw(), title="T", provider="C", min_words=40)
    assert isinstance(out, str) and len(out.split()) >= 10


def test_chain_exhausted_raises_fail_closed(monkeypatch):
    monkeypatch.setenv("TEST_MODE", "0")
    with patch.object(llm, "_curate_with_agent", return_value=None), \
         patch.object(llm, "_curate_with_gemini", return_value=None):
        with pytest.raises(AIProviderChainExhausted):
            llm.curate_script(
                _raw(), title="T", provider="A",
                min_words=40,
            )


def test_provider_A_success_short_circuits(monkeypatch):
    monkeypatch.setenv("TEST_MODE", "0")
    good = "Palabra " * 60
    with patch.object(llm, "_curate_with_agent", return_value=good) as mA, \
         patch.object(llm, "_curate_with_gemini") as mB:
        out = llm.curate_script(_raw(), title="T", provider="A", min_words=40)
        assert out == good
        mB.assert_not_called()
        assert mA.called


def test_fallback_to_B_when_A_fails(monkeypatch):
    monkeypatch.setenv("TEST_MODE", "0")
    good = "Guion " * 50
    with patch.object(llm, "_curate_with_agent", return_value=None), \
         patch.object(llm, "_curate_with_gemini", return_value=good):
        out = llm.curate_script(_raw(), title="T", provider="A", min_words=40)
        assert out == good


def test_story_investigator_never_returns_degraded_script():
    from src.agents.story_director import StoryDirectorAgent, StoryInvestigatorAgent
    from src.core.domain import AIProviderChainExhausted

    agent = StoryInvestigatorAgent.__new__(StoryInvestigatorAgent)
    fake_res = {"output": {"reply": "", "error": "harness down"}}
    with patch.object(StoryInvestigatorAgent, "run", return_value="/tmp/x"), \
         patch.object(StoryInvestigatorAgent, "consume", return_value=fake_res):
        with pytest.raises(AIProviderChainExhausted):
            agent.generate_script("tema")
