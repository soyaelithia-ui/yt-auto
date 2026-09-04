"""
src/media/multi_act_renderer.py - Multi-Act FFmpeg Video Compositor.

Orchestrates sequential catalog/loop video scenes across narrative temporal acts in a
single FFmpeg filter_complex pass, with tactical SCP HUD overlays (drawtext/drawbox),
real FFmpeg xfade transitions (duration-aware via calculate_xfade_duration),
and optional ASS subtitles. FFmpeg-only (no Canvas/Three.js/WebGL/wgpu).
"""
from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from lib.ffmpeg import run_ffmpeg, FFmpegExecutionError
from src.log import get_logger

logger = get_logger("multi_act_renderer")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


def calculate_xfade_duration(scene_durations: List[float], transition_duration: float = 0.75) -> float:
    """Calculates total duration across scenes with transitions: sum(durations) - ((n - 1) * transition_duration)."""
    if not scene_durations:
        return 0.0
    if len(scene_durations) == 1:
        return float(scene_durations[0])
    num_transitions = len(scene_durations) - 1
    return float(sum(scene_durations) - (num_transitions * transition_duration))


def clamp_transition_duration(dur1: float, dur2: float, requested_transition: float = 0.75) -> float:
    """Clamps transition duration to <= 30% of the shortest adjacent scene duration."""
    shortest = min(float(dur1), float(dur2))
    return min(float(requested_transition), shortest * 0.30)


@dataclass
class NarrativeSceneAct:
    """Represents a discrete temporal act with a specific code-driven visual theme."""
    act_index: int
    start_sec: float
    duration_sec: float
    title: str
    theme_category: str  # 'scp', 'space_abyss', 'monsters', 'dark_forest', 'cosmic_horror'
    hud_badge: str = "NIVEL 5 // CLASIFICADO"
    hud_site: str = "SITIO-62C // CONTENCIÓN"
    hud_telemetry: str = "STATUS: OPERACIONAL // SENSOR HUME ONLINE"
    color_hex: str = "#00FF88"


class MultiActVideoRenderer:
    """Composites sequential procedural scenes into a unified cinematic master video."""

    def __init__(self, loops_dir: Optional[Path] = None):
        self.iconic_dir = ROOT_DIR / "assets" / "loops" / "thematic_iconic"
        self.loops_dir = loops_dir or (ROOT_DIR / "assets" / "loops" / "web_procedural")

    def resolve_loop_for_theme(self, category: str, is_vertical: bool = False) -> Path:
        """Finds the best available procedural loop MP4 for the given category."""
        # 1. Check thematic_iconic directory first
        if self.iconic_dir.is_dir():
            suffix = "1080x1920" if is_vertical else "1920x1080"
            matches = list(self.iconic_dir.glob(f"*{category}*{suffix}*.mp4"))
            if not matches:
                matches = list(self.iconic_dir.glob(f"*{category}*.mp4"))
            if matches:
                return matches[0]

        # 2. Fallback to web_procedural category directory
        cat_dir = self.loops_dir / category
        suffix_l = "_v_" if is_vertical else "_h_"
        
        candidates = []
        if cat_dir.is_dir():
            candidates = list(cat_dir.glob(f"*{suffix_l}*.mp4"))
            if not candidates:
                candidates = list(cat_dir.glob("*.mp4"))
        
        if not candidates:
            # Fallback across all loops
            all_loops = list(self.loops_dir.glob(f"**/*{suffix_l}*.mp4"))
            if all_loops:
                return all_loops[0]
            any_loops = list(self.loops_dir.glob("**/*.mp4"))
            if any_loops:
                return any_loops[0]
            raise FileNotFoundError(f"No procedural video loops found for {category}")
        
        return candidates[0]

    def generate_ass_subtitles(
        self,
        acts: List[NarrativeSceneAct],
        output_ass: Path,
        is_vertical: bool = False,
        downward_drift_px: int = 0,
    ) -> Path:
        """Generates a clean, styled ASS subtitle file for the video acts."""
        width = 1080 if is_vertical else 1920
        height = 1920 if is_vertical else 1080
        font_size = 38 if is_vertical else 32
        base_margin_v = max(480, int(height * 0.25)) if is_vertical else max(130, int(height * 0.12))
        margin_v = base_margin_v + max(0, int(downward_drift_px))

        ass_content = f"""[Script Info]
Title: SCP-5000 Dynamic Subtitles
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Liberation Sans,{font_size},&H00FFFFFF,&H0000FFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,3,2,2,40,40,{margin_v},1
Style: Highlight,Liberation Sans,{font_size + 4},&H0000FF55,&H0000FFFF,&H00000000,&HA0000000,-1,0,0,0,100,100,0,0,1,3,3,2,40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        def format_ass_time(sec: float) -> str:
            h = int(sec // 3600)
            m = int((sec % 3600) // 60)
            s = sec % 60
            return f"{h}:{m:02d}:{s:05.2f}"

        for act in acts:
            st = format_ass_time(act.start_sec)
            et = format_ass_time(act.start_sec + act.duration_sec)
            title_clean = act.title.replace("\n", " ").replace("\\", "")
            ass_content += f"Dialogue: 0,{st},{et},Default,,0,0,0,,{{\\b1}}{title_clean}{{\\b0}}\n"

        output_ass.parent.mkdir(parents=True, exist_ok=True)
        with open(output_ass, "w", encoding="utf-8") as f:
            f.write(ass_content)
        return output_ass

    def composite_multi_act_video(
        self,
        acts: List[NarrativeSceneAct],
        audio_path: Path,
        output_video: Path,
        total_duration: float,
        is_vertical: bool = False,
        ass_subtitles: Optional[Path] = None,
    ) -> Path:
        """
        Builds a multi-act FFmpeg graph combining procedural loops with HUD telemetry and crossfades.
        """
        logger.info("🎬 Componiendo Video Multi-Escena (%d Actos, %.1fs, %s)...",
                    len(acts), total_duration, "9:16 Vertical" if is_vertical else "16:9 Horizontal")
        
        output_video.parent.mkdir(parents=True, exist_ok=True)
        w = 1080 if is_vertical else 1920
        h = 1920 if is_vertical else 1080

        # Build FFmpeg command with inputs
        cmd = ["ffmpeg", "-y", "-v", "error"]
        
        # Add loop video inputs for each act
        loop_paths: List[Path] = []
        for act in acts:
            lp = self.resolve_loop_for_theme(act.theme_category, is_vertical=is_vertical)
            loop_paths.append(lp)
            cmd.extend(["-stream_loop", "-1", "-t", f"{act.duration_sec:.3f}", "-i", str(lp)])

        # Add master audio as last input
        audio_idx = len(acts)
        cmd.extend(["-i", str(audio_path)])

        # Construct filter complex: per-act HUD prep, then real xfade (or passthrough for n=1).
        filter_parts = []
        for i, act in enumerate(acts):
            scale_filter = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps=30,format=yuv420p"

            site_esc = act.hud_site.replace(":", "\\:").replace("'", "")
            badge_esc = act.hud_badge.replace(":", "\\:").replace("'", "")

            hud_filters = (
                f"{scale_filter},"
                f"drawbox=x=40:y=40:w={w-80}:h=75:color=black@0.65:t=fill,"
                f"drawbox=x=40:y=40:w={w-80}:h=75:color={act.color_hex}@0.7:t=2,"
                f"drawtext=text='{site_esc}':fontcolor={act.color_hex}:fontsize=22:x=60:y=55:box=0,"
                f"drawtext=text='{badge_esc}':fontcolor=white:fontsize=20:x={w-420}:y=55:box=0"
            )
            filter_parts.append(f"[{i}:v]{hud_filters}[v_act{i}]")

        if len(acts) == 1:
            chained = "[v_act0]"
            xfade_out_dur = float(acts[0].duration_sec)
        else:
            cum = float(acts[0].duration_sec)
            current = "[v_act0]"
            xfade_out_dur = float(acts[0].duration_sec)
            for k in range(len(acts) - 1):
                t = clamp_transition_duration(
                    acts[k].duration_sec, acts[k + 1].duration_sec, 0.75
                )
                offset = max(0.0, cum - t)
                out_tag = f"[vx{k + 1}]" if k < len(acts) - 2 else "[v_xfaded]"
                filter_parts.append(
                    f"{current}[v_act{k + 1}]xfade=transition=fade:"
                    f"duration={t:.3f}:offset={offset:.3f}{out_tag}"
                )
                current = out_tag
                cum += float(acts[k + 1].duration_sec) - t
                xfade_out_dur += float(acts[k + 1].duration_sec) - t
            chained = current
            if total_duration > 0:
                xfade_out_dur = min(float(total_duration), xfade_out_dur)

        if ass_subtitles and ass_subtitles.is_file():
            sub_path_esc = str(ass_subtitles).replace("\\", "/").replace(":", "\\:")
            filter_parts.append(f"{chained}subtitles='{sub_path_esc}'[vout]")
            v_final = "[vout]"
        else:
            filter_parts.append(f"{chained}null[vout]")
            v_final = "[vout]"

        filter_complex_str = ";".join(filter_parts)

        cmd.extend([
            "-filter_complex", filter_complex_str,
            "-map", v_final,
            "-map", f"{audio_idx}:a:0",
            "-t", f"{(xfade_out_dur if len(acts) > 1 else float(total_duration)):.3f}",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "19",
            "-pix_fmt", "yuv420p",
            "-colorspace", "bt709",
            "-color_primaries", "bt709",
            "-color_trc", "bt709",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            "-movflags", "+faststart",
            str(output_video),
        ])

        logger.info("🚀 Ejecutando renderizado FFmpeg Multi-Escena...")
        run_ffmpeg(cmd, check=True)
        logger.info("✅ Master Multi-Escena Generado: %s (%.2f MB)", output_video.name, output_video.stat().st_size / (1024*1024))
        return output_video
