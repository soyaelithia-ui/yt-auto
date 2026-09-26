"""Unit tests verifying JSON schemas and I/O contracts for the 4 specialized pipeline agents.

Agents tested:
1. Cinematic Script Curator (`schemas/script_curator.schema.json`)
2. Art Director / Mood Visual (`schemas/art_director.schema.json`)
3. Scene Planner / Compositor (`schemas/scene_planner.schema.json`)
4. Visual & Audio QA Auditor (`schemas/video_qa.schema.json`)
"""

import json
from pathlib import Path
import pytest
import jsonschema
from jsonschema import Draft7Validator, validate, ValidationError


SCHEMAS_DIR = Path(__file__).resolve().parent.parent.parent / "schemas"


def load_schema(schema_name: str) -> dict:
    schema_path = SCHEMAS_DIR / schema_name
    assert schema_path.is_file(), f"Schema file not found: {schema_path}"
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


class TestDraft7SchemaValidity:
    """Verify that all four agent schemas are well-formed Draft-07 schemas."""

    @pytest.mark.parametrize(
        "schema_filename",
        [
            "script_curator.schema.json",
            "art_director.schema.json",
            "scene_planner.schema.json",
            "video_qa.schema.json",
        ],
    )
    def test_schema_itself_is_valid_draft7(self, schema_filename: str):
        schema_dict = load_schema(schema_filename)
        # Check that Draft7Validator can check schema itself
        Draft7Validator.check_schema(schema_dict)
        assert schema_dict["$schema"] == "http://json-schema.org/draft-07/schema#"


class TestScriptCuratorSchema:
    """Tests for Agent 1: Cinematic Script Curator schema."""

    @pytest.fixture
    def schema(self):
        return load_schema("script_curator.schema.json")

    @pytest.fixture
    def valid_longform_script(self):
        return {
            "version": "2.0",
            "metadata": {
                "title": "El Misterio del Faro Olvidado",
                "channel_lane": "moku-horror-long",
                "target_format": "longform",
                "total_word_count": 650,
                "estimated_duration_sec": 620.0,
                "hook_summary": "Un guardafaro descubre que la luz atrae entidades del fondo abisal.",
                "tension_curve": [1, 2, 3, 4, 5, 3],
            },
            "acts": [
                {
                    "act_number": 1,
                    "act_title": "Acto I: Llegada y Aislamiento",
                    "dramatic_role": "exposition_inception",
                    "scenes": [
                        {
                            "scene_id": "scene_001",
                            "scene_index": 1,
                            "tension_level": 1,
                            "narration_text": "La niebla cubría los arrecifes cuando desembarqué en el islote solitario.",
                            "word_count": 120,
                            "estimated_duration_sec": 50.0,
                            "environmental_mood": "Océano tormentoso y frío",
                            "audio_pacing_cue": "calm_slow",
                        },
                        {
                            "scene_id": "scene_002",
                            "scene_index": 2,
                            "tension_level": 2,
                            "narration_text": "El antiguo mecanismo de la linterna chirriaba con un ritmo casi orgánico.",
                            "word_count": 140,
                            "estimated_duration_sec": 60.0,
                            "environmental_mood": "Interior de la torre metálica y húmeda",
                            "audio_pacing_cue": "steady_dramatic",
                        },
                    ],
                },
                {
                    "act_number": 2,
                    "act_title": "Acto II: El Fenómeno Anómalo",
                    "dramatic_role": "rising_action_dread",
                    "scenes": [
                        {
                            "scene_id": "scene_003",
                            "scene_index": 3,
                            "tension_level": 3,
                            "narration_text": "Las sombras bajo el agua comenzaron a moverse contra la marea.",
                            "word_count": 150,
                            "estimated_duration_sec": 65.0,
                            "environmental_mood": "Aguas profundas bioluminiscentes",
                            "audio_pacing_cue": "tense_accelerando",
                        }
                    ],
                },
                {
                    "act_number": 3,
                    "act_title": "Acto III: La Ruptura",
                    "dramatic_role": "climax_confrontation",
                    "scenes": [
                        {
                            "scene_id": "scene_004",
                            "scene_index": 4,
                            "tension_level": 5,
                            "narration_text": "El cristal estalló cuando los tentáculos colosales envolvieron la cúpula.",
                            "word_count": 130,
                            "estimated_duration_sec": 55.0,
                            "environmental_mood": "Cúpula destruida bajo lluvia torrencial",
                            "audio_pacing_cue": "intense_urgent",
                        }
                    ],
                },
                {
                    "act_number": 4,
                    "act_title": "Acto IV: Silencio Abisal",
                    "dramatic_role": "aftermath_revelation",
                    "scenes": [
                        {
                            "scene_id": "scene_005",
                            "scene_index": 5,
                            "tension_level": 2,
                            "narration_text": "Ahora la luz no guía a los barcos; los atrae hacia su despertar.",
                            "word_count": 110,
                            "estimated_duration_sec": 48.0,
                            "environmental_mood": "Amanecer brumoso desolado",
                            "audio_pacing_cue": "whispered_grave",
                        }
                    ],
                },
            ],
        }

    def test_valid_script_curator_payload(self, schema, valid_longform_script):
        validate(instance=valid_longform_script, schema=schema)

    def test_invalid_tension_level_out_of_bounds(self, schema, valid_longform_script):
        valid_longform_script["acts"][0]["scenes"][0]["tension_level"] = 6
        with pytest.raises(ValidationError) as excinfo:
            validate(instance=valid_longform_script, schema=schema)
        assert "6 is greater than the maximum of 5" in str(excinfo.value)

    def test_invalid_scene_id_pattern(self, schema, valid_longform_script):
        valid_longform_script["acts"][0]["scenes"][0]["scene_id"] = "scene_1"
        with pytest.raises(ValidationError) as excinfo:
            validate(instance=valid_longform_script, schema=schema)
        assert "does not match '^scene_[0-9]{3}$'" in str(excinfo.value)

    def test_missing_metadata_required_field(self, schema, valid_longform_script):
        del valid_longform_script["metadata"]["tension_curve"]
        with pytest.raises(ValidationError) as excinfo:
            validate(instance=valid_longform_script, schema=schema)
        assert "'tension_curve' is a required property" in str(excinfo.value)

    def test_invalid_dramatic_role_enum(self, schema, valid_longform_script):
        valid_longform_script["acts"][0]["dramatic_role"] = "invalid_role"
        with pytest.raises(ValidationError):
            validate(instance=valid_longform_script, schema=schema)

    def test_invalid_act_number_exceeds_max(self, schema, valid_longform_script):
        valid_longform_script["acts"][0]["act_number"] = 5
        with pytest.raises(ValidationError):
            validate(instance=valid_longform_script, schema=schema)

    def test_invalid_audio_pacing_cue_enum(self, schema, valid_longform_script):
        valid_longform_script["acts"][0]["scenes"][0]["audio_pacing_cue"] = "rap_fast"
        with pytest.raises(ValidationError):
            validate(instance=valid_longform_script, schema=schema)


class TestArtDirectorSchema:
    """Tests for Agent 2: Art Director / Mood Visual schema."""

    @pytest.fixture
    def schema(self):
        return load_schema("art_director.schema.json")

    @pytest.fixture
    def valid_visual_plan(self):
        return {
            "version": "2.0",
            "theme_lane": "cosmic_horror",
            "global_color_grade": {
                "lut_profile": "deep_abyss_rec709",
                "color_space": "Rec.709",
                "contrast_curve": "cinematic_s_curve",
                "saturation_modifier": 0.85,
            },
            "scenes": [
                {
                    "scene_id": "scene_001",
                    "scene_index": 1,
                    "tension_level": 1,
                    "environment_name": "Islote rocoso y faro victoriano",
                    "palette": {
                        "primary": "#0B0B10",
                        "secondary": "#1C1028",
                        "accent": "#12282D",
                        "shadow": "#050508",
                        "highlight": "#3A6D7C",
                    },
                    "lighting": {
                        "style": "Cold moonlight chiaroscuro with fog diffusion",
                        "color_temp_kelvin": 6500,
                        "key_direction": "backlight_silhouette",
                        "volumetric_fog_density": 0.45,
                    },
                    "atmosphere": {
                        "weather_effect": "dense_fog",
                        "particle_layer": "dust_motes",
                        "vignette_strength": 0.35,
                    },
                    "camera_composition": {
                        "shot_type": "extreme_wide",
                        "depth_of_field": "deep_focus_f8",
                        "focal_length_mm": 24,
                    },
                },
                {
                    "scene_id": "scene_002",
                    "scene_index": 2,
                    "tension_level": 4,
                    "environment_name": "Cúpula de la linterna de vidrio",
                    "palette": {
                        "primary": "#0B0B10",
                        "secondary": "#1C1028",
                        "accent": "#12282D",
                        "shadow": "#050508",
                        "highlight": "#3A6D7C",
                    },
                    "lighting": {
                        "style": "Harsh emergency lantern beam casting long geometric shadows",
                        "color_temp_kelvin": 4500,
                        "key_direction": "side_chiaroscuro",
                        "volumetric_fog_density": 0.60,
                    },
                    "atmosphere": {
                        "weather_effect": "rain_on_lens",
                        "particle_layer": "smoke_drift",
                        "vignette_strength": 0.50,
                    },
                    "camera_composition": {
                        "shot_type": "dutch_angle",
                        "depth_of_field": "shallow_f1.4",
                        "focal_length_mm": 50,
                    },
                },
            ],
        }

    def test_valid_art_director_payload(self, schema, valid_visual_plan):
        validate(instance=valid_visual_plan, schema=schema)

    @pytest.mark.parametrize(
        "lane_id,palette",
        [
            (
                "cosmic_horror",
                {
                    "primary": "#0B0B10",
                    "secondary": "#1C1028",
                    "accent": "#12282D",
                    "shadow": "#050508",
                    "highlight": "#3A6D7C",
                },
            ),
            (
                "creepypasta",
                {
                    "primary": "#141E18",
                    "secondary": "#1E2022",
                    "accent": "#2C221E",
                    "shadow": "#0D0F0E",
                    "highlight": "#8C7B48",
                },
            ),
            (
                "scp_foundation",
                {
                    "primary": "#2B2E33",
                    "secondary": "#1A1C20",
                    "accent": "#1E6B37",
                    "shadow": "#0E1012",
                    "highlight": "#C87D1A",
                },
            ),
            (
                "drama_aita",
                {
                    "primary": "#1A2230",
                    "secondary": "#251E1C",
                    "accent": "#8A4B4B",
                    "shadow": "#0F141C",
                    "highlight": "#D1C2A5",
                },
            ),
        ],
    )
    def test_all_theme_lane_palettes_validate(self, schema, valid_visual_plan, lane_id, palette):
        valid_visual_plan["theme_lane"] = lane_id
        valid_visual_plan["scenes"][0]["palette"] = palette
        validate(instance=valid_visual_plan, schema=schema)

    def test_invalid_hex_color_code(self, schema, valid_visual_plan):
        valid_visual_plan["scenes"][0]["palette"]["primary"] = "0B0B10"  # Missing leading #
        with pytest.raises(ValidationError) as excinfo:
            validate(instance=valid_visual_plan, schema=schema)
        assert "does not match '^#[0-9A-Fa-f]{6}$'" in str(excinfo.value)

    def test_invalid_theme_lane_enum(self, schema, valid_visual_plan):
        valid_visual_plan["theme_lane"] = "cyberpunk_neon"
        with pytest.raises(ValidationError):
            validate(instance=valid_visual_plan, schema=schema)

    def test_color_temp_kelvin_out_of_range(self, schema, valid_visual_plan):
        valid_visual_plan["scenes"][0]["lighting"]["color_temp_kelvin"] = 12000
        with pytest.raises(ValidationError):
            validate(instance=valid_visual_plan, schema=schema)

    def test_missing_palette_color_key(self, schema, valid_visual_plan):
        del valid_visual_plan["scenes"][0]["palette"]["highlight"]
        with pytest.raises(ValidationError):
            validate(instance=valid_visual_plan, schema=schema)


class TestScenePlannerSchema:
    """Tests for Agent 3: Scene Planner / Compositor schema."""

    @pytest.fixture
    def schema(self):
        return load_schema("scene_planner.schema.json")

    @pytest.fixture
    def valid_scene_manifest(self):
        return {
            "version": "2.0",
            "resolution": [1920, 1080],
            "fps": 30,
            "duration_sec": 120.0,
            "audio": {
                "narration_path": "data/worksets/run_001/narration.wav",
                "music_path": "assets/music/horror_ambient.mp3",
                "music_volume": 0.14,
                "sidechain_ducking": {
                    "ducking_db": -18.0,
                    "attack_ms": 20.0,
                    "release_ms": 350.0,
                },
            },
            "safe_area": {
                "margin_top": 124,
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
                    "engine": "director",
                    "engine_config": {
                        "asset_path": "data/worksets/run_001/scene_001_matte.png",
                        "depth_map": "data/worksets/run_001/scene_001_depth.png",
                        "motion": {
                            "zoom_start": 1.0,
                            "zoom_end": 1.08,
                            "pan_direction": "center_to_top",
                            "easing": "cubic-bezier(0.25, 0.1, 0.25, 1.0)",
                        },
                    },
                    "particle_overlay": {
                        "type": "dust_motes",
                        "opacity": 0.4,
                        "blend_mode": "screen",
                    },
                    "transition": {
                        "type": "crossfade",
                        "duration_sec": 1.5,
                    },
                },
                {
                    "scene_index": 2,
                    "scene_id": "scene_002",
                    "start_sec": 60.0,
                    "duration_sec": 60.0,
                    "tension_level": 4,
                    "engine": "video_loop",
                    "engine_config": {
                        "template_name": "cosmic_horror_loop.mp4",
                    },
                    "particle_overlay": {
                        "type": "dense_fog",
                        "opacity": 0.6,
                        "blend_mode": "overlay",
                    },
                    "transition": {
                        "type": "dip_to_black",
                        "duration_sec": 0.8,
                    },
                },
            ],
            "subtitles": [
                {
                    "start": 0.5,
                    "end": 3.2,
                    "text": "La niebla cubría los arrecifes solitarios.",
                },
                {
                    "start": 3.5,
                    "end": 7.0,
                    "text": "Ningún barco se atrevía a cruzar el estrecho.",
                },
            ],
        }

    def test_valid_scene_manifest_payload(self, schema, valid_scene_manifest):
        validate(instance=valid_scene_manifest, schema=schema)

    def test_invalid_engine_type(self, schema, valid_scene_manifest):
        valid_scene_manifest["scenes"][0]["engine"] = "unreal_engine_5"
        with pytest.raises(ValidationError):
            validate(instance=valid_scene_manifest, schema=schema)

    def test_missing_safe_area(self, schema, valid_scene_manifest):
        del valid_scene_manifest["safe_area"]
        with pytest.raises(ValidationError):
            validate(instance=valid_scene_manifest, schema=schema)

    def test_invalid_audio_ducking_structure(self, schema, valid_scene_manifest):
        del valid_scene_manifest["audio"]["sidechain_ducking"]["attack_ms"]
        with pytest.raises(ValidationError):
            validate(instance=valid_scene_manifest, schema=schema)

    def test_fps_not_allowed(self, schema, valid_scene_manifest):
        valid_scene_manifest["fps"] = 120
        with pytest.raises(ValidationError):
            validate(instance=valid_scene_manifest, schema=schema)

    def test_invalid_particle_overlay_blend_mode(self, schema, valid_scene_manifest):
        valid_scene_manifest["scenes"][0]["particle_overlay"]["blend_mode"] = "color_dodge"
        with pytest.raises(ValidationError):
            validate(instance=valid_scene_manifest, schema=schema)


class TestVideoQASchema:
    """Tests for Agent 4: Visual & Audio QA Auditor schema."""

    @pytest.fixture
    def schema(self):
        return load_schema("video_qa.schema.json")

    @pytest.fixture
    def valid_qa_report(self):
        return {
            "version": "2.0",
            "run_id": "run_20260826_moku_001",
            "overall_pass": True,
            "quality_score": 96,
            "tier1_audio_metrics": {
                "integrated_lufs": -14.1,
                "true_peak_dbtp": -1.6,
                "stereo_correlation": 0.88,
                "whistle_tones_detected": 0,
                "passed": True,
            },
            "tier2_visual_metrics": {
                "resolution": "1920x1080",
                "video_codec": "h264",
                "pixel_format": "yuv420p",
                "faststart_moov_valid": True,
                "avg_luminance": 34.5,
                "dark_ratio": 0.28,
                "longest_black_sec": 0.4,
                "freeze_detected": False,
                "passed": True,
            },
            "tier3_vision_review": {
                "summary": "Pristine Full HD render. Atmospheric lighting and subtitles comply with safe area bounds.",
                "findings": [
                    {
                        "severity": "low",
                        "category": "visual",
                        "timecode_sec": 58.5,
                        "description": "Minor crossfade luminance dip within acceptable broadcast threshold.",
                        "suggested_fix": "No action required.",
                    }
                ],
            },
            "rejection_reasons": [],
        }

    def test_valid_qa_report_payload(self, schema, valid_qa_report):
        validate(instance=valid_qa_report, schema=schema)

    def test_valid_rejected_qa_report_payload(self, schema, valid_qa_report):
        valid_qa_report["overall_pass"] = False
        valid_qa_report["quality_score"] = 45
        valid_qa_report["tier1_audio_metrics"]["passed"] = False
        valid_qa_report["tier1_audio_metrics"]["integrated_lufs"] = -10.2  # Too loud
        valid_qa_report["tier2_visual_metrics"]["passed"] = False
        valid_qa_report["tier2_visual_metrics"]["avg_luminance"] = 14.0  # Too dark
        valid_qa_report["rejection_reasons"] = [
            "Audio LUFS exceeds acceptable threshold (-10.2 LUFS vs target -14.0 LUFS)",
            "Average perceptual luminance below minimum (14.0 < 22.0)",
        ]
        validate(instance=valid_qa_report, schema=schema)

    def test_quality_score_out_of_bounds(self, schema, valid_qa_report):
        valid_qa_report["quality_score"] = 105
        with pytest.raises(ValidationError) as excinfo:
            validate(instance=valid_qa_report, schema=schema)
        assert "105 is greater than the maximum of 100" in str(excinfo.value)

    def test_missing_required_tier2_metric(self, schema, valid_qa_report):
        del valid_qa_report["tier2_visual_metrics"]["faststart_moov_valid"]
        with pytest.raises(ValidationError):
            validate(instance=valid_qa_report, schema=schema)

    def test_invalid_finding_severity_enum(self, schema, valid_qa_report):
        valid_qa_report["tier3_vision_review"]["findings"][0]["severity"] = "catastrophic"
        with pytest.raises(ValidationError):
            validate(instance=valid_qa_report, schema=schema)

    def test_missing_rejection_reasons_array(self, schema, valid_qa_report):
        del valid_qa_report["rejection_reasons"]
        with pytest.raises(ValidationError):
            validate(instance=valid_qa_report, schema=schema)


class TestCrossAgentContractCompatibility:
    """Tests confirming cross-agent pipeline handoffs pass schema validation end-to-end."""

    def test_script_to_art_to_scene_to_qa_flow(self):
        script_schema = load_schema("script_curator.schema.json")
        art_schema = load_schema("art_director.schema.json")
        scene_schema = load_schema("scene_planner.schema.json")
        qa_schema = load_schema("video_qa.schema.json")

        # 1. Script Curator Output
        script_payload = {
            "version": "2.0",
            "metadata": {
                "title": "SCP-087 Escalera Infinita",
                "channel_lane": "moku-scp-shorts",
                "target_format": "short",
                "total_word_count": 95,
                "estimated_duration_sec": 42.0,
                "hook_summary": "Exploración de descenso clase D en SCP-087",
                "tension_curve": [3, 4, 5],
            },
            "acts": [
                {
                    "act_number": 1,
                    "act_title": "Descenso Inicial",
                    "dramatic_role": "exposition_inception",
                    "scenes": [
                        {
                            "scene_id": "scene_001",
                            "scene_index": 1,
                            "tension_level": 3,
                            "narration_text": "El sujeto D-8432 inicia el descenso por el tramo 17 de la escalera.",
                            "word_count": 32,
                            "estimated_duration_sec": 14.0,
                            "environmental_mood": "Hormigón brutalista y oscuridad absoluta",
                            "audio_pacing_cue": "steady_dramatic",
                        },
                        {
                            "scene_id": "scene_002",
                            "scene_index": 2,
                            "tension_level": 4,
                            "narration_text": "Los sollozos infantiles se escuchan a 200 metros bajo sus pies.",
                            "word_count": 33,
                            "estimated_duration_sec": 14.0,
                            "environmental_mood": "Ecos metálicos distorsionados",
                            "audio_pacing_cue": "tense_accelerando",
                        },
                        {
                            "scene_id": "scene_003",
                            "scene_index": 3,
                            "tension_level": 5,
                            "narration_text": "El rostro sin pupilas emerge directamente frente al foco de su linterna.",
                            "word_count": 30,
                            "estimated_duration_sec": 14.0,
                            "environmental_mood": "Encuentro hostil y estática de video",
                            "audio_pacing_cue": "intense_urgent",
                        },
                    ],
                }
            ],
        }
        validate(instance=script_payload, schema=script_schema)

        # 2. Art Director Output for the same scenes
        art_payload = {
            "version": "2.0",
            "theme_lane": "scp_foundation",
            "global_color_grade": {
                "lut_profile": "brutalist_containment_rec709",
                "color_space": "Rec.709",
                "contrast_curve": "crushed_low_mid",
                "saturation_modifier": 0.70,
            },
            "scenes": [
                {
                    "scene_id": s["scene_id"],
                    "scene_index": s["scene_index"],
                    "tension_level": s["tension_level"],
                    "environment_name": s["environmental_mood"],
                    "palette": {
                        "primary": "#2B2E33",
                        "secondary": "#1A1C20",
                        "accent": "#1E6B37",
                        "shadow": "#0E1012",
                        "highlight": "#C87D1A",
                    },
                    "lighting": {
                        "style": "Overhead flickering fluorescent with harsh shadows",
                        "color_temp_kelvin": 4500,
                        "key_direction": "top_down",
                        "volumetric_fog_density": 0.3,
                    },
                    "atmosphere": {
                        "weather_effect": "crt_phosphor_flicker",
                        "particle_layer": "dust_motes",
                        "vignette_strength": 0.45,
                    },
                    "camera_composition": {
                        "shot_type": "medium_shot" if s["tension_level"] < 5 else "dutch_angle",
                        "depth_of_field": "shallow_f1.4",
                        "focal_length_mm": 35,
                    },
                }
                for act in script_payload["acts"]
                for s in act["scenes"]
            ],
        }
        validate(instance=art_payload, schema=art_schema)

        # 3. Scene Planner Output
        scene_payload = {
            "version": "2.0",
            "resolution": [1080, 1920],
            "fps": 30,
            "duration_sec": 42.0,
            "audio": {
                "narration_path": "data/worksets/scp_087/narration.wav",
                "music_path": "assets/music/horror_ambient.mp3",
                "music_volume": 0.12,
                "sidechain_ducking": {
                    "ducking_db": -18.0,
                    "attack_ms": 20.0,
                    "release_ms": 350.0,
                },
            },
            "safe_area": {
                "margin_top": 330,
                "margin_bottom": 330,
                "margin_left": 72,
                "margin_right": 72,
            },
            "scenes": [
                {
                    "scene_index": s["scene_index"],
                    "scene_id": s["scene_id"],
                    "start_sec": float((s["scene_index"] - 1) * 14.0),
                    "duration_sec": 14.0,
                    "tension_level": s["tension_level"],
                    "engine": "video_loop" if s["tension_level"] == 3 else "director",
                    "engine_config": {
                        "template_name": "scp_terminal_loop.mp4" if s["tension_level"] == 3 else None,
                        "asset_path": f"data/worksets/scp_087/{s['scene_id']}.mp4" if s["tension_level"] != 3 else None,
                    },
                    "particle_overlay": {
                        "type": "crt_lines" if s["tension_level"] == 3 else "dust_motes",
                        "opacity": 0.5,
                        "blend_mode": "screen",
                    },
                    "transition": {
                        "type": "chromatic_glitch" if s["tension_level"] == 5 else "crossfade",
                        "duration_sec": 0.3 if s["tension_level"] == 5 else 0.8,
                    },
                }
                for s in art_payload["scenes"]
            ],
            "subtitles": [
                {"start": 0.0, "end": 14.0, "text": "El sujeto D-8432 inicia el descenso por el tramo 17."},
                {"start": 14.0, "end": 28.0, "text": "Los sollozos infantiles se escuchan a 200 metros bajo sus pies."},
                {"start": 28.0, "end": 42.0, "text": "El rostro sin pupilas emerge directamente frente a la linterna."},
            ],
        }
        validate(instance=scene_payload, schema=scene_schema)

        # 4. Video QA Output
        qa_payload = {
            "version": "2.0",
            "run_id": "scp_087_prod_run",
            "overall_pass": True,
            "quality_score": 98,
            "tier1_audio_metrics": {
                "integrated_lufs": -13.9,
                "true_peak_dbtp": -1.5,
                "stereo_correlation": 0.92,
                "whistle_tones_detected": 0,
                "passed": True,
            },
            "tier2_visual_metrics": {
                "resolution": "1080x1920",
                "video_codec": "h264",
                "pixel_format": "yuv420p",
                "faststart_moov_valid": True,
                "avg_luminance": 28.4,
                "dark_ratio": 0.35,
                "longest_black_sec": 0.2,
                "freeze_detected": False,
                "passed": True,
            },
            "tier3_vision_review": {
                "summary": "Clean vertical 9:16 SCP production, excellent terminal readability and safe area adherence.",
                "findings": [],
            },
            "rejection_reasons": [],
        }
        validate(instance=qa_payload, schema=qa_schema)
