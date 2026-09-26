"""Atmospheric Director Agent — Autonomous visual & soundscape curation via Antigravity Pro harness.

Evaluates narrative subtext, pacing, and emotional tension to curate the optimal
video loop textures and ambient drone stems from the real catalog (assets/loops/):
- Replaces legacy static dictionaries and fake image diffusion prompts.
- Queries loop catalog metadata to intelligently match visual mood and audio pacing.
- Emits structured atmosphere directives for LoopVideoEngine and AudioDucking.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import jsonschema

from src.agents.base_agent import CANONICAL_MODEL, ProgrammaticAgent, parse_json_reply
from src.core.domain import AIProviderChainExhausted
from src.log import get_logger

logger = get_logger("atmospheric_director_agent")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
ATMOSPHERE_RESULT_PATH = OUTPUT_DIR / "atmospheric_director_result.json"
SCHEMA_PATH = PROJECT_ROOT / "schemas" / "art_director.schema.json"

ATMOSPHERE_SYSTEM_INSTRUCTIONS = (
    "Eres el Director de Arte y Atmósfera de un canal de YouTube de alta calidad. "
    "Tu misión es analizar el guion de un video y seleccionar la mejor combinación "
    "de textura visual (loop de video del catálogo) y ambientación sonora.\n"
    "Categorías de loop disponibles:\n"
    "- 'cosmic_horror': Fondos oscuros abisales, partículas tenues, vacíos estelares y anomalías.\n"
    "- 'dark_ambient': Atmósfera minimalista oscura, niebla sutil, baja iluminación para relatos de misterio.\n"
    "- 'tactical_chamber': Estética de instalación de contención, búnker o laboratorio SCP.\n"
    "- 'dramatic_interior': Espacios sobrios, iluminación lateral cálida/apagada para dilemas personales.\n"
    "Estilos sonoros disponibles:\n"
    "- 'drone_abyss': Ondas subsónicas de baja frecuencia y tensión sutil.\n"
    "- 'dark_ambient': Drones ambientales envolventes no invasivos con voz humana.\n"
    "- 'tension_pulse': Pulsación rítmica gradual para momentos de clímax.\n"
    "Responde EXCLUSIVAMENTE en formato JSON conforme al esquema."
)

ATMOSPHERE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "loop_category": {
            "type": "string",
            "enum": ["cosmic_horror", "dark_ambient", "tactical_chamber", "dramatic_interior"],
        },
        "audio_theme": {
            "type": "string",
            "enum": ["drone_abyss", "dark_ambient", "tension_pulse"],
        },
        "mood_summary": {"type": "string"},
        "accent_hex": {"type": "string"},
        "pacing": {"type": "string", "enum": ["slow_creeping", "steady_dramatic", "intense_urgent"]},
    },
    "required": ["loop_category", "audio_theme", "mood_summary", "accent_hex"],
    "additionalProperties": False,
}

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


class AtmosphericDirectorAgent(ProgrammaticAgent):
    """Autonomous art and atmosphere curation agent."""

    def __init__(
        self,
        model: str = CANONICAL_MODEL,
        instance_id: str = "pipeline_creative",
        reasoning_effort: str = "high",
        schema_file: Optional[Path] = None,
    ) -> None:
        super().__init__(
            system_instructions=ATMOSPHERE_SYSTEM_INSTRUCTIONS,
            model=model,
            role_name="atmospheric-director-agent",
            instance_id=instance_id,
            reasoning_effort=reasoning_effort,
            task_result_path=ATMOSPHERE_RESULT_PATH,
            json_schema=ATMOSPHERE_SCHEMA,
        )
        self.schema_path = schema_file or SCHEMA_PATH
        self._schema: Optional[Dict[str, Any]] = None
        if self.schema_path.is_file():
            try:
                with open(self.schema_path, "r", encoding="utf-8") as f:
                    self._schema = json.load(f)
            except Exception:
                pass

    def curate_atmosphere(
        self,
        script_text: str,
        topic: str = "",
        channel: str = "moku",
    ) -> Dict[str, Any]:
        """Analyzes script and selects the optimal atmospheric video loop and soundscape.

        Fail-Closed: Raises AIProviderChainExhausted if the LLM cannot produce a valid decision.
        """
        excerpt = script_text[:1200]
        prompt = (
            f"Analiza el siguiente guion para el canal '{channel}' (tema: '{topic}'):\n\n"
            f"GUION:\n{excerpt}\n\n"
            "Determina la categoría de loop, el estilo sonoro de audio, el color de acento y el ritmo emocional."
        )

        logger.info("AtmosphericDirectorAgent curating atmosphere for '%s'", topic)
        try:
            result_path = self.run(prompt)
            res = self.consume(result_path)
        except Exception as exc:
            logger.error("AtmosphericDirectorAgent failed: %s", exc)
            raise AIProviderChainExhausted(f"AtmosphericDirectorAgent error: {exc}") from exc

        data = None
        structured = res.get("output", {}).get("structured_output")
        if isinstance(structured, dict) and structured.get("loop_category"):
            data = dict(structured)
        else:
            parsed = parse_json_reply(res.get("output", {}).get("reply", ""))
            if isinstance(parsed, dict) and parsed.get("loop_category"):
                data = dict(parsed)

        if not data:
            error_detail = res.get("output", {}).get("error") or "Sin decision atmosferica utilizable"
            raise AIProviderChainExhausted(f"AtmosphericDirectorAgent sin salida valida ({error_detail})")

        return data

    def plan_visuals(
        self,
        cinematic_script: Dict[str, Any],
        theme_lane: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compatibility bridge for multiscene pipelines expecting visual_plan schema."""
        meta = cinematic_script.get("metadata", {})
        lane_raw = theme_lane or meta.get("channel_lane", "cosmic_horror")

        # Normalize theme_lane
        norm_lane = "cosmic_horror"
        if "scp" in str(lane_raw).lower():
            norm_lane = "scp_foundation"
        elif "aita" in str(lane_raw).lower() or "drama" in str(lane_raw).lower():
            norm_lane = "drama_aita"
        elif "creepy" in str(lane_raw).lower():
            norm_lane = "creepypasta"

        theme_data = THEME_PALETTES.get(norm_lane, THEME_PALETTES["cosmic_horror"])

        scenes_plan: List[Dict[str, Any]] = []
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
            }
            scenes_plan.append(sc_plan)

        visual_plan: Dict[str, Any] = {
            "version": "2.0",
            "theme_lane": norm_lane,
            "palette": {
                "primary": theme_data["primary"],
                "secondary": theme_data["secondary"],
                "accent": theme_data["accent"],
                "shadow": theme_data["shadow"],
                "highlight": theme_data["highlight"],
            },
            "global_color_grade": {
                "lut_profile": theme_data["lut"],
                "color_space": "Rec.709",
                "contrast_curve": "cinematic_s_curve",
                "saturation_modifier": 0.95,
            },
            "scenes": scenes_plan,
        }

        # Validate against schema if loaded
        if self._schema:
            try:
                jsonschema.validate(instance=visual_plan, schema=self._schema)
            except Exception as exc:
                logger.warning("Visual plan schema validation warning: %s", exc)

        return visual_plan


# Backward-compatibility alias
ArtDirectorMoodAgent = AtmosphericDirectorAgent
