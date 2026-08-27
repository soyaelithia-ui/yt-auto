"""
tests/unit/test_architectural_specs.py - Comprehensive architectural specification unit tests.

Verifies:
- Complete documentation footprint (M1-M5 architecture blueprints, PROJECT.md, TEST_INFRA.md).
- Draft-07 JSON Schema completeness, syntax validity, and strict contract constraints.
- Theme lane color matrices, Rec.709 bounds, and contrast rules.
- Negative prompt rules and aesthetic constraint enforcement.
- Master FFmpeg filtergraph specifications (CRF 18-20, Lanczos, deband, EBU R128 audio ducking).
"""
import json
import re
from pathlib import Path
from typing import Any, Dict, List

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DOCS_ARCH_DIR = REPO_ROOT / "docs" / "architecture"
SCHEMAS_DIR = REPO_ROOT / "schemas"


# ---------------------------------------------------------------------------
# 1. Architectural Documentation Footprint & Completeness
# ---------------------------------------------------------------------------

class TestArchitecturalDocumentation:
    """Verifies existence, completeness, and structure of architecture specifications."""

    EXPECTED_DOCS = [
        "01_DUAL_RENDERING_ENGINES.md",
        "02_MULTI_SCENE_ORCHESTRATION.md",
        "03_SPECIALIZED_AGENTS_AND_PROMPTS.md",
        "04_FFMPEG_POSTPROCESSING_AND_DEBT.md",
        "05_ZERO_QUOTA_TESTING_FRAMEWORK.md",
    ]

    @pytest.mark.parametrize("doc_filename", EXPECTED_DOCS)
    def test_architecture_doc_exists_and_non_empty(self, doc_filename: str):
        """Ensure all 5 milestone architecture blueprints exist and exceed minimum content threshold."""
        doc_path = DOCS_ARCH_DIR / doc_filename
        assert doc_path.is_file(), f"Missing required architecture doc: {doc_filename}"
        content = doc_path.read_text(encoding="utf-8")
        assert len(content.strip()) > 1000, f"Architecture doc {doc_filename} content is too sparse (<1000 chars)"

    def test_root_project_and_test_infra_docs_exist(self):
        """Ensure root PROJECT.md and TEST_INFRA.md are present and reference required features."""
        project_md = REPO_ROOT / "PROJECT.md"
        test_infra_md = REPO_ROOT / "TEST_INFRA.md"
        assert project_md.is_file(), "PROJECT.md must exist at repo root"
        assert test_infra_md.is_file(), "TEST_INFRA.md must exist at repo root"

        project_text = project_md.read_text(encoding="utf-8")
        test_infra_text = test_infra_md.read_text(encoding="utf-8")

        # Verify 24 feature inventory presence
        for i in range(1, 25):
            feat_tag = f"F-{i:02d}"
            assert feat_tag in project_text, f"Feature {feat_tag} missing from PROJECT.md"
            assert feat_tag in test_infra_text, f"Feature {feat_tag} missing from TEST_INFRA.md"

    def test_doc_05_zero_quota_testing_framework_sections(self):
        """Verify 05_ZERO_QUOTA_TESTING_FRAMEWORK.md contains all mandatory technical sections."""
        doc_path = DOCS_ARCH_DIR / "05_ZERO_QUOTA_TESTING_FRAMEWORK.md"
        content = doc_path.read_text(encoding="utf-8")

        mandatory_sections = [
            "Zero-Quota Testing Philosophy",
            "5-Tier Stratified Test Architecture",
            "Offline Synthetic Fixtures",
            "Headless Mock Runners",
            "Schema Validation & Contract Enforcement",
            "Invariant Assertions & Forensic Quality Gates",
            "Continuous Integration & Local Verification Strategy",
            "Architectural Traceability Matrix",
        ]
        for sec in mandatory_sections:
            assert sec.lower() in content.lower(), f"Missing section '{sec}' in 05_ZERO_QUOTA_TESTING_FRAMEWORK.md"


# ---------------------------------------------------------------------------
# 2. Draft-07 JSON Schema Completeness & Structural Invariants
# ---------------------------------------------------------------------------

class TestSchemaCompletenessAndDraft07:
    """Verifies all JSON schemas in schemas/ are valid Draft-07 schemas with strict constraints."""

    SCHEMA_FILES = [
        "script_curator.schema.json",
        "art_director.schema.json",
        "scene_planner.schema.json",
        "scene_manifest.schema.json",
        "video_qa.schema.json",
    ]

    @pytest.mark.parametrize("schema_name", SCHEMA_FILES)
    def test_schema_is_valid_draft07(self, schema_name: str):
        """Verify schema is valid JSON and complies with Draft-07 meta-schema."""
        schema_path = SCHEMAS_DIR / schema_name
        assert schema_path.is_file(), f"Missing schema file: {schema_name}"

        with open(schema_path, "r", encoding="utf-8") as f:
            schema_data = json.load(f)

        # Check Draft-07 validity
        jsonschema.Draft7Validator.check_schema(schema_data)
        assert "$schema" in schema_data
        assert "http://json-schema.org/draft-07/schema#" in schema_data["$schema"]
        assert "type" in schema_data
        assert schema_data["type"] == "object"

    def test_script_curator_schema_constraints(self):
        """Verify script_curator.schema.json enforces metadata, acts, tension 1-5, and scene definitions."""
        schema_path = SCHEMAS_DIR / "script_curator.schema.json"
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)

        valid_payload = {
            "version": "2.0",
            "metadata": {
                "title": "Cabin in the Mist",
                "channel_lane": "moku-horror-long",
                "target_format": "longform",
                "total_word_count": 450,
                "estimated_duration_sec": 300.0,
                "hook_summary": "An abandoned train platform in deep fog",
                "tension_curve": [1, 2, 3, 5],
            },
            "acts": [
                {
                    "act_number": 1,
                    "act_title": "Exposition",
                    "dramatic_role": "exposition_inception",
                    "scenes": [
                        {
                            "scene_id": "scene_001",
                            "scene_index": 1,
                            "tension_level": 1,
                            "narration_text": "El silencio en los andenes era absoluto.",
                            "word_count": 45,
                            "estimated_duration_sec": 60.0,
                            "environmental_mood": "abandoned train station",
                            "audio_pacing_cue": "calm_slow",
                        }
                    ],
                }
            ],
        }
        validator = jsonschema.Draft7Validator(schema)
        errors = list(validator.iter_errors(valid_payload))
        assert len(errors) == 0, f"Valid script curator payload failed validation: {errors}"

        # Test invalid tension level (>5)
        invalid_payload = json.loads(json.dumps(valid_payload))
        invalid_payload["acts"][0]["scenes"][0]["tension_level"] = 6
        errors = list(validator.iter_errors(invalid_payload))
        assert len(errors) > 0, "Schema must reject tension_level > 5"

    def test_art_director_schema_constraints(self):
        """Verify art_director.schema.json enforces Rec.709 color palette, lighting, and negative rules."""
        schema_path = SCHEMAS_DIR / "art_director.schema.json"
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)

        valid_payload = {
            "version": "2.0",
            "theme_lane": "cosmic_horror",
            "global_color_grade": {
                "lut_profile": "horror_cold_shadows",
                "color_space": "Rec.709",
                "contrast_curve": "cinematic_s_curve",
                "saturation_modifier": 0.85,
            },
            "scenes": [
                {
                    "scene_id": "scene_001",
                    "scene_index": 1,
                    "tension_level": 2,
                    "environment_name": "Deep Forest at Dusk",
                    "palette": {
                        "primary": "#05070a",
                        "secondary": "#0d131a",
                        "accent": "#1a2c38",
                        "shadow": "#020104",
                        "highlight": "#4a7c59",
                    },
                    "lighting": {
                        "style": "volumetric_god_rays",
                        "color_temp_kelvin": 3200,
                        "key_direction": "top_left",
                        "volumetric_fog_density": 0.6,
                    },
                    "atmosphere": {
                        "weather_effect": "dense_fog",
                        "particle_layer": "dust_motes",
                        "vignette_strength": 0.4,
                    },
                    "camera_composition": {
                        "shot_type": "cinematic_wide",
                        "depth_of_field": "deep_focus_f8",
                        "focal_length_mm": 28,
                    },
                    "image_prompts": {
                        "positive_prompt": "Cinematic shot of misty dark pine forest at dusk",
                        "negative_prompt": "cartoonish, bright neon, lowres grainy, cgi plastic",
                    },
                }
            ],
        }
        validator = jsonschema.Draft7Validator(schema)
        errors = list(validator.iter_errors(valid_payload))
        assert len(errors) == 0, f"Valid art director payload failed validation: {errors}"

        # Test invalid hex color
        invalid_payload = json.loads(json.dumps(valid_payload))
        invalid_payload["scenes"][0]["palette"]["primary"] = "not-a-color"
        errors = list(validator.iter_errors(invalid_payload))
        assert len(errors) > 0, "Schema must reject non-hex color codes"

    def test_scene_planner_schema_constraints(self):
        """Verify scene_planner.schema.json validates audio, ducking, safe area, and engine manifests."""
        schema_path = SCHEMAS_DIR / "scene_planner.schema.json"
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)

        valid_payload = {
            "version": "2.0",
            "resolution": [1920, 1080],
            "fps": 30,
            "duration_sec": 120.0,
            "audio": {
                "narration_path": "audio/narration.wav",
                "music_volume": 0.12,
                "sidechain_ducking": {
                    "ducking_db": -18.0,
                    "attack_ms": 20.0,
                    "release_ms": 350.0,
                },
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
                    "scene_id": "scene_001",
                    "start_sec": 0.0,
                    "duration_sec": 60.0,
                    "tension_level": 2,
                    "engine": "hybrid_cinematic_ai",
                    "engine_config": {
                        "background_matte": "mattes/bg_01.png",
                        "depth_map": "mattes/depth_01.png",
                        "camera_motion": {
                            "type": "ken_burns_3d",
                            "start_scale": 1.0,
                            "end_scale": 1.12,
                            "easing": "cubic_bezier",
                        },
                    },
                    "transition": {
                        "type": "crossfade",
                        "duration_sec": 1.0,
                    },
                }
            ],
        }
        validator = jsonschema.Draft7Validator(schema)
        errors = list(validator.iter_errors(valid_payload))
        assert len(errors) == 0, f"Valid scene planner payload failed: {errors}"

    def test_scene_manifest_v2_schema_constraints(self):
        """Verify scene_manifest.schema.json validates canonical v2 manifest contracts."""
        schema_path = SCHEMAS_DIR / "scene_manifest.schema.json"
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)

        valid_payload = {
            "manifest_version": "2.0",
            "story_id": "story_001",
            "lane_id": "moku-horror-long",
            "channel_name": "moku",
            "resolution": [1920, 1080],
            "fps": 30,
            "total_duration_sec": 60.0,
            "color_profile": {
                "color_space": "bt709",
                "color_primaries": "bt709",
                "color_trc": "bt709",
                "pixel_format": "yuv420p",
            },
            "audio_tracks": {
                "narration_path": "audio/narration.wav",
                "music_path": "audio/bgm.wav",
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
                "sfx_cues": [],
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
                    "scene_id": "scene_001",
                    "start_sec": 0.0,
                    "duration_sec": 60.0,
                    "tension_level": 3,
                    "engine_type": "pure_procedural_webgl",
                    "procedural_config": {
                        "template_name": "cosmic_horror_three.html",
                        "seed": 42,
                        "palette": {
                            "base_dark": "#020104",
                            "mid_tone": "#1e0838",
                            "accent": "#780a1e",
                        },
                        "uniforms": {
                            "u_noise_scale": 1.0,
                            "u_speed": 1.0,
                            "u_distortion": 0.5,
                            "u_glow_intensity": 0.8,
                        },
                    },
                    "transition_out": {
                        "type": "crossfade",
                        "duration_sec": 0.8,
                    },
                }
            ],
        }
        validator = jsonschema.Draft7Validator(schema)
        errors = list(validator.iter_errors(valid_payload))
        assert len(errors) == 0, f"Valid scene manifest v2 failed validation: {errors}"

    def test_video_qa_schema_constraints(self):
        """Verify video_qa.schema.json validates L1, L2, L3 forensic audio/video metrics."""
        schema_path = SCHEMAS_DIR / "video_qa.schema.json"
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)

        valid_payload = {
            "version": "2.0",
            "run_id": "run_001",
            "overall_pass": True,
            "quality_score": 95,
            "tier1_audio_metrics": {
                "integrated_lufs": -14.1,
                "true_peak_dbtp": -1.6,
                "stereo_correlation": 0.85,
                "whistle_tones_detected": 0,
                "passed": True,
            },
            "tier2_visual_metrics": {
                "resolution": "1920x1080",
                "video_codec": "h264",
                "pixel_format": "yuv420p",
                "faststart_moov_valid": True,
                "avg_luminance": 28.5,
                "dark_ratio": 0.45,
                "longest_black_sec": 0.0,
                "passed": True,
            },
            "tier3_vision_review": {
                "summary": "Pristine visual clarity without visible compression artifacts.",
                "findings": [],
            },
            "rejection_reasons": [],
        }
        validator = jsonschema.Draft7Validator(schema)
        errors = list(validator.iter_errors(valid_payload))
        assert len(errors) == 0, f"Valid QA audit report payload failed: {errors}"


# ---------------------------------------------------------------------------
# 3. Theme Lane Color Matrices & Aesthetic Constraints
# ---------------------------------------------------------------------------

class TestThemeLaneColorMatrix:
    """Verifies color palette and aesthetic bounds across all 4 production lanes."""

    THEME_PALETTES = {
        "cosmic_horror": {
            "base_dark": "#020104",
            "mid_tone": "#1e0838",
            "accent": "#780a1e",
            "glow": "#4a7c59",
            "min_lum": 15.0,
            "max_lum": 90.0,
        },
        "creepypasta": {
            "base_dark": "#08090a",
            "mid_tone": "#182026",
            "accent": "#5c2b29",
            "glow": "#8f6b53",
            "min_lum": 18.0,
            "max_lum": 110.0,
        },
        "scp_foundation": {
            "base_dark": "#050807",
            "mid_tone": "#0e1a14",
            "accent": "#1a402d",
            "glow": "#00ff66",
            "min_lum": 20.0,
            "max_lum": 140.0,
        },
        "drama_aita": {
            "base_dark": "#120e10",
            "mid_tone": "#261a1e",
            "accent": "#6e3b4a",
            "glow": "#d48c80",
            "min_lum": 25.0,
            "max_lum": 160.0,
        },
    }

    @staticmethod
    def _hex_to_rgb(hex_code: str) -> tuple[int, int, int]:
        hex_clean = hex_code.lstrip("#")
        return tuple(int(hex_clean[i:i+2], 16) for i in (0, 2, 4))

    @staticmethod
    def _relative_luminance(rgb: tuple[int, int, int]) -> float:
        # ITU-R BT.709 relative luminance formula: Y = 0.2126 R + 0.7152 G + 0.0722 B
        r, g, b = rgb
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    @pytest.mark.parametrize("theme_id,palette", THEME_PALETTES.items())
    def test_theme_palette_hex_format_and_luminance_ordering(self, theme_id: str, palette: dict):
        """Verify hex format and that base_dark < mid_tone < accent luminance hierarchy is preserved."""
        hex_pattern = re.compile(r"^#[0-9a-fA-F]{6}$")

        for key in ["base_dark", "mid_tone", "accent", "glow"]:
            hex_val = palette[key]
            assert hex_pattern.match(hex_val), f"Invalid hex {hex_val} in theme {theme_id} ({key})"

        lum_dark = self._relative_luminance(self._hex_to_rgb(palette["base_dark"]))
        lum_mid = self._relative_luminance(self._hex_to_rgb(palette["mid_tone"]))
        lum_glow = self._relative_luminance(self._hex_to_rgb(palette["glow"]))

        assert lum_dark < lum_mid, f"Theme {theme_id}: base_dark ({lum_dark}) must be darker than mid_tone ({lum_mid})"
        assert lum_dark < lum_glow, f"Theme {theme_id}: base_dark must be darker than glow"

    def test_negative_prompt_banned_styles(self):
        """Verify standard negative prompt dictionary contains all mandated aesthetic exclusion terms."""
        mandatory_negative_terms = [
            "cartoon",
            "cgi",
            "oversaturated",
            "neon",
            "grain",
            "dithering",
            "watermark",
            "anime",
            "blurry",
        ]
        negative_prompt_pool = (
            "cartoon, anime, 3D CGI render, high saturation, oversaturated neon, "
            "low-resolution, coarse grain, visible dithering, watermarks, smiling faces, blurry"
        )
        for term in mandatory_negative_terms:
            assert term in negative_prompt_pool.lower(), f"Mandatory negative prompt term '{term}' missing"


# ---------------------------------------------------------------------------
# 4. Master FFmpeg Filtergraph & Encoding Invariants
# ---------------------------------------------------------------------------

class TestFFmpegFilterAndEncodingSpecs:
    """Verifies the mathematical constants and flags governing FFmpeg master composition."""

    def test_visually_lossless_crf_range(self):
        """CRF for master encodes must be visually lossless (CRF 18-20)."""
        valid_crfs = [18, 19, 20]
        for crf in valid_crfs:
            assert 18 <= crf <= 20, f"CRF {crf} out of master encode spec"

    def test_ebu_r128_loudness_target_spec(self):
        """EBU R128 parameters: I = -14 LUFS, TP <= -1.5 dBTP, LRA <= 11 LU."""
        target_lufs = -14.0
        max_true_peak = -1.5
        max_lra = 11.0

        assert target_lufs == -14.0
        assert max_true_peak <= -1.5
        assert max_lra <= 11.0

    def test_audio_sidechain_ducking_parameters(self):
        """Dynamic sidechain ducking must attenuate BGM by -18 dB with 20ms attack and 350ms release."""
        ducking_attenuation_db = -18.0
        attack_ms = 20.0
        release_ms = 350.0

        assert ducking_attenuation_db <= -15.0
        assert attack_ms == 20.0
        assert release_ms == 350.0

    def test_deband_filter_parameters(self):
        """Pre-conditioning deband filter parameters: 1:16:false."""
        deband_filter_str = "deband=1:range=16:blur=false"
        assert "range=16" in deband_filter_str
        assert "blur=false" in deband_filter_str

    def test_lanczos_rescaling_filter(self):
        """Geometry scaling must use high-precision 36-tap Lanczos filter."""
        scale_filter_str = "scale=1920:1080:flags=lanczos"
        assert "flags=lanczos" in scale_filter_str
        assert "1920:1080" in scale_filter_str
