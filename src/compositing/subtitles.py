"""
src/compositing/subtitles.py - Dynamic Word-Level Karaoke Terminal Subtitles (ASS).

Generates Advanced SubStation Alpha (.ass) subtitles with retro computer terminal fonts,
word-by-word karaoke synchronization (\\k tags), safe-area positioning, and phosphor highlighting.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from src.log import get_logger

logger = get_logger("karaoke_subtitles")


def format_ass_timestamp(seconds: float) -> str:
    """Formats float seconds into ASS timestamp format: H:MM:SS.cs (centiseconds)."""
    total_cs = max(0, int(round(seconds * 100)))
    hours = total_cs // 360000
    remainder = total_cs % 360000
    minutes = remainder // 6000
    remainder = remainder % 6000
    secs = remainder // 100
    cs = remainder % 100
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def hex_to_ass_color(hex_str: str, alpha: str = "00") -> str:
    """Converts #RRGGBB hex color to ASS &HAABBGGRR& format."""
    if not hex_str:
        return f"&H{alpha}FFFFFF&"
    if hex_str.startswith("&H") and hex_str.endswith("&"):
        return hex_str
    clean = hex_str.replace("#", "").strip()
    if len(clean) == 3:
        clean = "".join([c * 2 for c in clean])
    if len(clean) == 6:
        r, g, b = clean[0:2], clean[2:4], clean[4:6]
        return f"&H{alpha}{b.upper()}{g.upper()}{r.upper()}&"
    elif len(clean) == 8:
        r, g, b, a = clean[0:2], clean[2:4], clean[4:6], clean[6:8]
        return f"&H{a.upper()}{b.upper()}{g.upper()}{r.upper()}&"
    return f"&H{alpha}FFFFFF&"


class TerminalKaraokeSubtitleGenerator:
    """Generates phosphor-green terminal karaoke ASS subtitles."""

    def __init__(
        self,
        font_name: str = "Courier New",
        active_color: str = "&H0066FF00&",     # Phosphor green active highlight (ASS BGR: &H00BBGGRR&)
        inactive_color: str = "&H00FFFFFF&",   # Crisp white inactive text
        outline_color: str = "&H00000000&",    # Pure black stroke
        background_box_color: str = "&H90051208&",  # Translucent dark abyssal green backdrop
    ) -> None:
        self.font_name = font_name
        self.active_color = hex_to_ass_color(active_color) if active_color.startswith("#") else active_color
        self.inactive_color = hex_to_ass_color(inactive_color) if inactive_color.startswith("#") else inactive_color
        self.outline_color = hex_to_ass_color(outline_color) if outline_color.startswith("#") else outline_color
        self.background_box_color = hex_to_ass_color(background_box_color, alpha="90") if background_box_color.startswith("#") else background_box_color

    def generate_ass(
        self,
        word_timestamps: List[Dict[str, Any]],
        output_ass_path: Union[str, Path],
        width: int = 1080,
        height: int = 1920,
        words_per_cue: int = 3,
        downward_drift_px: int = 0,
    ) -> Path:
        """
        Groups word timestamps into short high-impact cues (2-4 words) with ASS \\k karaoke tags.
        """
        out_p = Path(output_ass_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)

        if not word_timestamps:
            # Generate empty valid ASS header
            out_p.write_text(self._build_header(width, height, downward_drift_px=downward_drift_px), encoding="utf-8")
            return out_p

        # Group words into cues
        cues = self._group_words_to_cues(word_timestamps, max_words=words_per_cue)

        ass_lines = [self._build_header(width, height, downward_drift_px=downward_drift_px)]
        ass_lines.append("[Events]")
        ass_lines.append("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text")

        for cue in cues:
            start_val = max(0.0, float(cue["start_sec"]))
            end_val = max(start_val + 0.1, float(cue["end_sec"]))
            start_str = format_ass_timestamp(start_val)
            end_str = format_ass_timestamp(end_val)

            # Build karaoke formatted string
            # In ASS: {\k<centiseconds>}word
            karaoke_text_parts = []
            prev_w_end = start_val
            for w in cue["words"]:
                w_start = float(w["start"])
                w_end = float(w["end"])
                if w_start > prev_w_end:
                    gap_cs = int(round((w_start - prev_w_end) * 100))
                    if gap_cs > 0:
                        karaoke_text_parts.append(f"{{\\k{gap_cs}}}")
                dur_cs = max(1, int(round((w_end - w_start) * 100)))
                # Highlight active word with phosphor green
                clean_w = str(w["word"]).strip()
                karaoke_text_parts.append(f"{{\\k{dur_cs}}}{clean_w}")
                prev_w_end = w_end

            text_line = " ".join(karaoke_text_parts)
            ass_lines.append(
                f"Dialogue: 0,{start_str},{end_str},TerminalKaraoke,,0,0,0,,{text_line}"
            )

        out_p.write_text("\n".join(ass_lines), encoding="utf-8")
        logger.info("Subtítulos ASS terminal generados: %s (%d cues)", out_p.name, len(cues))
        return out_p

    def _group_words_to_cues(
        self,
        word_timestamps: List[Dict[str, Any]],
        max_words: int = 3,
    ) -> List[Dict[str, Any]]:
        cues: List[Dict[str, Any]] = []
        current_words: List[Dict[str, Any]] = []

        for stamp in word_timestamps:
            w_text = str(stamp.get("word", stamp.get("w", ""))).strip()
            if not w_text:
                continue
            
            w_start = max(0.0, float(stamp.get("start", stamp.get("s", 0.0))))
            w_end = max(w_start + 0.05, float(stamp.get("end", stamp.get("e", w_start + 0.3))))
            word_obj = {
                "word": w_text,
                "start": w_start,
                "end": w_end,
            }

            if len(current_words) >= max_words:
                cues.append({
                    "start_sec": current_words[0]["start"],
                    "end_sec": max(current_words[0]["start"] + 0.1, current_words[-1]["end"]),
                    "words": current_words,
                })
                current_words = [word_obj]
            else:
                current_words.append(word_obj)

        if current_words:
            cues.append({
                "start_sec": current_words[0]["start"],
                "end_sec": max(current_words[0]["start"] + 0.1, current_words[-1]["end"]),
                "words": current_words,
            })

        # Ensure continuity and strictly positive duration
        for i in range(len(cues) - 1):
            if cues[i]["end_sec"] > cues[i + 1]["start_sec"]:
                cues[i]["end_sec"] = max(cues[i]["start_sec"] + 0.05, cues[i + 1]["start_sec"])
            elif cues[i + 1]["start_sec"] - cues[i]["end_sec"] < 0.25:
                cues[i]["end_sec"] = cues[i + 1]["start_sec"]

        return cues

    def _build_header(self, width: int, height: int, downward_drift_px: int = 0) -> str:
        # Centered vertically in the lower-middle safe zone (alignment = 2 / bottom-center with margin)
        # Guarantees >= 480px margin for portrait (clearing mobile UI controls) and >= 130px for landscape.
        base_margin_v = max(480, int(height * 0.25)) if height > width else max(130, int(height * 0.12))
        margin_v = base_margin_v + max(0, int(downward_drift_px))
        font_size = int(height * 0.038) if height > width else int(height * 0.055)

        return f"""[Script Info]
Title: Cosmic Analog Horror Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: {width}
PlayResY: {height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: TerminalKaraoke,{self.font_name},{font_size},{self.active_color},{self.inactive_color},{self.outline_color},{self.background_box_color},-1,0,0,0,100,100,1,0,1,3,2,2,40,40,{margin_v},1
"""
