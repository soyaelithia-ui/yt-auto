"""
src/media/subtitles_ass.py - ASS Subtitle Generator with Karaoke Timing and Monotonic Sanitizer.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


def format_ass_timestamp(seconds: float) -> str:
    """Convert floating-point seconds into standard ASS timestamp H:MM:SS.cs."""
    if seconds < 0:
        seconds = 0.0
    total_centis = int(round(seconds * 100))
    cs = total_centis % 100
    total_secs = total_centis // 100
    s = total_secs % 60
    total_mins = total_secs // 60
    m = total_mins % 60
    h = total_mins // 60
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def sanitize_timestamps(
    word_timestamps: Optional[List[Dict[str, Any]]],
    min_word_duration: float = 0.08,
    max_word_duration: float = 5.0,
    epsilon: float = 0.0,
    total_audio_duration: Optional[float] = None,
    sort_by_time: bool = False,
) -> List[Dict[str, Any]]:
    """Enforce strict monotonic causality, positive durations, and fix overlapping timestamps.

    Invariants:
    1. Non-negativity: start[n] >= 0.0, end[n] > start[n]
    2. Minimum duration: end[n] - start[n] >= min_word_duration (> 0.0)
    3. Strict causality: start[n] >= end[n-1] + epsilon
    4. Bounded audio length: end[n] <= total_audio_duration (when specified)
    5. Clean tokens: Empty/whitespace tokens removed, ASS special characters escaped
    """
    if not word_timestamps or not isinstance(word_timestamps, list):
        return []

    # 1. Prune invalid tokens and sanitize numeric values
    parsed: List[Dict[str, Any]] = []
    for item in word_timestamps:
        if not isinstance(item, dict):
            continue
        raw_word = str(item.get("word") if item.get("word") is not None else item.get("text", "")).strip()
        if not raw_word:
            continue

        # Escape ASS special override syntax characters
        clean_word = raw_word.replace("\\", "/").replace("{", "(").replace("}", ")")

        try:
            raw_start = float(item.get("start", item.get("w_start", 0.0)))
            if math.isnan(raw_start) or math.isinf(raw_start):
                raw_start = 0.0
        except (TypeError, ValueError):
            raw_start = 0.0

        try:
            raw_end = float(item.get("end", item.get("w_end", raw_start)))
            if math.isnan(raw_end) or math.isinf(raw_end):
                raw_end = raw_start
        except (TypeError, ValueError):
            raw_end = raw_start

        parsed.append({
            "word": clean_word,
            "raw_start": raw_start,
            "raw_end": raw_end,
        })

    if not parsed:
        return []

    # 2. Optional Chronological Pre-Sort
    if sort_by_time:
        parsed.sort(key=lambda x: (x["raw_start"], x["raw_end"]))

    # 3. Forward Monotonic Pass (O(N))
    sanitized: List[Dict[str, Any]] = []
    prev_end = 0.0

    for item in parsed:
        word = item["word"]
        raw_start = max(0.0, item["raw_start"])
        raw_end = item["raw_end"]

        # Causality enforcement
        start = max(raw_start, prev_end + epsilon)

        # Duration clamping
        raw_dur = raw_end - item["raw_start"]
        if raw_dur >= min_word_duration:
            duration = min(raw_dur, max_word_duration)
        else:
            duration = min_word_duration

        end = start + duration
        if end <= start:
            end = start + min_word_duration

        prev_end = end
        sanitized.append({
            "word": word,
            "start": round(start, 3),
            "end": round(end, 3),
        })

    # 4. Total Audio Duration Clamping & Backward Compression Pass
    if total_audio_duration is not None and total_audio_duration > 0 and sanitized:
        t_max = float(total_audio_duration)
        if sanitized[-1]["end"] > t_max:
            overflow = sanitized[-1]["end"] - t_max
            total_slack = sum(max(0.0, (w["end"] - w["start"]) - min_word_duration) for w in sanitized)

            if total_slack >= overflow and total_slack > 0:
                ratio = overflow / total_slack
                curr_end = t_max
                for i in range(len(sanitized) - 1, -1, -1):
                    w = sanitized[i]
                    dur = w["end"] - w["start"]
                    slack = max(0.0, dur - min_word_duration)
                    new_dur = max(min_word_duration, dur - (slack * ratio))
                    new_end = min(w["end"], curr_end)
                    new_start = max(0.0, new_end - new_dur)
                    w["start"] = round(new_start, 3)
                    w["end"] = round(new_end, 3)
                    curr_end = max(0.0, w["start"] - epsilon)
            else:
                # Direct tail clamping
                for w in sanitized:
                    if w["start"] >= t_max:
                        w["start"] = max(0.0, round(t_max - min_word_duration, 3))
                    w["end"] = min(w["end"], round(t_max, 3))
                    if w["end"] <= w["start"]:
                        w["end"] = round(w["start"] + 0.01, 3)

    return sanitized


class ASSSubtitleGenerator:
    """Generates Advanced SubStation Alpha (.ass) subtitle files with karaoke tags for libass."""

    THEME_COLORS: Dict[str, Dict[str, str]] = {
        "scp_emerald": {
            "primary": "&H0000FF00",       # Bright Emerald Green (BGR)
            "secondary": "&H00FFFFFF",     # Crisp White (BGR)
            "outline": "&H00000000",       # Black
            "back": "&H80000000",          # Semi-transparent dark drop
            "font": "Montserrat Black",
        },
        "amber_crt": {
            "primary": "&H0000A5FF",       # Amber Orange (BGR #FFA500)
            "secondary": "&H00FFFFFF",
            "outline": "&H00000000",
            "back": "&H80000000",
            "font": "Inter Bold",
        },
        "tactical_amber": {
            "primary": "&H0000A5FF",       # Amber Orange alias
            "secondary": "&H00FFFFFF",
            "outline": "&H00000000",
            "back": "&H80000000",
            "font": "Inter Bold",
        },
        "cyber_cyan": {
            "primary": "&H00FFFF00",       # Cyan (BGR #00FFFF)
            "secondary": "&H00FFFFFF",
            "outline": "&H00000000",
            "back": "&H80000000",
            "font": "Montserrat Black",
        },
        "cosmic_cyan": {
            "primary": "&H00FFFF00",       # Cyan alias
            "secondary": "&H00FFFFFF",
            "outline": "&H00000000",
            "back": "&H80000000",
            "font": "Montserrat Black",
        },
        "crimson_alert": {
            "primary": "&H000000FF",       # Crimson Red (BGR #FF0000)
            "secondary": "&H00FFFFFF",
            "outline": "&H00000000",
            "back": "&H80000000",
            "font": "Montserrat Black",
        },
        "default": {
            "primary": "&H0000FFFF",       # Electric Yellow (BGR #FFFF00)
            "secondary": "&H00FFFFFF",
            "outline": "&H00000000",
            "back": "&H80000000",
            "font": "Montserrat Black",
        },
    }

    def __init__(self, fonts_dir: Optional[Union[str, Path]] = None) -> None:
        self.fonts_dir = Path(fonts_dir) if fonts_dir else Path("assets/fonts")

    def _resolve_font_hermetic(self, requested_font: str) -> str:
        """Resolve font name with hermetic disk fallback if requested font is missing."""
        if requested_font in ("Inter Bold", "Inter-Bold", "Inter"):
            inter_bold = self.fonts_dir / "Inter-Bold.ttf"
            inter_regular = self.fonts_dir / "Inter.ttf"
            if not inter_bold.exists() and not inter_regular.exists():
                # Fallback to Montserrat Black if present
                montserrat_black = self.fonts_dir / "Montserrat-Black.ttf"
                if montserrat_black.exists():
                    return "Montserrat Black"
        return requested_font

    def generate_ass_file(
        self,
        word_timestamps: Optional[List[Dict[str, Any]]],
        output_path: Union[str, Path],
        video_width: int = 1080,
        video_height: int = 1920,
        theme_name: str = "scp_emerald",
        words_per_cue: int = 3,
        margin_v: int = 260,
        font_name: Optional[str] = None,
        font_size: int = 56,
        karaoke_tag: str = r"\kf",
        **kwargs: Any,
    ) -> Path:
        """Generate a complete .ass file with karaoke word timing and safe area margin."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        sanitized = sanitize_timestamps(word_timestamps)
        theme = self.THEME_COLORS.get(theme_name, self.THEME_COLORS["default"])

        base_font = font_name or theme.get("font", "Montserrat Black")
        resolved_font = self._resolve_font_hermetic(base_font)

        primary_col = theme.get("primary", "&H0000FFFF")
        secondary_col = theme.get("secondary", "&H00FFFFFF")
        outline_col = theme.get("outline", "&H00000000")
        back_col = theme.get("back", "&H80000000")

        lines = [
            "[Script Info]",
            "Title: yt-auto Generated Subtitles",
            "ScriptType: v4.00+",
            f"PlayResX: {video_width}",
            f"PlayResY: {video_height}",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: Default,{resolved_font},{font_size},{primary_col},{secondary_col},{outline_col},{back_col},-1,0,0,0,100,100,0,0,1,4,0,2,40,40,{margin_v},0",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]

        if not sanitized:
            out.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return out

        cue_groups: List[List[Dict[str, Any]]] = []
        chunk_size = max(1, words_per_cue)
        for i in range(0, len(sanitized), chunk_size):
            cue_groups.append(sanitized[i : i + chunk_size])

        for group in cue_groups:
            cue_start = group[0]["start"]
            cue_end = group[-1]["end"]

            tokens: List[str] = []
            for w in group:
                dur_sec = max(0.01, w["end"] - w["start"])
                dur_cs = max(1, int(round(dur_sec * 100)))
                tag = karaoke_tag if karaoke_tag.startswith("\\") else f"\\{karaoke_tag}"
                tokens.append(f"{{{tag}{dur_cs}}}{w['word']}")

            cue_text = " ".join(tokens)
            start_str = format_ass_timestamp(cue_start)
            end_str = format_ass_timestamp(cue_end)
            lines.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{cue_text}")

        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return out


def force_pillow_subtitles_enabled(extra: Optional[Dict[str, Any]] = None) -> bool:
    """Opt-in only: Pillow frame-bridge subtitles are off by default (libass preferred).

    Enable with FORCE_PILLOW_SUBTITLES=1 or force_pillow_subtitles=True in call kwargs.
    """
    env = os.environ.get("FORCE_PILLOW_SUBTITLES", "").strip().lower()
    if env in ("1", "true", "yes", "on"):
        return True
    if extra and bool(extra.get("force_pillow_subtitles")):
        return True
    return False


def word_timestamps_from_cues(cues: Optional[List[Any]]) -> List[Dict[str, Any]]:
    """Flatten CodeSubtitleDrawer cues into word_timestamps for ASSSubtitleGenerator."""
    words: List[Dict[str, Any]] = []
    if not cues:
        return words
    for cue in cues:
        cue_words = getattr(cue, "words", None) or []
        for w in cue_words:
            text = getattr(w, "text", None) or getattr(w, "word", "") or ""
            if not str(text).strip():
                continue
            words.append(
                {
                    "word": str(text).strip(),
                    "start": float(getattr(w, "start_sec", getattr(w, "start", 0.0)) or 0.0),
                    "end": float(getattr(w, "end_sec", getattr(w, "end", 0.0)) or 0.0),
                }
            )
    return words


def write_ass_from_cues_or_words(
    *,
    output_path: Union[str, Path],
    word_timestamps: Optional[List[Dict[str, Any]]] = None,
    cues: Optional[List[Any]] = None,
    video_width: int = 1080,
    video_height: int = 1920,
    theme_name: str = "default",
    margin_v: int = 260,
    time_offset_sec: float = 0.0,
) -> Path:
    """Generate an ASS file from word timestamps or Pillow-era cues (libass path).

    time_offset_sec: subtract from cue times when burning onto a scene segment whose
    local timeline starts at 0 while cues are absolute (scene_start_sec).
    """
    stamps = list(word_timestamps or [])
    if not stamps and cues:
        stamps = word_timestamps_from_cues(cues)
    if time_offset_sec:
        shifted: List[Dict[str, Any]] = []
        for w in stamps:
            start = max(0.0, float(w.get("start", 0.0)) - float(time_offset_sec))
            end = max(start + 0.01, float(w.get("end", start)) - float(time_offset_sec))
            shifted.append({**w, "start": start, "end": end})
        stamps = shifted
    generator = ASSSubtitleGenerator()
    return generator.generate_ass_file(
        word_timestamps=stamps,
        output_path=output_path,
        video_width=video_width,
        video_height=video_height,
        theme_name=theme_name,
        margin_v=margin_v,
    )
