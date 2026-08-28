"""
src/narrative/engine.py - 5-Phase Tension Curve Narrative Generator & Script Compiler.
"""
from __future__ import annotations

import datetime
import math
from typing import Any, Dict, List, Optional, Union

from src.narrative.archetypes import ARCHETYPE_PRESETS
from src.narrative.schema import (
    AudioContract,
    CosmicScriptContract,
    NarrativeArchetype,
    SceneContract,
    SFXCue,
    VideoFormat,
    VoicePreset,
)
from src.log import get_logger

logger = get_logger("narrative_engine")


class CosmicNarrativeEngine:
    """Generates structured Cosmic/Analog Horror script contracts following the 5-Phase Tension Curve."""

    def __init__(self, default_archetype: NarrativeArchetype = NarrativeArchetype.HYDROACOUSTIC_TELEMETRY) -> None:
        self.default_archetype = default_archetype

    def generate_script(
        self,
        topic: Optional[str] = None,
        archetype: Optional[Union[NarrativeArchetype, str]] = None,
        video_format: VideoFormat = VideoFormat.SHORT_VERTICAL,
        duration_sec: float = 35.0,
        iso_timestamp: Optional[str] = None,
    ) -> CosmicScriptContract:
        """
        Synthesizes a 5-phase tension script contract.

        Phase 1: Baseline (telemetry / normal protocol)
        Phase 2: Micro-anomaly (subtle sensor deviation)
        Phase 3: Escalation (containment warping, protocol failure)
        Phase 4: Climax (colossal scale / spatial break)
        Phase 5: Ambiguity / Redaction & Loop hook
        """
        if archetype is None:
            norm_arch = self.default_archetype
        elif isinstance(archetype, str):
            norm_arch = NarrativeArchetype(archetype.lower().strip())
        else:
            norm_arch = archetype

        preset = ARCHETYPE_PRESETS.get(norm_arch, ARCHETYPE_PRESETS[NarrativeArchetype.HYDROACOUSTIC_TELEMETRY])
        
        now_str = iso_timestamp or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        telemetry_header = f"REC [●] {now_str} // LVL-5 RESTRICTED"

        title = topic or preset["title_template"]

        # Build narration text across 5 phases
        phases = preset["phases"]
        p1 = phases["p1_baseline"]
        p2 = phases["p2_micro"]
        p3 = phases["p3_escalation"]
        p4 = phases["p4_climax"]
        p5 = phases["p5_loop"]
        loop_phrase = preset.get("loop_connector", "")

        if video_format == VideoFormat.SHORT_VERTICAL:
            full_voice_text = f"{p1}... {p2}... {p3}... {p4}... {p5}"
            total_dur = max(20.0, min(50.0, float(duration_sec)))
        else:
            full_voice_text = f"{p1} ... {p2} ... [ALERTA DE SECTOR] ... {p3} ... {p4} ... [DATOS EXPURGADOS] ... {p5}"
            total_dur = max(60.0, float(duration_sec))

        # Build SFX timeline synchronized to tension curve
        sfx_timeline = self._build_sfx_timeline(total_dur, norm_arch)

        # Build scenes timeline mapping to shaders
        scenes = self._build_scenes_timeline(total_dur, preset)

        audio = AudioContract(
            voice_text=full_voice_text,
            voice_preset=preset["voice_preset"],
            drone_base_freq_hz=preset["drone_freq"],
            sfx_timeline=sfx_timeline,
        )

        return CosmicScriptContract(
            title=title,
            format=video_format,
            telemetry_header=telemetry_header,
            audio=audio,
            scenes=scenes,
            loop_continuity_phrase=loop_phrase if video_format == VideoFormat.SHORT_VERTICAL else None,
        )

    def _build_sfx_timeline(self, total_dur: float, archetype: NarrativeArchetype) -> List[SFXCue]:
        """Calculates precise timestamps for SFX cues along the 5-phase curve."""
        t_phase1 = 0.0
        t_phase2 = total_dur * 0.22
        t_phase3 = total_dur * 0.50
        t_phase4 = total_dur * 0.78

        cues: List[SFXCue] = [
            SFXCue(time_sec=round(t_phase1, 2), sfx_id="ptt_squelch", volume=0.9),
        ]

        if archetype == NarrativeArchetype.HYDROACOUSTIC_TELEMETRY:
            cues.extend([
                SFXCue(time_sec=round(t_phase2, 2), sfx_id="sonar_ping_deep_reverb", volume=0.85),
                SFXCue(time_sec=round(t_phase3, 2), sfx_id="hull_stress_metal_groan", volume=1.0),
                SFXCue(time_sec=round(t_phase4, 2), sfx_id="singularity_glitch_burst", volume=1.0),
            ])
        elif archetype == NarrativeArchetype.PROCEDURAL_INSTITUTIONAL_MANUAL:
            cues.extend([
                SFXCue(time_sec=round(t_phase2, 2), sfx_id="geiger_clicks", volume=0.75),
                SFXCue(time_sec=round(t_phase3, 2), sfx_id="singularity_glitch_burst", volume=0.9),
                SFXCue(time_sec=round(t_phase4, 2), sfx_id="static_burst", volume=1.0),
            ])
        else:  # SPECULATIVE_BIOLOGICAL_DOSSIER
            cues.extend([
                SFXCue(time_sec=round(t_phase2, 2), sfx_id="sonar_ping_deep_reverb", volume=0.8),
                SFXCue(time_sec=round(t_phase3, 2), sfx_id="hull_stress_metal_groan", volume=1.0),
                SFXCue(time_sec=round(t_phase4, 2), sfx_id="singularity_glitch_burst", volume=1.0),
            ])

        return cues

    def _build_scenes_timeline(self, total_dur: float, preset: Dict[str, Any]) -> List[SceneContract]:
        """Maps narrative acts into distinct WebGL scene shaders with progressive tension parameters."""
        shaders = preset["shader_sequence"]
        num_scenes = len(shaders)
        scene_dur = total_dur / float(num_scenes)

        scenes: List[SceneContract] = []
        for i, sh_id in enumerate(shaders):
            start = round(i * scene_dur, 2)
            end = round(total_dur if i == num_scenes - 1 else (i + 1) * scene_dur, 2)
            tension = min(1.0, (i + 1) / float(num_scenes))
            glitch = 0.02 + 0.08 * (i / float(max(1, num_scenes - 1)))

            if i == 0:
                hud = preset.get("hud_baseline", "STATUS: MONITORING")
            elif i == 1:
                hud = preset.get("hud_escalation", "STATUS: ANOMALY")
            else:
                hud = preset.get("hud_climax", "STATUS: CRITICAL")

            scenes.append(
                SceneContract(
                    start_sec=start,
                    end_sec=end,
                    shader_id=sh_id,
                    shader_params={
                        "uGlitchIntensity": round(glitch, 3),
                        "uTension": round(tension, 2),
                        "uColorTint": [0.05, 0.35, 0.15] if "RADAR" in sh_id else ([0.2, 0.1, 0.4] if "SINGULARITY" in sh_id else [0.08, 0.15, 0.12]),
                    },
                    hud_status=hud,
                )
            )

        return scenes
