"""
src/media/thumbnails/typography.py - High-CTR Dynamic Typography with Double Strokes and Gaussian Shadows.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

logger = logging.getLogger("thumbnail_typography")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
FONTS_DIR = REPO_ROOT / "assets" / "fonts"


class DynamicTypographyEngine:
    """
    Renders high-impact YouTube thumbnail hook titles:
    - 2-4 emotional words in uppercase.
    - Angled tilt (-3.5° to +4°) for urgent visual energy.
    - Multi-layer drop shadow with Gaussian diffusion.
    - Double perimeter stroke (heavy black outline + neon accent glow).
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
        w, h = canvas.size
        is_vertical = h > w

        # Auto font sizing
        if not base_font_size:
            base_font_size = int(w * (0.09 if is_vertical else 0.075))
            base_font_size = max(52, min(120, base_font_size))

        fnt = cls.resolve_font(font_name, base_font_size)

        # Clean text into 2-4 punchy words
        words = text.strip().upper().replace("\n", " ").split()
        if len(words) > 5:
            words = words[:4]
        
        # Word wrap into 1 or 2 lines
        lines: List[str] = []
        if len(words) <= 2:
            lines.append(" ".join(words))
        elif len(words) == 3:
            lines.append(words[0])
            lines.append(f"{words[1]} {words[2]}")
        else:
            lines.append(f"{words[0]} {words[1]}")
            lines.append(f"{words[2]} {words[3]}")

        # Render text block on temporary transparent canvas for rotation
        temp_pad = 200
        temp_w = int(max_width + temp_pad * 2)
        line_height = int(base_font_size * 1.15)
        temp_h = int(len(lines) * line_height + temp_pad * 2)

        txt_img = Image.new("RGBA", (temp_w, temp_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(txt_img)

        # Draw lines
        cur_y = temp_pad
        for idx, line in enumerate(lines):
            fill_col = primary_color if idx == 0 else accent_color
            bbox = draw.textbbox((0, 0), line, font=fnt)
            line_w = bbox[2] - bbox[0]
            cur_x = (temp_w - line_w) // 2

            # 1. Diffuse Deep Drop Shadow (multi-offset)
            shadow_stroke = max(8, base_font_size // 8)
            draw.text(
                (cur_x + 8, cur_y + 8),
                line,
                font=fnt,
                fill=(0, 0, 0, 240),
                stroke_width=shadow_stroke + 4,
                stroke_fill=(0, 0, 0, 240),
            )

            # 2. Heavy Black Outer Stroke
            draw.text(
                (cur_x, cur_y),
                line,
                font=fnt,
                fill=(0, 0, 0, 255),
                stroke_width=shadow_stroke,
                stroke_fill=(0, 0, 0, 255),
            )

            # 3. Bright Vibrant Core Fill
            draw.text(
                (cur_x, cur_y),
                line,
                font=fnt,
                fill=fill_col,
            )

            cur_y += line_height

        # Diffuse blur on shadow
        shadow_blur = txt_img.filter(ImageFilter.GaussianBlur(radius=3))
        txt_composite = Image.alpha_composite(shadow_blur, txt_img)

        # Rotate text by tilt angle
        if abs(tilt_angle) > 0.1:
            txt_composite = txt_composite.rotate(tilt_angle, resample=Image.Resampling.BICUBIC, expand=True)

        # Precision composite onto canvas
        rot_w, rot_h = txt_composite.size
        center_x = pos_x + max_width // 2
        center_y = pos_y + (len(lines) * line_height) // 2
        paste_x = center_x - rot_w // 2
        paste_y = center_y - rot_h // 2
        
        canvas_rgba = canvas.convert("RGBA")
        canvas_rgba.paste(txt_composite, (paste_x, paste_y), txt_composite)

        return canvas_rgba.convert("RGB")
