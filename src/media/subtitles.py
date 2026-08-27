"""
src/media/subtitle_drawer.py - Programmatic Subtitle Engine.

Renders high-impact, modern viral-style karaoke subtitles directly in code (Python Pillow / Canvas2D)
with word-by-word active highlighting, neon glows, rounded backdrop pills, and strict safe-area placement.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from src.log import get_logger

logger = get_logger("subtitle_drawer")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_FONT_PATH = ROOT_DIR / "assets" / "fonts" / "Montserrat-Black.ttf"


@dataclass
class SubtitleWord:
    text: str
    start_sec: float
    end_sec: float


@dataclass
class SubtitleCue:
    words: List[SubtitleWord]
    start_sec: float
    end_sec: float
    full_text: str = ""

    def is_active(self, t: float) -> bool:
        return self.start_sec <= t <= self.end_sec


@dataclass
class SubtitleTheme:
    font_path: Path = DEFAULT_FONT_PATH
    font_size: int = 54
    active_color: Tuple[int, int, int, int] = (0, 255, 102, 255)  # Emerald Neon
    inactive_color: Tuple[int, int, int, int] = (255, 255, 255, 245)  # Crisp White
    stroke_color: Tuple[int, int, int, int] = (0, 0, 0, 255)  # Pitch Black Outline
    stroke_width: int = 4
    bg_pill_color: Tuple[int, int, int, int] = (4, 12, 8, 195)  # Semi-transparent Dark Pill
    bg_pill_border: Optional[Tuple[int, int, int, int]] = (0, 255, 102, 140)  # Subtle Neon Trim
    bg_pill_radius: int = 18
    safe_margin_bottom: int = 380  # Safe vertical margin above Shorts/TikTok UI
    shadow_offset: Tuple[int, int] = (0, 4)
    shadow_color: Tuple[int, int, int, int] = (0, 0, 0, 180)


THEME_PRESETS: Dict[str, SubtitleTheme] = {
    "scp_neon": SubtitleTheme(
        active_color=(0, 255, 102, 255),  # SCP Emerald Green
        bg_pill_color=(3, 12, 6, 210),
        bg_pill_border=(0, 255, 102, 160),
    ),
    "viral_yellow": SubtitleTheme(
        active_color=(255, 230, 0, 255),  # Electric Yellow
        bg_pill_color=(10, 10, 10, 205),
        bg_pill_border=(255, 230, 0, 120),
    ),
    "horror_crimson": SubtitleTheme(
        active_color=(255, 50, 50, 255),  # Blood Red
        bg_pill_color=(12, 2, 2, 215),
        bg_pill_border=(255, 40, 40, 150),
    ),
    "drama_warm": SubtitleTheme(
        active_color=(255, 180, 50, 255),  # Warm Amber
        bg_pill_color=(18, 14, 10, 190),
        bg_pill_border=(255, 180, 50, 100),
    ),
}


class CodeSubtitleDrawer:
    """
    Renders word-synced karaoke subtitles directly onto frame buffers in memory.
    """

    def __init__(self, theme: Optional[SubtitleTheme] = None, font_size: Optional[int] = None) -> None:
        self.theme = theme or THEME_PRESETS["scp_neon"]
        if font_size:
            self.theme.font_size = font_size
        self._font_cache: Dict[int, ImageFont.FreeTypeFont] = {}

    def _get_font(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        if size not in self._font_cache:
            font_file = self.theme.font_path
            if font_file.is_file():
                try:
                    self._font_cache[size] = ImageFont.truetype(str(font_file), size)
                except Exception as e:
                    logger.warning("Failed to load font %s: %s. Using default font.", font_file, e)
                    return ImageFont.load_default()
            else:
                return ImageFont.load_default()
        return self._font_cache[size]

    @staticmethod
    def parse_word_timestamps(
        word_timestamps: List[Dict[str, Any]],
        words_per_cue: int = 3,
        max_chars: int = 26,
    ) -> List[SubtitleCue]:
        """
        Groups stream of raw word timestamps into short, high-energy subtitle cues (2-4 words).
        """
        if not word_timestamps:
            return []

        cues: List[SubtitleCue] = []
        current_words: List[SubtitleWord] = []
        current_char_len = 0

        for stamp in word_timestamps:
            w_text = str(stamp.get("word", "")).strip()
            if not w_text:
                continue
            w_start = float(stamp.get("start", 0.0))
            w_end = float(stamp.get("end", w_start + 0.3))

            word_obj = SubtitleWord(text=w_text, start_sec=w_start, end_sec=w_end)

            if len(current_words) >= words_per_cue or (current_char_len + len(w_text) > max_chars and current_words):
                cue_start = current_words[0].start_sec
                cue_end = current_words[-1].end_sec
                full_txt = " ".join([w.text for w in current_words])
                cues.append(SubtitleCue(words=current_words, start_sec=cue_start, end_sec=cue_end, full_text=full_txt))
                current_words = [word_obj]
                current_char_len = len(w_text)
            else:
                current_words.append(word_obj)
                current_char_len += len(w_text) + 1

        if current_words:
            cue_start = current_words[0].start_sec
            cue_end = current_words[-1].end_sec
            full_txt = " ".join([w.text for w in current_words])
            cues.append(SubtitleCue(words=current_words, start_sec=cue_start, end_sec=cue_end, full_text=full_txt))

        # Ensure cue end times span continuously to avoid jarring flashing
        for i in range(len(cues) - 1):
            if cues[i + 1].start_sec - cues[i].end_sec < 0.4:
                cues[i].end_sec = cues[i + 1].start_sec

        return cues

    def draw_on_frame(
        self,
        frame: Image.Image,
        current_time_sec: float,
        cues: List[SubtitleCue],
        theme_override: Optional[SubtitleTheme] = None,
    ) -> Image.Image:
        """
        Draws active subtitle cue onto image frame buffer.
        """
        if not cues:
            return frame

        # Find active cue
        active_cue: Optional[SubtitleCue] = None
        for cue in cues:
            if cue.is_active(current_time_sec):
                active_cue = cue
                break

        if not active_cue:
            return frame

        theme = theme_override or self.theme
        w_img, h_img = frame.size

        # Responsive font sizing: 54px for 1080x1920, 36px for horizontal
        is_vertical = h_img > w_img
        dynamic_font_size = theme.font_size if is_vertical else int(theme.font_size * 0.72)
        font = self._get_font(dynamic_font_size)

        # Measure words
        words_data = []
        total_text_width = 0
        space_width = 16
        line_height = dynamic_font_size + 8

        for word in active_cue.words:
            # Uppercase for viral punchy impact
            display_text = word.text.upper()
            bbox = font.getbbox(display_text)
            w_w = bbox[2] - bbox[0]
            w_h = bbox[3] - bbox[1]
            line_height = max(line_height, w_h)
            
            # Check if this specific word is currently being spoken
            is_active_word = (word.start_sec <= current_time_sec <= word.end_sec) or (
                # If current_time is at end of cue, highlight last word
                word == active_cue.words[-1] and current_time_sec >= word.start_sec
            )

            words_data.append({
                "text": display_text,
                "width": w_w,
                "height": w_h,
                "is_active": is_active_word,
                "raw_word": word,
            })
            total_text_width += w_w + space_width

        total_text_width -= space_width  # Remove trailing space

        # Position calculation inside safe area
        pad_x = 28
        pad_y = 16
        box_w = total_text_width + pad_x * 2
        box_h = line_height + pad_y * 2

        center_x = w_img // 2
        safe_margin = theme.safe_margin_bottom if is_vertical else 120
        box_y = h_img - safe_margin - box_h
        box_x = center_x - (box_w // 2)

        # Localized fast patch composite (100x faster than full 1080x1920 alpha composite)
        pill_rect = (box_x, box_y, box_x + box_w, box_y + box_h)
        patch = frame.crop(pill_rect).convert("RGBA")
        patch_pill = Image.new("RGBA", patch.size, (0, 0, 0, 0))
        patch_draw = ImageDraw.Draw(patch_pill)
        patch_draw.rounded_rectangle(
            [0, 0, box_w, box_h],
            radius=theme.bg_pill_radius,
            fill=theme.bg_pill_color,
            outline=theme.bg_pill_border,
            width=2 if theme.bg_pill_border else 0,
        )
        patch = Image.alpha_composite(patch, patch_pill)
        frame.paste(patch.convert("RGB"), (box_x, box_y))

        draw = ImageDraw.Draw(frame)
        cursor_x = box_x + pad_x
        baseline_y = box_y + pad_y + 2

        for wd in words_data:
            text = wd["text"]
            is_active = wd["is_active"]
            fill_color = theme.active_color[:3] if is_active else theme.inactive_color[:3]
            stroke_col = theme.stroke_color[:3]
            shadow_col = theme.shadow_color[:3]

            # Drop Shadow
            draw.text(
                (cursor_x + theme.shadow_offset[0], baseline_y + theme.shadow_offset[1]),
                text,
                font=font,
                fill=shadow_col,
                stroke_width=theme.stroke_width,
                stroke_fill=shadow_col,
            )

            # Main text with stroke
            draw.text(
                (cursor_x, baseline_y),
                text,
                font=font,
                fill=fill_color,
                stroke_width=theme.stroke_width + (1 if is_active else 0),
                stroke_fill=stroke_col,
            )

            cursor_x += wd["width"] + space_width

        return frame


def apply_code_subtitles_to_video(
    input_mp4: Union[Path, str],
    output_mp4: Union[Path, str],
    subtitle_cues: List[SubtitleCue],
    scene_start_sec: float,
    width: int,
    height: int,
    fps: int,
    crf: int = 18,
    subtitle_theme: Optional[SubtitleTheme] = None,
    drawer: Optional[CodeSubtitleDrawer] = None,
) -> Path:
    """
    Overlays programmatic code-rendered subtitles onto a video file frame-by-frame.
    """
    import subprocess
    in_path = Path(input_mp4).resolve()
    out_path = Path(output_mp4).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    if not subtitle_cues:
        import shutil
        shutil.copy2(in_path, out_path)
        return out_path

    drawer = drawer or CodeSubtitleDrawer(theme=subtitle_theme)
    read_cmd = [
        "ffmpeg", "-y", "-i", str(in_path),
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"
    ]
    write_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps),
        "-i", "-",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
        "-crf", str(crf), "-preset", "faster", "-b:v", "4500k", "-maxrate", "6000k", "-bufsize", "8000k", "-threads", "0", "-movflags", "+faststart",
        str(out_path),
    ]

    frame_size = width * height * 3
    proc_in = subprocess.Popen(read_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    proc_out = subprocess.Popen(write_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    frame_idx = 0
    while True:
        raw_bytes = proc_in.stdout.read(frame_size) if proc_in.stdout else b""
        if not raw_bytes or len(raw_bytes) < frame_size:
            break
        img = Image.frombytes("RGB", (width, height), raw_bytes)
        t_sec = scene_start_sec + (frame_idx / float(fps))
        img = drawer.draw_on_frame(img, t_sec, subtitle_cues, theme_override=subtitle_theme)
        if proc_out.stdin:
            proc_out.stdin.write(img.tobytes())
        frame_idx += 1

    if proc_in.stdout:
        proc_in.stdout.close()
    proc_in.wait()
    if proc_out.stdin:
        proc_out.stdin.flush()
        proc_out.stdin.close()
    proc_out.wait()
    return out_path
