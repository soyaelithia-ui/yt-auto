"""
tests/unit/test_scene_manifest_v2.py - Comprehensive Unit Tests for Canonical Scene Manifest v2.0 Contract.

Verifies Draft-07 JSON Schema validation, Pydantic v2 data models, builder functions,
edge cases, and rejection of invalid payloads for Dual-Engine video rendering.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import jsonschema
import pytest

from src.scene_manifest import (
    AudioTracks,
    CameraMotionConfig,
    ColorProfile,
    DuckingConfig,
    HybridAIConfig,
    LayerConfig,
    SafeArea,
    SceneConfig,
    SceneManifestV2,
    SFXCue,
    SubtitleCue,
    TransitionConfig,
    build_scene_manifest,
    build_scene_manifest_v2,
    get_scene_manifest_schema,
    load_scene_manifest,
    save_scene_manifest,
    validate_scene_manifest,
)


@pytest.fixture
def canonical_v2_payload() -> Dict[str, Any]:
    """Provides a canonical valid v2.0 scene manifest dictionary."""
    return {
        "manifest_version": "2.0",
        "story_id": "moku_horror_ep42_the_abyss",
        "lane_id": "moku-horror-long",
        "channel_name": "moku",
        "resolution": [1920, 1080],
        "fps": 30,
        "total_duration_sec": 140.0,
        "color_profile": {
            "color_space": "bt709",
            "color_primaries": "bt709",
            "color_trc": "bt709",
            "pixel_format": "yuv420p",
        },
        "audio_tracks": {
            "narration_path": "/app/work/runs/run_001/narration.wav",
            "music_path": "/app/assets/music/dark_ambient_drone.wav",
            "music_volume": 0.12,
            "ducking": {
                "enabled": True,
                "threshold": 0.035,
                "ratio": 8.0,
                "attack_ms": 20.0,
                "release_ms": 350.0,
                "target_lufs": -14.0,
                "max_tp": -1.5,
                "lra": 11.0,
            },
            "sfx_cues": [
                {
                    "sfx_id": "sub_bass_drop_01",
                    "sfx_path": "/app/assets/sfx/sub_drop.wav",
                    "timestamp_sec": 45.2,
                    "volume": 0.65,
                    "pan": 0.0,
                }
            ],
        },
        "safe_area": {
            "margin_top": 60,
            "margin_bottom": 124,
            "margin_left": 85,
            "margin_right": 85,
        },
        "scenes": [
            {
                "scene_index": 1,
                "scene_id": "scene_01_abandoned_manor",
                "environment_name": "Mansion en Penumbra",
                "start_sec": 0.0,
                "duration_sec": 65.0,
                "tension_level": 2,
                "engine_type": "hybrid_cinematic_ai",
                "hybrid_ai_config": {
                    "background_image_path": "/app/work/runs/run_001/scene_01_matte.png",
                    "depth_map_path": "/app/work/runs/run_001/scene_01_depth.png",
                    "prompt_used": "Victorian abandoned manor interior in nocturnal shadows",
                    "seed": 928411,
                    "layers": [
                        {
                            "layer_id": "foreground_drapes",
                            "asset_path": "/app/work/runs/run_001/scene_01_fg_drapes.png",
                            "z_depth": 0.85,
                            "blend_mode": "normal",
                            "opacity": 0.95,
                        }
                    ],
                    "camera_motion": {
                        "type": "ken_burns_3d",
                        "start_zoom": 1.0,
                        "end_zoom": 1.06,
                        "pan_direction": "center_to_top",
                        "easing": "cubic_bezier",
                        "parallax_intensity": 0.12,
                    },
                    "lighting": {
                        "volumetric_rays": True,
                        "light_source_pos": [0.75, 0.2],
                        "intensity": 0.35,
                        "flicker_frequency": 0.0,
                        "color_tint": "#a5b4fc",
                    },
                    "particles": {
                        "type": "dust_motes",
                        "density": 35,
                        "velocity": 0.8,
                        "color": "#e0e7ff",
                        "opacity": 0.3,
                    },
                },
                "transition_out": {
                    "type": "depth_dissolve",
                    "duration_sec": 1.0,
                },
            },
            {
                "scene_index": 2,
                "scene_id": "scene_02_cosmic_rift",
                "environment_name": "Grieta Dimensional",
                "start_sec": 65.0,
                "duration_sec": 75.0,
                "tension_level": 4,
                "engine_type": "catalog_loop",
                "transition_out": {
                    "type": "cut",
                    "duration_sec": 0.0,
                },
            },
        ],
        "subtitles": [
            {
                "start": 0.0,
                "end": 3.4,
                "text": "Nadie sabe qué ocurrió en aquella mansión tras la tormenta de 1923.",
            }
        ],
    }


# ===========================================================================
# 1. Draft-07 JSON Schema Compliance Tests
# ===========================================================================

def test_json_schema_is_valid_draft07():
    """Verify that schemas/scene_manifest.schema.json adheres to Draft-07 meta-schema."""
    schema = get_scene_manifest_schema()
    assert isinstance(schema, dict)
    assert schema.get("$schema") == "http://json-schema.org/draft-07/schema#"
    jsonschema.Draft7Validator.check_schema(schema)


def test_canonical_manifest_validates_against_schema(canonical_v2_payload):
    """Verify canonical manifest payload validates cleanly against the JSON Schema."""
    schema = get_scene_manifest_schema()
    validator = jsonschema.Draft7Validator(schema)
    errors = list(validator.iter_errors(canonical_v2_payload))
    assert len(errors) == 0, f"Schema validation errors: {[e.message for e in errors]}"


def test_validate_scene_manifest_function_succeeds(canonical_v2_payload, tmp_path):
    """Verify validate_scene_manifest accepts valid dict and valid file."""
    # Test dictionary directly
    assert validate_scene_manifest(canonical_v2_payload) is True

    # Test file path
    manifest_file = tmp_path / "scene_manifest.json"
    manifest_file.write_text(json.dumps(canonical_v2_payload), encoding="utf-8")
    assert validate_scene_manifest(manifest_file) is True


# ===========================================================================
# 2. Pydantic v2 Model Parsing & Roundtrip Serialization
# ===========================================================================

def test_pydantic_model_instantiation(canonical_v2_payload):
    """Verify SceneManifestV2 model parses canonical dictionary and typed fields."""
    manifest = SceneManifestV2.model_validate(canonical_v2_payload)
    assert manifest.manifest_version == "2.0"
    assert manifest.story_id == "moku_horror_ep42_the_abyss"
    assert manifest.fps == 30
    assert manifest.resolution == [1920, 1080]
    assert len(manifest.scenes) == 2
    assert manifest.scenes[0].engine_type == "hybrid_cinematic_ai"
    assert manifest.scenes[1].engine_type == "catalog_loop"
    assert manifest.scenes[0].tension_level == 2
    assert manifest.scenes[1].tension_level == 4


def test_save_and_load_scene_manifest_roundtrip(canonical_v2_payload, tmp_path):
    """Verify save_scene_manifest and load_scene_manifest maintain exact roundtrip fidelity."""
    manifest = SceneManifestV2.model_validate(canonical_v2_payload)
    manifest_path = tmp_path / "roundtrip_manifest.json"

    saved_path = save_scene_manifest(manifest, manifest_path)
    assert saved_path.is_file()

    loaded_data = load_scene_manifest(saved_path)
    assert loaded_data["story_id"] == canonical_v2_payload["story_id"]
    assert loaded_data["total_duration_sec"] == canonical_v2_payload["total_duration_sec"]
    assert len(loaded_data["scenes"]) == len(canonical_v2_payload["scenes"])


# ===========================================================================
# 3. Builder Function (build_scene_manifest_v2) Tests
# ===========================================================================

def test_build_scene_manifest_v2_default_catalog_loop(tmp_path):
    """Verify build_scene_manifest_v2 generates valid manifest with default catalog loop scene."""
    manifest_path = build_scene_manifest_v2(
        work_dir=tmp_path,
        story_id="story_catalog_loop_test",
        lane_id="moku-horror-long",
        channel_name="moku",
        total_duration_sec=90.0,
        narration_path=tmp_path / "narration.wav",
        music_path=tmp_path / "music.wav",
        resolution=(1920, 1080),
        fps=30,
    )
    assert manifest_path.is_file()
    assert validate_scene_manifest(manifest_path) is True

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["manifest_version"] == "2.0"
    assert len(data["scenes"]) == 1
    assert data["scenes"][0]["engine_type"] == "catalog_loop"
    assert data["safe_area"]["margin_bottom"] == 124


def test_build_scene_manifest_v2_shorts_vertical(tmp_path):
    """Verify build_scene_manifest_v2 configures vertical safe area correctly for 9:16 shorts."""
    manifest_path = build_scene_manifest_v2(
        work_dir=tmp_path,
        story_id="scp_short_096",
        lane_id="moku-scp-shorts",
        channel_name="scp_foundation",
        total_duration_sec=52.0,
        narration_path=tmp_path / "narration_short.wav",
        resolution=(1080, 1920),
        fps=30,
    )
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["resolution"] == [1080, 1920]
    assert data["safe_area"]["margin_bottom"] == 330
    assert data["safe_area"]["margin_left"] == 72


def test_build_scene_manifest_v2_with_explicit_scenes(tmp_path):
    """Verify build_scene_manifest_v2 with multi-engine explicit scenes."""
    scenes = [
        {
            "scene_index": 1,
            "scene_id": "sc1",
            "environment_name": "Forest",
            "start_sec": 0.0,
            "duration_sec": 45.0,
            "tension_level": 3,
            "engine_type": "hybrid_cinematic_ai",
            "hybrid_ai_config": {
                "background_image_path": "/path/to/forest.png",
                "depth_map_path": "/path/to/forest_depth.png",
                "particles": {"type": "fog_mist", "density": 50, "velocity": 1.2},
            },
            "transition_out": {"type": "crossfade", "duration_sec": 1.0},
        },
        {
            "scene_index": 2,
            "scene_id": "sc2",
            "environment_name": "Void",
            "start_sec": 45.0,
            "duration_sec": 45.0,
            "tension_level": 5,
            "engine_type": "catalog_loop",
            "transition_out": {"type": "crossfade", "duration_sec": 0.8},
        },
    ]

    manifest_path = build_scene_manifest_v2(
        work_dir=tmp_path,
        story_id="story_multi_scene",
        lane_id="moku-horror-long",
        channel_name="moku",
        total_duration_sec=90.0,
        narration_path=tmp_path / "narration.wav",
        scenes=scenes,
        sfx_cues=[{"sfx_id": "cue_01", "sfx_path": "/sfx/boom.wav", "timestamp_sec": 44.5, "volume": 0.8}],
        subtitles=[{"start": 0.0, "end": 2.5, "text": "El bosque permanecía en silencio."}],
    )
    assert validate_scene_manifest(manifest_path) is True
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(data["scenes"]) == 2
    assert len(data["audio_tracks"]["sfx_cues"]) == 1
    assert len(data["subtitles"]) == 1


# ===========================================================================
# 4. Strict Validation & Rejection of Invalid Manifests
# ===========================================================================

def test_reject_invalid_tension_level(canonical_v2_payload):
    """Tension level outside 1..5 must be rejected."""
    payload = dict(canonical_v2_payload)
    payload["scenes"][0]["tension_level"] = 6
    with pytest.raises(ValueError, match=r"tension_level|maximum"):
        validate_scene_manifest(payload)

    payload["scenes"][0]["tension_level"] = 0
    with pytest.raises(ValueError, match=r"tension_level|minimum"):
        validate_scene_manifest(payload)


def test_reject_invalid_engine_type(canonical_v2_payload):
    """Engine type not in allowed enum must be rejected."""
    payload = dict(canonical_v2_payload)
    payload["scenes"][0]["engine_type"] = "unreal_engine_5"
    with pytest.raises(ValueError, match=r"engine_type|enum"):
        validate_scene_manifest(payload)


def test_reject_missing_narration_path(canonical_v2_payload):
    """Missing narration_path in audio_tracks must be rejected."""
    payload = dict(canonical_v2_payload)
    del payload["audio_tracks"]["narration_path"]
    with pytest.raises(ValueError, match=r"narration_path"):
        validate_scene_manifest(payload)


def test_reject_invalid_resolution(canonical_v2_payload):
    """Resolution with dimensions < 640 or invalid length must be rejected."""
    payload = dict(canonical_v2_payload)
    payload["resolution"] = [320, 240]
    with pytest.raises(ValueError, match=r"resolution|minimum"):
        validate_scene_manifest(payload)

    payload["resolution"] = [1920]
    with pytest.raises(ValueError, match=r"resolution"):
        validate_scene_manifest(payload)


def test_reject_empty_scenes(canonical_v2_payload):
    """Manifest with empty scenes array must be rejected."""
    payload = dict(canonical_v2_payload)
    payload["scenes"] = []
    with pytest.raises(ValueError, match=r"scenes|minItems"):
        validate_scene_manifest(payload)


def test_reject_missing_required_top_level_keys(canonical_v2_payload):
    """Missing top-level keys like safe_area or story_id must be rejected."""
    for req_key in ["story_id", "lane_id", "channel_name", "safe_area", "audio_tracks"]:
        payload = dict(canonical_v2_payload)
        del payload[req_key]
        with pytest.raises(ValueError):
            validate_scene_manifest(payload)


def test_reject_nonexistent_manifest_file(tmp_path):
    """Validating non-existent file raises ValueError."""
    non_existent = tmp_path / "does_not_exist.json"
    with pytest.raises(ValueError, match=r"missing or empty"):
        validate_scene_manifest(non_existent)


def test_reject_malformed_json_file(tmp_path):
    """Validating corrupted JSON file raises ValueError."""
    broken = tmp_path / "broken.json"
    broken.write_text("{this is not valid json:", encoding="utf-8")
    with pytest.raises(ValueError, match=r"invalid JSON"):
        validate_scene_manifest(broken)


# ===========================================================================
# 5. Backwards Compatibility with Legacy v1 Manifests
# ===========================================================================

def test_legacy_build_scene_manifest_compatibility(tmp_path):
    """Verify legacy build_scene_manifest continues to work and validates cleanly."""
    narration_p = tmp_path / "legacy_narr.wav"
    narration_p.touch()

    images = [str(tmp_path / "img1.png"), str(tmp_path / "img2.png")]
    for img in images:
        Path(img).touch()

    manifest_path = build_scene_manifest(
        work_dir=tmp_path,
        scp_id="story-legacy-123",
        title="Test Legacy Story",
        narration_path=narration_p,
        duration_sec=30.0,
        scene_images=images,
        subtitles=[{"start": 0.0, "end": 2.0, "word": "Hola"}],
        resolution=(1080, 1920),
    )
    assert manifest_path.is_file()
    assert validate_scene_manifest(manifest_path) is True

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["version"] == "1.0"
    assert len(data["scenes"]) == 2
    assert data["audio"]["narration_path"] == str(narration_p)
