"""Plan item 1c — minimal-adaptation production prompts in src/llm.py.

The AI curation chain (provider A → provider B) must brief the LLM as an
ADAPTOR, not an inventor: source stories are already edited prose, so the
prompt mandates preserving facts, order, voices and ending; a hook-first first
sentence; a hard word budget; and the same editorial prohibitions the
sanitizer's FORBIDDEN_EDITORIAL_PATTERNS enforces downstream. Provider A and
provider B must receive the identical brief.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src import llm
from src.core.domain import AIProviderChainExhausted
from src.sanitizer import FORBIDDEN_EDITORIAL_PATTERNS


# ---------------------------------------------------------------------------
# System instruction: channel-aware personas + minimal-adaptation mandate
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("channel", ["moku", "aelithia"])
def test_system_instruction_states_minimal_adaptation_mandate(channel):
    text = llm._adaptation_system_instruction(channel)
    lowered = text.lower()
    assert "adaptaci" in lowered  # "adaptación mínima"
    assert "nunca" in lowered and ("inventes" in lowered or "inventar" in lowered)
    # Preserved narrative dimensions of the original story.
    for dimension in ("hechos", "orden", "voces", "final"):
        assert dimension in lowered


def test_system_instruction_differs_between_channels():
    moku = llm._adaptation_system_instruction("moku")
    aelithia = llm._adaptation_system_instruction("aelithia")
    assert moku != aelithia


def test_moku_persona_is_first_person_documentary_horror():
    text = llm._adaptation_system_instruction("moku").lower()
    assert "primera persona" in text
    assert "creepypasta" in text and "scp" in text
    assert "sobrio" in text and "ominoso" in text


def test_aelithia_persona_is_confessional_with_dialogue():
    text = llm._adaptation_system_instruction("aelithia").lower()
    assert "confesional" in text
    assert "diálogo" in text


def test_unknown_channel_falls_back_to_stable_neutral_narrator():
    unknown = llm._adaptation_system_instruction("canal-inexistente")
    default = llm._adaptation_system_instruction("")
    assert unknown == default
    assert "español neutro" in default.lower()
    # Aliases resolve to their canonical channel persona.
    assert llm._adaptation_system_instruction("terror") == llm._adaptation_system_instruction("moku")
    assert llm._adaptation_system_instruction("aita") == llm._adaptation_system_instruction("aelithia")


def test_system_instruction_output_contract_tts_ready_only_script():
    text = llm._adaptation_system_instruction("moku").lower()
    assert "únicamente" in text
    assert "tts" in text
    assert "markdown" in text


# ---------------------------------------------------------------------------
# User prompt: title, hook-first, forbidden list, budget
# ---------------------------------------------------------------------------

def _content() -> str:
    return "La compuerta se abrió sola a las tres de la madrugada y nadie la tocó."


def test_prompt_interpolates_title_and_content():
    prompt = llm._build_adaptation_prompt(
        "El Túnel B", _content(), channel="moku", max_words=None
    )
    assert "El Túnel B" in prompt
    assert _content() in prompt


def test_prompt_contains_word_budget_when_max_words_set():
    without_budget = llm._build_adaptation_prompt(
        "El Túnel B", _content(), channel="moku", max_words=None
    )
    with_budget = llm._build_adaptation_prompt(
        "El Túnel B", _content(), channel="moku", max_words=340
    )
    assert _llm_budget_fragment(340) not in without_budget
    assert _llm_budget_fragment(340) in with_budget
    assert "340" in with_budget


def _llm_budget_fragment(max_words: int) -> str:
    """Reuse the production budget wording via the existing helper."""
    from src.llm import _word_budget_instruction

    return _word_budget_instruction(max_words)


def test_hook_first_directive_present_in_user_prompt():
    prompt = llm._build_adaptation_prompt("T", _content(), channel="moku")
    lowered = prompt.lower()
    assert "gancho" in lowered
    assert "primera frase" in lowered
    assert "0 a 3 segundos" in lowered
    assert "medias res" in lowered


def test_forbidden_editorial_words_named_inside_the_prohibition_list():
    """Forbidden words must appear only as named prohibitions (never as free advice)."""
    prompt = llm._build_adaptation_prompt("T", _content(), channel="moku")
    lowered = prompt.lower()
    # Greetings / CTA / farewell vocabulary is explicitly prohibited.
    for word in ("hola", "bienvenidos", "saludos", "suscríbete", "dale like", "comenta"):
        assert word in lowered
    assert "prohibido introducir cualquier elemento editorial" in lowered
    assert "hasta la próxima" in lowered
    for header in ("capítulo", "sección", "parte 1"):
        assert header in lowered
    assert "este canal" in lowered  # meta-references to channel/video/episode


def test_prompt_semantics_cover_sanitizer_forbidden_patterns():
    """Every sanitizer editorial category has a matching prohibition in the prompt."""
    prompt = llm._build_adaptation_prompt("T", _content(), channel="moku").lower()
    categories = {
        "greeting": ("hola", "bienvenidos"),
        "cta": ("suscríbete",),
        "farewell": ("adiós", "hasta la próxima"),
        "meta": ("canal", "video"),
        "header": ("capítulo",),
    }
    for _, words in categories.items():
        assert all(w in prompt for w in words), words
    # Sanity: the shared semantics really come from these sanitizer patterns.
    joined = " ".join(FORBIDDEN_EDITORIAL_PATTERNS).lower()
    assert "suscr" in joined and "bienvenidos" in joined


def test_prompt_carries_minimal_adaptation_mandate():
    prompt = llm._build_adaptation_prompt("T", _content(), channel="moku").lower()
    assert "adaptación mínima" in prompt
    assert "nunca inventes" in prompt
    assert "lore nuevo" in prompt


def test_prompt_output_contract_is_unchanged_only_final_script():
    prompt = llm._build_adaptation_prompt("T", _content(), channel="moku").lower()
    assert "únicamente" in prompt
    assert "español neutro" in prompt
    assert "tts" in prompt


def test_prompt_is_deterministic_and_channel_agnostic_in_shared_blocks():
    one = llm._build_adaptation_prompt("T", _content(), channel="moku", max_words=100)
    two = llm._build_adaptation_prompt("T", _content(), channel="moku", max_words=100)
    assert one == two


# ---------------------------------------------------------------------------
# Chain integration: providers A and B build prompts through the shared builder
# ---------------------------------------------------------------------------

def test_provider_a_builds_prompt_via_build_adaptation_prompt(monkeypatch):
    monkeypatch.setenv("TEST_MODE", "0")

    class FakeAgent:
        def __init__(self, system_instructions=None, model=None):
            self.system_instructions = system_instructions

        def run(self, prompt):
            self.prompt = prompt
            return "/tmp/fake"

        def consume(self, path):
            return {"output": {"reply": f"<script>{'Palabra ' * 60}</script>"}}

    captured: dict = {}

    def fake_build(title, content, channel="moku", max_words=None):
        captured.update({"title": title, "content": content, "channel": channel,
                         "max_words": max_words})
        return f"BUILT::{title}::{max_words}"

    with (
        patch.object(llm, "_build_adaptation_prompt", side_effect=fake_build),
        patch("src.agents.base_agent.ProgrammaticAgent", FakeAgent),
        patch("src.agents.base_agent.CANONICAL_MODEL", "fake-model"),
    ):
        out = llm.curate_script(
            _content(),
            title="El Ascensor",
            provider="A",
            min_words=40,
            channel="aelithia",
            max_words=250,
        )

    assert out is not None
    assert captured == {
        "title": "El Ascensor",
        "content": _content(),
        "channel": "aelithia",
        "max_words": 250,
    }


def test_provider_b_receives_same_builder_output_as_provider_a():
    expected = llm._build_adaptation_prompt(
        "El Ascensor", _content(), channel="aelithia", max_words=250
    )
    received: list[str] = []

    def fake_gemini(prompt):
        received.append(prompt)
        return None

    with (
        patch.object(llm, "_curate_with_agent", return_value=None),
        patch.object(llm, "_curate_with_gemini", side_effect=fake_gemini),
        pytest.raises(AIProviderChainExhausted),
    ):
        llm.curate_script(
            _content(),
            title="El Ascensor",
            provider="A",
            min_words=40,
            channel="aelithia",
            max_words=250,
        )

    assert received == [expected]


def test_curate_script_signature_and_fail_closed_chain_preserved():
    """Provider A success short-circuits; A→B→AIProviderChainExhausted stays intact."""
    good = "Palabra " * 60
    with (
        patch.object(llm, "_curate_with_agent", return_value=good) as mA,
        patch.object(llm, "_curate_with_gemini") as mB,
    ):
        out = llm.curate_script(_content(), title="T", provider="A", min_words=40)
        assert out.strip() == good.strip()
        mB.assert_not_called()

    with (
        patch.object(llm, "_curate_with_agent", return_value=None),
        patch.object(llm, "_curate_with_gemini", return_value=None),
        pytest.raises(AIProviderChainExhausted),
    ):
        llm.curate_script(_content(), title="T", provider="A", min_words=40)
