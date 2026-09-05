"""
src/media/multi_act_renderer.py - Multi-Act FFmpeg Video Compositor.

Orchestrates sequential catalog/loop video scenes across narrative temporal acts in a
single FFmpeg filter_complex pass, with theme-agnostic niche HUD overlays (drawtext/drawbox layouts: top_bar / card / bottom_bar),
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
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from lib.ffmpeg import run_ffmpeg, FFmpegExecutionError, probe_media
from src.log import get_logger
from src.media.director_single_pass import director_single_pass_enabled
from src.media.encode_defaults import default_render_crf, default_render_preset
from src.media.subtitles_ass import (
    calculate_font_size,
    calculate_safe_margins,
    escape_ffmpeg_filter_path,
    has_active_subtitles,
)

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
    otherwise act hud_* / color fields use default hud_layout (theme_category is a free label only).
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
    """Visual HUD telemetry and metadata for theme-agnostic FFmpeg HUD layouts.

    ``hud_layout`` selects geometry only (top_bar | card | bottom_bar).
    ``story_type`` is a free label and MUST NOT drive geometry.
    """
    lane_id: str = ""
    story_type: str = ""
    hud_layout: str = "top_bar"  # top_bar | card | bottom_bar
    hud_badge: str = ""
    hud_site: str = ""
    telemetry_label: str = ""
    accent_color_hex: str = "#00FF88"
    tension_level: int = 1


# Shared HUD typography / stroke (coherence across hud_layout variants).
HUD_FONT_PRIMARY = 20
HUD_FONT_SECONDARY = 18
HUD_FONT_META = 16
HUD_BORDERW = 2
HUD_BORDERCOLOR = "black@0.85"
_GENERIC_HUD_ACCENTS = frozenset({"", "#00ff88"})  # NicheHudConfig default only
HEX_COLOR_PATTERN = re.compile(r"^#([0-9a-fA-F]{6})$")


def _escape_ffmpeg_color(color: Any, default: str = "#00FF88") -> str:
    """Keep only #RRGGBB so corrupt accents cannot leak into drawbox/drawtext."""
    if not color or not isinstance(color, str):
        return default
    s = color.strip()
    if s.startswith("0x") and len(s) == 8:
        s = "#" + s[2:]
    m = HEX_COLOR_PATTERN.match(s)
    if m:
        return f"#{m.group(1).upper()}"
    return default


def _escape_drawtext(text: str) -> str:
    """Escapes text for FFmpeg drawtext filter."""
    if not text:
        return ""
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "").replace("%", "\\%")


def resolve_hud_accent_color(accent_color_hex: str = "", lane_id: str = "", story_type: str = "") -> str:
    """Prefer explicit accent; else ChannelProfileRegistry by lane_id; else default.

    ``story_type`` is accepted for call-site compatibility but MUST NOT pick colors.
    """
    raw = (accent_color_hex or "").strip()
    if raw and raw.lower() not in _GENERIC_HUD_ACCENTS:
        escaped = _escape_ffmpeg_color(raw, default="")
        if escaped:
            return escaped
    key = (lane_id or "").strip()
    if key:
        try:
            from src.core.channel_profile import ChannelProfileRegistry

            accent = (ChannelProfileRegistry.get_channel(key).visual.palette.accent or "").strip()
            if accent:
                return _escape_ffmpeg_color(accent, default="#00FF88")
        except Exception:
            pass
    return _escape_ffmpeg_color(raw, default="#00FF88")


def hud_safe_margins(width: int, height: int) -> Dict[str, int]:
    """Video HUD margins aligned with thumbnail Shorts/longform safe-zones.

    Keeps drawtext/drawbox clear of YouTube Shorts UI (top chrome, right rail,
    bottom caption/channel controls) without slowing the cheap-director path.
    """
    from src.media.thumbnails.layout import AspectLayoutManager

    safe = AspectLayoutManager.get_safe_zone(width, height)
    is_vertical = height > width
    return {
        "left": int(safe.left),
        "right": int(safe.right),
        "top": int(safe.top),
        "bottom": int(safe.bottom),
        "width": int(safe.width),
        "height": int(safe.height),
        "is_vertical": 1 if is_vertical else 0,
        "font_primary": HUD_FONT_PRIMARY + (2 if is_vertical else 0),
        "font_secondary": HUD_FONT_SECONDARY,
        "font_meta": HUD_FONT_META,
    }


def _drawtext(
    text: str,
    *,
    fontcolor: str,
    fontsize: int,
    x: str | int,
    y: str | int,
) -> str:
    """Consistent drawtext with shared stroke for readability on busy footage."""
    return (
        f"drawtext=text='{text}':fontcolor={fontcolor}:fontsize={fontsize}:"
        f"x={x}:y={y}:box=0:borderw={HUD_BORDERW}:bordercolor={HUD_BORDERCOLOR}"
    )


_ALLOWED_HUD_LAYOUTS = frozenset({"top_bar", "card", "bottom_bar"})


def _normalize_hud_layout(value: Any) -> str:
    layout = str(value or "top_bar").strip().lower()
    return layout if layout in _ALLOWED_HUD_LAYOUTS else "top_bar"


def niche_hud_from_mapping(data: Optional[Dict[str, Any]]) -> Optional[NicheHudConfig]:
    """Build NicheHudConfig from planner/manifest ``niche_hud`` dict when present."""
    if not isinstance(data, dict) or not data:
        return None
    if data.get("enabled") is False or data.get("hud_enabled") is False:
        return None
    raw_layout = str(data.get("hud_layout") or "").strip().lower()
    if raw_layout in ("none", "off", "disabled", "false"):
        return None
    story = str(data.get("story_type") or data.get("lane_id") or "").strip()
    if not (data.get("hud_badge") or data.get("hud_site") or data.get("telemetry_label")):
        return None
    lane_id = str(data.get("lane_id") or "")
    return NicheHudConfig(
        lane_id=lane_id,
        story_type=story or "generic",
        hud_layout=_normalize_hud_layout(data.get("hud_layout")),
        hud_badge=str(data.get("hud_badge") or ""),
        hud_site=str(data.get("hud_site") or ""),
        telemetry_label=str(data.get("telemetry_label") or ""),
        accent_color_hex=resolve_hud_accent_color(
            str(data.get("accent_color_hex") or ""),
            lane_id=lane_id,
            story_type=story or "generic",
        ),
        tension_level=int(data.get("tension_level") or 1),
    )


def niche_hud_from_act(act: "NarrativeSceneAct") -> Optional[NicheHudConfig]:
    """Resolve niche HUD: prefer planner ``act.niche_hud`` dict, else defaults.

    Does NOT map theme_category keywords (scp/aita/reddit/abyss/horror) to
    geometry. ``story_type`` remains a free label from theme_category; layout
    defaults to ``top_bar``. DIRECTOR_SINGLE_PASS / MultiSceneCompositor burn
    the same overlay when planner ``niche_hud`` is present.
    """
    if getattr(act, "niche_hud", None) is not None:
        return niche_hud_from_mapping(act.niche_hud)
    if not (act.hud_badge or act.hud_site or act.hud_telemetry):
        return None
    story = str(act.theme_category or "").strip() or "generic"
    lane_id = str(getattr(act, "lane_id", "") or "")
    return NicheHudConfig(
        lane_id=lane_id,
        story_type=story,
        hud_layout="top_bar",
        hud_badge=act.hud_badge,
        hud_site=act.hud_site,
        telemetry_label=act.hud_telemetry,
        accent_color_hex=resolve_hud_accent_color(
            act.color_hex or "",
            lane_id=lane_id,
            story_type=story,
        ),
        tension_level=1,
    )


def build_niche_hud_filter(
    width: int,
    height: int,
    hud_cfg: Optional[NicheHudConfig],
    duration_sec: float,
) -> str:
    """Build FFmpeg drawtext/drawbox HUD snippet (shared with DIRECTOR_SINGLE_PASS).

    Geometry branches ONLY on ``hud_cfg.hud_layout`` (top_bar | card | bottom_bar).
    ``story_type`` / niche name strings MUST NOT select geometry.
    """
    if hud_cfg is None:
        return ""
    layout_raw = getattr(hud_cfg, "hud_layout", "top_bar")
    if str(layout_raw).strip().lower() in ("none", "off", "disabled", "false"):
        return ""
    accent = resolve_hud_accent_color(
        hud_cfg.accent_color_hex,
        lane_id=hud_cfg.lane_id,
        story_type=hud_cfg.story_type,
    )
    site_esc = _escape_drawtext(hud_cfg.hud_site)
    badge_esc = _escape_drawtext(hud_cfg.hud_badge)
    telemetry_esc = _escape_drawtext(hud_cfg.telemetry_label)
    if not (site_esc or badge_esc or telemetry_esc):
        return ""
    layout = _normalize_hud_layout(layout_raw)
    filters: List[str] = []
    m = hud_safe_margins(width, height)
    is_vertical = bool(m["is_vertical"])
    margin_x = int(m["left"])
    content_w = int(m["width"])
    font_p = int(m["font_primary"])
    font_s = int(m["font_secondary"])
    font_m = int(m["font_meta"])
    text_x = margin_x + 20

    if layout == "card":
        # Former Reddit-card geometry (theme-agnostic).
        card_w = min(content_w, 860)
        card_h = 120 if is_vertical else 95
        card_x = margin_x + max(0, (content_w - card_w) // 2)
        card_y = int(m["top"])
        filters.append(f"drawbox=x={card_x}:y={card_y}:w={card_w}:h={card_h}:color=black@0.6:t=fill")
        filters.append(f"drawbox=x={card_x}:y={card_y}:w={card_w}:h={card_h}:color={accent}@0.75:t=2")
        filters.append(
            _drawtext(badge_esc, fontcolor=accent, fontsize=font_p, x=card_x + 25, y=card_y + 15)
        )
        filters.append(
            _drawtext(site_esc, fontcolor="white@0.9", fontsize=font_s, x=card_x + 25, y=card_y + 45)
        )
        if telemetry_esc:
            filters.append(
                _drawtext(
                    telemetry_esc,
                    fontcolor=f"{accent}@0.95",
                    fontsize=font_m,
                    x=card_x + 25,
                    y=card_y + 75,
                )
            )
    elif layout == "bottom_bar":
        # Bottom bar on landscape; top safe bar on vertical (avoid YT Shorts UI).
        bar_h = 90 if is_vertical else 75
        if is_vertical:
            bar_y = int(m["top"])
        else:
            bar_y = max(int(m["top"]), int(m["bottom"]) - bar_h)
        filters.append(f"drawbox=x={margin_x}:y={bar_y}:w={content_w}:h={bar_h}:color=black@0.75:t=fill")
        filters.append(f"drawbox=x={margin_x}:y={bar_y}:w={content_w}:h={bar_h}:color={accent}@0.6:t=2")
        filters.append(_drawtext(site_esc, fontcolor=accent, fontsize=font_p, x=text_x, y=bar_y + 15))
        filters.append(
            _drawtext(telemetry_esc, fontcolor="white", fontsize=font_s, x=text_x, y=bar_y + 45)
        )
        if badge_esc:
            badge_x = max(text_x, int(m["right"]) - 300)
            filters.append(
                _drawtext(badge_esc, fontcolor=accent, fontsize=font_s, x=badge_x, y=bar_y + 25)
            )
    else:
        # top_bar — former SCP top-bar geometry (theme-agnostic default).
        bar_h = 90 if is_vertical else 70
        bar_y = int(m["top"])
        filters.append(f"drawbox=x={margin_x}:y={bar_y}:w={content_w}:h={bar_h}:color=black@0.7:t=fill")
        filters.append(f"drawbox=x={margin_x}:y={bar_y}:w={content_w}:h={bar_h}:color={accent}@0.8:t=2")
        filters.append(_drawtext(site_esc, fontcolor=accent, fontsize=font_p, x=text_x, y=bar_y + 15))
        badge_x = max(text_x, int(m["right"]) - 340)
        filters.append(_drawtext(badge_esc, fontcolor="white", fontsize=font_s, x=badge_x, y=bar_y + 15))
        if telemetry_esc:
            filters.append(
                _drawtext(
                    telemetry_esc,
                    fontcolor="white@0.8",
                    fontsize=font_m,
                    x=text_x,
                    y=bar_y + bar_h - 28,
                )
            )
        if hud_cfg.tension_level >= 4:
            filters.append(
                f"drawbox=x={margin_x}:y={bar_y}:w={content_w}:h={bar_h}:color=red@0.25:enable='gte(t,0)':t=fill"
            )
            alert_x = max(text_x, int(m["right"]) - 380)
            filters.append(
                _drawtext(
                    "[ALERT // ANOMALOUS TENSION]",
                    fontcolor="red",
                    fontsize=font_m,
                    x=alert_x,
                    y=bar_y + bar_h - 28,
                )
            )

    return ",".join(filters)


class MultiActVideoRenderer:
    """Composites sequential procedural scenes into a unified cinematic master video."""

    def __init__(self, loops_dir: Optional[Path] = None):
        self.iconic_dir = ROOT_DIR / "assets" / "loops" / "thematic_iconic"
        self.loops_dir = loops_dir or (ROOT_DIR / "assets" / "loops" / "web_procedural")

    def _stream_copy_signature(
        self, loop_path: Path
    ) -> Optional[Tuple[int, int, str, str, str]]:
        """Return (w, h, codec, pix_fmt, time_base) for concat demuxer -c:v copy safety."""
        try:
            probe = probe_media(loop_path)
            vs = probe.video_streams[0] if probe.video_streams else probe.primary_video
            if vs is None:
                return None
            time_base = ""
            for s in (probe.raw_payload or {}).get("streams", []):
                if s.get("codec_type") == "video":
                    time_base = str(s.get("time_base") or "")
                    break
            return (
                int(vs.width),
                int(vs.height),
                str(getattr(vs, "codec_name", "") or ""),
                str(getattr(vs, "pix_fmt", "") or ""),
                time_base,
            )
        except Exception:
            return None

    def _loops_homogeneous_for_stream_copy(
        self, loop_paths: List[Path], width: int, height: int
    ) -> bool:
        """True only when all loops share WxH/codec/pix_fmt/time_base and match target WxH."""
        if not loop_paths:
            return False
        sigs: List[Tuple[int, int, str, str, str]] = []
        for p in loop_paths:
            sig = self._stream_copy_signature(p)
            if sig is None:
                return False
            if sig[0] != int(width) or sig[1] != int(height):
                return False
            if not sig[2] or not sig[3]:
                return False
            sigs.append(sig)
        first = sigs[0]
        return all(s == first for s in sigs)

    def build_scene_hud_filter(
        self,
        width: int,
        height: int,
        hud_cfg: NicheHudConfig,
        duration_sec: float,
    ) -> str:
        """Build FFmpeg filtergraph snippet for niche HUD (layout-driven, theme-agnostic)."""
        return build_niche_hud_filter(width, height, hud_cfg, duration_sec)


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
        font_size = calculate_font_size(width, height)
        margin_l, margin_r, margin_v = calculate_safe_margins(width, height, downward_drift_px)

        ass_content = f"""[Script Info]
Title: SCP-5000 Dynamic Subtitles
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Liberation Sans,{font_size},&H00FFFFFF,&H0000FFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,3,2,2,{margin_l},{margin_r},{margin_v},1
Style: Highlight,Liberation Sans,{font_size + 4},&H0000FF55,&H0000FFFF,&H00000000,&HA0000000,-1,0,0,0,100,100,0,0,1,3,3,2,{margin_l},{margin_r},{margin_v},1

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

        # Check for director single-pass stream-copy eligibility:
        # Near-zero CPU: when DIRECTOR_SINGLE_PASS=1, no xfade, no HUD, no subtitles,
        # and all loop files match target geometry, codec, pixel format, and time_base.
        hud_snippets = [
            self.build_scene_hud_filter(w, h, niche_hud_from_act(act), float(act.duration_sec))
            for act in acts
        ]
        has_hud = any(bool(s) for s in hud_snippets)
        has_subtitles = has_active_subtitles(ass_subtitles)
        homogeneous = self._loops_homogeneous_for_stream_copy(loop_paths, w, h)
        can_stream_copy = (
            director_single_pass_enabled()
            and not use_xfade
            and not has_hud
            and not has_subtitles
            and homogeneous
        )

        if can_stream_copy:
            logger.info("🚀 Ejecutando ensamble stream-copy Multi-Acto (DIRECTOR_SINGLE_PASS)...")
            with tempfile.TemporaryDirectory(prefix="multiact_stream_copy_") as tmp_dir_str:
                tmp_dir = Path(tmp_dir_str)
                trimmed: List[Path] = []
                for idx, (lp, act) in enumerate(zip(loop_paths, acts)):
                    out_seg = tmp_dir / f"act_trim_{idx:03d}.mp4"
                    cmd_trim = [
                        "ffmpeg", "-y",
                        "-stream_loop", "-1",
                        "-i", str(lp),
                        "-t", f"{act.duration_sec:.3f}",
                        "-c:v", "copy",
                        "-an",
                        "-movflags", "+faststart",
                        str(out_seg),
                    ]
                    run_ffmpeg(cmd_trim, check=True)
                    trimmed.append(out_seg)

                concat_list = tmp_dir / "acts_concat.txt"
                with open(concat_list, "w", encoding="utf-8") as f:
                    for t_p in trimmed:
                        f.write(f"file '{t_p.resolve()}'\n")

                cmd_mux = [
                    "ffmpeg", "-y", "-v", "error",
                    "-f", "concat", "-safe", "0", "-i", str(concat_list),
                    "-i", str(audio_path),
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-ar", "44100",
                    "-t", f"{out_dur:.3f}",
                    "-movflags", "+faststart",
                    str(output_video),
                ]
                run_ffmpeg(cmd_mux, check=True)
                logger.info(
                    "✅ Master Multi-Escena Stream-Copy Generado: %s (%.2f MB)",
                    output_video.name,
                    output_video.stat().st_size / (1024 * 1024) if output_video.exists() else 0.0,
                )
                return output_video

        if director_single_pass_enabled():
            logger.info(
                "MultiAct stream-copy ineligible (xfade=%s hud=%s subs=%s homogeneous=%s); "
                "re-encoding with preset=%s crf=%s",
                use_xfade,
                has_hud,
                has_subtitles,
                homogeneous,
                default_render_preset(),
                default_render_crf(),
            )

        filter_parts = []
        for i, act in enumerate(acts):
            scale_filter = (
                f"scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h},fps=30,setsar=1,format=yuv420p"
            )
            hud_overlay = hud_snippets[i]
            hud_filters = f"{scale_filter},{hud_overlay}" if hud_overlay else scale_filter
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

        if ass_subtitles and has_active_subtitles(ass_subtitles):
            sub_path_esc = escape_ffmpeg_filter_path(ass_subtitles)
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
