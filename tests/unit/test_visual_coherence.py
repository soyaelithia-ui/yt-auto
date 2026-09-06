from src.media.visual_coherence import (
    ordered_script_scene_ids,
    timing_scales_to_audio,
    visual_plan_palette,
)
from src.agents.art_director import ArtDirectorMoodAgent


def test_script_order_is_act_flatten():
    script = {
        "acts": [
            {"scenes": [{"scene_id": "a"}, {"scene_id": "b"}]},
            {"scenes": [{"scene_id": "c"}]},
        ]
    }
    assert ordered_script_scene_ids(script) == ["a", "b", "c"]


def test_timing_scales_sum_to_audio():
    scaled = timing_scales_to_audio([10, 20, 30], 60.0)
    assert abs(sum(scaled) - 60.0) < 0.05
    assert all(d >= 1.0 for d in scaled)


def test_art_director_emits_top_level_palette():
    agent = ArtDirectorMoodAgent(schema_file=None)
    script = {
        "metadata": {"channel_lane": "moku-scp-shorts"},
        "acts": [{"scenes": [
            {"scene_id": "scene_001", "scene_index": 1, "tension_level": 3,
             "environmental_mood": "Containment", "estimated_duration_sec": 8},
            {"scene_id": "scene_002", "scene_index": 2, "tension_level": 4,
             "environmental_mood": "Breach", "estimated_duration_sec": 10},
        ]}],
    }
    plan = agent.plan_visuals(script, theme_lane="scp")
    assert plan["theme_lane"] == "scp_foundation"
    assert plan["palette"]["accent"]
    pal = visual_plan_palette(plan)
    assert pal["accent"] == plan["palette"]["accent"]
    assert [s["scene_id"] for s in plan["scenes"]] == ["scene_001", "scene_002"]
