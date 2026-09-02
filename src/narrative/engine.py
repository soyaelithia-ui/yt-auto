"""
src/narrative/engine.py - 5-Phase Tension Curve Narrative Generator & Script Compiler.
"""
from __future__ import annotations

import datetime
import math
import re
from typing import Any, Dict, List, Optional, Union

from src.narrative.archetypes import (
    ARCHETYPE_PRESETS,
    REC709_PALETTE_TABLES,
    resolve_archetype_for_topic,
)
from src.narrative.schema import (
    AudioContract,
    CameraTransform,
    CosmicScriptContract,
    NarrativeArchetype,
    Rec709Palette,
    SceneContract,
    SceneContractV2,
    SFXCue,
    TensionLevel,
    VideoFormat,
    VoicePreset,
)
from src.log import get_logger

logger = get_logger("narrative_engine")


def score_5phase_tension_curve(num_scenes: int = 5) -> List[int]:
    """
    Evaluates and assigns discrete 5-phase tension scores strictly in [1, 5]:
    Phase 1 (Baseline / Exposition): Tension 1-2
    Phase 2 (Micro-anomaly / Deviation): Tension 2-3
    Phase 3 (Escalation / Containment): Tension 3-4
    Phase 4 (Climax / Catastrophic Rupture): Tension 5
    Phase 5 (Ambiguity / Loop Hook): Tension 2-3
    """
    n = max(3, int(num_scenes))
    if n == 3:
        return [2, 5, 2]
    if n == 4:
        return [1, 3, 5, 2]
    if n == 5:
        return [1, 2, 4, 5, 2]

    # For n > 5:
    curve = [1]
    climax_idx = n - 2
    for i in range(1, climax_idx):
        # Scale between 2 and 4
        frac = i / float(climax_idx)
        val = int(round(2.0 + 2.0 * frac))
        curve.append(max(2, min(4, val)))
    curve.append(5)  # Climax
    curve.append(2)  # Loop hook
    return curve


def clamp_and_smooth_tension_curve(
    raw_scores: List[int],
    enforce_climax: bool = False,
) -> List[int]:
    """
    Clamps raw tension scores strictly to [1, 5] and smooths abrupt step jumps (Delta T > 2)
    using monotonic easing.
    """
    if not raw_scores:
        return [1, 2, 3, 5, 2]

    # 1. Clamp to [1, 5]
    clamped = [max(1, min(5, int(s))) for s in raw_scores]

    # Check if inverted or monotonic decreasing
    is_decreasing = len(clamped) >= 3 and all(clamped[i] >= clamped[i+1] for i in range(len(clamped)-1))
    if is_decreasing or enforce_climax:
        # Re-score according to 5-phase curve
        return score_5phase_tension_curve(len(clamped))

    # 2. Smooth jumps > 2 (forward and backward passes)
    smoothed = list(clamped)
    for _ in range(3):
        for i in range(len(smoothed) - 1):
            if smoothed[i + 1] - smoothed[i] > 2:
                smoothed[i + 1] = smoothed[i] + 2
            elif smoothed[i] - smoothed[i + 1] > 2:
                smoothed[i + 1] = smoothed[i] - 2

    # Final pass clamp
    smoothed = [max(1, min(5, s)) for s in smoothed]
    return smoothed


def segment_narration_into_scenes(
    narration_text: str,
    wpm: float = 165.0,
    min_scene_dur: float = 7.0,
    max_scene_dur: float = 12.0,
) -> List[Dict[str, Any]]:
    """
    Segments narration text into semantic scene acts respecting 7.0s <= duration <= 12.0s
    at 160-175 WPM. Automatically merges sub-7.0s orphan phrases into preceding scenes.
    """
    clean_text = narration_text.strip()
    if not clean_text:
        clean_text = "Registro narrativo."

    # Sentence boundary splitting with abbreviation protection
    sentences = re.split(r"(?<=[.!?…])\s+|\n+", clean_text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        sentences = [clean_text]

    target_words = int(round((9.0 / 60.0) * wpm))
    max_words = int(round((max_scene_dur / 60.0) * wpm))
    min_words = int(round((min_scene_dur / 60.0) * wpm))

    # Group sentences into initial buckets
    buckets: List[List[str]] = []
    current_bucket: List[str] = []
    current_wcount = 0

    for sent in sentences:
        w_cnt = len(sent.split())
        if current_bucket and (current_wcount + w_cnt > max_words or current_wcount >= target_words):
            buckets.append(current_bucket)
            current_bucket = [sent]
            current_wcount = w_cnt
        else:
            current_bucket.append(sent)
            current_wcount += w_cnt

    if current_bucket:
        buckets.append(current_bucket)

    # Convert buckets into scene strings
    scene_texts = [" ".join(b).strip() for b in buckets if b]

    # Check for short orphan trailing scenes and merge
    if len(scene_texts) > 1:
        last_words = len(scene_texts[-1].split())
        last_dur = (last_words / wpm) * 60.0
        if last_dur < min_scene_dur:
            prev_words = len(scene_texts[-2].split())
            merged_dur = ((prev_words + last_words) / wpm) * 60.0
            if merged_dur <= max_scene_dur + 0.5:
                # Merge trailing orphan into previous scene
                scene_texts[-2] = f"{scene_texts[-2]} {scene_texts[-1]}"
                scene_texts.pop()
            else:
                # Rebalance words between last two scenes
                all_words = (scene_texts[-2] + " " + scene_texts[-1]).split()
                mid = len(all_words) // 2
                scene_texts[-2] = " ".join(all_words[:mid])
                scene_texts[-1] = " ".join(all_words[mid:])

    # Build scene objects
    tension_curve = score_5phase_tension_curve(len(scene_texts))
    scenes: List[Dict[str, Any]] = []

    for idx, text in enumerate(scene_texts):
        words = len(text.split())
        dur = round(max(min_scene_dur, min(max_scene_dur, (words / wpm) * 60.0)), 2)
        scenes.append({
            "scene_id": f"scene_{idx + 1:03d}",
            "scene_index": idx + 1,
            "narration_text": text,
            "word_count": max(1, words),
            "duration_sec": dur,
            "tension_level": tension_curve[idx] if idx < len(tension_curve) else 3,
        })

    return scenes


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
        Synthesizes an open-domain 5-phase tension script contract.
        """
        if archetype is None:
            norm_arch = resolve_archetype_for_topic(topic) if topic else self.default_archetype
        elif isinstance(archetype, str):
            try:
                norm_arch = NarrativeArchetype(archetype.lower().strip())
            except ValueError:
                norm_arch = resolve_archetype_for_topic(topic) or self.default_archetype
        else:
            norm_arch = archetype

        preset = ARCHETYPE_PRESETS.get(norm_arch, ARCHETYPE_PRESETS[NarrativeArchetype.HYDROACOUSTIC_TELEMETRY])

        now_str = iso_timestamp or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        telemetry_header = f"REC [●] {now_str} // LVL-5 RESTRICTED"

        title = topic.strip() if topic and topic.strip() else preset["title_template"]

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

        # Build scenes timeline mapping to shaders, tension, and Rec.709 palette
        scenes = self._build_scenes_timeline(total_dur, preset, norm_arch)

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

    def _build_scenes_timeline(
        self,
        total_dur: float,
        preset: Dict[str, Any],
        archetype: NarrativeArchetype,
    ) -> List[SceneContract]:
        """Maps narrative acts into distinct WebGL scene shaders with progressive tension parameters."""
        shaders = preset["shader_sequence"]
        num_scenes = len(shaders)
        scene_dur = total_dur / float(num_scenes)
        tension_scores = score_5phase_tension_curve(num_scenes)
        palette = preset.get("palette", REC709_PALETTE_TABLES.get(archetype.value, REC709_PALETTE_TABLES["cosmic_horror"]))

        scenes: List[SceneContract] = []
        for i, sh_id in enumerate(shaders):
            start = round(i * scene_dur, 2)
            end = round(total_dur if i == num_scenes - 1 else (i + 1) * scene_dur, 2)
            tension = min(1.0, (i + 1) / float(num_scenes))
            t_int = tension_scores[i] if i < len(tension_scores) else 3
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
                        "tensionLevel": t_int,
                        "uColorTint": [0.05, 0.35, 0.15] if "RADAR" in sh_id else ([0.2, 0.1, 0.4] if "SINGULARITY" in sh_id else [0.08, 0.15, 0.12]),
                    },
                    hud_status=hud,
                    tension_level=t_int,
                    palette=palette,
                    camera_transform=CameraTransform(offset_x=0.0, offset_y=0.0, rotation_deg=0.0, zoom_scale=1.0),
                )
            )

        return scenes
