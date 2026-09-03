import pytest
from lib.qa.diversity_gate import audit_scene_diversity, SceneDiversityGate


def test_scene_diversity_fails_on_4_scenes_longform():
    # Longform 600s (10m) with only 4 scenes
    manifest = {
        "duration_sec": 600.0,
        "scenes": [
            {"scene_id": "sc1", "duration_sec": 150.0, "image_path": "loop1.mp4"},
            {"scene_id": "sc2", "duration_sec": 150.0, "image_path": "loop2.mp4"},
            {"scene_id": "sc3", "duration_sec": 150.0, "image_path": "loop3.mp4"},
            {"scene_id": "sc4", "duration_sec": 150.0, "image_path": "loop4.mp4"},
        ]
    }
    passed, code, msg, details = audit_scene_diversity(manifest, duration_sec=600.0)
    assert not passed
    assert code == "ERR_QA_SCENE_DIVERSITY_INSUFFICIENT"
    assert "at least 6" in msg or "insufficient" in msg.lower()


def test_scene_diversity_fails_on_single_asset_dominance():
    # 865s video with 1 asset covering 100% of the runtime
    manifest = {
        "duration_sec": 865.0,
        "scenes": [
            {"scene_id": "sc1", "duration_sec": 216.25, "image_path": "loop_tactical_101.mp4"},
            {"scene_id": "sc2", "duration_sec": 216.25, "image_path": "loop_tactical_101.mp4"},
            {"scene_id": "sc3", "duration_sec": 216.25, "image_path": "loop_tactical_101.mp4"},
            {"scene_id": "sc4", "duration_sec": 216.25, "image_path": "loop_tactical_101.mp4"},
            {"scene_id": "sc5", "duration_sec": 216.25, "image_path": "loop_tactical_101.mp4"},
            {"scene_id": "sc6", "duration_sec": 216.25, "image_path": "loop_tactical_101.mp4"},
        ]
    }
    passed, code, msg, details = audit_scene_diversity(manifest, duration_sec=865.0)
    assert not passed
    assert code == "ERR_QA_ASSET_DOMINANCE_EXCEEDED"
    assert "25%" in msg or "dominance" in msg.lower()


def test_scene_diversity_passes_on_varied_longform():
    # 600s with 16 diverse scenes and no single asset > 25%
    scenes = []
    for i in range(16):
        scenes.append({
            "scene_id": f"sc{i+1}",
            "duration_sec": 37.5,
            "image_path": f"loop_{i % 6}.mp4"  # 6 different loops, max 3 scenes per loop = 18.75%
        })
    manifest = {"duration_sec": 600.0, "scenes": scenes}
    passed, code, msg, details = audit_scene_diversity(manifest, duration_sec=600.0)
    assert passed
    assert code == "OK_SCENE_DIVERSITY"


def test_scene_diversity_handles_none_procedural_config():
    # Manifest with procedural_config: None
    scenes = [
        {"scene_id": f"sc{i}", "duration_sec": 40.0, "image_path": None, "procedural_config": None, "category": f"cat_{i % 5}"}
        for i in range(15)
    ]
    manifest = {"duration_sec": 600.0, "scenes": scenes}
    passed, code, msg, details = audit_scene_diversity(manifest, duration_sec=600.0)
    assert passed
    assert code == "OK_SCENE_DIVERSITY"

