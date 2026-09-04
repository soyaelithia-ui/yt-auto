"""
src/media/multi_act_renderer.py - Multi-Act FFmpeg Video Compositor.

Orchestrates sequential catalog/loop video scenes across narrative temporal acts in a
single FFmpeg filter_complex pass, with niche HUD overlays (SCP / Reddit-AITA / abyssal drawtext/drawbox),
real FFmpeg xfade transitions when MULTIACT_XFADE=1 (default; duration-aware via
calculate_xfade_duration — callers must pass that for total_duration so A/V -t align),
or fade+concat without timeline shrink when MULTIACT_XFADE=0. Optional ASS subtitles.
FFmpeg-only (no Canvas/Three.js/WebGL/wgpu).
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
from src.media.encode_defaults import default_render_crf, default_render_preset

logger = get_logger("multi_act_renderer")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


def clamp_transition_duration(dur1: float, dur2: float, requested_transition: float = 0.75) -> float:
    """Clamps transition duration to <= 30% of the shortest adjacent scene duration."""
    shortest = min(float(dur1), float(dur2))
    return max(0.05, min(float(requested_transition), shortest * 0.30))


def calculate_xfade_duration(
    scene_durations: List[float],
    transition_duration: float = 0.75,
    *,
    clamp: bool = True,
) -> float:
    """Total timeline after xfade overlaps.

    Uses the same clamp_transition_duration rules as the FFmpeg graph so callers
    can pass this value as total_duration / -t and keep audio+video aligned.
    """
    if not scene_durations:
        return 0.0
    if len(scene_durations) == 1:
        return float(scene_durations[0])
    out = float(scene_durations[0])
    for i in range(len(scene_durations) - 1):
        if clamp:
            t = clamp_transition_duration(
                scene_durations[i], scene_durations[i + 1], transition_duration
            )
        else:
            t = float(transition_duration)
        out += float(scene_durations[i + 1]) - t
    return out


def multiact_xfade_enabled() -> bool:
    """Real xfade shortens the timeline; default on (docs claim xfade) but opt-out via MULTIACT_XFADE=0."""
    return os.environ.get("MULTIACT_XFADE", "1").strip().lower() in (
        "1", "true", "yes", "on",
    )


@dataclass
class NarrativeSceneAct:
    """Represents a discrete temporal act with a specific code-driven visual theme.

    Optional ``niche_hud`` dict (planner/manifest shape) is preferred when present;
    otherwise theme_category + hud_* fields drive theme mapping.
    """
    act_index: int
    start_sec: float
    duration_sec: float
    title: str
    theme_category: str  # 'scp', 'space_abyss', 'monsters', 'dark_forest', 'cosmic_horror'
    hud_badge: str = "NIVEL 5 // CLASIFICADO"
    hud_site: str = "SITIO-62C // CONTENCIÓN"
    hud_telemetry: str = "STATUS: OPERACIONAL // SENSOR HUME ONLINE"
    color_hex: str = "#00FF88"
    niche_hud: Optional[Dict[str, Any]] = None



@dataclass
class NicheHudConfig:
    """Visual HUD telemetry and metadata configuration for niche channel layouts."""
    lane_id: str = ""
    story_type: str = ""
    hud_badge: str = ""
    hud_site: str = ""
    telemetry_label: str = ""
    accent_color_hex: str = "#00FF88"
    tension_level: int = 1


def _escape_drawtext(text: str) -> str:
    """Escapes text for FFmpeg drawtext filter."""
    if not text:
        return ""
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "").replace("%", "\\%")


def niche_hud_from_mapping(data: Optional[Dict[str, Any]]) -> Optional[NicheHudConfig]:
    """Build NicheHudConfig from planner/manifest ``niche_hud`` dict when present."""
    if not isinstance(data, dict) or not data:
        return None
    story = str(data.get("story_type") or data.get("lane_id") or "").strip()
    if not story and not (data.get("hud_badge") or data.get("hud_site")):
        return None
    return NicheHudConfig(
        lane_id=str(data.get("lane_id") or ""),
        story_type=story or "horror",
        hud_badge=str(data.get("hud_badge") or ""),
        hud_site=str(data.get("hud_site") or ""),
        telemetry_label=str(data.get("telemetry_label") or ""),
        accent_color_hex=str(data.get("accent_color_hex") or "#00FF88"),
        tension_level=int(data.get("tension_level") or 1),
    )


def niche_hud_from_act(act: "NarrativeSceneAct") -> NicheHudConfig:
    """Resolve niche HUD: prefer planner ``act.niche_hud`` dict, else theme mapping.

    Note: DIRECTOR_SINGLE_PASS / MultiSceneCompositor stream-copy path does **not**
    burn these overlays (avoids forced re-encode). Consumption is on MultiAct
    filtergraph renders and any caller that builds NicheHudConfig explicitly.
    """
    from_planner = niche_hud_from_mapping(getattr(act, "niche_hud", None))
    if from_planner is not None:
        return from_planner
    cat = (act.theme_category or "").lower()
    if "scp" in cat or "found" in cat or "anomaly" in cat:
        story = "scp"
    elif "aita" in cat or "reddit" in cat or "drama" in cat:
        story = "reddit_aita"
    else:
        story = "horror"
    return NicheHudConfig(
        story_type=story,
        hud_badge=act.hud_badge,
        hud_site=act.hud_site,
        telemetry_label=act.hud_telemetry,
        accent_color_hex=act.color_hex or "#00FF88",
        tension_level=1,
    )


class MultiActVideoRenderer:
    """Composites sequential procedural scenes into a unified cinematic master video."""

    def __init__(self, loops_dir: Optional[Path] = None):
        self.iconic_dir = ROOT_DIR / "assets" / "loops" / "thematic_iconic"
        self.loops_dir = loops_dir or (ROOT_DIR / "assets" / "loops" / "web_procedural")

    def build_scene_hud_filter(
        self,
        width: int,
        height: int,
        hud_cfg: NicheHudConfig,
        duration_sec: float,
    ) -> str:
        """Build FFmpeg filtergraph snippet for niche HUD (SCP / Reddit / abyssal)."""
        accent = hud_cfg.accent_color_hex or "#00FF88"
        site_esc = _escape_drawtext(hud_cfg.hud_site)
        badge_esc = _escape_drawtext(hud_cfg.hud_badge)
        telemetry_esc = _escape_drawtext(hud_cfg.telemetry_label)
        story = (hud_cfg.story_type or hud_cfg.lane_id or "").lower()
        filters: List[str] = []
        is_vertical = height > width

        if "scp" in story:
            bar_h = 70 if not is_vertical else 90
            bar_y = 40 if not is_vertical else 120
            filters.append(f"drawbox=x=40:y={bar_y}:w={width-80}:h={bar_h}:color=black@0.7:t=fill")
            filters.append(f"drawbox=x=40:y={bar_y}:w={width-80}:h={bar_h}:color={accent}@0.8:t=2")
            filters.append(f"drawtext=text='{site_esc}':fontcolor={accent}:fontsize=20:x=60:y={bar_y+15}:box=0")
            filters.append(f"drawtext=text='{badge_esc}':fontcolor=white:fontsize=18:x={width-360}:y={bar_y+15}:box=0")
            if telemetry_esc:
                filters.append(
                    f"drawtext=text='{telemetry_esc}':fontcolor=white@0.8:fontsize=16:x=60:y={bar_y+bar_h-28}:box=0"
                )
            if hud_cfg.tension_level >= 4:
                filters.append(
                    f"drawbox=x=40:y={bar_y}:w={width-80}:h={bar_h}:color=red@0.25:enable='gte(t,0)':t=fill"
                )
                filters.append(
                    f"drawtext=text='[ALERT // ANOMALOUS TENSION]':fontcolor=red:fontsize=16:x={width-400}:y={bar_y+bar_h-28}:box=0"
                )
        elif "aita" in story or "reddit" in story or "drama" in story:
            card_w = min(width - 80, 860)
            card_h = 95 if not is_vertical else 120
            card_x = (width - card_w) // 2
            card_y = 50 if not is_vertical else 140
            filters.append(f"drawbox=x={card_x}:y={card_y}:w={card_w}:h={card_h}:color=black@0.6:t=fill")
            filters.append(f"drawbox=x={card_x}:y={card_y}:w={card_w}:h={card_h}:color={accent}@0.75:t=2")
            filters.append(
                f"drawtext=text='{badge_esc}':fontcolor={accent}:fontsize=22:x={card_x+25}:y={card_y+15}:box=0"
            )
            filters.append(
                f"drawtext=text='{site_esc}':fontcolor=white@0.9:fontsize=18:x={card_x+25}:y={card_y+45}:box=0"
            )
            if telemetry_esc:
                filters.append(
                    f"drawtext=text='{telemetry_esc}':fontcolor=#FFAA00:fontsize=16:x={card_x+25}:y={card_y+75}:box=0"
                )
        else:
            bar_h = 75
            bar_y = height - 120 if not is_vertical else height - 260
            filters.append(f"drawbox=x=40:y={bar_y}:w={width-80}:h={bar_h}:color=black@0.75:t=fill")
            filters.append(f"drawbox=x=40:y={bar_y}:w={width-80}:h={bar_h}:color={accent}@0.6:t=2")
            filters.append(f"drawtext=text='{site_esc}':fontcolor={accent}:fontsize=20:x=60:y={bar_y+15}:box=0")
            filters.append(
                f"drawtext=text='{telemetry_esc}':fontcolor=white:fontsize=18:x=60:y={bar_y+45}:box=0"
            )
            if badge_esc:
                filters.append(
                    f"drawtext=text='{badge_esc}':fontcolor={accent}:fontsize=18:x={width-320}:y={bar_y+25}:box=0"
                )

        return ",".join(filters)


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

        # Construct filter complex: per-act HUD prep, then xfade or concat.
        # Contract: a single output -t trims BOTH mapped video and audio to the same duration.
        # Callers should pass total_duration=calculate_xfade_duration([...]) when xfade is on.
        use_xfade = multiact_xfade_enabled() and len(acts) > 1
        act_durs = [float(a.duration_sec) for a in acts]
        if use_xfade:
            contract_dur = calculate_xfade_duration(act_durs, 0.75, clamp=True)
            if total_duration > 0 and abs(float(total_duration) - contract_dur) > 0.05:
                logger.warning(
                    "MultiAct total_duration=%.3f differs from calculate_xfade_duration=%.3f; "
                    "using contract duration for A/V -t alignment (pass calculate_xfade_duration).",
                    float(total_duration),
                    contract_dur,
                )
            out_dur = contract_dur
        else:
            # No overlap shrink: keep full act sum (or caller total when provided).
            out_dur = float(total_duration) if total_duration > 0 else float(sum(act_durs))

        filter_parts = []
        for i, act in enumerate(acts):
            scale_filter = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps=30,format=yuv420p"

            hud_cfg = niche_hud_from_act(act)
            hud_overlay = self.build_scene_hud_filter(w, h, hud_cfg, float(act.duration_sec))
            hud_filters = f"{scale_filter},{hud_overlay}"
            filter_parts.append(f"[{i}:v]{hud_filters}[v_act{i}]")

        if len(acts) == 1:
            chained = "[v_act0]"
        elif use_xfade:
            cum = float(acts[0].duration_sec)
            current = "[v_act0]"
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
            chained = current
        else:
            # Safe non-shrinking path: concat acts (opt-out via MULTIACT_XFADE=0).
            labels = "".join(f"[v_act{i}]" for i in range(len(acts)))
            filter_parts.append(f"{labels}concat=n={len(acts)}:v=1:a=0[v_concat]")
            chained = "[v_concat]"

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
            "-t", f"{out_dur:.3f}",
            "-c:v", "libx264",
            "-preset", default_render_preset(),
            "-crf", str(default_render_crf()),
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
