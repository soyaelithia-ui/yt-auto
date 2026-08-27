"""
src/agents/scene_planner_compositor.py - Agent 3: Scene Planner / Compositor.

Merges the narrative script (Agent 1) and visual plan (Agent 2) with audio master tracks,
decides engine selection (Hybrid Cinematic AI vs Pure Procedural WebGL/Canvas),
configures camera motion, transitions, sidechain ducking, and generates the canonical
scene_manifest.json. Validates output with schemas/scene_manifest.schema.json.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import jsonschema

from src.log import get_logger
from src.scene_manifest import (
    AudioTracks,
    CameraMotionConfig,
    ColorProfile,
    DuckingConfig,
    HybridAIConfig,
    LightingConfig,
    ParticleConfig,
    ProceduralConfig,
    ProceduralPalette,
    SafeArea,
    SceneConfig,
    SceneManifestV2,
    TransitionConfig,
)

logger = get_logger("scene_planner_compositor")

SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "schemas" / "scene_manifest.schema.json"


class ScenePlannerCompositorAgent:
    """Agent 3: Synthesizes SceneManifestV2 from Script and Visual Plan."""

    def __init__(self, schema_file: Optional[Path] = None) -> None:
        self.schema_path = schema_file or SCHEMA_PATH
        self._schema: Optional[Dict[str, Any]] = None
        if self.schema_path.is_file():
            with open(self.schema_path, "r", encoding="utf-8") as f:
                self._schema = json.load(f)

    def plan_manifest(
        self,
        script: Dict[str, Any],
        visual_plan: Dict[str, Any],
        story_id: str,
        narration_path: str,
        music_path: Optional[str] = None,
        lane_id: Optional[str] = None,
        channel_name: str = "moku",
        resolution: Optional[List[int]] = None,
        fps: int = 30,
    ) -> Dict[str, Any]:
        """
        Builds a canonical scene_manifest.json payload.
        """
        meta = script.get("metadata", {})
        lane = lane_id or meta.get("channel_lane", "moku-horror-long")
        target_fmt = meta.get("target_format", "longform")

        # Resolve resolution
        if resolution:
            res = resolution
        elif target_fmt == "short" or "short" in lane.lower():
            res = [1080, 1920]
        else:
            res = [1920, 1080]

        # Flatten script scenes and visual plan scenes
        script_scenes: List[Dict[str, Any]] = []
        for act in script.get("acts", []):
            for sc in act.get("scenes", []):
                script_scenes.append(sc)

        plan_scenes_map: Dict[str, Dict[str, Any]] = {
            sc.get("scene_id", ""): sc for sc in visual_plan.get("scenes", [])
        }

        # Build SceneConfig objects with exact continuous time offsets
        current_time = 0.0
        scenes_data: List[Dict[str, Any]] = []

        for idx, sc_script in enumerate(script_scenes):
            sc_id = sc_script.get("scene_id", f"scene_{idx+1:03d}")
            sc_plan = plan_scenes_map.get(sc_id, {})
            duration = float(sc_script.get("estimated_duration_sec", 60.0))
            tension = int(sc_script.get("tension_level", 3))
            env_name = sc_plan.get("environment_name", sc_script.get("environmental_mood", "Scene Atmosphere"))

            # Alternating Engine Selection for rich variety
            # Procedural for high tension or abstract lanes; Hybrid for narrative environments
            if tension == 5 or idx % 3 == 2 or "waves" in env_name.lower() or "abyss" in env_name.lower():
                engine_type = "pure_procedural_webgl"
                palette_data = sc_plan.get("palette", {})
                proc_config = {
                    "template_name": "cosmic_horror_three.html" if res[0] > res[1] else "cosmic_horror_three.html",
                    "seed": 42 + idx * 17,
                    "palette": {
                        "base_dark": palette_data.get("shadow", "#04080e"),
                        "mid_tone": palette_data.get("primary", "#0c1824"),
                        "accent": palette_data.get("accent", "#00ffcc"),
                    },
                    "uniforms": {
                        "u_noise_scale": 1.0 + 0.2 * tension,
                        "u_speed": 0.8 + 0.15 * tension,
                        "u_distortion": 0.3 + 0.1 * tension,
                        "u_glow_intensity": 0.7 + 0.08 * tension,
                    },
                }
                hybrid_config = None
            else:
                engine_type = "hybrid_cinematic_ai"
                proc_config = None
                
                # Pan direction logic
                pan_dirs = ["center_to_top", "left_to_right", "right_to_left", "center_to_bottom"]
                pan_dir = pan_dirs[idx % len(pan_dirs)]

                lighting_data = sc_plan.get("lighting", {})
                atmosphere_data = sc_plan.get("atmosphere", {})

                hybrid_config = {
                    "seed": 1000 + idx * 31,
                    "layers": [],
                    "camera_motion": {
                        "type": "ken_burns_3d",
                        "start_zoom": 1.0,
                        "end_zoom": round(1.04 + 0.025 * tension, 3),
                        "pan_direction": pan_dir,
                        "easing": "cubic_bezier",
                        "parallax_intensity": round(0.1 + 0.08 * tension, 2),
                    },
                    "lighting": {
                        "volumetric_rays": tension >= 3,
                        "light_source_pos": [0.75, 0.25],
                        "intensity": round(0.25 + 0.1 * tension, 2),
                        "flicker_frequency": 2.5 if tension >= 4 else 0.0,
                        "color_tint": sc_plan.get("palette", {}).get("accent", "#ffffff"),
                    },
                    "particles": {
                        "type": atmosphere_data.get("particle_layer", "fog_mist") if atmosphere_data.get("particle_layer") in ("dust_motes", "ember_sparks", "fog_mist", "spores", "rain_streaks") else "fog_mist",
                        "density": 30 + 20 * tension,
                        "velocity": round(0.8 + 0.25 * tension, 2),
                        "color": sc_plan.get("palette", {}).get("highlight", "#ffffff"),
                        "opacity": 0.45,
                    },
                }
                pos_prompt = sc_plan.get("image_prompts", {}).get("positive_prompt")
                if pos_prompt:
                    hybrid_config["prompt_used"] = pos_prompt

            scene_entry: Dict[str, Any] = {
                "scene_index": idx + 1,
                "scene_id": sc_id,
                "environment_name": env_name,
                "start_sec": round(current_time, 2),
                "duration_sec": round(duration, 2),
                "tension_level": tension,
                "engine_type": engine_type,
                "transition_out": {
                    "type": "crossfade" if idx < len(script_scenes) - 1 else "fade_to_black",
                    "duration_sec": 0.8,
                },
            }

            if hybrid_config:
                scene_entry["hybrid_ai_config"] = hybrid_config
            if proc_config:
                scene_entry["procedural_config"] = proc_config

            scenes_data.append(scene_entry)
            current_time += duration

        total_duration = round(current_time, 2)

        # Safe area boundaries
        safe_area = {
            "margin_top": 60 if res[0] > res[1] else 120,
            "margin_bottom": 124 if res[0] > res[1] else 330,
            "margin_left": 85 if res[0] > res[1] else 40,
            "margin_right": 85 if res[0] > res[1] else 40,
        }

        manifest_payload: Dict[str, Any] = {
            "manifest_version": "2.0",
            "story_id": story_id,
            "lane_id": lane,
            "channel_name": channel_name,
            "resolution": res,
            "fps": fps,
            "total_duration_sec": total_duration,
            "color_profile": {
                "color_space": "bt709",
                "color_primaries": "bt709",
                "color_trc": "bt709",
                "pixel_format": "yuv420p",
            },
            "audio_tracks": {
                "narration_path": narration_path,
                "music_path": music_path or "",
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
            "safe_area": safe_area,
            "scenes": scenes_data,
            "subtitles": [],
            "branding": {
                "stamp_text": f"[{channel_name.upper()}]",
                "channel_name": channel_name,
            },
            "hook_text": meta.get("title", "")[:80],
            "thumbnail_candidate_timestamp": 5.0,
        }

        # Validate with Draft-07 schema
        if self._schema:
            jsonschema.validate(instance=manifest_payload, schema=self._schema)

        return manifest_payload
