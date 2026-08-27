"""
tests/unit/test_scene_manifest_adversarial.py - Adversarial Stress & Edge-Case Test Suite.

Empirical validation and boundary stress-testing for Canonical Scene Manifest Contract v2.0
and Draft-07 JSON Schema (schemas/scene_manifest.schema.json).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict

import jsonschema
import pytest
from pydantic import ValidationError

from src.scene_manifest import (
    AudioTracks,
    CameraMotionConfig,
    ColorProfile,
    DuckingConfig,
    HybridAIConfig,
    LayerConfig,
    LightingConfig,
    ParticleConfig,
    ProceduralConfig,
    ProceduralPalette,
    ProceduralUniforms,
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
def valid_base_payload() -> Dict[str, Any]:
    """Base valid v2.0 manifest payload for mutation and stress testing."""
    return {
        "manifest_version": "2.0",
        "story_id": "ep_99_adversarial_test",
        "lane_id": "moku-horror-long",
        "channel_name": "moku",
        "resolution": [1920, 1080],
        "fps": 30,
        "total_duration_sec": 120.0,
        "color_profile": {
            "color_space": "bt709",
            "color_primaries": "bt709",
            "color_trc": "bt709",
            "pixel_format": "yuv420p",
        },
        "audio_tracks": {
            "narration_path": "/path/to/narr.wav",
            "music_path": "/path/to/music.wav",
            "music_volume": 0.15,
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
                    "sfx_id": "sfx_01",
                    "sfx_path": "/sfx/impact.wav",
                    "timestamp_sec": 12.5,
                    "volume": 0.7,
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
                "scene_id": "sc_01",
                "environment_name": "Haunted Mansion",
                "start_sec": 0.0,
                "duration_sec": 60.0,
                "tension_level": 3,
                "engine_type": "hybrid_cinematic_ai",
                "hybrid_ai_config": {
                    "background_image_path": "/bg/mansion.png",
                    "depth_map_path": "/bg/mansion_depth.png",
                    "prompt_used": "gothic abandoned manor in moonlight",
                    "seed": 12345,
                    "layers": [
                        {
                            "layer_id": "ly_01",
                            "asset_path": "/fg/vines.png",
                            "z_depth": 0.8,
                            "blend_mode": "normal",
                            "opacity": 0.9,
                        }
                    ],
                    "camera_motion": {
                        "type": "ken_burns_3d",
                        "start_zoom": 1.0,
                        "end_zoom": 1.1,
                        "pan_direction": "center_to_top",
                        "easing": "cubic_bezier",
                        "parallax_intensity": 0.2,
                    },
                    "lighting": {
                        "volumetric_rays": True,
                        "light_source_pos": [0.3, 0.4],
                        "intensity": 0.5,
                        "flicker_frequency": 1.2,
                        "color_tint": "#aabbcc",
                    },
                    "particles": {
                        "type": "dust_motes",
                        "density": 50,
                        "velocity": 1.0,
                        "color": "#ffffff",
                        "opacity": 0.4,
                    },
                },
                "transition_out": {
                    "type": "crossfade",
                    "duration_sec": 1.0,
                },
            },
            {
                "scene_index": 2,
                "scene_id": "sc_02",
                "environment_name": "Cosmic Abyss",
                "start_sec": 60.0,
                "duration_sec": 60.0,
                "tension_level": 5,
                "engine_type": "pure_procedural_webgl",
                "procedural_config": {
                    "template_name": "cosmic_horror_three.html",
                    "seed": 999,
                    "palette": {
                        "base_dark": "#020104",
                        "mid_tone": "#1e0838",
                        "accent": "#780a1e",
                    },
                    "uniforms": {
                        "u_noise_scale": 1.5,
                        "u_speed": 1.2,
                        "u_distortion": 0.7,
                        "u_glow_intensity": 0.9,
                    },
                },
                "transition_out": {
                    "type": "cut",
                    "duration_sec": 0.0,
                },
            },
        ],
        "subtitles": [
            {
                "start": 0.0,
                "end": 2.5,
                "text": "La penumbra consumió cada rincón de la casa.",
            }
        ],
        "branding": {
            "stamp_text": "[MOKU]",
            "channel_name": "moku",
        },
        "hook_text": "La Mansión Maldita",
        "thumbnail_candidate_timestamp": 10.0,
    }


# ===========================================================================
# 1. Tension Level Adversarial Stress Tests (Levels 0, 6, Negative, Floats, Types)
# ===========================================================================

class TestTensionLevelAdversarial:
    """Stress tests on tension_level boundaries [1..5]."""

    @pytest.mark.parametrize("invalid_tension", [0, 6, -1, 10, 100, -99])
    def test_reject_out_of_range_integer_tension(self, valid_base_payload, invalid_tension):
        payload = copy.deepcopy(valid_base_payload)
        payload["scenes"][0]["tension_level"] = invalid_tension
        with pytest.raises(ValueError, match=r"tension_level|minimum|maximum"):
            validate_scene_manifest(payload)

    @pytest.mark.parametrize("invalid_tension_type", ["3", "high", None, [], {}, True])
    def test_reject_non_integer_tension(self, valid_base_payload, invalid_tension_type):
        payload = copy.deepcopy(valid_base_payload)
        payload["scenes"][0]["tension_level"] = invalid_tension_type
        with pytest.raises(ValueError):
            validate_scene_manifest(payload)

    @pytest.mark.parametrize("valid_tension", [1, 2, 3, 4, 5])
    def test_accept_valid_tension_levels(self, valid_base_payload, valid_tension):
        payload = copy.deepcopy(valid_base_payload)
        payload["scenes"][0]["tension_level"] = valid_tension
        assert validate_scene_manifest(payload) is True


# ===========================================================================
# 2. Scene Duration & Temporal Boundary Adversarial Tests
# ===========================================================================

class TestDurationAndCadenceAdversarial:
    """Stress tests on scene duration, pacing, and total duration boundaries."""

    @pytest.mark.parametrize("invalid_dur", [-10.0, -0.01, 0.0, 0.05])
    def test_reject_sub_minimum_scene_duration(self, valid_base_payload, invalid_dur):
        payload = copy.deepcopy(valid_base_payload)
        payload["scenes"][0]["duration_sec"] = invalid_dur
        with pytest.raises(ValueError, match=r"duration_sec|minimum"):
            validate_scene_manifest(payload)

    @pytest.mark.parametrize("invalid_total_dur", [-1.0, 0.0, 0.05])
    def test_reject_sub_minimum_total_duration(self, valid_base_payload, invalid_total_dur):
        payload = copy.deepcopy(valid_base_payload)
        payload["total_duration_sec"] = invalid_total_dur
        with pytest.raises(ValueError, match=r"total_duration_sec|minimum"):
            validate_scene_manifest(payload)

    @pytest.mark.parametrize("invalid_type", ["60", "forty-five", None, [60]])
    def test_reject_non_numeric_duration(self, valid_base_payload, invalid_type):
        payload = copy.deepcopy(valid_base_payload)
        payload["scenes"][0]["duration_sec"] = invalid_type
        with pytest.raises(ValueError):
            validate_scene_manifest(payload)

    @pytest.mark.parametrize("valid_dur", [0.1, 8.0, 15.0, 45.0, 60.0, 90.0, 120.0])
    def test_accept_valid_durations(self, valid_base_payload, valid_dur):
        payload = copy.deepcopy(valid_base_payload)
        payload["scenes"][0]["duration_sec"] = valid_dur
        assert validate_scene_manifest(payload) is True


# ===========================================================================
# 3. Engine Type Enforcement & Rejection of Illegal Engines
# ===========================================================================

class TestEngineTypeAdversarial:
    """Stress tests on engine_type enumeration."""

    @pytest.mark.parametrize("illegal_engine", [
        "unreal_engine_5",
        "unity_hdrp",
        "blender_cycles",
        "hybrid",
        "procedural",
        "HYBRID_CINEMATIC_AI",
        "PURE_PROCEDURAL_WEBGL",
        "",
        "unknown_engine",
        123,
    ])
    def test_reject_illegal_engine_types(self, valid_base_payload, illegal_engine):
        payload = copy.deepcopy(valid_base_payload)
        payload["scenes"][0]["engine_type"] = illegal_engine
        with pytest.raises(ValueError, match=r"engine_type|enum"):
            validate_scene_manifest(payload)

    @pytest.mark.parametrize("valid_engine", [
        "hybrid_cinematic_ai",
        "pure_procedural_webgl",
        "procedural_canvas2d",
    ])
    def test_accept_valid_engine_types(self, valid_base_payload, valid_engine):
        payload = copy.deepcopy(valid_base_payload)
        payload["scenes"][0]["engine_type"] = valid_engine
        assert validate_scene_manifest(payload) is True


# ===========================================================================
# 4. Missing Required Fields (Top-level, Audio, Scene, Subtitles, Layers)
# ===========================================================================

class TestRequiredFieldsAdversarial:
    """Systematic deletion of every required contract field."""

    @pytest.mark.parametrize("top_key", [
        "manifest_version",
        "story_id",
        "lane_id",
        "channel_name",
        "resolution",
        "fps",
        "total_duration_sec",
        "audio_tracks",
        "safe_area",
        "scenes",
    ])
    def test_reject_missing_top_level_required_fields(self, valid_base_payload, top_key):
        payload = copy.deepcopy(valid_base_payload)
        del payload[top_key]
        with pytest.raises(ValueError, match=top_key):
            validate_scene_manifest(payload)

    @pytest.mark.parametrize("scene_key", [
        "scene_index",
        "scene_id",
        "start_sec",
        "duration_sec",
        "tension_level",
        "engine_type",
    ])
    def test_reject_missing_scene_required_fields(self, valid_base_payload, scene_key):
        payload = copy.deepcopy(valid_base_payload)
        del payload["scenes"][0][scene_key]
        with pytest.raises(ValueError, match=scene_key):
            validate_scene_manifest(payload)

    @pytest.mark.parametrize("safe_key", [
        "margin_top",
        "margin_bottom",
        "margin_left",
        "margin_right",
    ])
    def test_reject_missing_safe_area_fields(self, valid_base_payload, safe_key):
        payload = copy.deepcopy(valid_base_payload)
        del payload["safe_area"][safe_key]
        with pytest.raises(ValueError, match=safe_key):
            validate_scene_manifest(payload)

    @pytest.mark.parametrize("layer_key", ["layer_id", "asset_path", "z_depth"])
    def test_reject_missing_layer_required_fields(self, valid_base_payload, layer_key):
        payload = copy.deepcopy(valid_base_payload)
        del payload["scenes"][0]["hybrid_ai_config"]["layers"][0][layer_key]
        with pytest.raises(ValueError, match=layer_key):
            validate_scene_manifest(payload)

    @pytest.mark.parametrize("sub_key", ["start", "end", "text"])
    def test_reject_missing_subtitle_required_fields(self, valid_base_payload, sub_key):
        payload = copy.deepcopy(valid_base_payload)
        del payload["subtitles"][0][sub_key]
        with pytest.raises(ValueError, match=sub_key):
            validate_scene_manifest(payload)

    @pytest.mark.parametrize("sfx_key", ["sfx_path", "timestamp_sec", "volume"])
    def test_reject_missing_sfx_required_fields(self, valid_base_payload, sfx_key):
        payload = copy.deepcopy(valid_base_payload)
        del payload["audio_tracks"]["sfx_cues"][0][sfx_key]
        with pytest.raises(ValueError, match=sfx_key):
            validate_scene_manifest(payload)


# ===========================================================================
# 5. Resolution & FPS Constraints
# ===========================================================================

class TestResolutionAndFPSAdversarial:
    """Stress tests on resolution dimensions and framerates."""

    @pytest.mark.parametrize("bad_res", [
        [320, 240],      # Sub-minimum (<640)
        [639, 1080],     # Width boundary - 1
        [1920, 639],     # Height boundary - 1
        [0, 1080],       # Zero width
        [-1920, 1080],   # Negative width
        [1920],          # Single item
        [1920, 1080, 3], # 3 items
        [],              # Empty
        "1920x1080",     # String
    ])
    def test_reject_invalid_resolutions(self, valid_base_payload, bad_res):
        payload = copy.deepcopy(valid_base_payload)
        payload["resolution"] = bad_res
        with pytest.raises(ValueError, match=r"resolution|minimum"):
            validate_scene_manifest(payload)

    @pytest.mark.parametrize("good_res", [
        [640, 640],
        [1280, 720],
        [1920, 1080],
        [1080, 1920],
        [3840, 2160],
        [2160, 3840],
    ])
    def test_accept_valid_resolutions(self, valid_base_payload, good_res):
        payload = copy.deepcopy(valid_base_payload)
        payload["resolution"] = good_res
        assert validate_scene_manifest(payload) is True

    @pytest.mark.parametrize("bad_fps", [0, -30, 15, 29.97, 48, 120, "30", None])
    def test_reject_invalid_fps(self, valid_base_payload, bad_fps):
        payload = copy.deepcopy(valid_base_payload)
        payload["fps"] = bad_fps
        with pytest.raises(ValueError, match=r"fps|enum"):
            validate_scene_manifest(payload)

    @pytest.mark.parametrize("good_fps", [24, 25, 30, 50, 60])
    def test_accept_valid_fps(self, valid_base_payload, good_fps):
        payload = copy.deepcopy(valid_base_payload)
        payload["fps"] = good_fps
        assert validate_scene_manifest(payload) is True


# ===========================================================================
# 6. Hex Color Format & Palette Validation
# ===========================================================================

class TestHexColorAdversarial:
    """Stress tests on color hex regex patterns (#rrggbb)."""

    @pytest.mark.parametrize("bad_hex", [
        "#fff",         # 3-digit hex
        "020104",       # Missing #
        "#02010400",    # 8-digit ARGB
        "#gggggg",      # Non-hex characters
        "rgb(2,1,4)",   # CSS rgb function
        "red",          # Named color
        "",             # Empty string
        "#12345",       # 5 characters
        "#1234567",     # 7 characters
    ])
    def test_reject_invalid_color_tint(self, valid_base_payload, bad_hex):
        payload = copy.deepcopy(valid_base_payload)
        payload["scenes"][0]["hybrid_ai_config"]["lighting"]["color_tint"] = bad_hex
        with pytest.raises(ValueError, match=r"color_tint|pattern"):
            validate_scene_manifest(payload)

    @pytest.mark.parametrize("bad_hex", ["#fff", "1e0838", "#zzzzzz", "dark_violet"])
    def test_reject_invalid_procedural_palette(self, valid_base_payload, bad_hex):
        payload = copy.deepcopy(valid_base_payload)
        payload["scenes"][1]["procedural_config"]["palette"]["mid_tone"] = bad_hex
        with pytest.raises(ValueError, match=r"mid_tone|pattern"):
            validate_scene_manifest(payload)

    @pytest.mark.parametrize("good_hex", ["#020104", "#1E0838", "#780A1E", "#ffffff", "#000000"])
    def test_accept_valid_hex_colors(self, valid_base_payload, good_hex):
        payload = copy.deepcopy(valid_base_payload)
        payload["scenes"][0]["hybrid_ai_config"]["lighting"]["color_tint"] = good_hex
        payload["scenes"][1]["procedural_config"]["palette"]["base_dark"] = good_hex
        assert validate_scene_manifest(payload) is True


# ===========================================================================
# 7. Numeric Ranges & Bounded Constraints (Volume, Pan, Depth, Opacity, Density)
# ===========================================================================

class TestNumericBoundsAdversarial:
    """Stress tests on bounded numeric ranges [0..1], [-1..1], [0..500], [0..3s]."""

    @pytest.mark.parametrize("bad_val", [-0.1, 1.1, 2.0, -10.0])
    def test_music_volume_bounds(self, valid_base_payload, bad_val):
        payload = copy.deepcopy(valid_base_payload)
        payload["audio_tracks"]["music_volume"] = bad_val
        with pytest.raises(ValueError, match=r"music_volume|minimum|maximum"):
            validate_scene_manifest(payload)

    @pytest.mark.parametrize("bad_val", [-0.1, 1.1, 5.0])
    def test_sfx_volume_bounds(self, valid_base_payload, bad_val):
        payload = copy.deepcopy(valid_base_payload)
        payload["audio_tracks"]["sfx_cues"][0]["volume"] = bad_val
        with pytest.raises(ValueError, match=r"volume|minimum|maximum"):
            validate_scene_manifest(payload)

    @pytest.mark.parametrize("bad_val", [-1.1, 1.1, -2.0, 2.0])
    def test_sfx_pan_bounds(self, valid_base_payload, bad_val):
        payload = copy.deepcopy(valid_base_payload)
        payload["audio_tracks"]["sfx_cues"][0]["pan"] = bad_val
        with pytest.raises(ValueError, match=r"pan|minimum|maximum"):
            validate_scene_manifest(payload)

    @pytest.mark.parametrize("bad_val", [-0.1, 1.05, 2.0])
    def test_z_depth_bounds(self, valid_base_payload, bad_val):
        payload = copy.deepcopy(valid_base_payload)
        payload["scenes"][0]["hybrid_ai_config"]["layers"][0]["z_depth"] = bad_val
        with pytest.raises(ValueError, match=r"z_depth|minimum|maximum"):
            validate_scene_manifest(payload)

    @pytest.mark.parametrize("bad_val", [-1, 501, 1000])
    def test_particle_density_bounds(self, valid_base_payload, bad_val):
        payload = copy.deepcopy(valid_base_payload)
        payload["scenes"][0]["hybrid_ai_config"]["particles"]["density"] = bad_val
        with pytest.raises(ValueError, match=r"density|minimum|maximum"):
            validate_scene_manifest(payload)

    @pytest.mark.parametrize("bad_val", [-0.1, 5.1, 10.0])
    def test_particle_velocity_bounds(self, valid_base_payload, bad_val):
        payload = copy.deepcopy(valid_base_payload)
        payload["scenes"][0]["hybrid_ai_config"]["particles"]["velocity"] = bad_val
        with pytest.raises(ValueError, match=r"velocity|minimum|maximum"):
            validate_scene_manifest(payload)

    @pytest.mark.parametrize("bad_val", [-0.1, 3.1, 5.0])
    def test_transition_duration_bounds(self, valid_base_payload, bad_val):
        payload = copy.deepcopy(valid_base_payload)
        payload["scenes"][0]["transition_out"]["duration_sec"] = bad_val
        with pytest.raises(ValueError, match=r"duration_sec|minimum|maximum"):
            validate_scene_manifest(payload)

    @pytest.mark.parametrize("bad_pos", [[0.5], [0.5, 0.5, 0.5], []])
    def test_light_source_pos_length(self, valid_base_payload, bad_pos):
        payload = copy.deepcopy(valid_base_payload)
        payload["scenes"][0]["hybrid_ai_config"]["lighting"]["light_source_pos"] = bad_pos
        with pytest.raises(ValueError, match=r"light_source_pos|minItems|maxItems|coordinates"):
            validate_scene_manifest(payload)


# ===========================================================================
# 8. Story ID & Safe Area Boundary Tests
# ===========================================================================

class TestStoryIdAndSafeAreaAdversarial:
    """Stress tests on story_id identifier characters and safe_area coordinates."""

    @pytest.mark.parametrize("bad_story_id", [
        "story!@#$",
        "story with spaces",
        "story/subpath",
        "story\\escape",
        "story<tag>",
        "story.with.dots",
        "",
    ])
    def test_reject_invalid_story_id(self, valid_base_payload, bad_story_id):
        payload = copy.deepcopy(valid_base_payload)
        payload["story_id"] = bad_story_id
        with pytest.raises(ValueError, match=r"story_id|pattern"):
            validate_scene_manifest(payload)

    @pytest.mark.parametrize("good_story_id", [
        "moku_horror_01",
        "SCP-096-BREACH",
        "story_123_abc_XYZ",
        "drama-aita-42",
    ])
    def test_accept_valid_story_id(self, valid_base_payload, good_story_id):
        payload = copy.deepcopy(valid_base_payload)
        payload["story_id"] = good_story_id
        assert validate_scene_manifest(payload) is True

    @pytest.mark.parametrize("bad_margin", [-1, -60, -100])
    def test_reject_negative_safe_area_margins(self, valid_base_payload, bad_margin):
        payload = copy.deepcopy(valid_base_payload)
        payload["safe_area"]["margin_top"] = bad_margin
        with pytest.raises(ValueError, match=r"margin_top|minimum"):
            validate_scene_manifest(payload)


# ===========================================================================
# 9. High-Level Builders Robustness & Error Handling
# ===========================================================================

class TestBuilderRobustnessAdversarial:
    """Stress tests on build_scene_manifest_v2 and legacy builder under unusual conditions."""

    def test_builder_auto_calculates_safe_area_for_shorts(self, tmp_path):
        manifest_path = build_scene_manifest_v2(
            work_dir=tmp_path,
            story_id="scp_short_stress",
            lane_id="moku-scp-shorts",
            channel_name="moku",
            total_duration_sec=55.0,
            narration_path=tmp_path / "audio.wav",
            resolution=(1080, 1920),
        )
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data["safe_area"]["margin_bottom"] == 330
        assert data["safe_area"]["margin_left"] == 72

    def test_builder_auto_calculates_safe_area_for_longform(self, tmp_path):
        manifest_path = build_scene_manifest_v2(
            work_dir=tmp_path,
            story_id="horror_long_stress",
            lane_id="moku-horror-long",
            channel_name="moku",
            total_duration_sec=600.0,
            narration_path=tmp_path / "audio.wav",
            resolution=(1920, 1080),
        )
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data["safe_area"]["margin_bottom"] == 124
        assert data["safe_area"]["margin_left"] == 85

    def test_builder_rejects_negative_total_duration(self, tmp_path):
        with pytest.raises(ValueError):
            build_scene_manifest_v2(
                work_dir=tmp_path,
                story_id="bad_dur",
                total_duration_sec=-10.0,
                narration_path=tmp_path / "audio.wav",
            )

    def test_builder_handles_empty_sfx_and_subtitles(self, tmp_path):
        manifest_path = build_scene_manifest_v2(
            work_dir=tmp_path,
            story_id="empty_aux_test",
            lane_id="moku-horror-long",
            channel_name="moku",
            total_duration_sec=75.0,
            narration_path=tmp_path / "audio.wav",
            sfx_cues=[],
            subtitles=[],
        )
        assert manifest_path.is_file()
        assert validate_scene_manifest(manifest_path) is True


# ===========================================================================
# 10. Schema & Model Parity Verification (Fuzz / Invariant Test)
# ===========================================================================

def test_schema_and_model_parity_on_mutations(valid_base_payload):
    """
    Assert that JSON Schema validator and Pydantic model_validate
    agree 100% on valid vs invalid mutations.
    """
    schema = get_scene_manifest_schema()
    validator = jsonschema.Draft7Validator(schema)

    mutations = [
        # (mutation_fn, should_be_valid, description)
        (lambda p: p.update({"manifest_version": "2.0"}), True, "standard v2.0"),
        (lambda p: p.update({"manifest_version": "2.1"}), True, "v2.1 manifest"),
        (lambda p: p.update({"manifest_version": "2.0.0"}), True, "v2.0.0 semantic"),
        (lambda p: p.update({"manifest_version": "3.0"}), False, "unsupported version 3.0"),
        (lambda p: p.update({"story_id": "bad story id"}), False, "spaces in story_id"),
        (lambda p: p["scenes"][0].update({"tension_level": 1}), True, "min tension 1"),
        (lambda p: p["scenes"][0].update({"tension_level": 5}), True, "max tension 5"),
        (lambda p: p["scenes"][0].update({"tension_level": 0}), False, "under min tension 0"),
        (lambda p: p["scenes"][0].update({"tension_level": 6}), False, "over max tension 6"),
        (lambda p: p["scenes"][0].update({"engine_type": "procedural_canvas2d"}), True, "canvas2d engine"),
        (lambda p: p["scenes"][0].update({"engine_type": "fake_engine"}), False, "fake engine"),
        (lambda p: p.update({"resolution": [640, 640]}), True, "min resolution 640x640"),
        (lambda p: p.update({"resolution": [639, 640]}), False, "sub-min resolution 639"),
        (lambda p: p.update({"fps": 24}), True, "cinema 24 fps"),
        (lambda p: p.update({"fps": 60}), True, "high 60 fps"),
        (lambda p: p.update({"fps": 120}), False, "unsupported 120 fps"),
    ]

    for mut_fn, expected_valid, desc in mutations:
        payload = copy.deepcopy(valid_base_payload)
        mut_fn(payload)

        # 1. JSON schema check
        schema_valid = validator.is_valid(payload)
        # 2. Pydantic model check
        try:
            SceneManifestV2.model_validate(payload)
            pydantic_valid = True
        except Exception:
            pydantic_valid = False

        assert schema_valid == expected_valid, (
            f"Schema validation discrepancy on '{desc}': expected {expected_valid}, got {schema_valid}"
        )
        assert pydantic_valid == expected_valid, (
            f"Pydantic validation discrepancy on '{desc}': expected {expected_valid}, got {pydantic_valid}"
        )
        assert schema_valid == pydantic_valid, (
            f"Parity failure between Schema ({schema_valid}) and Pydantic ({pydantic_valid}) on '{desc}'"
        )


# ===========================================================================
# 11. Exhaustive Enum Variations & Multi-Scene Scaling
# ===========================================================================

class TestExhaustiveEnumsAndScalingAdversarial:
    """Stress tests on all internal configuration enum values and multi-scene scaling."""

    @pytest.mark.parametrize("blend_mode", ["normal", "screen", "multiply", "overlay", "add"])
    def test_valid_layer_blend_modes(self, valid_base_payload, blend_mode):
        payload = copy.deepcopy(valid_base_payload)
        payload["scenes"][0]["hybrid_ai_config"]["layers"][0]["blend_mode"] = blend_mode
        assert validate_scene_manifest(payload) is True

    @pytest.mark.parametrize("bad_blend_mode", ["subtraction", "difference", "xor", "darken"])
    def test_reject_invalid_layer_blend_modes(self, valid_base_payload, bad_blend_mode):
        payload = copy.deepcopy(valid_base_payload)
        payload["scenes"][0]["hybrid_ai_config"]["layers"][0]["blend_mode"] = bad_blend_mode
        with pytest.raises(ValueError, match=r"blend_mode|enum"):
            validate_scene_manifest(payload)

    @pytest.mark.parametrize("cam_type", [
        "ken_burns_3d",
        "parallax_drift",
        "orbital_pan",
        "zoom_in",
        "zoom_out",
        "pan_left",
        "pan_right",
        "static",
    ])
    def test_valid_camera_motion_types(self, valid_base_payload, cam_type):
        payload = copy.deepcopy(valid_base_payload)
        payload["scenes"][0]["hybrid_ai_config"]["camera_motion"]["type"] = cam_type
        assert validate_scene_manifest(payload) is True

    @pytest.mark.parametrize("bad_cam_type", ["drone_fpv", "whip_pan", "dolly_zoom", "shaky_cam"])
    def test_reject_invalid_camera_motion_types(self, valid_base_payload, bad_cam_type):
        payload = copy.deepcopy(valid_base_payload)
        payload["scenes"][0]["hybrid_ai_config"]["camera_motion"]["type"] = bad_cam_type
        with pytest.raises(ValueError, match=r"type|enum"):
            validate_scene_manifest(payload)

    @pytest.mark.parametrize("particle_type", [
        "dust_motes",
        "ember_sparks",
        "fog_mist",
        "spores",
        "rain_streaks",
        "none",
    ])
    def test_valid_particle_types(self, valid_base_payload, particle_type):
        payload = copy.deepcopy(valid_base_payload)
        payload["scenes"][0]["hybrid_ai_config"]["particles"]["type"] = particle_type
        assert validate_scene_manifest(payload) is True

    @pytest.mark.parametrize("bad_particle_type", ["snowflakes", "fireflies", "blood_splatter", "confetti"])
    def test_reject_invalid_particle_types(self, valid_base_payload, bad_particle_type):
        payload = copy.deepcopy(valid_base_payload)
        payload["scenes"][0]["hybrid_ai_config"]["particles"]["type"] = bad_particle_type
        with pytest.raises(ValueError, match=r"type|enum"):
            validate_scene_manifest(payload)

    @pytest.mark.parametrize("trans_type", [
        "crossfade",
        "volumetric_fade",
        "depth_dissolve",
        "glitch_cut",
        "cut",
        "fade_to_black",
        "fade",
    ])
    def test_valid_transition_types(self, valid_base_payload, trans_type):
        payload = copy.deepcopy(valid_base_payload)
        payload["scenes"][0]["transition_out"]["type"] = trans_type
        assert validate_scene_manifest(payload) is True

    @pytest.mark.parametrize("bad_trans_type", ["wipe", "iris_in", "page_curl", "slide_up"])
    def test_reject_invalid_transition_types(self, valid_base_payload, bad_trans_type):
        payload = copy.deepcopy(valid_base_payload)
        payload["scenes"][0]["transition_out"]["type"] = bad_trans_type
        with pytest.raises(ValueError, match=r"type|enum"):
            validate_scene_manifest(payload)

    def test_scaling_to_100_scenes(self, valid_base_payload):
        """Stress test manifest validation scaling up to 100 sequential multi-engine scenes."""
        payload = copy.deepcopy(valid_base_payload)
        scenes = []
        engines = ["hybrid_cinematic_ai", "pure_procedural_webgl", "procedural_canvas2d"]
        cum_sec = 0.0
        for i in range(1, 101):
            dur = 60.0
            eng = engines[(i - 1) % len(engines)]
            sc = {
                "scene_index": i,
                "scene_id": f"scene_{i:03d}",
                "environment_name": f"Environment {i}",
                "start_sec": cum_sec,
                "duration_sec": dur,
                "tension_level": ((i - 1) % 5) + 1,
                "engine_type": eng,
                "transition_out": {"type": "crossfade", "duration_sec": 0.8},
            }
            if eng == "hybrid_cinematic_ai":
                sc["hybrid_ai_config"] = {
                    "background_image_path": f"/bg/img_{i}.png",
                    "depth_map_path": f"/bg/depth_{i}.png",
                }
            elif eng == "pure_procedural_webgl":
                sc["procedural_config"] = {
                    "template_name": "cosmic_horror_three.html",
                    "seed": i * 100,
                }
            scenes.append(sc)
            cum_sec += dur

        payload["scenes"] = scenes
        payload["total_duration_sec"] = cum_sec
        assert validate_scene_manifest(payload) is True

    def test_reject_invalid_input_types_to_validator(self):
        """Validating invalid non-dict non-path types raises ValueError."""
        with pytest.raises(ValueError, match=r"must be a Path, str, or dict"):
            validate_scene_manifest(12345)  # type: ignore

        with pytest.raises(ValueError, match=r"must be a Path, str, or dict"):
            validate_scene_manifest(["not", "a", "dict"])  # type: ignore

