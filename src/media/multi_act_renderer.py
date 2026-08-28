"""
src/media/multi_act_renderer.py - Code-Based Multi-Scene Procedural Video Compositor.

Orchestrates sequential procedural video scenes (Canvas 2D / Three.js / WebGL / CSS)
across narrative temporal acts, with tactical SCP HUD overlays, smooth crossfade transitions,
and dynamic ASS subtitles. 100% code-driven without external static image scraping.
"""
from __future__ import annotations

import json
import logging
import math
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from src.log import get_logger

logger = get_logger("multi_act_renderer")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


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
    ) -> Path:
        """Generates a clean, styled ASS subtitle file for the video acts."""
        width = 1080 if is_vertical else 1920
        height = 1920 if is_vertical else 1080
        font_size = 38 if is_vertical else 32
        margin_v = 280 if is_vertical else 65

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

        # Construct filter complex
        filter_parts = []
        seg_labels = []

        for i, act in enumerate(acts):
            # Scale & crop loop
            scale_filter = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps=30,format=yuv420p"
            
            # HUD Overlay via drawtext (escape colons and apostrophes)
            site_esc = act.hud_site.replace(":", "\\:").replace("'", "")
            badge_esc = act.hud_badge.replace(":", "\\:").replace("'", "")
            title_esc = act.title.replace(":", "\\:").replace("'", "")
            
            # Draw HUD boxes and text in safe area
            hud_filters = (
                f"{scale_filter},"
                f"drawbox=x=40:y=40:w={w-80}:h=75:color=black@0.65:t=fill,"
                f"drawbox=x=40:y=40:w={w-80}:h=75:color={act.color_hex}@0.7:t=2,"
                f"drawtext=text='{site_esc}':fontcolor={act.color_hex}:fontsize=22:x=60:y=55:box=0,"
                f"drawtext=text='{badge_esc}':fontcolor=white:fontsize=20:x={w-420}:y=55:box=0"
            )
            
            # Apply slight fade-in and fade-out at act boundaries
            fade_dur = 0.5
            fade_out_start = max(0.1, act.duration_sec - fade_dur)
            trans_filter = f"{hud_filters},fade=t=in:st=0:d={fade_dur},fade=t=out:st={fade_out_start:.3f}:d={fade_dur}"
            
            filter_parts.append(f"[{i}:v]{trans_filter}[v_act{i}]")
            seg_labels.append(f"[v_act{i}]")

        # Concat all act video streams
        concat_in = "".join(seg_labels)
        filter_parts.append(f"{concat_in}concat=n={len(acts)}:v=1:a=0[v_concat]")

        # Apply subtitles if provided
        if ass_subtitles and ass_subtitles.is_file():
            sub_path_esc = str(ass_subtitles).replace("\\", "/").replace(":", "\\:")
            filter_parts.append(f"[v_concat]subtitles='{sub_path_esc}'[vout]")
            v_final = "[vout]"
        else:
            v_final = "[v_concat]"

        filter_complex_str = ";".join(filter_parts)

        cmd.extend([
            "-filter_complex", filter_complex_str,
            "-map", v_final,
            "-map", f"{audio_idx}:a:0",
            "-t", f"{total_duration:.3f}",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "19",
            "-pix_fmt", "yuv420p",
            "-colorspace", "bt709",
            "-color_primaries", "bt709",
            "-color_trc", "bt709",
            "-c:a", "copy",
            "-movflags", "+faststart",
            str(output_video),
        ])

        logger.info("🚀 Ejecutando renderizado FFmpeg Multi-Escena...")
        subprocess.run(cmd, check=True)
        logger.info("✅ Master Multi-Escena Generado: %s (%.2f MB)", output_video.name, output_video.stat().st_size / (1024*1024))
        return output_video
