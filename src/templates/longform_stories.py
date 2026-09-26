"""
src/templates/longform_stories.py - Multi-storyline library for longform narratives.
Loads externalized storyline templates from config/templates/ ensuring modularity,
diversity (Jaccard < 0.25), and zero context token bloat.
"""
from __future__ import annotations

import hashlib
from typing import Any, Callable, List, Optional, Sequence

from src.templates.loader import load_template_json, render_paragraphs
from src.templates.longform_stories_ext import (
    build_drama_adoption_extortion,
    build_drama_fake_fundraiser,
    build_drama_property_usurpation,
    build_drama_secret_inheritance,
    build_horror_asylum,
    build_horror_deepsea,
    build_horror_observatory,
    build_horror_saltmine,
)


def build_horror_mountain_radio(topic: str, **kwargs: Any) -> str:
    """Story 0: Mountain Radio Station Operator."""
    from src.templates.narratives import _build_horror_radio_base
    return _build_horror_radio_base(topic, **kwargs)


def build_drama_family_debt(topic: str, **kwargs: Any) -> str:
    """Story 0: Birthday Loan & Secret Will."""
    from src.templates.narratives import _build_drama_family_debt_base
    return _build_drama_family_debt_base(topic, **kwargs)


def build_horror_bunker(topic: str, **kwargs: Any) -> str:
    """Story 1: Subterranean Granite Geological Bunker."""
    tpl = load_template_json("longform_stories_horror.json")
    return render_paragraphs(tpl["bunker"], {"topic": topic})


def build_horror_lighthouse(topic: str, **kwargs: Any) -> str:
    """Story 2: Desolate Cape Fog Lighthouse Keeper."""
    tpl = load_template_json("longform_stories_horror.json")
    return render_paragraphs(tpl["lighthouse"], {"topic": topic})


def build_horror_rail(topic: str, **kwargs: Any) -> str:
    """Story 3: Siberian Freight Railway Signalman."""
    tpl = load_template_json("longform_stories_horror.json")
    return render_paragraphs(tpl["rail"], {"topic": topic})


def get_wedding_story(topic: str) -> str:
    """Story 1 base: Wedding Extravaganza & Broken Engagement."""
    tpl = load_template_json("longform_stories_drama.json")
    return render_paragraphs(tpl["wedding"], {"topic": topic})


def get_wedding_story_v2(topic: str) -> str:
    """Story 1 extended: In-depth psychological and legal reflections."""
    base = get_wedding_story(topic)
    tpl = load_template_json("longform_stories_drama.json")
    extra = render_paragraphs(tpl["wedding_v2_extra"], {"topic": topic})
    return base + "\n\n" + extra


def build_drama_wedding_house(topic: str, **kwargs: Any) -> str:
    """Story 1: Complete wedding and house drama narrative."""
    s = get_wedding_story_v2(topic)
    tpl = load_template_json("longform_stories_drama.json")
    return s + "\n\n" + tpl["wedding_house_final"]


def get_business_story(topic: str) -> str:
    """Story 2 base: Small Business Embezzlement & Hostile Partner."""
    tpl = load_template_json("longform_stories_drama.json")
    return render_paragraphs(tpl["business"], {"topic": topic})


def build_drama_business_betrayal(topic: str, **kwargs: Any) -> str:
    """Story 2: Complete business betrayal narrative."""
    return get_business_story(topic)


def get_eldercare_story(topic: str) -> str:
    """Story 3 base: Eldercare Abandonment & Greedy Siblings."""
    tpl = load_template_json("longform_stories_drama.json")
    return render_paragraphs(tpl["eldercare"], {"topic": topic})


def build_drama_eldercare_will(topic: str, **kwargs: Any) -> str:
    """Story 3: Complete eldercare and will dispute narrative."""
    return get_eldercare_story(topic)


HORROR_STORIES: List[Callable[..., str]] = [
    build_horror_mountain_radio,
    build_horror_bunker,
    build_horror_lighthouse,
    build_horror_rail,
    build_horror_deepsea,
    build_horror_asylum,
    build_horror_observatory,
    build_horror_saltmine,
]

DRAMA_STORIES: List[Callable[..., str]] = [
    build_drama_family_debt,
    build_drama_wedding_house,
    build_drama_business_betrayal,
    build_drama_eldercare_will,
    build_drama_secret_inheritance,
    build_drama_fake_fundraiser,
    build_drama_property_usurpation,
    build_drama_adoption_extortion,
]


def _synthesize_hybrid_story(
    stories: List[Callable[..., str]],
    start_idx: int,
    topic: str,
    recent_texts: Sequence[str],
    **kwargs: Any,
) -> Optional[str]:
    """Combinatorial modular synthesis fallback if all individual base stories collide."""
    from src.core.quality import text_similarity

    for combo in range(len(stories)):
        idx_a = (start_idx + combo) % len(stories)
        idx_b = (start_idx + combo + 2) % len(stories)
        idx_c = (start_idx + combo + 4) % len(stories)
        pa = [p.strip() for p in stories[idx_a](topic, **kwargs).split("\n\n") if p.strip()]
        pb = [p.strip() for p in stories[idx_b](topic, **kwargs).split("\n\n") if p.strip()]
        pc = [p.strip() for p in stories[idx_c](topic, **kwargs).split("\n\n") if p.strip()]
        min_len = min(len(pa), len(pb), len(pc))
        if min_len >= 8:
            hybrid = []
            for p_idx in range(min_len):
                if p_idx % 3 == 0:
                    hybrid.append(pa[p_idx])
                elif p_idx % 3 == 1:
                    hybrid.append(pb[p_idx])
                else:
                    hybrid.append(pc[p_idx])
            hybrid_story = "\n\n".join(hybrid)
            max_sim = max((text_similarity(hybrid_story, prev) for prev in recent_texts), default=0.0)
            if max_sim < 0.68:
                return hybrid_story
    return None


def get_horror_longform_story(topic: str, index: Optional[int] = None, **kwargs: Any) -> str:
    """Returns a diverse longform story for Horror channel, strictly avoiding collision."""
    if index is not None:
        return HORROR_STORIES[index % len(HORROR_STORIES)](topic, **kwargs)

    recent_texts = kwargs.get("recent_texts")
    if not recent_texts:
        try:
            from src.config import DEFAULT_DB_PATH
            from src.core.repository import QueueRepository
            recent_texts = QueueRepository(DEFAULT_DB_PATH).recent_published_texts("horror")
        except Exception:
            recent_texts = ()

    if "La Estación de Radio Olvidada" in topic or "radio" in topic.lower():
        start_idx = 0
    else:
        seed = kwargs.get("seed")
        if seed is not None:
            start_idx = int(seed) % len(HORROR_STORIES)
        else:
            h = int(hashlib.md5(topic.encode("utf-8")).hexdigest()[:8], 16)
            start_idx = h % len(HORROR_STORIES)

    from src.core.quality import text_similarity

    best_story = ""
    min_sim = 1.0

    for offset in range(len(HORROR_STORIES)):
        cand_idx = (start_idx + offset) % len(HORROR_STORIES)
        candidate = HORROR_STORIES[cand_idx](topic, **kwargs)
        if not recent_texts:
            return candidate
        max_sim = max((text_similarity(candidate, prev) for prev in recent_texts), default=0.0)
        if max_sim < 0.70:
            return candidate
        if max_sim < min_sim:
            min_sim = max_sim
            best_story = candidate

    if recent_texts and min_sim >= 0.70:
        clean_kwargs = {k: v for k, v in kwargs.items() if k != "recent_texts"}
        hybrid = _synthesize_hybrid_story(HORROR_STORIES, start_idx, topic, recent_texts, **clean_kwargs)
        if hybrid:
            return hybrid

    return best_story or HORROR_STORIES[start_idx](topic, **kwargs)


def get_drama_longform_story(topic: str, index: Optional[int] = None, **kwargs: Any) -> str:
    """Returns a diverse longform story for Drama channel, strictly avoiding collision."""
    if index is not None:
        return DRAMA_STORIES[index % len(DRAMA_STORIES)](topic, **kwargs)

    recent_texts = kwargs.get("recent_texts")
    if not recent_texts:
        try:
            from src.config import DEFAULT_DB_PATH
            from src.core.repository import QueueRepository
            recent_texts = QueueRepository(DEFAULT_DB_PATH).recent_published_texts("drama")
        except Exception:
            recent_texts = ()

    if "El Testamento de la Abuela" in topic:
        start_idx = 0
    else:
        seed = kwargs.get("seed")
        if seed is not None:
            start_idx = int(seed) % len(DRAMA_STORIES)
        else:
            h = int(hashlib.md5(topic.encode("utf-8")).hexdigest()[:8], 16)
            start_idx = h % len(DRAMA_STORIES)

    from src.core.quality import text_similarity

    best_story = ""
    min_sim = 1.0

    for offset in range(len(DRAMA_STORIES)):
        cand_idx = (start_idx + offset) % len(DRAMA_STORIES)
        candidate = DRAMA_STORIES[cand_idx](topic, **kwargs)
        if not recent_texts:
            return candidate
        max_sim = max((text_similarity(candidate, prev) for prev in recent_texts), default=0.0)
        if max_sim < 0.70:
            return candidate
        if max_sim < min_sim:
            min_sim = max_sim
            best_story = candidate

    if recent_texts and min_sim >= 0.70:
        clean_kwargs = {k: v for k, v in kwargs.items() if k != "recent_texts"}
        hybrid = _synthesize_hybrid_story(DRAMA_STORIES, start_idx, topic, recent_texts, **clean_kwargs)
        if hybrid:
            return hybrid

    return best_story or DRAMA_STORIES[start_idx](topic, **kwargs)


# Canonical functions and compatibility aliases
build_horror_longform_story = get_horror_longform_story
build_drama_longform_story = get_drama_longform_story
MOKU_STORIES = HORROR_STORIES
AELITHIA_STORIES = DRAMA_STORIES
get_moku_longform_story = get_horror_longform_story
get_aelithia_longform_story = get_drama_longform_story

