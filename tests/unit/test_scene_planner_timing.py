"""Unit tests for ScenePlannerCompositorAgent duration synchronization and timing coordination."""
import json
from pathlib import Path
import pytest

from src.agents.scene_planner import ScenePlannerCompositorAgent


@pytest.fixture
def dummy_script():
    return {
        "metadata": {
            "title": "Prueba de Sincronización Temporal",
            "channel_lane": "moku-horror-long",
            "target_format": "longform",
        },
        "acts": [
            {
                "act_number": 1,
                "scenes": [
                    {
                        "scene_id": "scene_001",
                        "estimated_duration_sec": 50.0,
                        "tension_level": 2,
                        "environmental_mood": "Bosque nublado",
                    },
                    {
                        "scene_id": "scene_002",
                        "estimated_duration_sec": 50.0,
                        "tension_level": 3,
                        "environmental_mood": "Cabaña abandonada",
                    },
                ],
            },
            {
                "act_number": 2,
                "scenes": [
                    {
                        "scene_id": "scene_003",
                        "estimated_duration_sec": 100.0,
                        "tension_level": 5,
                        "environmental_mood": "Abismo cósmico",
                    }
                ],
            },
        ],
    }


@pytest.fixture
def dummy_visual_plan():
    return {
        "theme_lane": "cosmic_horror",
        "scenes": [
            {
                "scene_id": "scene_001",
                "environment_name": "Bosque",
                "palette": {"primary": "#0c1824", "shadow": "#04080e", "accent": "#00ffcc", "highlight": "#ffffff"},
                "lighting": {"volumetric_rays": False},
                "atmosphere": {"particle_layer": "fog_mist"},
            },
            {
                "scene_id": "scene_002",
                "environment_name": "Cabaña",
                "palette": {"primary": "#0c1824", "shadow": "#04080e", "accent": "#00ffcc", "highlight": "#ffffff"},
                "lighting": {"volumetric_rays": True},
                "atmosphere": {"particle_layer": "dust_motes"},
            },
            {
                "scene_id": "scene_003",
                "environment_name": "Abismo",
                "palette": {"primary": "#0c1824", "shadow": "#04080e", "accent": "#00ffcc", "highlight": "#ffffff"},
                "lighting": {"volumetric_rays": True},
                "atmosphere": {"particle_layer": "spores"},
            },
        ],
    }


def test_scene_planner_scales_durations_to_actual_audio_duration(dummy_script, dummy_visual_plan):
    planner = ScenePlannerCompositorAgent()
    actual_audio = 600.0  # Raw estimated total is 50 + 50 + 100 = 200s

    manifest = planner.plan_manifest(
        script=dummy_script,
        visual_plan=dummy_visual_plan,
        story_id="test_story",
        narration_path="data/worksets/run_001/speech.wav",
        lane_id="moku-horror-long",
        channel_name="moku",
        actual_audio_duration=actual_audio,
    )

    assert manifest["total_duration_sec"] == 600.0
    scenes = manifest["scenes"]
    assert len(scenes) == 3

    # Scaled proportionally: 50 -> 150s, 50 -> 150s, 100 -> 300s
    assert scenes[0]["duration_sec"] == 150.0
    assert scenes[0]["start_sec"] == 0.0

    assert scenes[1]["duration_sec"] == 150.0
    assert scenes[1]["start_sec"] == 150.0

    assert scenes[2]["duration_sec"] == 300.0
    assert scenes[2]["start_sec"] == 300.0

    total_scenes_duration = sum(sc["duration_sec"] for sc in scenes)
    assert abs(total_scenes_duration - 600.0) < 0.01


def test_scene_planner_unscaled_fallback_when_no_actual_audio(dummy_script, dummy_visual_plan):
    planner = ScenePlannerCompositorAgent()

    manifest = planner.plan_manifest(
        script=dummy_script,
        visual_plan=dummy_visual_plan,
        story_id="test_story",
        narration_path="data/worksets/run_001/speech.wav",
        lane_id="moku-horror-long",
        channel_name="moku",
        actual_audio_duration=None,
    )

    scenes = manifest["scenes"]
    assert scenes[0]["duration_sec"] == 50.0
    assert scenes[1]["duration_sec"] == 50.0
    assert scenes[2]["duration_sec"] == 100.0
    assert manifest["total_duration_sec"] == 200.0
