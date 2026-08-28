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
        actual_audio_duration: Optional[float] = None,
        subdivide_shots: bool = False,
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

        # Resolve exact target audio duration for timing coordination
        target_duration = actual_audio_duration
        if (target_duration is None or target_duration <= 0) and narration_path and Path(narration_path).is_file():
            try:
                from lib.ffmpeg import probe_media
                probe = probe_media(narration_path)
                if probe and probe.duration > 0:
                    target_duration = float(probe.duration)
            except Exception as exc:
                logger.debug("Failed probing narration duration in ScenePlanner: %s", exc)

        # Proportional scene duration calculation aligned with actual audio track
        raw_durations = [float(sc.get("estimated_duration_sec", 60.0)) for sc in script_scenes]
        total_raw = sum(raw_durations) if raw_durations else 0.0

        if target_duration and target_duration > 0 and total_raw > 0:
            scale = target_duration / total_raw
            scaled_durations = [max(1.0, round(d * scale, 2)) for d in raw_durations]
            diff = round(target_duration - sum(scaled_durations), 2)
            if scaled_durations:
                scaled_durations[-1] = max(1.0, round(scaled_durations[-1] + diff, 2))
        else:
            scaled_durations = raw_durations

        # Build SceneConfig objects with dynamic cinematic pacing (8-15s per cut for longform)
        current_time = 0.0
        scenes_data: List[Dict[str, Any]] = []
        is_longform = (target_duration and target_duration > 180.0) or target_fmt == "longform" or "long" in lane.lower()
        do_subdivide = subdivide_shots or meta.get("subdivide_shots", False) or meta.get("dynamic_pacing", False)

        global_scene_idx = 1
        pan_directions = ["center_to_top", "left_to_right", "right_to_left", "center_to_bottom"]
        camera_motion_types = ["ken_burns_3d", "parallax_drift", "zoom_in", "zoom_out", "pan_left", "pan_right"]

        for idx, sc_script in enumerate(script_scenes):
            sc_id_base = sc_script.get("scene_id", f"scene_{idx+1:03d}")
            sc_plan = plan_scenes_map.get(sc_id_base, {})
            scene_total_dur = scaled_durations[idx] if idx < len(scaled_durations) else float(sc_script.get("estimated_duration_sec", 60.0))
            tension = max(1, min(5, int(sc_script.get("tension_level", 3))))
            env_name = sc_plan.get("environment_name", sc_script.get("environmental_mood", "Scene Atmosphere"))

            # Calculate granular sub-shots if scene duration exceeds 15 seconds in longform and subdivision enabled
            if do_subdivide and is_longform and scene_total_dur > 15.0:
                target_sub_dur = 11.0  # ideal 8-15s sweet spot
                num_subshots = max(1, int(round(scene_total_dur / target_sub_dur)))
                sub_duration = round(scene_total_dur / num_subshots, 2)
                sub_durations = [sub_duration] * num_subshots
                sub_durations[-1] = max(1.0, round(scene_total_dur - sum(sub_durations[:-1]), 2))
            else:
                sub_durations = [scene_total_dur]

            for sub_i, sub_dur in enumerate(sub_durations):
                sub_sc_id = f"scene_{global_scene_idx:03d}"
                pan_dir = pan_directions[global_scene_idx % len(pan_directions)]
                motion_type = camera_motion_types[global_scene_idx % len(camera_motion_types)]

                # Alternating Engine & Template Selection
                # Interleave procedural 3D oceanic and classified SCP terminal for rich cinematic variety
                is_procedural = (tension >= 4 or global_scene_idx % 2 == 1 or "waves" in env_name.lower() or "abyss" in env_name.lower())
                
                if is_procedural:
                    engine_type = "pure_procedural_webgl"
                    palette_data = sc_plan.get("palette", {})

                    # Switch between 3D Oceanic Abyss and SCP Terminal HUD
                    if "scp" in lane.lower() and (global_scene_idx % 4 == 2 or "terminal" in env_name.lower() or "log" in env_name.lower()):
                        template_name = "scp_terminal_css.html"
                    else:
                        template_name = "cosmic_horror_three.html"

                    proc_config = {
                        "template_name": template_name,
                        "seed": 42 + global_scene_idx * 19,
                        "palette": {
                            "base_dark": palette_data.get("shadow", "#000305"),
                            "mid_tone": palette_data.get("primary", "#041421"),
                            "accent": palette_data.get("accent", "#00e5a3"),
                        },
                        "uniforms": {
                            "u_noise_scale": round(1.0 + 0.25 * tension, 2),
                            "u_speed": round(0.85 + 0.18 * tension, 2),
                            "u_distortion": round(0.35 + 0.12 * tension, 2),
                            "u_glow_intensity": round(0.8 + 0.1 * tension, 2),
                        },
                    }
                    hybrid_config = None
                else:
                    engine_type = "hybrid_cinematic_ai"
                    proc_config = None

                    atmosphere_data = sc_plan.get("atmosphere", {})
                    particle_type = atmosphere_data.get("particle_layer", "fog_mist")
                    if particle_type not in ("dust_motes", "ember_sparks", "fog_mist", "spores", "rain_streaks"):
                        particle_type = "fog_mist"

                    hybrid_config = {
                        "seed": 1000 + global_scene_idx * 37,
                        "layers": [],
                        "camera_motion": {
                            "type": motion_type,
                            "start_zoom": 1.0,
                            "end_zoom": round(1.05 + 0.03 * tension, 3),
                            "pan_direction": pan_dir,
                            "easing": "cubic_bezier",
                            "parallax_intensity": round(0.12 + 0.09 * tension, 2),
                        },
                        "lighting": {
                            "volumetric_rays": tension >= 3,
                            "light_source_pos": [0.75, 0.25],
                            "intensity": round(0.28 + 0.12 * tension, 2),
                            "flicker_frequency": round(3.5 if tension >= 4 else 0.0, 1),
                            "color_tint": sc_plan.get("palette", {}).get("accent", "#00e5a3"),
                        },
                        "particles": {
                            "type": particle_type,
                            "density": 35 + 25 * tension,
                            "velocity": round(0.9 + 0.3 * tension, 2),
                            "color": sc_plan.get("palette", {}).get("highlight", "#b0fff1"),
                            "opacity": 0.5,
                        },
                    }
                    pos_prompt = sc_plan.get("image_prompts", {}).get("positive_prompt")
                    if pos_prompt:
                        hybrid_config["prompt_used"] = pos_prompt

                scene_entry: Dict[str, Any] = {
                    "scene_index": global_scene_idx,
                    "scene_id": sub_sc_id,
                    "environment_name": f"{env_name} (Cut {sub_i+1})" if len(sub_durations) > 1 else env_name,
                    "start_sec": round(current_time, 2),
                    "duration_sec": round(sub_dur, 2),
                    "tension_level": tension,
                    "engine_type": engine_type,
                    "transition_out": {
                        "type": "crossfade" if (idx < len(script_scenes) - 1 or sub_i < len(sub_durations) - 1) else "fade_to_black",
                        "duration_sec": 0.6 if is_longform else 0.8,
                    },
                }

                if hybrid_config:
                    scene_entry["hybrid_ai_config"] = hybrid_config
                if proc_config:
                    scene_entry["procedural_config"] = proc_config

                scenes_data.append(scene_entry)
                current_time += sub_dur
                global_scene_idx += 1

        total_duration = round(target_duration if target_duration and target_duration > 0 else current_time, 2)

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
