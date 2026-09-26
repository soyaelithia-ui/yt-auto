"""
tests/unit/test_creative_agents_refocus.py - Unit tests for refocused creative agents
and sanitized narrative engine contracts.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict
import jsonschema
import pytest

from src.agents.atmospheric_director import AtmosphericDirectorAgent
from src.agents.seo_optimizer import SeoOptimizerAgent
from src.narrative.archetypes import ARCHETYPE_PRESETS, NarrativeArchetype
from src.narrative.engine import CosmicNarrativeEngine
from src.narrative.schema import CosmicScriptContract, VideoFormat

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ART_DIRECTOR_SCHEMA_PATH = REPO_ROOT / "schemas" / "art_director.schema.json"
SEO_SCHEMA_PATH = REPO_ROOT / "schemas" / "seo_metadata.schema.json"
NARRATIVE_SCHEMA_PATH = REPO_ROOT / "src" / "narrative" / "schema.json"


def test_atmospheric_director_emits_pure_catalog_and_audio() -> None:
    """Verifies that AtmosphericDirectorAgent returns pure catalog loops and soundscape directives
    with zero diffusion prompts, zero uniform params, and zero WGSL archetypes."""
    director = AtmosphericDirectorAgent()

    # 1. Test plan_visuals()
    dummy_script = {
        "metadata": {"channel_lane": "cosmic_horror"},
        "acts": [
            {
                "act_id": "act_1",
                "scenes": [
                    {
                        "scene_id": "scene_001",
                        "scene_index": 1,
                        "tension_level": 2,
                        "environmental_mood": "Deep Abyssal Trench",
                        "narration_text": "Los sensores submarinos detectan pulsos anómalos.",
                    }
                ],
            }
        ],
    }
    visual_plan = director.plan_visuals(dummy_script, theme_lane="cosmic_horror")
    
    # Assert top-level structure
    assert visual_plan.get("version") == "2.0"
    assert "scenes" in visual_plan
    assert len(visual_plan["scenes"]) == 1

    scene = visual_plan["scenes"][0]
    # Assert zero diffusion prompts
    assert "image_prompts" not in scene
    assert "positive_prompt" not in scene
    assert "negative_prompt" not in scene
    # Assert zero uniform params
    assert "uniform_params" not in scene
    # Assert zero WGSL archetype_id
    assert "archetype_id" not in scene

    # Validate against art_director.schema.json
    if ART_DIRECTOR_SCHEMA_PATH.is_file():
        with open(ART_DIRECTOR_SCHEMA_PATH, "r", encoding="utf-8") as f:
            art_schema = json.load(f)
        jsonschema.validate(instance=visual_plan, schema=art_schema)


def test_seo_optimizer_emits_text_free_thumbnail_request() -> None:
    """Verifies that SeoOptimizerAgent emits thumbnail_asset_request with text_free=True,
    and zero typography layout, font, or badge properties."""
    optimizer = SeoOptimizerAgent()
    seo_data = optimizer.optimize(
        topic="Anomalía Espacial de la Singularidad",
        target_format="short",
        niche="moku",
        use_agent=False,
    )

    assert "thumbnail_asset_request" in seo_data
    req = seo_data["thumbnail_asset_request"]
    assert req.get("bank") == "local_ai"
    assert req.get("text_free") is True
    assert "archetype" in req
    assert "focal_subject" in req

    # Assert zero typography, badges, fonts, titles, or layout coordinates
    forbidden_keys = [
        "title", "headline", "badge", "badge_text", "font", "font_size",
        "typography", "text_layout", "watermark", "overlay", "x", "y",
    ]
    for key in forbidden_keys:
        assert key not in req, f"Forbidden key '{key}' found in thumbnail_asset_request"

    # Validate against seo_metadata.schema.json
    if SEO_SCHEMA_PATH.is_file():
        with open(SEO_SCHEMA_PATH, "r", encoding="utf-8") as f:
            seo_schema = json.load(f)
        jsonschema.validate(instance=seo_data, schema=seo_schema)


def test_narrative_engine_emits_scenes_without_shader_sequence() -> None:
    """Verifies that NarrativeEngine presets and generated scenes contain zero
    shader_sequence, shader_id, or shader_params."""
    # 1. Presets in ARCHETYPE_PRESETS must not contain shader_sequence
    for arch, preset in ARCHETYPE_PRESETS.items():
        assert "shader_sequence" not in preset, f"Preset {arch} contains shader_sequence"
        assert "visual_sequence" in preset, f"Preset {arch} should contain visual_sequence"

    # 2. CosmicNarrativeEngine scene generation
    engine = CosmicNarrativeEngine()
    script = engine.generate_script(
        topic="Anomalía de descompresión abisal",
        video_format=VideoFormat.SHORT_VERTICAL,
        duration_sec=35.0,
    )

    assert len(script.scenes) >= 1
    for sc in script.scenes:
        sc_dict = sc.to_dict() if hasattr(sc, "to_dict") else dict(sc)
        assert "shader_sequence" not in sc_dict
        assert "shader_id" not in sc_dict
        assert "shader_params" not in sc_dict

    # 3. JSON schema validation against narrative/schema.json
    if NARRATIVE_SCHEMA_PATH.is_file():
        with open(NARRATIVE_SCHEMA_PATH, "r", encoding="utf-8") as f:
            narrative_schema = json.load(f)
        # Ensure schema.json itself does not require or define shader_id/shader_params
        scene_props = narrative_schema.get("properties", {}).get("scenes", {}).get("items", {}).get("properties", {})
        assert "shader_id" not in scene_props
        assert "shader_params" not in scene_props
        # Validate script serialization
        jsonschema.validate(instance=script.to_dict(), schema=narrative_schema)
