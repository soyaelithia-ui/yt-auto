"""
src/agents/scene_planner_compositor.py - Agent 3: Scene Planner / Compositor.

Merges the narrative script (Agent 1) and visual plan (Agent 2) with audio master tracks,
decides engine selection (Hybrid Cinematic AI vs Pre-rendered Loop / FFmpeg),
configures camera motion, transitions, sidechain ducking, and generates the canonical
scene_manifest.json. Validates output with schemas/scene_manifest.schema.json.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import jsonschema

from src.log import get_logger
from src.media.visual_coherence import (
    ordered_script_scene_ids,
    plan_scenes_by_id,
    timing_scales_to_audio,
    visual_plan_palette,
)

logger = get_logger("scene_planner_compositor")

SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "schemas" / "scene_manifest.schema.json"

HEX_COLOR_PATTERN = re.compile(r"^#([0-9a-fA-F]{6})$")


def validate_hex_color(val: Any, default: str = "#00FF88") -> str:
    """Validate that val matches standard hex format (#RRGGBB). If invalid or null, return default."""
    if val and isinstance(val, str):
        val_s = val.strip()
        if val_s.startswith("0x") and len(val_s) == 8:
            val_s = "#" + val_s[2:]
        m = HEX_COLOR_PATTERN.match(val_s)
        if m:
            return f"#{m.group(1).upper()}"
    return default


class SceneManifestCompiler:
    """Deterministic compiler: Synthesizes SceneManifestV2 from Script, Visual Plan, and Audio."""

    def __init__(self, schema_file: Optional[Path] = None) -> None:
        self.schema_path = schema_file or SCHEMA_PATH
        self._schema: Optional[Dict[str, Any]] = None
        if self.schema_path.is_file():
            with open(self.schema_path, "r", encoding="utf-8") as f:
                self._schema = json.load(f)

    @staticmethod
    def _extract_hud_layout(
        channel_name: str,
        lane_id: str,
        meta: Dict[str, Any],
        visual_plan: Dict[str, Any],
        ch_cfg: Optional[Any] = None,
        ln_cfg: Optional[Any] = None,
        explicit_hud_layout: Optional[str] = None,
    ) -> str:
        hud_layout_candidate = (
            explicit_hud_layout
            or meta.get("hud_layout")
            or meta.get("hud_style")
            or visual_plan.get("hud_layout")
            or visual_plan.get("hud_style")
        )
        if not hud_layout_candidate and ln_cfg:
            if isinstance(ln_cfg, dict):
                hud_layout_candidate = ln_cfg.get("hud_layout") or ln_cfg.get("hud_style")
            else:
                hud_layout_candidate = getattr(ln_cfg, "hud_layout", None) or getattr(ln_cfg, "hud_style", None)

        if not hud_layout_candidate and ch_cfg:
            if isinstance(ch_cfg, dict):
                hud_layout_candidate = ch_cfg.get("hud_layout") or ch_cfg.get("hud_style")
            else:
                hud_layout_candidate = getattr(ch_cfg, "hud_layout", None) or getattr(ch_cfg, "hud_style", None)

        lane_l = (lane_id or "").lower()
        story_l = str(meta.get("story_type") or "").lower()
        ch_l = (channel_name or "").lower()

        _allowed = frozenset({"top_bar", "card", "bottom_bar"})
        cand = str(hud_layout_candidate or "").strip().lower()
        if (
            cand in ("none", "off", "disabled", "false")
            or meta.get("hud_enabled") is False
            or visual_plan.get("hud_enabled") is False
        ):
            return "none"
        if cand in _allowed:
            return cand
        if cand in ("scp", "classified", "terminal") or "scp" in lane_l or "scp" in story_l:
            return "top_bar"
        if (
            cand in ("reddit_aita", "reddit", "aita", "drama")
            or any(k in lane_l for k in ("aita", "reddit", "drama"))
            or any(k in story_l for k in ("aita", "reddit"))
        ):
            return "card"
        if (
            cand in ("scifi", "cyberpunk", "space")
            or any(k in lane_l for k in ("scifi", "space"))
            or "scifi" in ch_l
        ):
            return "top_bar"
        return "bottom_bar"

    @staticmethod
    def _extract_accent_color(
        channel_name: str,
        lane_id: str,
        meta: Dict[str, Any],
        visual_plan: Dict[str, Any],
        ch_cfg: Optional[Any] = None,
        ln_cfg: Optional[Any] = None,
        explicit_accent: Optional[str] = None,
    ) -> str:
        raw_accent = (
            explicit_accent
            or meta.get("accent_color")
            or meta.get("accent_color_hex")
            or meta.get("palette", {}).get("accent")
            or visual_plan.get("accent_color")
            or visual_plan.get("palette", {}).get("accent")
        )
        if not raw_accent and ln_cfg:
            if isinstance(ln_cfg, dict):
                raw_accent = ln_cfg.get("accent_color") or ln_cfg.get("palette", {}).get("accent")
            else:
                raw_accent = getattr(ln_cfg, "accent_color", None)
                if not raw_accent and hasattr(ln_cfg, "palette"):
                    pal = getattr(ln_cfg, "palette")
                    raw_accent = getattr(pal, "accent", None) if pal else None

        if not raw_accent and ch_cfg:
            if isinstance(ch_cfg, dict):
                raw_accent = (
                    ch_cfg.get("accent_color")
                    or ch_cfg.get("accent_color_hex")
                    or ch_cfg.get("visual", {}).get("palette", {}).get("accent")
                    or ch_cfg.get("palette", {}).get("accent")
                    or ch_cfg.get("accent")
                )
            else:
                vis = getattr(ch_cfg, "visual", None)
                pal = getattr(vis, "palette", None) if vis else getattr(ch_cfg, "palette", None)
                raw_accent = getattr(pal, "accent", None) if pal else getattr(ch_cfg, "accent_color", None)

        if not raw_accent:
            try:
                from src.core.channel_profile import ChannelProfileRegistry
                cid = ChannelProfileRegistry.normalize_channel_id(channel_name or lane_id)
                profile = ChannelProfileRegistry.get_channel(cid)
                if profile and profile.visual and profile.visual.palette:
                    raw_accent = profile.visual.palette.accent
            except Exception:
                pass

        lane_l = (lane_id or "").lower()
        story_l = str(meta.get("story_type") or "").lower()
        ch_l = (channel_name or "").lower()

        if "scp" in lane_l or "scp" in story_l:
            safe_accent_default = "#00FF66"
        elif any(k in lane_l for k in ("aita", "reddit", "drama")) or "aita" in story_l:
            safe_accent_default = "#FF4500"
        elif any(k in lane_l for k in ("scifi", "space")) or "scifi" in ch_l:
            safe_accent_default = "#00F0FF"
        else:
            safe_accent_default = "#00E5FF"

        return validate_hex_color(
            raw_accent if raw_accent is not None else safe_accent_default,
            default="#00FF88",
        )

    @staticmethod
    def _extract_primary_color(
        channel_name: str,
        lane_id: str,
        meta: Dict[str, Any],
        visual_plan: Dict[str, Any],
        ch_cfg: Optional[Any] = None,
    ) -> str:
        raw_primary = (
            meta.get("primary_color")
            or meta.get("primary_color_hex")
            or meta.get("palette", {}).get("primary")
            or visual_plan.get("primary_color")
            or visual_plan.get("palette", {}).get("primary")
        )
        if not raw_primary and ch_cfg:
            if isinstance(ch_cfg, dict):
                raw_primary = (
                    ch_cfg.get("primary_color")
                    or ch_cfg.get("visual", {}).get("palette", {}).get("primary")
                    or ch_cfg.get("palette", {}).get("primary")
                )
            else:
                vis = getattr(ch_cfg, "visual", None)
                pal = getattr(vis, "palette", None) if vis else getattr(ch_cfg, "palette", None)
                raw_primary = getattr(pal, "primary", None) if pal else None

        if not raw_primary:
            try:
                from src.core.channel_profile import ChannelProfileRegistry
                cid = ChannelProfileRegistry.normalize_channel_id(channel_name or lane_id)
                profile = ChannelProfileRegistry.get_channel(cid)
                if profile and profile.visual and profile.visual.palette:
                    raw_primary = profile.visual.palette.primary
            except Exception:
                pass

        return validate_hex_color(raw_primary, default="#030A14")

    @staticmethod
    def _extract_channel_palette_and_hud(
        channel_name: str,
        lane_id: str,
        meta: Dict[str, Any],
        visual_plan: Dict[str, Any],
        channel_config: Optional[Any] = None,
        lane_config: Optional[Any] = None,
        explicit_hud_layout: Optional[str] = None,
        explicit_accent: Optional[str] = None,
    ) -> Tuple[str, str, str]:
        """Extracts and validates suggested (hud_layout, accent_color_hex, primary_color_hex)."""
        ch_cfg = channel_config or meta.get("channel_config") or visual_plan.get("channel_config")
        ln_cfg = lane_config or meta.get("lane_config") or visual_plan.get("lane_config")

        resolved_layout = ScenePlannerCompositorAgent._extract_hud_layout(
            channel_name, lane_id, meta, visual_plan, ch_cfg, ln_cfg, explicit_hud_layout
        )
        resolved_accent = ScenePlannerCompositorAgent._extract_accent_color(
            channel_name, lane_id, meta, visual_plan, ch_cfg, ln_cfg, explicit_accent
        )
        resolved_primary = ScenePlannerCompositorAgent._extract_primary_color(
            channel_name, lane_id, meta, visual_plan, ch_cfg
        )
        return resolved_layout, resolved_accent, resolved_primary

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
                "drama",
                "drama",
                {},
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
                "classified_terminal",
                {},
            )

        # 2. Synaptic / Consciousness / Neural / Mind / Brain / Telepathy / Memory
        synaptic_keywords = {
            "mente", "cerebro", "neuronal", "sinapsis", "conciencia", "telepatia", "telepatía",
            "recuerdo", "memoria", "psiquico", "psíquico", "red", "matriz", "psicologico", "psicológico",
            "brain", "mind", "neural", "synapse", "synaptic", "consciousness", "cyber", "digital", "data", "matrix", "psycho", "psychological", "pneuma"
        }
        if "dark_ambient" not in excluded and (
            words.intersection(synaptic_keywords)
            or any(k in text for k in ("mente", "cerebro", "neural", "conciencia", "sinap", "mind", "psychological"))
        ):
            return (
                "dark_ambient",
                "dark_ambient",
                {},
            )

        # 3. Cosmic Singularity / Black Hole / Vortex / Relativistic Abyss / Space / Void
        cosmic_keywords = {
            "singularidad", "agujero negro", "vortice", "vórtice", "espacio", "cosmico", "cósmico",
            "gravedad", "lente", "galaxia", "universo", "horizonte", "sucesos", "vacio", "vacío",
            "singularity", "void", "black_hole", "rift", "portal", "abyss", "cosmic", "space", "vortex", "dimension", "event horizon"
        }
        if "cosmic_horror" not in excluded and (
            words.intersection(cosmic_keywords)
            or any(k in text for k in ("singularidad", "vortice", "vórtice", "espacio", "agujero negro", "singularity", "black hole", "rift", "cosmic", "event horizon"))
        ):
            return (
                "cosmic_horror",
                "cosmic_horror",
                {},
            )

        # 4. Anomaly Silhouette / Monster / Beast / Breach / Creature / Colossus / Titan
        anomaly_keywords = {
            "criatura", "monstruo", "titan", "coloso", "bestia", "anomalia", "anomalía",
            "demonio", "ojos", "garra", "fauce", "devorar", "emerger", "despertar",
            "monster", "monsters", "creature", "creatures", "beast", "breach", "rampage",
            "threat", "chaos", "climax", "confrontation", "colossus", "titan", "cataclysmic"
        }
        if "horror" not in excluded and (
            words.intersection(anomaly_keywords)
            or any(k in text for k in ("criatura", "monstruo", "coloso", "anomal", "monster", "beast", "devor", "rampage", "cataclysm"))
            or (tension >= 4 and dramatic_role in ("climax_confrontation", "climax_manifestation"))
        ):
            return (
                "horror",
                "horror",
                {},
            )

        # 5. Atmospheric Landscape / Wasteland / Steppe / Monoliths / Lighthouse / Coast / Ocean
        landscape_keywords = {
            "paramo", "páramo", "estepa", "ceniza", "cenizas", "monolito", "monolitos", "desierto",
            "llanura", "montana", "montaña", "ruinas", "caminante", "faro", "costa", "mar", "oceano",
            "océano", "fosa", "playa", "marino", "tormenta", "olas", "ola", "isla", "niebla",
            "wasteland", "steppe", "monolith", "desert", "ruins", "ash", "landscape", "lighthouse", "ocean", "sea", "coast"
        }
        if "dark_forest" not in excluded and (
            words.intersection(landscape_keywords)
            or any(k in text for k in ("paramo", "páramo", "monolito", "faro", "costa", "ceniza", "estepa", "mar ", "oceano", "océano", "wasteland", "desert", "monolith"))
        ):
            return (
                "dark_forest",
                "dark_forest",
                {},
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
                "tactical_chamber",
                {},
            )

        # 7. Dynamic Fallback: Choose the next available distinct archetype
        all_archetypes = [
            ("dark_forest", "dark_forest", {}),
            ("classified_terminal", "classified_terminal", {}),
            ("tactical_chamber", "tactical_chamber", {}),
            ("horror", "horror", {}),
            ("dark_ambient", "dark_ambient", {}),
            ("cosmic_horror", "cosmic_horror", {}),
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
        *,
        channel_config: Optional[Any] = None,
        lane_config: Optional[Any] = None,
        hud_layout: Optional[str] = None,
        accent_color: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Builds a canonical scene_manifest.json payload.
        """
        meta = script.get("metadata", {})
        lane = lane_id or meta.get("channel_lane", "moku-horror-long")
        target_fmt = meta.get("target_format", "longform")

        resolved_layout, resolved_accent, resolved_primary = self._extract_channel_palette_and_hud(
            channel_name=channel_name,
            lane_id=lane,
            meta=meta,
            visual_plan=visual_plan,
            channel_config=channel_config or kwargs.get("channel_config"),
            lane_config=lane_config or kwargs.get("lane_config"),
            explicit_hud_layout=hud_layout or kwargs.get("hud_layout"),
            explicit_accent=accent_color or kwargs.get("accent_color"),
        )

        # Resolve resolution
        if resolution:
            res = resolution
        elif target_fmt == "short" or "short" in lane.lower():
            res = [1080, 1920]
        else:
            res = [1920, 1080]

        # Flatten script scenes in act order (SSOT inclusion/order — do not reshuffle)
        _ = ordered_script_scene_ids(script)
        script_scenes: List[Dict[str, Any]] = []
        for act in script.get("acts", []):
            act_role = act.get("dramatic_role", "")
            for sc in act.get("scenes", []):
                if not sc.get("dramatic_role") and act_role:
                    sc["dramatic_role"] = act_role
                script_scenes.append(sc)

        plan_scenes_map: Dict[str, Dict[str, Any]] = plan_scenes_by_id(visual_plan)
        # Prefer art_director top-level palette when channel extract is thin
        _vp_pal = visual_plan_palette(visual_plan)
        if _vp_pal.get("accent") and (not resolved_accent or resolved_accent == "#00FF88"):
            resolved_accent = _vp_pal["accent"]
        if _vp_pal.get("primary") and (not resolved_primary or resolved_primary in ("#041421", "")):
            resolved_primary = _vp_pal["primary"]

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

        raw_durations = [float(sc.get("estimated_duration_sec", 60.0)) for sc in script_scenes]
        scaled_durations = timing_scales_to_audio(raw_durations, target_duration)

        # Build SceneConfig objects with dynamic cinematic pacing (8-15s per cut for longform)
        current_time = 0.0
        scenes_data: List[Dict[str, Any]] = []
        is_longform = (target_duration and target_duration > 180.0) or target_fmt == "longform" or "long" in lane.lower()
        do_subdivide = subdivide_shots or meta.get("subdivide_shots", False) or meta.get("dynamic_pacing", False)

        global_scene_idx = 1

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
                # Every scene is a local catalog loop.  There is deliberately no
                # camera-motion, procedural, hybrid, or generated-frame branch.
                engine_type = "catalog_loop"
                dram_role = sc_script.get("dramatic_role", "")
                narration_snippet = sc_script.get("narration_text", "") or sc_script.get("scene_text", "")

                # For Shorts: exclude all previously used archetypes to guarantee 100% distinct scenes.
                # For Longform: exclude the immediate previous archetype to prevent static back-to-back loops.
                excluded = set(used_archetypes_short) if not is_longform else ({prev_archetype} if prev_archetype else set())

                upstream_archetype = sc_plan.get("archetype_id")
                if upstream_archetype:
                    category = upstream_archetype
                else:
                    category, _template_name, _custom_params = self._resolve_scene_archetype(
                        env_name=f"{env_name} {narration_snippet}",
                        tension=tension,
                        dramatic_role=dram_role,
                        lane_id=lane,
                        scene_idx=global_scene_idx,
                        excluded_archetypes=excluded,
                    )
                used_archetypes_short.add(category)
                prev_archetype = category

                scene_entry: Dict[str, Any] = {
                    "scene_index": global_scene_idx,
                    "scene_id": sub_sc_id,
                    "environment_name": category,
                    "start_sec": round(current_time, 2),
                    "duration_sec": round(sub_dur, 2),
                    "tension_level": tension,
                    "engine_type": engine_type,
                    "transition_out": {
                        "type": "crossfade" if (idx < len(script_scenes) - 1 or sub_i < len(sub_durations) - 1) else "fade_to_black",
                        "duration_sec": 0.6 if is_longform else 0.8,
                    },
                }

                # The renderer receives only a local visual asset; no HUD or text
                # payload is written into the manifest.
                from src.media.thumbnails.asset_resolver import ThematicAssetResolver
                arch = category
                resolved_asset = ThematicAssetResolver.resolve_scene_asset_path(
                    channel_id=lane,
                    archetype=str(arch),
                    scene_idx=global_scene_idx,
                    is_vertical=(res[1] > res[0]),
                )
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


# Backward-compatibility alias
ScenePlannerCompositorAgent = SceneManifestCompiler
