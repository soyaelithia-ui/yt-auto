"""
src/media/thumbnails/typography.py - High-CTR Dynamic Typography with 3D Effects and Multi-Pass Compositing.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Tuple, Union

from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont

logger = logging.getLogger("thumbnail_typography")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
FONTS_DIR = REPO_ROOT / "assets" / "fonts"


def _parse_color(color: Union[str, Tuple[int, ...]]) -> Tuple[int, int, int]:
    if isinstance(color, tuple):
        return color[:3]
    if isinstance(color, str):
        try:
            return ImageColor.getrgb(color)[:3]
        except Exception:
            return (255, 255, 255)
    return (255, 255, 255)


class DynamicTypographyEngine:
    """
    Renders high-impact YouTube thumbnail hook titles:
    - Optional ambient glow (off by default for CTR layouts)
    - Directional 3D drop shadow, crisp exterior stroke, core fill
    - Word-bounded wrap into at most 2 lines with shrink-to-fit
    """

    MAX_TITLE_LINES = 2
    ELLIPSIS = "…"
    BASE_MIN_FONT_PX = 28
    BASE_MIN_FONT_HEIGHT = 1080

    @classmethod
    def resolve_font(cls, font_name: str, size: int) -> ImageFont.FreeTypeFont:
        font_path = FONTS_DIR / font_name
        if font_path.is_file():
            try:
                return ImageFont.truetype(str(font_path), size=size)
            except Exception:
                pass
        # Fallbacks
        for alt in ["Montserrat-Black.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"]:
            p = FONTS_DIR / alt
            if p.is_file():
                try:
                    return ImageFont.truetype(str(p), size=size)
                except Exception:
                    pass
        try:
            return ImageFont.truetype("DejaVuSans-Bold.ttf", size=size)
        except Exception:
            return ImageFont.load_default()

    @classmethod
    def min_title_font_size(cls, canvas_height: int) -> int:
        """~28px at 1080p, scaled with canvas height."""
        h = max(1, int(canvas_height or cls.BASE_MIN_FONT_HEIGHT))
        return max(12, int(round(cls.BASE_MIN_FONT_PX * h / cls.BASE_MIN_FONT_HEIGHT)))

    @classmethod
    def split_title_to_safe_lines(
        cls,
        text: str,
        max_chars_per_line: int = 22,
        max_lines: int = MAX_TITLE_LINES,
    ) -> List[str]:
        """Split on word boundaries into at most two lines. Never cuts mid-word."""
        normalized = " ".join((text or "").split())
        words = normalized.split()
        if not words:
            return [normalized]

        if len(normalized) <= max_chars_per_line:
            return [normalized]

        max_lines = max(1, int(max_lines))
        lines: List[str] = []
        current: List[str] = []
        current_len = 0

        for idx, word in enumerate(words):
            extra = len(word) if not current else 1 + len(word)
            overflows = bool(current) and (current_len + extra) > max_chars_per_line
            if overflows:
                if len(lines) + 1 >= max_lines:
                    current.extend(words[idx:])
                    lines.append(" ".join(current))
                    return lines
                lines.append(" ".join(current))
                current = [word]
                current_len = len(word)
            else:
                current.append(word)
                current_len += extra

        if current:
            lines.append(" ".join(current))
        return lines[:max_lines]

    @classmethod
    def _text_width(cls, draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
        if not text:
            return 0
        box = draw.textbbox((0, 0), text, font=font)
        return box[2] - box[0]

    @classmethod
    def _wrap_words_to_width(
        cls,
        words: List[str],
        font: ImageFont.ImageFont,
        max_width: int,
        draw: ImageDraw.ImageDraw,
        max_lines: int = MAX_TITLE_LINES,
        ellipsis: bool = False,
    ) -> List[str]:
        if not words:
            return [""]

        def fits(ws: List[str], extra: str = "") -> bool:
            if not ws:
                return True
            return cls._text_width(draw, " ".join(ws) + extra, font) <= max_width

        if fits(words):
            return [" ".join(words)]

        lines: List[List[str]] = []
        remaining = list(words)
        max_lines = max(1, int(max_lines))

        for line_idx in range(max_lines):
            last = line_idx == max_lines - 1
            if last:
                if ellipsis and remaining:
                    acc: List[str] = []
                    leftover = remaining
                    for w in leftover:
                        trial = acc + [w]
                        if acc and not fits(trial, cls.ELLIPSIS):
                            break
                        acc.append(w)
                    if len(acc) < len(leftover):
                        if acc:
                            return [" ".join(x) for x in lines] + [" ".join(acc) + cls.ELLIPSIS]
                        # Single overflowing word: never mid-word cut.
                        return [" ".join(x) for x in lines] + [leftover[0] + cls.ELLIPSIS]
                    return [" ".join(x) for x in lines] + [" ".join(acc)]
                if remaining:
                    lines.append(remaining)
                break

            acc = []
            while remaining:
                trial = acc + [remaining[0]]
                if acc and not fits(trial):
                    break
                acc.append(remaining.pop(0))
                if len(acc) == 1 and not fits(acc):
                    break
            if acc:
                lines.append(acc)
            else:
                break

        return [" ".join(x) for x in lines if x]

    @classmethod
    def draw_text_with_effects(
        cls,
        canvas: Image.Image,
        text: str,
        pos_x: int,
        pos_y: int,
        max_width: int,
        font_name: str = "Montserrat-Black.ttf",
        font_size: Optional[int] = None,
        fill_color: Union[str, Tuple[int, ...]] = "#FFE600",
        stroke_color: Union[str, Tuple[int, ...]] = "#000000",
        stroke_width: int = 12,
        shadow_offset: Tuple[int, int] = (8, 12),
        shadow_blur: int = 4,
        glow_color: Optional[Union[str, Tuple[int, ...]]] = None,
        glow_radius: int = 0,
        tilt_angle: float = 0.0,
        line_spacing_mult: float = 1.15,
        align: str = "center",
    ) -> Image.Image:
        """
        Executes 4-pass 3D typography rendering:
        1. Ambient diffuse glow (Gaussian blurred)
        2. Directional 3D drop shadow (offset + blurred)
        3. Crisp outer stroke
        4. Foreground core fill
        """
        w, h = canvas.size
        is_vertical = h > w

        if font_size is None:
            font_size = int(w * (0.09 if is_vertical else 0.075))
            font_size = max(48, min(120, font_size))

        words = " ".join((text or "").replace("\n", " ").split()).split()
        if not words:
            words = [(text or "").strip() or ""]

        dummy_img = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
        dummy_draw = ImageDraw.Draw(dummy_img)
        min_font = cls.min_title_font_size(h)
        size = max(min_font, int(font_size))
        lines: List[str] = []
        fnt = cls.resolve_font(font_name, size)

        while True:
            fnt = cls.resolve_font(font_name, size)
            lines = cls._wrap_words_to_width(
                words,
                fnt,
                max_width,
                dummy_draw,
                max_lines=cls.MAX_TITLE_LINES,
                ellipsis=False,
            )
            overflows = any(cls._text_width(dummy_draw, line, fnt) > max_width for line in lines)
            if not overflows:
                break
            if size <= min_font:
                lines = cls._wrap_words_to_width(
                    words,
                    fnt,
                    max_width,
                    dummy_draw,
                    max_lines=cls.MAX_TITLE_LINES,
                    ellipsis=True,
                )
                break
            nxt = max(min_font, int(size * 0.92))
            if nxt >= size:
                nxt = size - 1
            size = nxt

        font_size = size
        fnt = cls.resolve_font(font_name, font_size)
        if not lines:
            lines = [" ".join(words)]

        pad = 250
        temp_w = int(max_width + pad * 2)
        line_h = int(font_size * line_spacing_mult)
        temp_h = int(len(lines) * line_h + pad * 2)

        glow_rgb = _parse_color(glow_color) if glow_color else None
        fill_rgb = _parse_color(fill_color)
        stroke_rgb = _parse_color(stroke_color)

        # Measure lines
        line_widths = [
            dummy_draw.textbbox((0, 0), line, font=fnt)[2] - dummy_draw.textbbox((0, 0), line, font=fnt)[0]
            for line in lines
        ]

        # Layer 1: Ambient Diffuse Glow
        glow_layer = Image.new("RGBA", (temp_w, temp_h), (0, 0, 0, 0))
        if glow_rgb and glow_radius > 0:
            draw_glow = ImageDraw.Draw(glow_layer)
            cur_y = pad
            for idx, line in enumerate(lines):
                lw = line_widths[idx]
                cur_x = (temp_w - lw) // 2 if align == "center" else pad
                draw_glow.text(
                    (cur_x, cur_y),
                    line,
                    font=fnt,
                    fill=(*glow_rgb, 200),
                    stroke_width=stroke_width + glow_radius,
                    stroke_fill=(*glow_rgb, 200),
                )
                cur_y += line_h
            glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=glow_radius))

        # Layer 2: Directional 3D Drop Shadow
        shadow_layer = Image.new("RGBA", (temp_w, temp_h), (0, 0, 0, 0))
        draw_shadow = ImageDraw.Draw(shadow_layer)
        cur_y = pad + shadow_offset[1]
        for idx, line in enumerate(lines):
            lw = line_widths[idx]
            cur_x = ((temp_w - lw) // 2 if align == "center" else pad) + shadow_offset[0]
            draw_shadow.text(
                (cur_x, cur_y),
                line,
                font=fnt,
                fill=(0, 0, 0, 240),
                stroke_width=stroke_width + 4,
                stroke_fill=(0, 0, 0, 240),
            )
            cur_y += line_h
        if shadow_blur > 0:
            shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=shadow_blur))

        # Layer 3 & 4: Crisp Stroke & High-Visibility Core Fill
        core_layer = Image.new("RGBA", (temp_w, temp_h), (0, 0, 0, 0))
        draw_core = ImageDraw.Draw(core_layer)
        cur_y = pad
        for idx, line in enumerate(lines):
            lw = line_widths[idx]
            cur_x = (temp_w - lw) // 2 if align == "center" else pad
            # 3. Stroke
            draw_core.text(
                (cur_x, cur_y),
                line,
                font=fnt,
                fill=(*stroke_rgb, 255),
                stroke_width=stroke_width,
                stroke_fill=(*stroke_rgb, 255),
            )
            # 4. Fill
            draw_core.text(
                (cur_x, cur_y),
                line,
                font=fnt,
                fill=(*fill_rgb, 255),
            )
            cur_y += line_h

        # Combine typography layers
        combined = Image.alpha_composite(glow_layer, shadow_layer)
        combined = Image.alpha_composite(combined, core_layer)

        # Apply tilt angle
        if abs(tilt_angle) > 0.1:
            combined = combined.rotate(tilt_angle, resample=Image.Resampling.BICUBIC, expand=True)

        # Position and paste onto canvas
        rot_w, rot_h = combined.size
        if align == "center":
            center_x = pos_x + max_width // 2
            center_y = pos_y + (len(lines) * line_h) // 2
            paste_x = center_x - rot_w // 2
            paste_y = center_y - rot_h // 2
        else:
            paste_x = pos_x - pad - (rot_w - temp_w) // 2
            paste_y = pos_y - pad - (rot_h - temp_h) // 2

        canvas_rgba = canvas.convert("RGBA")
        canvas_rgba.paste(combined, (paste_x, paste_y), combined)
        return canvas_rgba.convert("RGB")

    @classmethod
    def render_hook_title(
        cls,
        canvas: Image.Image,
        text: str,
        pos_x: int,
        pos_y: int,
        max_width: int,
        font_name: str = "Montserrat-Black.ttf",
        primary_color: str = "#FFE600",
        accent_color: str = "#FF003B",
        tilt_angle: float = -3.5,
        base_font_size: Optional[int] = None,
    ) -> Image.Image:
        """
        Renders hook title using 4-pass draw_text_with_effects.
        """
        hook_text = " ".join((text or "").strip().upper().replace("\n", " ").split())
        return cls.draw_text_with_effects(
            canvas=canvas,
            text=hook_text,
            pos_x=pos_x,
            pos_y=pos_y,
            max_width=max_width,
            font_name=font_name,
            font_size=base_font_size,
            fill_color=primary_color,
            stroke_color="#000000",
            stroke_width=12,
            shadow_offset=(8, 12),
            shadow_blur=4,
            glow_color=None,
            glow_radius=0,
            tilt_angle=tilt_angle,
        )
