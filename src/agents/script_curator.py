"""
src/agents/cinematic_script_curator.py - Agent 1: Cinematic Script Curator.

Transforms raw input stories, community submissions, or canonical lore into structured
4-Act dramatic scripts with progressive tension curve grading (1-5), scene-by-scene timing
(45-90s pacing for longform, 8-15s for shorts), lane-calibrated environmental moods,
and sanitized neutral Spanish narration text.
Validates output against schemas/script_curator.schema.json.
"""
from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import jsonschema

from src.log import get_logger

logger = get_logger("cinematic_script_curator")

SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "schemas" / "script_curator.schema.json"

# Valid schema Draft-07 audio pacing cues
VALID_AUDIO_PACING_CUES = {
    "calm_slow",
    "steady_dramatic",
    "tense_accelerando",
    "intense_urgent",
    "whispered_grave",
}


# ============================================================================
# LANE PROFILES & THEMATIC NARRATIVE FORMULAS
# ============================================================================

LANE_CURATION_CONFIGS = {
    "moku-scp-shorts": {
        "channel": "moku",
        "target_format": "short",
        "default_wpm": 165.0,
        "target_scene_dur": 11.0,
        "min_scene_dur": 8.0,
        "max_scene_dur": 15.0,
        "min_total_dur": 60.0,
        "max_total_dur": 180.0,
        "min_scenes": 4,
        "max_scenes": 12,
        "acts": [
            {
                "act_number": 1,
                "act_title": "Acto I: Designación y Procedimientos de Contención",
                "dramatic_role": "exposition_inception",
                "tension_profile": [1, 2],
                "moods": [
                    "Búnker de Contención Subterráneo con Iluminación Fluorescente",
                    "Cámara de Aislamiento de Hormigón Blindado y Titanio",
                    "Laboratorio de Investigación Nivel 4 de la Fundación SCP",
                ],
            },
            {
                "act_number": 2,
                "act_title": "Acto II: Registro de Incidentes y Pruebas no Autorizadas",
                "dramatic_role": "rising_action_dread",
                "tension_profile": [3, 4],
                "moods": [
                    "Sala de Observación con Vidrio Reforzado y Sensores Térmicos",
                    "Pasillo de Acceso Restringido con Luces Intermitentes",
                    "Cámara de Pruebas con Sujetos Clase-D y Monitores Anómalos",
                ],
            },
            {
                "act_number": 3,
                "act_title": "Acto III: Brecha Crítica y Manifestación Hostil",
                "dramatic_role": "climax_confrontation",
                "tension_profile": [5],
                "moods": [
                    "Zona Cero de Ruptura de Contención con Sirenas y Luces Rojas",
                    "Compuertas Hidráulicas Destruidas y Estática en Cámaras",
                    "Manifestación Hostil de la Anomalía en Penumbra Total",
                ],
            },
            {
                "act_number": 4,
                "act_title": "Acto IV: Protocolo de Emergencia y Archivo Clasificado",
                "dramatic_role": "aftermath_revelation",
                "tension_profile": [3, 2],
                "moods": [
                    "Terminal de Archivo Clasificado Nivel 5 bajo Protocolo de Bloqueo",
                    "Perímetro de Cuarentena Sellado con Hormigón Armado",
                    "Sala de Monitoreo en Silencio de Emergencia tras la Brecha",
                ],
            },
        ],
    },
    "moku-horror-long": {
        "channel": "moku",
        "target_format": "longform",
        "default_wpm": 140.0,
        "target_scene_dur": 90.0,
        "min_scene_dur": 45.0,
        "max_scene_dur": 150.0,
        "min_total_dur": 600.0,
        "max_total_dur": 1800.0,
        "min_scenes": 5,
        "max_scenes": 8,
        "acts": [
            {
                "act_number": 1,
                "act_title": "Acto I: Incepción Sensorial y Aislamiento",
                "dramatic_role": "exposition_inception",
                "tension_profile": [1, 2],
                "moods": [
                    "Estación de monitoreo aislada rodeada de niebla densa y pinos silenciosos",
                    "Torre de control en penumbra con tenue resplandor verde de cuadrantes analógicos",
                    "Perímetro boscoso exterior con niebla baja y descenso brusco de temperatura",
                ],
            },
            {
                "act_number": 2,
                "act_title": "Acto II: Tensión Creciente y Advertencias Ignoradas",
                "dramatic_role": "rising_action_dread",
                "tension_profile": [2, 3, 4],
                "moods": [
                    "Consola de radio con luces fluorescentes parpadeando bajo pulso electromagnético",
                    "Sala de archivos con archivadores de acero y libretas de guardias desaparecidos",
                    "Corredor exterior helado con escarcha sobre barandillas metálicas y niebla baja",
                ],
            },
            {
                "act_number": 3,
                "act_title": "Acto III: Confrontación Inexplicable y Ruptura",
                "dramatic_role": "climax_confrontation",
                "tension_profile": [4, 5, 5],
                "moods": [
                    "Cúpula de observación quebrada con ventanal astillado y fulgor de bengala roja",
                    "Puerta blindada cediendo con sombra tridimensional proyectada bajo el umbral",
                    "Manifestación anómala violenta en la penumbra del bosque",
                ],
            },
            {
                "act_number": 4,
                "act_title": "Acto IV: Secuela Psicológica y Trauma Permanente",
                "dramatic_role": "aftermath_revelation",
                "tension_profile": [3, 2],
                "moods": [
                    "Amanecer brumoso desolado sobre carretera forestal con vehículos oficiales",
                    "Apartamento urbano en penumbra nocturna con receptor de radio emitiendo estática",
                    "Expediente sellado bajo reserva oficial y custodia permanente",
                ],
            },
        ],
    },
    "aelithia-aita-long": {
        "channel": "aelithia",
        "target_format": "longform",
        "default_wpm": 145.0,
        "target_scene_dur": 90.0,
        "min_scene_dur": 45.0,
        "max_scene_dur": 150.0,
        "min_total_dur": 600.0,
        "max_total_dur": 1800.0,
        "min_scenes": 5,
        "max_scenes": 8,
        "acts": [
            {
                "act_number": 1,
                "act_title": "Acto I: El Dilema Moral y Contexto Familiar",
                "dramatic_role": "exposition_inception",
                "tension_profile": [1, 2],
                "moods": [
                    "Salas de estar cálidas con iluminación hogareña",
                    "Cena familiar cotidiana con ambiente distendido",
                    "Cocina doméstica al atardecer con luz suave",
                ],
            },
            {
                "act_number": 2,
                "act_title": "Acto II: El Detonante y Escalada del Conflicto",
                "dramatic_role": "rising_action_dread",
                "tension_profile": [2, 3, 4],
                "moods": [
                    "Discusión tensa en sala familiar bajo luz tenue",
                    "Mesa de comedor hostil con parientes enfrentados",
                    "Oficina legal con carpetas notariales y contratos",
                ],
            },
            {
                "act_number": 3,
                "act_title": "Acto III: Punto de Ruptura y Confrontación Directa",
                "dramatic_role": "climax_confrontation",
                "tension_profile": [4, 5],
                "moods": [
                    "Tribunal familiar explosivo con reproches a gritos",
                    "Audiencia judicial conciliatoria con tensión máxima",
                    "Ruptura definitiva en medio de una celebración interrumpida",
                ],
            },
            {
                "act_number": 4,
                "act_title": "Acto IV: Reflexión Comunitaria y Actualización Posterior",
                "dramatic_role": "aftermath_revelation",
                "tension_profile": [2, 1],
                "moods": [
                    "Cafetería reflexiva con luz natural",
                    "Amanecer de paz mental e independencia",
                    "Nuevo hogar con tranquilidad",
                ],
            },
        ],
    },
    "aelithia-drama-shorts": {
        "channel": "aelithia",
        "target_format": "short",
        "default_wpm": 165.0,
        "target_scene_dur": 11.0,
        "min_scene_dur": 8.0,
        "max_scene_dur": 15.0,
        "min_total_dur": 60.0,
        "max_total_dur": 180.0,
        "min_scenes": 4,
        "max_scenes": 12,
        "acts": [
            {
                "act_number": 1,
                "act_title": "Acto I: Planteamiento del Conflicto Familiar",
                "dramatic_role": "exposition_inception",
                "tension_profile": [1, 2],
                "moods": [
                    "Cafetería con luz natural y rostros tensos",
                    "Sala de estar moderna al anochecer con atmósfera cargada",
                    "Cocina doméstica con miradas evasivas",
                ],
            },
            {
                "act_number": 2,
                "act_title": "Acto II: La Exigencia Injusta y el Ultimátum",
                "dramatic_role": "rising_action_dread",
                "tension_profile": [3, 4],
                "moods": [
                    "Mesa de comedor con reproches directos",
                    "Pasillo estrecho con tensión creciente",
                    "Llamada telefónica acalorada en automóvil",
                ],
            },
            {
                "act_number": 3,
                "act_title": "Acto III: La Decisión Firme y Ruptura",
                "dramatic_role": "climax_confrontation",
                "tension_profile": [5],
                "moods": [
                    "Confrontación decisiva frente a la familia reunida",
                    "Portazo definitivo y silencio absoluto",
                    "Mirada resuelta ante el espejo",
                ],
            },
            {
                "act_number": 4,
                "act_title": "Acto IV: Reflexión Ética y Veredicto Comunitario",
                "dramatic_role": "aftermath_revelation",
                "tension_profile": [3, 2],
                "moods": [
                    "Apartamento en calma con luz matutina",
                    "Ventanal con lluvia suave y paz recobrada",
                    "Paseo solitario con serenidad interior",
                ],
            },
        ],
    },
    "scifi-singularity-shorts": {
        "channel": "scifi",
        "target_format": "short",
        "default_wpm": 160.0,
        "target_scene_dur": 11.0,
        "min_scene_dur": 8.0,
        "max_scene_dur": 15.0,
        "min_total_dur": 60.0,
        "max_total_dur": 180.0,
        "min_scenes": 4,
        "max_scenes": 12,
        "acts": [
            {
                "act_number": 1,
                "act_title": "Acto I: Detección de la Anomalía Cósmica",
                "dramatic_role": "exposition_inception",
                "tension_profile": [1, 2],
                "moods": [
                    "Puente de mando estelar con monitores holográficos y telemetría",
                    "Observatorio orbital sobre el horizonte de un planeta helado",
                    "Antenas parabólicas de radioastronomía bajo cielo nocturno",
                ],
            },
            {
                "act_number": 2,
                "act_title": "Acto II: Colapso de la Física Teórica",
                "dramatic_role": "rising_action_dread",
                "tension_profile": [3, 4],
                "moods": [
                    "Cámara de contención magnética con fluctuaciones del vacío",
                    "Vórtice gravitacional deformando el espacio visible",
                    "Consola de navegación alertando distorsión temporal extrema",
                ],
            },
            {
                "act_number": 3,
                "act_title": "Acto III: Cruce del Horizonte de Sucesos",
                "dramatic_role": "climax_confrontation",
                "tension_profile": [5],
                "moods": [
                    "Horizonte de sucesos brillando con radiación de Hawking",
                    "Disco de acreción gigantesco absorbiendo materia a velocidad lumínica",
                    "Singularidad central con colapso dimensional",
                ],
            },
            {
                "act_number": 4,
                "act_title": "Acto IV: Registro Estelar y Transmisión Final",
                "dramatic_role": "aftermath_revelation",
                "tension_profile": [3, 2],
                "moods": [
                    "Sonda espacial emitiendo último paquete de datos criptográficos",
                    "Vasto espacio interestelar con estrellas titilando en la distancia",
                    "Terminal de archivo de la misión con estatus confirmado",
                ],
            },
        ],
    },
    "scifi-singularity-long": {
        "channel": "scifi",
        "target_format": "longform",
        "default_wpm": 140.0,
        "target_scene_dur": 90.0,
        "min_scene_dur": 45.0,
        "max_scene_dur": 150.0,
        "min_total_dur": 600.0,
        "max_total_dur": 1800.0,
        "min_scenes": 5,
        "max_scenes": 8,
        "acts": [
            {
                "act_number": 1,
                "act_title": "Acto I: Incepción Teórica y Enigma Cósmico",
                "dramatic_role": "exposition_inception",
                "tension_profile": [1, 2],
                "moods": [
                    "Complejo de radiotelescopios en el desierto bajo vía láctea brillante",
                    "Sala de control de misión espacial con pantallas orbitales en tiempo real",
                    "Laboratorio de astrofísica con simulaciones computacionales hiperdensas",
                ],
            },
            {
                "act_number": 2,
                "act_title": "Acto II: La Paradoja Gravitacional y Alerta Instrumental",
                "dramatic_role": "rising_action_dread",
                "tension_profile": [2, 3, 4],
                "moods": [
                    "Sonda interestelar cruzando nebulosa oscura con estática de telemetría",
                    "Cámara de interferometría cuántica registrando ondas gravitatorias",
                    "Búnker de procesamiento de datos con alarmas térmicas silenciosas",
                ],
            },
            {
                "act_number": 3,
                "act_title": "Acto III: Punto Crítico y Frontera Relativista",
                "dramatic_role": "climax_confrontation",
                "tension_profile": [4, 5, 5],
                "moods": [
                    "Frontera del agujero negro supermasivo con lente gravitacional extremo",
                    "Chorros relativistas de plasma proyectándose a través de años luz",
                    "Colapso de espacio-tiempo en simulación holográfica inmersiva",
                ],
            },
            {
                "act_number": 4,
                "act_title": "Acto IV: Síntesis Astrofísica y Perspectiva Cósmica",
                "dramatic_role": "aftermath_revelation",
                "tension_profile": [3, 2],
                "moods": [
                    "Telescopio espacial flotando en el vacío con la Tierra en el fondo",
                    "Archivo estelar archivando expediente de la singularidad",
                    "Amanecer sobre observatorio de alta montaña",
                ],
            },
        ],
    },
}


class CinematicScriptCuratorAgent:
    """Agent 1: Generates structured, schema-compliant 4-Act dramatic scripts."""

    def __init__(self, schema_file: Optional[Path] = None) -> None:
        self.schema_path = schema_file or SCHEMA_PATH
        self._schema: Optional[Dict[str, Any]] = None
        if self.schema_path.is_file():
            with open(self.schema_path, "r", encoding="utf-8") as f:
                self._schema = json.load(f)

    def curate(
        self,
        raw_text: str,
        title: str,
        channel_lane: str = "moku-horror-long",
        target_format: str = "longform",
        words_per_minute: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Curates raw text into structured 4-Act screenplay with progressive tension curve.
        Enforces lane-specific timing, scene bounds, vocal cues, and Draft-07 schema validation.
        """
        # Resolve lane configuration
        lane_key, lane_cfg = self._resolve_lane_config(channel_lane, target_format)
        target_fmt = lane_cfg["target_format"]
        wpm = float(words_per_minute or lane_cfg["default_wpm"])

        # Sanitize raw text
        clean_text = self._sanitize_text(raw_text)

        # Fallback synthesis if input text is empty or minimal (<25 words)
        words = clean_text.split()
        if len(words) < 25:
            clean_text = self._generate_fallback_narrative(title, lane_key, clean_text)
            words = clean_text.split()

        total_words = max(1, len(words))
        raw_total_dur = (total_words / wpm) * 60.0

        # Enforce lane duration constraints
        min_total_dur = lane_cfg["min_total_dur"]
        max_total_dur = lane_cfg["max_total_dur"]
        min_scene_dur = lane_cfg["min_scene_dur"]
        max_scene_dur = lane_cfg["max_scene_dur"]
        target_scene_dur = lane_cfg["target_scene_dur"]

        # Sentence-aware slicing into scenes
        scene_texts = self._slice_into_scenes(
            clean_text=clean_text,
            target_scene_dur=target_scene_dur,
            min_scene_dur=min_scene_dur,
            max_scene_dur=max_scene_dur,
            wpm=wpm,
            min_scenes=lane_cfg["min_scenes"],
            max_scenes=lane_cfg["max_scenes"],
            target_format=target_fmt,
        )

        # Distribute scenes across 4 acts
        acts_specs = lane_cfg["acts"]
        scene_distribution = self._distribute_scenes_across_acts(len(scene_texts), len(acts_specs))

        acts_data: List[Dict[str, Any]] = []
        tension_curve: List[int] = []
        global_scene_idx = 1
        curr_scene_idx = 0

        for act_idx, act_spec in enumerate(acts_specs):
            act_num = act_spec["act_number"]
            act_title = act_spec["act_title"]
            dramatic_role = act_spec["dramatic_role"]
            tension_profile = act_spec["tension_profile"]
            mood_bank = act_spec["moods"]

            count_for_act = scene_distribution[act_idx]
            act_scenes: List[Dict[str, Any]] = []

            for sc_offset in range(count_for_act):
                if curr_scene_idx >= len(scene_texts):
                    break

                sc_text = scene_texts[curr_scene_idx]
                sc_words = len(sc_text.split())

                # Calculate duration clamped to strict bounds
                raw_dur = (sc_words / wpm) * 60.0
                sc_dur = round(max(min_scene_dur, min(max_scene_dur, raw_dur)), 2)

                # Progressive tension interpolation
                tension = self._interpolate_tension(tension_profile, sc_offset, count_for_act)
                tension_curve.append(tension)

                # Audio pacing cue calibrated to lane and tension
                pacing_cue = self._resolve_audio_pacing_cue(lane_key, act_num, tension, sc_offset, count_for_act)

                # Environmental mood derived semantically from narrative text
                mood = self._derive_semantic_environmental_mood(sc_text, mood_bank[sc_offset % len(mood_bank)], tension)

                scene_obj = {
                    "scene_id": f"scene_{global_scene_idx:03d}",
                    "scene_index": global_scene_idx,
                    "tension_level": tension,
                    "narration_text": sc_text,
                    "word_count": max(1, sc_words),
                    "estimated_duration_sec": sc_dur,
                    "environmental_mood": mood,
                    "audio_pacing_cue": pacing_cue,
                    "transition_reason": self._derive_transition_reason(act_num, dramatic_role, tension, sc_offset),
                }
                act_scenes.append(scene_obj)
                global_scene_idx += 1
                curr_scene_idx += 1

            if act_scenes:
                acts_data.append({
                    "act_number": act_num,
                    "act_title": act_title,
                    "dramatic_role": dramatic_role,
                    "scenes": act_scenes,
                })

        # Calculate final total duration from assembled scenes
        total_scene_duration = round(sum(s["estimated_duration_sec"] for a in acts_data for s in a["scenes"]), 2)
        final_total_duration = max(min_total_dur, min(max_total_dur, total_scene_duration))

        # Synthesize lane-specific hook summary
        hook_summary = self._synthesize_hook_summary(title, lane_key, clean_text)

        output_payload: Dict[str, Any] = {
            "version": "2.0",
            "metadata": {
                "title": title[:200] if title else "Crónica Narrativa",
                "channel_lane": channel_lane,
                "target_format": target_fmt,
                "total_word_count": max(1, sum(s["word_count"] for a in acts_data for s in a["scenes"])),
                "estimated_duration_sec": final_total_duration,
                "hook_summary": hook_summary,
                "tension_curve": tension_curve if tension_curve else [1, 2, 3, 4, 5, 2],
            },
            "acts": acts_data,
        }

        # Validate with Draft-07 schema
        if self._schema:
            jsonschema.validate(instance=output_payload, schema=self._schema)

        return output_payload

    # ========================================================================
    # INTERNAL HELPERS & SLICING ALGORITHMS
    # ========================================================================

    def _resolve_lane_config(self, channel_lane: str, target_format: str) -> Tuple[str, Dict[str, Any]]:
        """Resolves lane profile and configuration dictionary."""
        lane_str = str(channel_lane).strip()
        lane_lower = lane_str.lower()
        fmt_lower = str(target_format).strip().lower()

        # 1. Exact match check
        if lane_str in LANE_CURATION_CONFIGS:
            return lane_str, LANE_CURATION_CONFIGS[lane_str]
        if lane_lower in LANE_CURATION_CONFIGS:
            return lane_lower, LANE_CURATION_CONFIGS[lane_lower]

        # 2. SciFi matching
        if "scifi" in lane_lower or "singularity" in lane_lower or "singularidad" in lane_lower:
            if fmt_lower in ("short", "shorts", "vertical") or "short" in lane_lower:
                return "scifi-singularity-shorts", LANE_CURATION_CONFIGS["scifi-singularity-shorts"]
            return "scifi-singularity-long", LANE_CURATION_CONFIGS["scifi-singularity-long"]

        # 3. Aelithia / Drama matching
        if "aelithia" in lane_lower or "aita" in lane_lower or "drama" in lane_lower or "confession" in lane_lower:
            if fmt_lower in ("short", "shorts", "vertical") or "short" in lane_lower:
                return "aelithia-drama-shorts", LANE_CURATION_CONFIGS["aelithia-drama-shorts"]
            return "aelithia-aita-long", LANE_CURATION_CONFIGS["aelithia-aita-long"]

        # 4. Moku / SCP / Horror matching
        if "scp" in lane_lower:
            return "moku-scp-shorts", LANE_CURATION_CONFIGS["moku-scp-shorts"]
        if "horror" in lane_lower or "creepy" in lane_lower or "cosmic" in lane_lower:
            if fmt_lower in ("short", "shorts", "vertical") or "short" in lane_lower:
                return "moku-scp-shorts", LANE_CURATION_CONFIGS["moku-scp-shorts"]
            return "moku-horror-long", LANE_CURATION_CONFIGS["moku-horror-long"]

        # 5. Default fallback: longform horror or short based on target_format
        if fmt_lower in ("short", "shorts", "vertical"):
            return "moku-scp-shorts", LANE_CURATION_CONFIGS["moku-scp-shorts"]
        return "moku-horror-long", LANE_CURATION_CONFIGS["moku-horror-long"]

    @staticmethod
    def _derive_semantic_environmental_mood(text: str, fallback_mood: str, tension: int) -> str:
        """Derives a rich, contextual environmental mood from narration text keywords."""
        t_low = text.lower()
        if any(k in t_low for k in ("faro", "costa", "mar ", "marino", "oceano", "océano", "fosa", "abismo", "olas")):
            return "Faro costero aislado azotado por tormenta y anomalía en fosa oceánica"
        if any(k in t_low for k in ("paramo", "páramo", "estepa", "ceniza", "cenizas", "monolito", "monolitos")):
            return "Páramo desolado de cenizas grises y monolitos ciclópeos en el horizonte"
        if any(k in t_low for k in ("bunker", "búnker", "pasillo", "acero", "alarma", "cimiento", "laboratorio", "camara", "cámara")):
            return "Búnker táctico subterráneo con baliza de alarma estroboscópica y vibraciones"
        if any(k in t_low for k in ("criatura", "monstruo", "titan", "coloso", "demonio", "ojos", "fauce", "garra")):
            return "Manifestación colosal de entidad anómala emergiendo de niebla densa"
        if any(k in t_low for k in ("singularidad", "agujero negro", "vortice", "vórtice", "espacio", "cosmico", "cósmico", "gravedad")):
            return "Singularidad cósmica con distorsión gravitacional y disco de acreción"
        if any(k in t_low for k in ("mente", "cerebro", "conciencia", "sinapsis", "recuerdo", "memoria")):
            return "Matriz neuronal de conciencia bioluminiscente con impulsos sinápticos"
        if any(k in t_low for k in ("radar", "terminal", "clasificado", "pantalla", "expediente", "registro")):
            return "Consola CRT militar de vigilancia táctica con radar y telemetría"
        return fallback_mood

    @staticmethod
    def _derive_transition_reason(act_number: int, dramatic_role: str, tension: int, scene_offset: int) -> str:
        """Derives semantic transition motivation for scene changes."""
        reasons = {
            "exposition_inception": "Establecimiento del escenario inicial y presentación de anomalía contextual",
            "rising_action_dread": "Escalada de tensión dramática y desplazamiento hacia zona de peligro inminente",
            "climax_confrontation": "Punto de máxima confrontación y ruptura crítica del entorno",
            "aftermath_revelation": "Desenlace de la crisis y consecuencias permanentes en el entorno",
        }
        base_reason = reasons.get(dramatic_role, "Evolución narrativa y progresión de la atmósfera escénica")
        if tension >= 4:
            return f"{base_reason} (Ruptura crítica bajo tensión nivel {tension})"
        return f"{base_reason} (Transición de plano {scene_offset + 1})"

    def _slice_into_scenes(
        self,
        clean_text: str,
        target_scene_dur: float,
        min_scene_dur: float,
        max_scene_dur: float,
        wpm: float,
        min_scenes: int,
        max_scenes: int,
        target_format: str,
    ) -> List[str]:
        """
        Performs sentence-aware boundary slicing to produce balanced scene chunks.
        Guarantees minimum scene counts and respects min/max duration constraints.
        """
        sentences = self._split_into_sentences(clean_text)
        if not sentences:
            sentences = [clean_text] if clean_text.strip() else ["Relato sin contenido."]

        target_words_per_scene = max(10, int(round((target_scene_dur / 60.0) * wpm)))
        max_words_per_scene = max(15, int(round((max_scene_dur / 60.0) * wpm)))

        scene_buckets: List[List[str]] = []
        current_bucket: List[str] = []
        current_word_count = 0

        for sent in sentences:
            sent_words = len(sent.split())
            if current_bucket and (current_word_count + sent_words > max_words_per_scene or current_word_count >= target_words_per_scene):
                scene_buckets.append(current_bucket)
                current_bucket = [sent]
                current_word_count = sent_words
            else:
                current_bucket.append(sent)
                current_word_count += sent_words

        if current_bucket:
            scene_buckets.append(current_bucket)

        # Convert buckets to scene strings
        scenes = [" ".join(b).strip() for b in scene_buckets if b]

        # Enforce minimum scene count by splitting longer scenes on sentence boundaries
        while len(scenes) < min_scenes:
            longest_idx = max(range(len(scenes)), key=lambda i: len(scenes[i].split()))
            longest_text = scenes[longest_idx]
            sub_sents = self._split_into_sentences(longest_text)
            if len(sub_sents) > 1:
                mid = len(sub_sents) // 2
                scenes[longest_idx] = " ".join(sub_sents[:mid]).strip()
                scenes.insert(longest_idx + 1, " ".join(sub_sents[mid:]).strip())
            else:
                words = longest_text.split()
                if len(words) < 8:
                    break
                comma_idx = -1
                for w_i in range(len(words) // 3, 2 * len(words) // 3):
                    if words[w_i].endswith((",", ";", ":")):
                        comma_idx = w_i + 1
                        break
                split_at = comma_idx if comma_idx > 0 else len(words) // 2
                part1 = " ".join(words[:split_at]).strip()
                if not part1.endswith((".", "!", "?")):
                    part1 += "."
                part2 = " ".join(words[split_at:]).strip()
                scenes[longest_idx] = part1
                scenes.insert(longest_idx + 1, part2)

        # Enforce maximum scene count by merging shortest adjacent scenes if needed
        while len(scenes) > max_scenes:
            shortest_idx = min(range(len(scenes) - 1), key=lambda i: len(scenes[i].split()) + len(scenes[i + 1].split()))
            merged = f"{scenes[shortest_idx]} {scenes[shortest_idx + 1]}"
            scenes[shortest_idx] = merged
            scenes.pop(shortest_idx + 1)

        return scenes

    def _split_into_sentences(self, text: str) -> List[str]:
        """
        Splits text on sentence boundaries while protecting common abbreviations,
        acronyms, decimal numbers, and titles.
        """
        if not text:
            return []

        t = text

        # 1. Protect decimal dots (e.g. 3.5 -> 3__DOT__5)
        t = re.sub(r"(\d+)\.(\d+)", r"\1__DOT__\2", t)

        # 2. Protect titles and common abbreviations
        title_abbreviations = [
            r"\bDr\.",
            r"\bDra\.",
            r"\bSr\.",
            r"\bSra\.",
            r"\bSrta\.",
            r"\bProf\.",
            r"\bProfa\.",
            r"\bIng\.",
            r"\bLic\.",
            r"\bGral\.",
            r"\bCap\.",
            r"\bTen\.",
            r"\bnúm\.",
            r"\bnum\.",
            r"\bpág\.",
            r"\bpags?\.",
            r"\bvol\.",
            r"\bart\.",
            r"\bvs\.",
        ]
        for abbr_pat in title_abbreviations:
            def _replace_title(m: re.Match) -> str:
                return m.group(0).replace(".", "__DOT__")
            t = re.sub(abbr_pat, _replace_title, t, flags=re.IGNORECASE)

        # 3. Protect internal dot of a.m. / p.m. (a.m. -> a__DOT__m.)
        t = re.sub(r"(?i)\ba\.m\.", "a__DOT__m.", t)
        t = re.sub(r"(?i)\bp\.m\.", "p__DOT__m.", t)

        # 4. Protect etc. if followed by lowercase or comma
        t = re.sub(r"(?i)\betc\.(?=\s*[,;a-záéíóúñ])", "etc__DOT__", t)

        # Split on sentence terminals followed by space (or space before uppercase/punctuation) or newlines
        raw_sentences = re.split(r"(?<=[.!?…])\s+(?=[A-ZÁÉÍÓÚÑ¿¡\"«0-9])|(?<=[.!?…])\s+|\n+", t)
        cleaned_sentences: List[str] = []

        for s in raw_sentences:
            s_clean = s.strip()
            if s_clean:
                # Restore dots
                s_restored = s_clean.replace("__DOT__", ".")
                cleaned_sentences.append(s_restored)

        return cleaned_sentences if cleaned_sentences else [text]

    def _distribute_scenes_across_acts(self, total_scenes: int, num_acts: int = 4) -> List[int]:
        """Distributes scene counts across 4 acts ensuring at least 1 scene per act."""
        if total_scenes <= num_acts:
            return [1] * num_acts

        base = total_scenes // num_acts
        rem = total_scenes % num_acts
        counts = [base] * num_acts

        # Distribute remainder into rising action (Act 2) and climax (Act 3)
        for i in range(rem):
            counts[(i + 1) % num_acts] += 1

        return counts

    def _interpolate_tension(self, profile: List[int], offset: int, total: int) -> int:
        """Interpolates smooth progressive tension levels (1..5)."""
        if total <= 1:
            # If an act has only 1 scene, use its peak tension if it's a climax act (has 5), else median
            return max(1, min(5, max(profile) if 5 in profile else profile[len(profile) // 2]))
        if len(profile) == 1:
            return max(1, min(5, profile[0]))
        step = (len(profile) - 1) * (offset / (total - 1))
        idx = int(round(step))
        idx = max(0, min(len(profile) - 1, idx))
        return max(1, min(5, profile[idx]))

    def _resolve_audio_pacing_cue(
        self,
        lane_key: str,
        act_num: int,
        tension: int,
        offset: int,
        total_in_act: int,
    ) -> str:
        """Resolves valid Draft-07 audio pacing cue calibrated to lane dynamics."""
        if act_num == 4:
            # Epilogue / aftermath: whispered_grave for low tension / horror, or steady_dramatic
            if tension <= 2 or offset == total_in_act - 1:
                return "whispered_grave" if "horror" in lane_key or "scp" in lane_key else "calm_slow"
            return "steady_dramatic"

        if tension >= 5:
            return "intense_urgent"
        elif tension == 4:
            return "intense_urgent" if act_num == 3 else "tense_accelerando"
        elif tension == 3:
            return "tense_accelerando"
        elif tension == 2:
            return "steady_dramatic"
        else: # tension == 1
            return "calm_slow"

    def _synthesize_hook_summary(self, title: str, lane_key: str, clean_text: str) -> str:
        """Synthesizes high-retention lane-calibrated hook summary."""
        if "scp" in lane_key:
            # Look up canonical SCP lore if topic detected
            try:
                from src.core.scp_lore import lookup_scp
                scp_info = lookup_scp(title) or lookup_scp(clean_text[:100])
                if scp_info:
                    scp_id = scp_info.get("scp_id", "SCP")
                    obj_class = scp_info.get("object_class", "Euclid")
                    return f"Expediente clasificado de la Fundación SCP: Ítem #{scp_id} ({obj_class}) con protocolos de contención primaria y alerta de brecha."
            except Exception:
                pass
            return f"Expediente clasificado de la Fundación SCP sobre '{title[:60]}' con protocolos de contención y alerta de brecha crítica."

        elif "aita" in lane_key:
            first_sent = clean_text.split(".")[0] if "." in clean_text else clean_text[:80]
            if "¿" in first_sent or "malo" in first_sent.lower() or "mala" in first_sent.lower():
                return f"Dilema moral en primera persona: {first_sent.strip()}"
            return f"Dilema moral en primera persona sobre '{title[:60]}': ¿Soy la mala por negarme a ceder ante la presión familiar tras descubrir la verdad?"

        else: # horror longform
            return f"Relato en primera persona sobre '{title[:60]}' con inmersión sensorial inmediata ante anomalía nocturna inexplicable y escalada de dread."

    def _generate_fallback_narrative(self, title: str, lane_key: str, existing_text: str) -> str:
        """Generates deterministic, canon-grounded fallback story when input text is minimal."""
        try:
            from src.templates.narratives import (
                build_aelithia_longform_narrative,
                build_moku_longform_narrative,
                build_moku_short_narrative,
            )

            if "scp" in lane_key:
                return build_moku_short_narrative(topic=title or "SCP-087", channel="moku")
            elif "aita" in lane_key:
                return build_aelithia_longform_narrative(topic=title or "el conflicto de herencia familiar", channel="aelithia")
            else:
                return build_moku_longform_narrative(topic=title or "la frecuencia prohibida del bosque", channel="moku")
        except Exception as exc:
            logger.debug("Fallback template invocation notice: %s", exc)

        # Built-in robust text templates
        if "scp" in lane_key:
            return (
                f"SCP-173. No parpadees. Contención Euclid. "
                "Los protocolos de contención primaria exigen sellado hermético en búnker subterráneo de hormigón y titanio con tres operarios Clase-D. "
                "Durante la prueba de telemetría, los sensores registraron fluctuaciones fuera de escala mientras el contacto visual se rompía por un parpadeo involuntario. "
                "A las cero trescientas horas, la compuerta blindada colapsó ante una fuerza descomunal, desatando la brecha crítica de contención en el sector siete. "
                "El Sitio fue puesto bajo protocolo de aislamiento total y el expediente permanece clasificado bajo estricta custodia oficial."
            )
        elif "aita" in lane_key:
            return (
                f"¿Soy la mala por negarles mi dinero? "
                "Durante diez años trabajé turnos dobles para comprar mi primera vivienda, pero mi familia organizó una cena sorpresa para exigirme que saldara sus deudas. "
                "Cuando me negué con serenidad, la mesa se convirtió en un tribunal de reproches donde me acusaron de egoísta y amenazaron con expulsarme del círculo familiar. "
                "Descubrí además que habían falsificado documentos notariales para intentar acceder a mis cuentas bancarias sin mi consentimiento. "
                "Cancelé de inmediato todo apoyo económico y contraté asesoría legal para blindar mi patrimonio frente a los chantajes afectivos. "
                "¿Qué habrías hecho tú en mi lugar? ¿Fui demasiado lejos al poner este límite definitivo? "
                "Seis meses después, vivo con total tranquilidad y autonomía, confirmando que poner límites sanos es un acto indispensable de supervivencia."
            )
        else: # horror
            return (
                f"03:00. Alarmas imposibles en {title}. "
                "La niebla densa cubría los pinos centenarios mientras el frío glacial congelaba el vaho de mi respiración en la cabina de control. "
                "Al revisar los archivadores de acero, encontré los diarios de guardia de operadores desaparecidos que describían exactamente las mismas señales y advertían no responder a la radio. "
                "Una sombra alargada comenzó a deslizarse bajo el umbral de la puerta blindada mientras los altavoces repetían mi propio nombre en tiempo real. "
                "El cristal del ventanal estalló en pedazos ante una manifestación no euclidiana que me obligó a detonar la bengala de emergencia y huir a toda velocidad por el sendero forestal. "
                "Llegué al amanecer con las ropas rasgadas y los vehículos oficiales acordonaron el sector bajo estricto encubrimiento. "
                "Hoy vivo en la ciudad, pero cada vez que una radio emite estática sé que la presencia sigue esperando en el valle."
            )

    def _sanitize_text(self, text: str) -> str:
        """Sanitizes text, removing markdown headers, meta chatter, emojis, clichés, and artifacts."""
        if not text:
            return ""
        try:
            from src.sanitizer import sanitize_script_text
            t = sanitize_script_text(text, channel="moku")
        except Exception:
            t = text
        t = re.sub(r"#+\s*", "", t)
        t = re.sub(r"\[.*?\]", "", t)
        t = re.sub(r"\(http.*?\)", "", t)
        t = re.sub(r"[\*\_~`]", "", t)
        
        # Anti-cliché and boilerplate filter
        t = re.sub(r"(?i)\ben este video veremos\b", "", t)
        t = re.sub(r"(?i)\bbajo una universidad ordinaria\b", "en una instalación subterránea", t)
        t = re.sub(r"(?i)\bsuscr[íi]bete para m[áa]s\b", "", t)
        t = re.sub(r"(?i)\bpermanece bajo custodia oficial en\s*@\w+\.?\b", "", t)
        
        t = re.sub(r"\s+", " ", t).strip()
        return t
