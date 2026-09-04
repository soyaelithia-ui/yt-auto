"""
src/agents/scene_planner_compositor.py - Agent 3: Scene Planner / Compositor.

Merges the narrative script (Agent 1) and visual plan (Agent 2) with audio master tracks,
decides engine selection (Hybrid Cinematic AI vs Pure Procedural WebGL/Canvas),
configures camera motion, transitions, sidechain ducking, and generates the canonical
scene_manifest.json. Validates output with schemas/scene_manifest.schema.json.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

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

    @staticmethod
    def _resolve_scene_archetype(
        env_name: str,
        tension: int,
        dramatic_role: str = "",
        lane_id: str = "",
        scene_idx: int = 1,
        excluded_archetypes: Optional[set[str]] = None,
    ) -> Tuple[str, str, Dict[str, Any]]:
        """
        Universally resolves the visual archetype, template name, and dynamic custom parameters
        based on rich bilingual semantic context (Spanish & English), dramatic role, and tension.
        Guarantees variety and eliminates arbitrary cycle looping.
        """
        text = f"{env_name} {dramatic_role}".lower()
        words = set(re.findall(r'[a-zA-Z0-9_áéíóúüñ]+', text))
        lane_l = lane_id.lower()
        excluded = excluded_archetypes or set()

        # AITA / Drama Lane override
        if "aita" in lane_l or "drama" in lane_l or "confession" in lane_l:
            return (
                "drama_aita",
                "drama_waves_canvas.html",
                {"waveSpeed": round(0.8 + 0.2 * tension, 2), "glowIntensity": 1.0},
            )

        # 1. Classified / Terminal / Intel / Radar / Logs / Surveillance / Protocol / Telemetry / Archive
        terminal_keywords = {
            "terminal", "radar", "registro", "clasificado", "expediente", "consola", "pantalla",
            "senhal", "señal", "telemetria", "telemetría", "protocolo", "archivo", "dossier", "hud", "vigilancia", "alerta",
            "monitor", "monitors", "computer", "computers",
            "terminal", "log", "logs", "archive", "archives", "classified", "dossier", "hud", "radar", "protocol", "intel", "surveillance"
        }
        if "classified_terminal" not in excluded and (
            words.intersection(terminal_keywords)
            or any(k in text for k in ("terminal", "clasificado", "radar", "dossier", "expediente", "registro", "archive", "classified", "monitor"))
        ):
            return (
                "classified_terminal",
                "archetype_classified_terminal.html",
                {
                    "docTitle": "REGISTRO CLASIFICADO // EXPEDIENTE",
                    "alertLevel": f"NIVEL DE ALERTA {tension} // ACTIVO",
                    "glowIntensity": round(0.85 + 0.15 * tension, 2),
                },
            )

        # 2. Synaptic / Consciousness / Neural / Mind / Brain / Telepathy / Memory
        synaptic_keywords = {
            "mente", "cerebro", "neuronal", "sinapsis", "conciencia", "telepatia", "telepatía",
            "recuerdo", "memoria", "psiquico", "psíquico", "red", "matriz", "psicologico", "psicológico",
            "brain", "mind", "neural", "synapse", "synaptic", "consciousness", "cyber", "digital", "data", "matrix", "psycho", "psychological", "pneuma"
        }
        if "synaptic_network" not in excluded and (
            words.intersection(synaptic_keywords)
            or any(k in text for k in ("mente", "cerebro", "neural", "conciencia", "sinap", "mind", "psychological"))
        ):
            return (
                "synaptic_network",
                "archetype_synaptic_network.html",
                {
                    "nodeDensity": 24 + 6 * tension,
                    "pulseSpeed": round(0.85 + 0.2 * tension, 2),
                },
            )

        # 3. Cosmic Singularity / Black Hole / Vortex / Relativistic Abyss / Space / Void
        cosmic_keywords = {
            "singularidad", "agujero negro", "vortice", "vórtice", "espacio", "cosmico", "cósmico",
            "gravedad", "lente", "galaxia", "universo", "horizonte", "sucesos", "vacio", "vacío",
            "singularity", "void", "black_hole", "rift", "portal", "abyss", "cosmic", "space", "vortex", "dimension", "event horizon"
        }
        if "cosmic_singularity" not in excluded and (
            words.intersection(cosmic_keywords)
            or any(k in text for k in ("singularidad", "vortice", "vórtice", "espacio", "agujero negro", "singularity", "black hole", "rift", "cosmic", "event horizon"))
        ):
            return (
                "cosmic_singularity",
                "archetype_cosmic_singularity.html",
                {
                    "swirlSpeed": round(0.85 + 0.2 * tension, 2),
                    "singularityScale": round(0.95 + 0.08 * tension, 2),
                },
            )

        # 4. Anomaly Silhouette / Monster / Beast / Breach / Creature / Colossus / Titan
        anomaly_keywords = {
            "criatura", "monstruo", "titan", "coloso", "bestia", "anomalia", "anomalía",
            "demonio", "ojos", "garra", "fauce", "devorar", "emerger", "despertar",
            "monster", "monsters", "creature", "creatures", "beast", "breach", "rampage",
            "threat", "chaos", "climax", "confrontation", "colossus", "titan", "cataclysmic"
        }
        if "anomaly_silhouette" not in excluded and (
            words.intersection(anomaly_keywords)
            or any(k in text for k in ("criatura", "monstruo", "coloso", "anomal", "monster", "beast", "devor", "rampage", "cataclysm"))
            or (tension >= 4 and dramatic_role in ("climax_confrontation", "climax_manifestation"))
        ):
            return (
                "anomaly_silhouette",
                "archetype_anomaly_silhouette.html",
                {
                    "threatLevel": tension,
                    "emberCount": 35 + 10 * tension,
                },
            )

        # 5. Atmospheric Landscape / Wasteland / Steppe / Monoliths / Lighthouse / Coast / Ocean
        landscape_keywords = {
            "paramo", "páramo", "estepa", "ceniza", "cenizas", "monolito", "monolitos", "desierto",
            "llanura", "montana", "montaña", "ruinas", "caminante", "faro", "costa", "mar", "oceano",
            "océano", "fosa", "playa", "marino", "tormenta", "olas", "ola", "isla", "niebla",
            "wasteland", "steppe", "monolith", "desert", "ruins", "ash", "landscape", "lighthouse", "ocean", "sea", "coast"
        }
        if "atmospheric_landscape" not in excluded and (
            words.intersection(landscape_keywords)
            or any(k in text for k in ("paramo", "páramo", "monolito", "faro", "costa", "ceniza", "estepa", "mar ", "oceano", "océano", "wasteland", "desert", "monolith"))
        ):
            is_marine = any(k in text for k in ("faro", "mar", "costa", "oceano", "océano", "fosa", "ola", "lighthouse", "ocean", "sea"))
            return (
                "atmospheric_landscape",
                "archetype_atmospheric_landscape.html",
                {
                    "silhouetteType": "lighthouse" if is_marine else "monolith",
                    "stormType": "mist" if is_marine else ("ash" if tension >= 3 else "mist"),
                    "accentColor": "#00e5a3" if is_marine else "#22b8ff",
                },
            )

        # 6. Tactical Chamber / Bunker / Vault / Facility / Corridor / Containment / Laboratory
        chamber_keywords = {
            "bunker", "búnker", "camara", "cámara", "pasillo", "laboratorio", "instalacion",
            "instalación", "puerta", "bloqueo", "estroboscopio", "confinamiento", "estructura",
            "acero", "cimiento", "subterraneo", "subterráneo", "oficina",
            "chamber", "bunker", "corridor", "hall", "vault", "facility", "conclave", "subterranean", "room", "containment", "concrete"
        }
        if "tactical_chamber" not in excluded and (
            words.intersection(chamber_keywords)
            or any(k in text for k in ("bunker", "búnker", "camara", "cámara", "pasillo", "laboratorio", "acero", "cimiento", "vault", "containment"))
        ):
            return (
                "tactical_chamber",
                "archetype_tactical_chamber.html",
                {
                    "chamberType": "corridor" if tension <= 3 else "vault",
                    "strobeSpeed": round(0.75 + 0.25 * tension, 2),
                    "fogDensity": round(0.35 + 0.12 * tension, 2),
                },
            )

        # 7. Dynamic Fallback: Choose the next available distinct archetype
        all_archetypes = [
            ("atmospheric_landscape", "archetype_atmospheric_landscape.html", {"silhouetteType": "monolith", "stormType": "ash"}),
            ("classified_terminal", "archetype_classified_terminal.html", {"docTitle": "ARCHIVO CONFIDENCIAL", "alertLevel": f"NIVEL {tension}"}),
            ("tactical_chamber", "archetype_tactical_chamber.html", {"chamberType": "corridor"}),
            ("anomaly_silhouette", "archetype_anomaly_silhouette.html", {"threatLevel": tension}),
            ("synaptic_network", "archetype_synaptic_network.html", {"nodeDensity": 26}),
            ("cosmic_singularity", "archetype_cosmic_singularity.html", {"swirlSpeed": 1.0}),
        ]
        
        available = [a for a in all_archetypes if a[0] not in excluded]
        if available:
            return available[scene_idx % len(available)]
        return all_archetypes[scene_idx % len(all_archetypes)]

    def plan_manifest(
        self,
        script: Dict[str, Any],
        visual_plan: Dict[str, Any],
        story_id: str,
        narration_path: str,
        music_path: Optional[str] = None,
        music_volume: Optional[float] = None,
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
            act_role = act.get("dramatic_role", "")
            for sc in act.get("scenes", []):
                if not sc.get("dramatic_role") and act_role:
                    sc["dramatic_role"] = act_role
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

        used_archetypes_short: set[str] = set()
        prev_archetype: Optional[str] = None

        for idx, sc_script in enumerate(script_scenes):
            sc_id_base = sc_script.get("scene_id", f"scene_{idx+1:03d}")
            sc_plan = plan_scenes_map.get(sc_id_base, {})
            scene_total_dur = scaled_durations[idx] if idx < len(scaled_durations) else float(sc_script.get("estimated_duration_sec", 60.0))
            tension = max(1, min(5, int(sc_script.get("tension_level", 3))))
            env_name = sc_plan.get("environment_name", sc_script.get("environmental_mood", "Scene Atmosphere"))

            # If storyboard scenes are explicitly curated with semantic duration or transition reasons, preserve scenes
            has_storyboard = bool(sc_script.get("transition_reason") or sc_plan.get("archetype_id"))
            if do_subdivide and is_longform and scene_total_dur > 15.0 and not has_storyboard:
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

                # Engine & Template Selection
                # Use pure_procedural_webgl with dynamic universal visual archetypes for all scenes
                is_procedural = True
                
                if is_procedural:
                    engine_type = "pure_procedural_webgl"
                    palette_data = sc_plan.get("palette", {})
                    dram_role = sc_script.get("dramatic_role", "")
                    narration_snippet = sc_script.get("narration_text", "") or sc_script.get("scene_text", "")

                    # For Shorts: exclude all previously used archetypes to guarantee 100% distinct scenes
                    # For Longform: exclude the immediate previous archetype to prevent static back-to-back loops
                    excluded = set(used_archetypes_short) if not is_longform else ({prev_archetype} if prev_archetype else set())

                    upstream_archetype = sc_plan.get("archetype_id")
                    if upstream_archetype:
                        category = upstream_archetype
                        template_name = upstream_archetype
                        custom_params = sc_plan.get("uniform_params", {})
                    else:
                        category, template_name, custom_params = self._resolve_scene_archetype(
                            env_name=f"{env_name} {narration_snippet}",
                            tension=tension,
                            dramatic_role=dram_role,
                            lane_id=lane,
                            scene_idx=global_scene_idx,
                            excluded_archetypes=excluded,
                        )
                    used_archetypes_short.add(category)
                    prev_archetype = category

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
                            **custom_params,
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

                # Niche HUD telemetry + resolved visual-bank asset (PR #2 value on cheap director)
                lane_l = lane.lower()
                hud_badge = sc_plan.get("hud_badge") or sc_script.get("hud_badge")
                hud_site = sc_plan.get("hud_site") or sc_script.get("hud_site")
                telemetry = sc_plan.get("telemetry_label") or sc_script.get("telemetry_label")
                from src.media.multi_act_renderer import resolve_hud_accent_color
                plan_accent = sc_plan.get("palette", {}).get("accent") if isinstance(sc_plan.get("palette"), dict) else None
                if "scp" in lane_l or "scp" in str(meta.get("story_type", "")).lower():
                    story_type = "scp"
                    niche_hud = {
                        "lane_id": lane,
                        "story_type": story_type,
                        "hud_badge": hud_badge or f"NIVEL {tension} // {'KETER' if tension >= 4 else 'EUCLID'}: CLASIFICADO",
                        "hud_site": hud_site or "SITIO-19 // SECTOR-04",
                        "telemetry_label": telemetry or f"CAM-{global_scene_idx:02d}: CONTENCIÓN ACTIVA",
                        "accent_color_hex": resolve_hud_accent_color(
                            str(plan_accent or ""), lane_id=lane, story_type=story_type
                        ),
                        "tension_level": tension,
                    }
                elif "aita" in lane_l or "reddit" in lane_l or "drama" in lane_l:
                    story_type = "reddit_aita"
                    niche_hud = {
                        "lane_id": lane,
                        "story_type": story_type,
                        "hud_badge": hud_badge or "r/AmItheAsshole",
                        "hud_site": hud_site or f"OP: u/{str(meta.get('story_id', 'anon'))[:14]}",
                        "telemetry_label": telemetry or f"▲ {12 + global_scene_idx * 2}.4k upvotes • {global_scene_idx * 340} comments",
                        "accent_color_hex": resolve_hud_accent_color(
                            str(plan_accent or ""), lane_id=lane, story_type=story_type
                        ),
                        "tension_level": tension,
                    }
                else:
                    story_type = "horror"
                    niche_hud = {
                        "lane_id": lane,
                        "story_type": story_type,
                        "hud_badge": hud_badge or "ABYSSAL SONAR // REC",
                        "hud_site": hud_site or f"PROFUNDIDAD: {1200 + global_scene_idx * 450}M",
                        "telemetry_label": telemetry or "ECO NO IDENTIFICADO",
                        "accent_color_hex": resolve_hud_accent_color(
                            str(plan_accent or ""), lane_id=lane, story_type=story_type
                        ),
                        "tension_level": tension,
                    }

                from src.media.thumbnails.asset_resolver import ThematicAssetResolver
                arch = category if is_procedural else env_name
                resolved_asset = ThematicAssetResolver.resolve_scene_asset_path(
                    channel_id=lane,
                    archetype=str(arch),
                    scene_idx=global_scene_idx,
                    is_vertical=(res[1] > res[0]),
                )
                scene_entry["niche_hud"] = niche_hud
                scene_entry["camera_motion"] = {
                    "type": motion_type,
                    "pan_direction": pan_dir,
                    "start_zoom": 1.0,
                    "end_zoom": round(1.05 + 0.03 * tension, 3),
                }
                scene_entry["image_path"] = str(resolved_asset)
                scene_entry["asset_path"] = str(resolved_asset)

                scenes_data.append(scene_entry)
                current_time += sub_dur
                global_scene_idx += 1

        total_duration = round(target_duration if target_duration and target_duration > 0 else current_time, 2)

        # Safe area boundaries
        safe_area = {
            "margin_top": 60 if res[0] > res[1] else 120,
            "margin_bottom": 124 if res[0] > res[1] else 480,
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
                "music_volume": float(music_volume if music_volume is not None else 0.04),
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
