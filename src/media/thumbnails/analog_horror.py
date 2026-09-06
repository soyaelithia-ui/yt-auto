"""Analog-horror / found-footage grade helpers for thumbnails (Aelithia quality bar).

Matches craft cues from the approved quality ref: VHS grain, scanlines,
chromatic aberration, cyan/green cast, deep blacks, pixel camcorder OSD.
"""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFont


def apply_cyan_green_cast(img: Image.Image, strength: float = 0.28) -> Image.Image:
    """Push midtones toward aged VHS green/cyan while keeping red accents readable."""
    rgb = img.convert("RGB")
    arr = np.asarray(rgb, dtype=np.float32)
    cast = np.zeros_like(arr)
    cast[:, :, 1] = 18.0  # green
    cast[:, :, 2] = 28.0  # cyan/blue
    # Preserve relatively red pixels (blood / REC) by damping cast where R dominates
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    red_dom = np.clip((r - np.maximum(g, b)) / 80.0, 0.0, 1.0)[..., None]
    mix = strength * (1.0 - red_dom)
    out = np.clip(arr + cast * mix, 0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGB")


def deepen_blacks(img: Image.Image, crush: float = 0.22) -> Image.Image:
    """Crush shadows toward pure black for found-footage contrast."""
    arr = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0
    # Soft toe crush
    arr = np.clip((arr - crush) / (1.0 - crush), 0.0, 1.0)
    arr = np.power(arr, 1.05)
    return Image.fromarray((arr * 255.0).astype(np.uint8), "RGB")


def apply_scanlines(img: Image.Image, alpha: int = 35, step: int = 4) -> Image.Image:
    """CRT scanlines (subtle pass avoiding high-contrast edge artifacts in safe zones)."""
    rgba = img.convert("RGBA")
    w, h = rgba.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(0, h, step):
        draw.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))
    return Image.alpha_composite(rgba, overlay).convert("RGB")


def apply_vhs_grain(img: Image.Image, amount: float = 0.025, seed: int = 42) -> Image.Image:
    """Integrated film/VHS grain (not a flat overlay plate)."""
    rng = np.random.default_rng(seed)
    arr = np.asarray(img.convert("RGB"), dtype=np.float32)
    noise = rng.normal(0.0, 255.0 * amount, size=arr.shape).astype(np.float32)
    # Slightly stronger chroma noise on G/B for tape feel
    noise[:, :, 1] *= 1.15
    noise[:, :, 2] *= 1.25
    out = np.clip(arr + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGB")


def apply_chromatic_aberration(img: Image.Image, shift: int = 3) -> Image.Image:
    """RGB channel offset fringing typical of cheap optics / VHS."""
    rgb = img.convert("RGB")
    r, g, b = rgb.split()
    w, h = rgb.size
    r2 = Image.new("L", (w, h), 0)
    b2 = Image.new("L", (w, h), 0)
    r2.paste(r, (-shift, 0))
    b2.paste(b, (shift, 0))
    return Image.merge("RGB", (r2, g, b2))


def _pixel_font(size: int) -> ImageFont.ImageFont:
    """Blocky HUD font: render tiny default glyph sheet and nearest-scale."""
    base = ImageFont.load_default()
    # Pillow default is tiny; approximate pixel look by requesting bitmap size
    try:
        return ImageFont.load_default(size=max(8, size // 4))
    except TypeError:
        return base


def _parse_rgb(fill: str) -> Tuple[int, int, int]:
    if fill.startswith("#") and len(fill) == 7:
        return int(fill[1:3], 16), int(fill[3:5], 16), int(fill[5:7], 16)
    return 240, 240, 240


def render_pixel_text(text: str, fill: str, scale: int = 3) -> Image.Image:
    """Nearest-neighbor upscaled glyph plate for camcorder OSD."""
    font = ImageFont.load_default()
    probe = Image.new("L", (8, 8), 0)
    bbox = ImageDraw.Draw(probe).textbbox((0, 0), text, font=font)
    tw, th = max(1, bbox[2] - bbox[0]), max(1, bbox[3] - bbox[1])
    glyph = Image.new("L", (tw + 2, th + 2), 0)
    ImageDraw.Draw(glyph).text((1, 1), text, font=font, fill=255)
    big = glyph.resize((glyph.width * scale, glyph.height * scale), Image.Resampling.NEAREST)
    r, g, b = _parse_rgb(fill)
    plate = Image.new("RGBA", big.size, (r, g, b, 255))
    out = Image.new("RGBA", big.size, (0, 0, 0, 0))
    out.paste(plate, (0, 0), big)
    return out


def draw_pixel_text(
    host: Image.Image,
    xy: Tuple[int, int],
    text: str,
    fill: str,
    scale: int = 3,
) -> None:
    """Paste camcorder-OSD text onto an RGBA host image."""
    colored = render_pixel_text(text, fill, scale=scale)
    host.paste(colored, xy, colored)


def draw_camcorder_osd(
    img: Image.Image,
    *,
    cam_label: str = "CAM 04 [SUB-LEVEL B]",
    date_label: str = "1994-10-31",
    timecode: str = "00:04:12:46",
    rec: bool = True,
    battery: float = 0.75,
) -> Image.Image:
    """Paint pixel-style VCR OSD matching the quality-ref layout."""
    rgba = img.convert("RGBA")
    w, h = rgba.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    margin = max(24, w // 40)
    scale = 3 if w >= 1000 else 2

    # REC (top-left)
    if rec:
        r = max(6, w // 90)
        cx, cy = margin + r, margin + r + 4
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(220, 16, 16, 255))
        draw_pixel_text(overlay, (cx + r + 10, margin), "REC", fill="#FFEEEE", scale=scale)

    # Timecode (top-right)
    tc_plate = render_pixel_text(timecode, "#E8E8E8", scale=scale)
    tc_x = w - margin - tc_plate.width
    overlay.paste(tc_plate, (tc_x, margin), tc_plate)

    # Battery (top-right, placed safely to the left of timecode to avoid YouTube timestamp safe-zone collision)
    bw, bh = max(28, 18 * scale), max(12, 8 * scale)
    bx1 = tc_x - bw - 12
    by1 = margin + max(0, (tc_plate.height - bh) // 2)
    draw.rectangle([bx1, by1, bx1 + bw, by1 + bh], outline=(40, 200, 80, 255), width=2)
    draw.rectangle([bx1 + bw, by1 + bh // 4, bx1 + bw + 4, by1 + 3 * bh // 4], fill=(40, 200, 80, 255))
    fill_w = int((bw - 4) * max(0.0, min(1.0, battery)))
    if fill_w > 0:
        draw.rectangle([bx1 + 2, by1 + 2, bx1 + 2 + fill_w, by1 + bh - 2], fill=(40, 220, 90, 255))

    # Bottom-left metadata (clearing YouTube Shorts bottom 450px UI overlay in vertical mode)
    if h > w:
        by = min(h - margin - 28 * scale, h - 480 - 28 * scale)
    else:
        by = h - margin - 28 * scale
    draw_pixel_text(overlay, (margin, by), cam_label, fill="#E0E0E0", scale=scale)
    draw_pixel_text(overlay, (margin, by + 14 * scale), date_label, fill="#B0B0B0", scale=scale)

    return Image.alpha_composite(rgba, overlay).convert("RGB")


def apply_analog_horror_grade(
    img: Image.Image,
    *,
    target_size: Optional[Tuple[int, int]] = None,
    contrast: float = 1.32,
    ca_shift: int = 3,
    grain: float = 0.025,
    scanline_alpha: int = 35,
    cast_strength: float = 0.26,
    crush: float = 0.18,
    seed: int = 42,
    with_osd: bool = False,
    osd_kwargs: Optional[dict] = None,
) -> Image.Image:
    """Full found-footage grade pipeline for thumbnail plates."""
    out = img.convert("RGB")
    if target_size and out.size != target_size:
        out = out.resize(target_size, Image.Resampling.LANCZOS)

    out = deepen_blacks(out, crush=crush)
    out = apply_cyan_green_cast(out, strength=cast_strength)
    out = ImageEnhance.Contrast(out).enhance(contrast)
    out = apply_chromatic_aberration(out, shift=ca_shift)
    out = apply_vhs_grain(out, amount=grain, seed=seed)
    out = apply_scanlines(out, alpha=scanline_alpha, step=4)
    if with_osd:
        out = draw_camcorder_osd(out, **(osd_kwargs or {}))
    return out


__all__ = [
    "apply_analog_horror_grade",
    "apply_chromatic_aberration",
    "apply_cyan_green_cast",
    "apply_scanlines",
    "apply_vhs_grain",
    "deepen_blacks",
    "draw_camcorder_osd",
    "render_pixel_text",
]
