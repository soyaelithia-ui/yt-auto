"""Shared thumbnail script helpers (deduped from design_*_thumbnails)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# scripts/lib/thumb_common.py → parents[2] = repo root (not scripts/)
REPO_ROOT = Path(__file__).resolve().parents[2]


def resolve_thumbnail_output_dir(custom_path: str | Path | None = None) -> Path:
    if custom_path:
        target = Path(custom_path).resolve()
    elif os.getenv("YT_THUMBNAILS_DIR"):
        target = Path(os.environ["YT_THUMBNAILS_DIR"]).resolve()
    else:
        target = (REPO_ROOT / "artifacts" / "thumbnails").resolve()

    # Enforce Strict Confinement Guardrail
    try:
        target.relative_to(REPO_ROOT)
    except ValueError:
        raise PermissionError(
            f"Security Violation: Target path '{target}' escapes workspace root '{REPO_ROOT}'."
        )

    target.mkdir(parents=True, exist_ok=True)
    return target


def get_font(size: int) -> ImageFont.FreeTypeFont:
    font_path = REPO_ROOT / "assets" / "fonts" / "Montserrat-Black.ttf"
    if not font_path.exists():
        raise FileNotFoundError(f"Required font asset does not exist: {font_path}")
    return ImageFont.truetype(str(font_path), size=size)


def draw_text_with_effects(
    draw: ImageDraw.ImageDraw,
    canvas_size: Tuple[int, int],
    text: str,
    position: Tuple[int, int],
    font: ImageFont.FreeTypeFont,
    text_color: str = "#FFFFFF",
    stroke_color: str = "#000000",
    stroke_width: int = 8,
    shadow_offset: Tuple[int, int] = (6, 8),
    shadow_color: Tuple[int, int, int, int] = (0, 0, 0, 220),
    glow_color: Optional[Tuple[int, int, int, int]] = None,
    glow_radius: int = 15,
) -> Tuple[int, int, int, int]:
    """Draws heavy text with multi-layer shadow, stroke and optional ambient glow."""
    x, y = position
    w, h = canvas_size

    # 1. Glow layer if requested
    if glow_color:
        glow_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        g_draw = ImageDraw.Draw(glow_layer)
        g_draw.text(
            (x, y),
            text,
            font=font,
            fill=glow_color,
            stroke_width=stroke_width + glow_radius,
            stroke_fill=glow_color,
        )
        glow_blurred = glow_layer.filter(ImageFilter.GaussianBlur(glow_radius))
        draw._image.paste(glow_blurred, (0, 0), glow_blurred)

    # 2. Heavy drop shadow
    sx, sy = shadow_offset
    shadow_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow_layer)
    s_draw.text(
        (x + sx, y + sy),
        text,
        font=font,
        fill=shadow_color,
        stroke_width=stroke_width + 4,
        stroke_fill=shadow_color,
    )
    shadow_blurred = shadow_layer.filter(ImageFilter.GaussianBlur(6))
    draw._image.paste(shadow_blurred, (0, 0), shadow_blurred)

    # 3. Main text with stroke
    draw.text(
        (x, y),
        text,
        font=font,
        fill=text_color,
        stroke_width=stroke_width,
        stroke_fill=stroke_color,
    )

    bbox = font.getbbox(text)
    return (x, y, x + (bbox[2] - bbox[0]), y + (bbox[3] - bbox[1]))
