from src.media.visual_coherence import (
    ordered_script_scene_ids,
    timing_scales_to_audio,
    visual_plan_palette,
)
from src.agents.atmospheric_director import AtmosphericDirectorAgent as ArtDirectorMoodAgent


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


def test_build_coherent_color_grade():
    from src.media.visual_coherence import build_coherent_color_grade
    moku_grade = build_coherent_color_grade(channel="moku")
    assert "colorbalance=" in moku_grade
    assert "eq=" in moku_grade

    aelithia_grade = build_coherent_color_grade(channel="aelithia-drama")
    assert "saturation=" in aelithia_grade

    scifi_grade = build_coherent_color_grade(channel="singularidad-scifi")
    assert "contrast=" in scifi_grade


def test_harmonize_scene_transitions():
    from types import SimpleNamespace
    from src.media.visual_coherence import harmonize_scene_transitions

    scenes = [
        SimpleNamespace(scene_id="s1", tension_level=1, duration_sec=5.0),
        SimpleNamespace(scene_id="s2", tension_level=4, duration_sec=6.0),
        SimpleNamespace(scene_id="s3", tension_level=4, duration_sec=4.0),
    ]
    transitions = harmonize_scene_transitions(scenes, default_transition=0.5)
    assert len(transitions) == 2
    # s1 -> s2 has high tension jump (diff = 3) -> faster transition
    # s2 -> s3 has no tension jump (diff = 0) -> smoother transition
    assert transitions[0] < transitions[1]


def test_enforce_shorts_safe_zone():
    from src.media.visual_coherence import enforce_shorts_safe_zone
    safe = enforce_shorts_safe_zone(1080, 1920)
    assert safe["top"] >= 180
    assert safe["bottom"] >= 460
    assert safe["right"] >= 130
    assert safe["safe_width"] < 1080
    assert safe["safe_height"] < 1920


def test_validate_visual_continuity():
    from types import SimpleNamespace
    from src.media.visual_coherence import validate_visual_continuity

    assert validate_visual_continuity([])["valid"] is False

    scenes = [
        SimpleNamespace(scene_id="s1", tension_level=2, duration_sec=4.0),
        SimpleNamespace(scene_id="s2", tension_level=3, duration_sec=5.0),
    ]
    res = validate_visual_continuity(scenes)
    assert res["valid"] is True
    assert res["scene_count"] == 2
    assert res["total_duration"] == 9.0

