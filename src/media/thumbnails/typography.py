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
    - 4-Pass 3D Typography:
        Pass 1: Ambient Diffuse Glow
        Pass 2: Directional 3D Drop Shadow
        Pass 3: Crisp Exterior Stroke
        Pass 4: Foreground Vibrant Core Fill
    - Dynamic safe-line splitting for high-CTR dramatic titles.
    - Angled tilt (-3.5° to +4°) for urgent visual energy.
    """

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
    def split_title_to_safe_lines(cls, text: str, max_chars_per_line: int = 22) -> List[str]:
        """
        Splits text into 2-3 safe lines, preserving words and dramatic punctuation.
        """
        text = text.strip()
        words = text.split()
        if not words:
            return [text]

        if len(text) <= max_chars_per_line and len(words) <= 3:
            return [text]

        lines: List[str] = []
        current_line: List[str] = []
        current_len = 0

        for word in words:
            w_len = len(word)
            if current_line and (current_len + 1 + w_len) > max_chars_per_line:
                lines.append(" ".join(current_line))
                current_line = [word]
                current_len = w_len
            else:
                current_line.append(word)
                current_len += (1 if current_line else 0) + w_len

        if current_line:
            lines.append(" ".join(current_line))

        if len(lines) > 3:
            rem_words = [w for l in lines[2:] for w in l.split()]
            l3_words = []
            cur = 0
            for w in rem_words:
                if not l3_words or (cur + 1 + len(w)) <= max_chars_per_line:
                    l3_words.append(w)
                    cur += (1 if l3_words else 0) + len(w)
                else:
                    break
            if len(l3_words) < len(rem_words):
                l3 = " ".join(l3_words).rstrip(".,:;!?") + "..."
            else:
                l3 = " ".join(l3_words)
            lines = [lines[0], lines[1], l3]

        return lines

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
        glow_color: Optional[Union[str, Tuple[int, ...]]] = "#FF003B",
        glow_radius: int = 8,
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

        # Break text into lines
        if "\n" in text:
            lines = [l.strip() for l in text.split("\n") if l.strip()]
        else:
            threshold_len = 16 if is_vertical else 26
            max_chars = 15 if is_vertical else 20
            if len(text) > threshold_len:
                lines = cls.split_title_to_safe_lines(text, max_chars_per_line=max_chars)
            else:
                lines = [text.strip()]

        if not lines:
            lines = [text]

        # Auto-scale font_size down if any line width exceeds max_width
        dummy_img = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
        dummy_draw = ImageDraw.Draw(dummy_img)
        while font_size > 24:
            fnt = cls.resolve_font(font_name, font_size)
            max_lw = max(
                dummy_draw.textbbox((0, 0), line, font=fnt)[2] - dummy_draw.textbbox((0, 0), line, font=fnt)[0]
                for line in lines
            )
            if max_lw <= max_width:
                break
            font_size = max(20, int(font_size * 0.92))

        fnt = cls.resolve_font(font_name, font_size)

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
            paste_x = pos_x - pad
            paste_y = pos_y - pad

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
        # Clean text into 2-4 punchy words if very long
        words = text.strip().upper().replace("\n", " ").split()
        if len(words) > 5:
            words = words[:4]
            hook_text = " ".join(words)
        else:
            hook_text = text.strip().upper()

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
            glow_color=accent_color,
            glow_radius=8,
            tilt_angle=tilt_angle,
        )
