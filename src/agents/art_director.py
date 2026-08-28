"""
src/agents/art_director_mood.py - Agent 2: Art Director / Mood Visual.

Translates 4-Act cinematic scripts into detailed visual mood specifications,
applying strict Rec.709 color matrices, volumetric lighting parameters,
atmospheric particle layers, and positive/negative prompt directives.
Validates output against schemas/art_director.schema.json.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import jsonschema

from src.log import get_logger

logger = get_logger("art_director_mood")

SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "schemas" / "art_director.schema.json"


THEME_PALETTES = {
    "cosmic_horror": {
        "primary": "#041421",
        "secondary": "#0a2233",
        "accent": "#00e5a3",
        "shadow": "#000305",
        "highlight": "#b0fff1",
        "kelvin": 6500,
        "lut": "cosmic_abyss_rec709",
    },
    "creepypasta": {
        "primary": "#12080a",
        "secondary": "#261014",
        "accent": "#cc1824",
        "shadow": "#040102",
        "highlight": "#ffd8dc",
        "kelvin": 3200,
        "lut": "slasher_crimson_noir",
    },
    "scp_foundation": {
        "primary": "#030e06",
        "secondary": "#082110",
        "accent": "#00ff66",
        "shadow": "#000502",
        "highlight": "#c8ffe0",
        "kelvin": 5400,
        "lut": "crt_terminal_rec709",
    },
    "drama_aita": {
        "primary": "#181014",
        "secondary": "#2c1c22",
        "accent": "#ffaa44",
        "shadow": "#060304",
        "highlight": "#fff2e0",
        "kelvin": 4000,
        "lut": "warm_interior_drama",
    },
}


class ArtDirectorMoodAgent:
    """Agent 2: Generates Rec.709 color grades, lighting, and camera composition directives."""

    def __init__(self, schema_file: Optional[Path] = None) -> None:
        self.schema_path = schema_file or SCHEMA_PATH
        self._schema: Optional[Dict[str, Any]] = None
        if self.schema_path.is_file():
            with open(self.schema_path, "r", encoding="utf-8") as f:
                self._schema = json.load(f)

    def plan_visuals(
        self,
        cinematic_script: Dict[str, Any],
        theme_lane: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Creates a complete VisualPlan from a CinematicScript object.
        """
        meta = cinematic_script.get("metadata", {})
        lane_raw = theme_lane or meta.get("channel_lane", "cosmic_horror")
        
        # Normalize theme_lane
        norm_lane = "cosmic_horror"
        if "scp" in lane_raw.lower():
            norm_lane = "scp_foundation"
        elif "aita" in lane_raw.lower() or "drama" in lane_raw.lower():
            norm_lane = "drama_aita"
        elif "creepy" in lane_raw.lower():
            norm_lane = "creepypasta"

        theme_data = THEME_PALETTES[norm_lane]

        scenes_plan: List[Dict[str, Any]] = []

        # Flatten scenes from acts
        all_scenes: List[Dict[str, Any]] = []
        for act in cinematic_script.get("acts", []):
            for sc in act.get("scenes", []):
                all_scenes.append(sc)

        for sc in all_scenes:
            sc_id = sc.get("scene_id", "scene_001")
            sc_idx = int(sc.get("scene_index", 1))
            tension = max(1, min(5, int(sc.get("tension_level", 3))))
            env_name = sc.get("environmental_mood", "Atmospheric Chamber")

            # Lighting based on tension
            if tension <= 2:
                key_dir = "top_down" if tension == 1 else "side_chiaroscuro"
                fog_density = 0.25
                light_style = "Soft ambient chiaroscuro"
            elif tension in (3, 4):
                key_dir = "side_chiaroscuro" if tension == 3 else "backlight_silhouette"
                fog_density = 0.45
                light_style = "Dramatic rim and high contrast"
            else:
                key_dir = "under_chin_menace"
                fog_density = 0.65
                light_style = "Violent strobe flicker and extreme shadow"

            # Atmosphere and particles
            if norm_lane == "scp_foundation":
                weather_fx = "crt_phosphor_flicker"
                particle_lyr = "electric_embers" if tension > 3 else "dust_motes"
            elif norm_lane == "drama_aita":
                weather_fx = "none"
                particle_lyr = "dust_motes"
            else:
                weather_fx = "dense_fog" if tension <= 3 else "floating_embers"
                particle_lyr = "fog_mist" if tension <= 3 else "electric_embers"

            # Camera composition
            if sc_idx == 1:
                shot_type = "wide_establishing"
                dof = "deep_focus_f8"
                focal = 24
            elif tension >= 4:
                shot_type = "close_up_macro"
                dof = "shallow_f1.4"
                focal = 85
            else:
                shot_type = "medium_shot"
                dof = "medium_f4"
                focal = 50

            # Image prompts
            pos_prompt = (
                f"Masterpiece 8k cinematic matte painting, {env_name}, {light_style}, "
                f"volumetric lighting, photorealistic depth, color palette {theme_data['accent']} and {theme_data['secondary']}, "
                f"high contrast chiaroscuro, 35mm photograph, shot on Arri Alexa."
            )
            neg_prompt = (
                "noisy grain, coarse dithering, blurry, low resolution, cartoon, 3d render plastic, "
                "deformed, ugly, text, watermark, mutated, neon clownish colors, oversaturated."
            )

            sc_plan = {
                "scene_id": sc_id,
                "scene_index": sc_idx,
                "tension_level": tension,
                "environment_name": env_name,
                "palette": {
                    "primary": theme_data["primary"],
                    "secondary": theme_data["secondary"],
                    "accent": theme_data["accent"],
                    "shadow": theme_data["shadow"],
                    "highlight": theme_data["highlight"],
                },
                "lighting": {
                    "style": light_style,
                    "color_temp_kelvin": theme_data["kelvin"],
                    "key_direction": key_dir,
                    "volumetric_fog_density": fog_density,
                },
                "atmosphere": {
                    "weather_effect": weather_fx,
                    "particle_layer": particle_lyr,
                    "vignette_strength": round(0.2 + 0.1 * tension, 2),
                },
                "camera_composition": {
                    "shot_type": shot_type,
                    "depth_of_field": dof,
                    "focal_length_mm": focal,
                },
                "image_prompts": {
                    "positive_prompt": pos_prompt,
                    "negative_prompt": neg_prompt,
                },
            }
            scenes_plan.append(sc_plan)

        visual_plan: Dict[str, Any] = {
            "version": "2.0",
            "theme_lane": norm_lane,
            "global_color_grade": {
                "lut_profile": theme_data["lut"],
                "color_space": "Rec.709",
                "contrast_curve": "cinematic_s_curve",
                "saturation_modifier": 0.95,
            },
            "scenes": scenes_plan,
        }

        # Validate against schema
        if self._schema:
            jsonschema.validate(instance=visual_plan, schema=self._schema)

        return visual_plan
