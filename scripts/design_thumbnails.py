"""
scripts/design_thumbnails.py - Professional High-CTR Thumbnail Designer.

Composites cinematic AI-generated base artwork with viral YouTube typography,
multi-layer 3D shadows, contrast curves, and high-impact category badges.
"""
from __future__ import annotations

import sys
from pathlib import Path as _Path
_REPO = _Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import os
from pathlib import Path
from typing import Tuple, List, Optional
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance, ImageOps

from src.media.thumbnails.analog_horror import apply_analog_horror_grade

REPO_ROOT = Path(__file__).resolve().parents[1]


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


def draw_pill_badge(
    draw: ImageDraw.ImageDraw,
    text: str,
    top_left: Tuple[int, int],
    font: ImageFont.FreeTypeFont,
    bg_color: Tuple[int, int, int, int] = (10, 10, 15, 230),
    border_color: str = "#FF0033",
    text_color: str = "#FFFFFF",
    padding: Tuple[int, int] = (24, 12),
    border_width: int = 3,
    corner_radius: int = 12,
) -> Tuple[int, int, int, int]:
    """Draws an authoritative categorized badge (e.g. [ EXPEDIENTE CLASIFICADO ])."""
    x, y = top_left
    bbox = font.getbbox(text)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    pad_x, pad_y = padding
    box = [x, y, x + tw + pad_x * 2, y + th + pad_y * 2]

    # Draw rounded rectangle badge
    draw.rounded_rectangle(
        box,
        radius=corner_radius,
        fill=bg_color,
        outline=border_color,
        width=border_width,
    )
    # Center text inside
    draw.text(
        (x + pad_x, y + pad_y - 2),
        text,
        font=font,
        fill=text_color,
    )
    return tuple(box)


def apply_cinematic_grade(img: Image.Image, vignette_strength: float = 0.4) -> Image.Image:
    """Enhances contrast, saturation, and applies a smooth radial vignette."""
    img = ImageEnhance.Contrast(img).enhance(1.22)
    img = ImageEnhance.Color(img).enhance(1.15)
    img = ImageEnhance.Sharpness(img).enhance(1.25)

    w, h = img.size
    vignette = Image.new("L", (w, h), 255)
    v_draw = ImageDraw.Draw(vignette)
    v_draw.ellipse(
        [-w * 0.15, -h * 0.15, w * 1.15, h * 1.15],
        fill=0,
    )
    vignette = vignette.filter(ImageFilter.GaussianBlur(int(min(w, h) * 0.22)))

    black = Image.new("RGB", (w, h), (0, 0, 0))
    vignette_mask = ImageEnhance.Brightness(vignette).enhance(vignette_strength)
    return Image.composite(black, img, vignette_mask)


def design_scp_short_thumbnail(base_path: str, output_path: str) -> str:
    """Design 9:16 vertical thumbnail for SCP-173 Short."""
    base = Image.open(base_path).convert("RGB")
    w, h = 1080, 1920
    graded = apply_analog_horror_grade(
        base,
        target_size=(w, h),
        with_osd=True,
        osd_kwargs={
            "cam_label": "CAM 04 [SECTOR-19 VAULT]",
            "date_label": "1994-10-31",
            "timecode": "03:17:42:08",
        },
        seed=173,
    ).convert("RGBA")

    # Gradient overlay at top for text readability
    top_overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    o_draw = ImageDraw.Draw(top_overlay)
    for y in range(550):
        alpha = int(210 * (1.0 - (y / 550) ** 1.3))
        o_draw.line([(0, y), (w, y)], fill=(5, 5, 10, alpha))
    graded.paste(top_overlay, (0, 0), top_overlay)

    # Bottom dark overlay
    bot_overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    b_draw = ImageDraw.Draw(bot_overlay)
    for y in range(h - 350, h):
        progress = (y - (h - 350)) / 350
        alpha = int(220 * (progress ** 1.2))
        b_draw.line([(0, y), (w, y)], fill=(5, 5, 10, alpha))
    graded.paste(bot_overlay, (0, 0), bot_overlay)

    draw = ImageDraw.Draw(graded)

    # 1. Authority Badge
    badge_font = get_font(34)
    draw_pill_badge(
        draw,
        "EXPEDIENTE CLASIFICADO // SCP-173",
        (70, 95),
        badge_font,
        bg_color=(15, 0, 5, 235),
        border_color="#FF2233",
        text_color="#FFEEEE",
        padding=(26, 12),
        border_width=3,
        corner_radius=10,
    )

    # 2. Main Viral Hook
    hook_font_1 = get_font(108)
    hook_font_2 = get_font(90)

    draw_text_with_effects(
        draw,
        (w, h),
        "¡NO PARPADEES!",
        (65, 185),
        hook_font_1,
        text_color="#FFE500",
        stroke_color="#000000",
        stroke_width=12,
        shadow_offset=(8, 10),
        shadow_color=(0, 0, 0, 240),
        glow_color=(255, 30, 0, 140),
        glow_radius=18,
    )

    draw_text_with_effects(
        draw,
        (w, h),
        "LA ESCULTURA",
        (70, 315),
        hook_font_2,
        text_color="#FFFFFF",
        stroke_color="#000000",
        stroke_width=10,
        shadow_offset=(7, 9),
        shadow_color=(0, 0, 0, 230),
    )

    # 3. Bottom Hazard Label
    hazard_font = get_font(38)
    draw_pill_badge(
        draw,
        "CLASE: EUCLID  ·  PELIGRO MORTAL",
        (70, h - 170),
        hazard_font,
        bg_color=(20, 0, 0, 230),
        border_color="#FF9900",
        text_color="#FFAA00",
        padding=(30, 16),
        border_width=3,
        corner_radius=8,
    )

    graded.convert("RGB").save(output_path, "JPEG", quality=96, subsampling=0)
    return output_path


def design_aita_thumbnail(base_path: str, output_path: str) -> str:
    """Design 16:9 horizontal thumbnail for AITA Longform."""
    base = Image.open(base_path).convert("RGBA")
    w, h = 1920, 1080
    base = base.resize((w, h), Image.Resampling.LANCZOS)
    graded = apply_cinematic_grade(base.convert("RGB"), vignette_strength=0.32).convert("RGBA")

    # Dark gradient on left side (behind text) to preserve the face of the sister on right
    left_gradient = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    lg_draw = ImageDraw.Draw(left_gradient)
    for x in range(1050):
        alpha = int(225 * (1.0 - (x / 1050) ** 1.4))
        lg_draw.line([(x, 0), (x, h)], fill=(12, 10, 16, alpha))
    graded.paste(left_gradient, (0, 0), left_gradient)

    draw = ImageDraw.Draw(graded)

    # 1. Authority Tag
    badge_font = get_font(38)
    draw_pill_badge(
        draw,
        "CONFESIÓN FAMILIAR  ·  CASO REAL",
        (90, 80),
        badge_font,
        bg_color=(20, 15, 25, 235),
        border_color="#FFCC00",
        text_color="#FFF8E0",
        padding=(28, 14),
        border_width=3,
        corner_radius=10,
    )

    # 2. Viral Hook Lines (Left Side)
    f_huge = get_font(118)

    draw_text_with_effects(
        draw,
        (w, h),
        "¿LA MALA POR",
        (90, 185),
        f_huge,
        text_color="#FFFFFF",
        stroke_color="#000000",
        stroke_width=12,
        shadow_offset=(8, 10),
        shadow_color=(0, 0, 0, 240),
    )

    draw_text_with_effects(
        draw,
        (w, h),
        "NEGARME A",
        (90, 315),
        f_huge,
        text_color="#FF3333",
        stroke_color="#000000",
        stroke_width=12,
        shadow_offset=(8, 10),
        shadow_color=(0, 0, 0, 240),
        glow_color=(255, 30, 30, 150),
        glow_radius=20,
    )

    draw_text_with_effects(
        draw,
        (w, h),
        "PAGAR SU BODA?",
        (90, 445),
        f_huge,
        text_color="#FFD700",
        stroke_color="#000000",
        stroke_width=12,
        shadow_offset=(8, 10),
        shadow_color=(0, 0, 0, 240),
    )

    # 3. Punchy Callout Badge on bottom left
    callout_font = get_font(46)
    draw_pill_badge(
        draw,
        "«MI HERENCIA NO SE TOCA»",
        (90, 600),
        callout_font,
        bg_color=(15, 0, 5, 245),
        border_color="#FF3344",
        text_color="#FFFFFF",
        padding=(34, 18),
        border_width=3,
        corner_radius=12,
    )

    graded.convert("RGB").save(output_path, "JPEG", quality=96, subsampling=0)
    return output_path


def design_horror_thumbnail(base_path: str, output_path: str) -> str:
    """Design 16:9 horizontal thumbnail for Moku Horror Longform."""
    base = Image.open(base_path).convert("RGB")
    w, h = 1920, 1080
    graded = apply_analog_horror_grade(
        base,
        target_size=(w, h),
        with_osd=True,
        osd_kwargs={
            "cam_label": "CAM 04 [SUB-LEVEL B]",
            "date_label": "1994-10-31",
            "timecode": "03:42:19:12",
        },
        seed=1047,
    ).convert("RGBA")

    # Dark gradient on upper-left to frame text against dark clouds
    ul_gradient = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ug_draw = ImageDraw.Draw(ul_gradient)
    for y in range(650):
        for x in range(1150):
            dist = ((x / 1150) ** 2 + (y / 650) ** 2) ** 0.5
            if dist < 1.0:
                alpha = int(210 * (1.0 - dist))
                ug_draw.point((x, y), fill=(3, 6, 12, alpha))
    graded.paste(ul_gradient, (0, 0), ul_gradient)

    draw = ImageDraw.Draw(graded)

    # 1. Archive Badge
    badge_font = get_font(38)
    draw_pill_badge(
        draw,
        "REGISTRO DESCLASIFICADO  ·  FRECUENCIA 104.7",
        (90, 80),
        badge_font,
        bg_color=(5, 15, 10, 240),
        border_color="#00FF88",
        text_color="#E0FFF0",
        padding=(28, 14),
        border_width=3,
        corner_radius=10,
    )

    # 2. Main Title Hook
    f_huge = get_font(120)
    f_sub = get_font(95)

    draw_text_with_effects(
        draw,
        (w, h),
        "TRANSMISIÓN",
        (90, 180),
        f_huge,
        text_color="#FFFFFF",
        stroke_color="#000000",
        stroke_width=12,
        shadow_offset=(8, 10),
        shadow_color=(0, 0, 0, 240),
    )

    draw_text_with_effects(
        draw,
        (w, h),
        "PROHIBIDA",
        (90, 310),
        f_huge,
        text_color="#FF2233",
        stroke_color="#000000",
        stroke_width=12,
        shadow_offset=(8, 10),
        shadow_color=(0, 0, 0, 240),
        glow_color=(255, 0, 40, 160),
        glow_radius=22,
    )

    draw_text_with_effects(
        draw,
        (w, h),
        "LA MONTAÑA OSCURA",
        (90, 440),
        f_sub,
        text_color="#00FFCC",
        stroke_color="#000000",
        stroke_width=10,
        shadow_offset=(7, 9),
        shadow_color=(0, 0, 0, 230),
        glow_color=(0, 255, 200, 120),
        glow_radius=16,
    )

    # 3. Bottom Alert Tag
    alert_font = get_font(42)
    draw_pill_badge(
        draw,
        "«NUNCA DEBIÓ ESCUCHARSE»",
        (90, 570),
        alert_font,
        bg_color=(20, 0, 5, 245),
        border_color="#FF0044",
        text_color="#FFFFFF",
        padding=(32, 16),
        border_width=3,
        corner_radius=10,
    )

    graded.convert("RGB").save(output_path, "JPEG", quality=96, subsampling=0)
    return output_path


def main():
    output_dir = resolve_thumbnail_output_dir()
    scp_base = REPO_ROOT / "assets" / "thumbnails" / "scp_173_containment_1788480825325.jpg"
    aita_base = REPO_ROOT / "assets" / "thumbnails" / "inheritance_drama_wedding_1788480840010.jpg"
    horror_base = REPO_ROOT / "assets" / "thumbnails" / "abandoned_radio_mountain_1788480856078.jpg"

    scp_out = output_dir / "redesigned_thumb_scp_173.jpg"
    aita_out = output_dir / "redesigned_thumb_aita.jpg"
    horror_out = output_dir / "redesigned_thumb_horror.jpg"

    for base in (scp_base, aita_base, horror_base):
        if not base.exists():
            raise FileNotFoundError(f"Required base artwork does not exist: {base}")

    print("Compositing SCP-173 thumbnail...")
    design_scp_short_thumbnail(str(scp_base), str(scp_out))
    print(f"-> Saved: {scp_out}")

    print("Compositing AITA thumbnail...")
    design_aita_thumbnail(str(aita_base), str(aita_out))
    print(f"-> Saved: {aita_out}")

    print("Compositing Horror thumbnail...")
    design_horror_thumbnail(str(horror_base), str(horror_out))
    print(f"-> Saved: {horror_out}")

    for out_path, run_id in [
        (scp_out, "093e7ae9d19c4030bf678e729d796fbf"),
        (aita_out, "29168829ab644b6ca985edd030b41800"),
        (horror_out, "e86b45838f3c466b86042ed276b466b3"),
    ]:
        run_dest = REPO_ROOT / "work" / "cli" / run_id / "thumbnail.jpg"
        if run_dest.parent.exists():
            import shutil
            shutil.copyfile(out_path, run_dest)
            print(f"Copied redesigned thumbnail into {run_dest}")

if __name__ == "__main__":
    main()
