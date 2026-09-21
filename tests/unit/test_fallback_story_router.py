"""tests/unit/test_fallback_story_router.py - Unit tests for channel-specific fallback story routing."""

from src.templates.narratives import get_fallback_story


def test_get_fallback_story_moku():
    short_story = get_fallback_story("moku", is_short=True)
    long_story = get_fallback_story("moku", is_short=False)
    assert any(token in short_story for token in ("SCP", "Fundación", "silencio", "contención"))
    assert any(token in long_story for token in ("SCP", "Fundación", "silencio", "contención"))


def test_get_fallback_story_aelithia():
    short_story = get_fallback_story("aelithia", is_short=True)
    long_story = get_fallback_story("aelithia", is_short=False)
    assert any(token in short_story for token in ("herencia", "familia", "¿Soy", "malo", "mala"))
    assert any(token in long_story for token in ("herencia", "familia", "¿Soy", "malo", "mala"))
    assert "SCP" not in short_story
    assert "Fundación" not in short_story


def test_get_fallback_story_scifi():
    short_story = get_fallback_story("scifi", is_short=True)
    long_story = get_fallback_story("scifi", is_short=False)
    assert any(token in short_story for token in ("horizonte de sucesos", "relatividad", "espacio-tiempo", "tiempo"))
    assert any(token in long_story for token in ("horizonte de sucesos", "radiación", "cosmos", "astrofísica"))
    assert "SCP" not in short_story
    assert "¿Soy" not in short_story


def test_get_fallback_story_scifi_aliases():
    for alias in ("singularidad", "sci_fi", "scifi"):
        story = get_fallback_story(alias, is_short=True)
        assert any(token in story for token in ("horizonte de sucesos", "relatividad", "espacio-tiempo"))
        assert "SCP" not in story


def test_script_curator_agent_scifi_fallback_routing():
    from src.curators.text_splitter import CinematicScriptCuratorAgent

    curator = CinematicScriptCuratorAgent()
    short_fallback = curator._generate_fallback_narrative("Paradoja Cuántica", "scifi-shorts", "")
    long_fallback = curator._generate_fallback_narrative("Agujero Negro", "scifi-long", "")

    # Assert scifi fallback does NOT fall through to horror or SCP
    assert "SCP" not in short_fallback
    assert "SCP" not in long_fallback
    assert "bosque" not in short_fallback
    assert "bosque" not in long_fallback
    assert any(w in short_fallback for w in ("horizonte de sucesos", "relatividad", "espacio", "tiempo", "astrofísica", "gravitacional"))
    assert any(w in long_fallback for w in ("horizonte de sucesos", "radiación", "cosmos", "astrofísica", "gravitacional", "cuántico"))

