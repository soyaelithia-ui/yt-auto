"""
scripts/design_impeccable_thumbnails.py - Impeccable High-Craft Niche Thumbnail Engine.

Tailored specifically to:
1. SCP / Paranormal Short (Vertical 9:16) - Containment HUD, hazard chevrons, visceral fear hook.
2. Reddit Drama / AITA (Horizontal 16:9) - Authentic Reddit post card, emotional conflict framing.
3. Creepypasta / Analog Horror (Horizontal 16:9) - CRT scanlines, camcorder REC HUD, spectral phosphor typography.
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

from src.media.thumbnails.analog_horror import apply_analog_horror_grade, draw_camcorder_osd


import sys
from pathlib import Path as _P
_ROOT = _P(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from scripts.lib.thumb_common import (
    REPO_ROOT,
    resolve_thumbnail_output_dir,
    get_font,
    draw_text_with_effects,
)


def draw_hazard_stripes(draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int], stripe_width: int = 18):
    """Draws classic industrial yellow & black hazard warning stripes."""
    x0, y0, x1, y1 = box
    draw.rectangle(box, fill=(20, 20, 20))
    w = x1 - x0
    h = y1 - y0

    # Draw diagonal yellow lines
    for offset in range(-h, w + h, stripe_width * 2):
        points = [
            (x0 + offset, y1),
            (x0 + offset + stripe_width, y1),
            (x0 + offset + stripe_width + h, y0),
            (x0 + offset + h, y0),
        ]
        draw.polygon(points, fill=(255, 200, 0))


# ==============================================================================
# 1. SCP-173 SHORT (Vertical 9:16 - 1080x1920)
# ==============================================================================
def create_scp_impeccable_thumbnail(base_path: str, output_path: str) -> str:
    base = Image.open(base_path).convert("RGB")
    w, h = 1080, 1920

    # Analog-horror plate (VHS/CCTV) — quality bar from aelithia_quality_ref
    graded_rgb = apply_analog_horror_grade(
        base,
        target_size=(w, h),
        with_osd=True,
        osd_kwargs={
            "cam_label": "CAM 04 [SECTOR-19 VAULT]",
            "date_label": "1994-10-31",
            "timecode": "03:17:42:08",
            "battery": 0.7,
        },
        seed=173,
    )
    graded = graded_rgb.convert("RGBA")

    # Dark gradient over the dark corridor (right side) to let typography shine
    corridor_gradient = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    cg_draw = ImageDraw.Draw(corridor_gradient)
    for x in range(400, w):
        progress = (x - 400) / (w - 400)
        alpha = int(200 * (progress ** 1.3))
        cg_draw.line([(x, 0), (x, h)], fill=(4, 4, 8, alpha))
    graded.paste(corridor_gradient, (0, 0), corridor_gradient)

    draw = ImageDraw.Draw(graded)

    # --- A. Classification strip (OSD already painted by analog grade) ---

    # --- B. Foundation Classification Banner ---
    draw.rounded_rectangle([60, 120, w - 60, 175], radius=8, fill=(15, 10, 15, 235), outline="#FF1E27", width=2)
    f_badge = get_font(28)
    draw.text((85, 132), "FUNDACIÓN SCP  ·  OBJETO #173", font=f_badge, fill="#FFEEEE")
    draw.text((w - 380, 132), "NIVEL DE ACCESO: 4", font=f_badge, fill="#FF4444")

    # --- C. Massive Hook Typography (Right side / Center) ---
    f_huge = get_font(128)
    f_sub = get_font(96)

    # Positioned in the dark space (x: 460+) so SCP-173 on the left is untouched!
    draw_text_with_effects(
        draw,
        (w, h),
        "¡NO",
        (460, 240),
        f_huge,
        text_color="#FFFFFF",
        stroke_color="#000000",
        stroke_width=14,
        shadow_offset=(8, 12),
        shadow_color=(0, 0, 0, 255),
    )

    draw_text_with_effects(
        draw,
        (w, h),
        "PARPADEES!",
        (460, 380),
        f_sub,
        text_color="#FFE600",  # High-vis warning yellow
        stroke_color="#000000",
        stroke_width=14,
        shadow_offset=(8, 12),
        shadow_color=(0, 0, 0, 255),
        glow_color=(255, 40, 0, 180),
        glow_radius=25,
    )

    # Secondary punchline
    f_sec = get_font(68)
    draw_text_with_effects(
        draw,
        (w, h),
        "ROMPIÓ LA",
        (465, 520),
        f_sec,
        text_color="#F0F0F0",
        stroke_color="#000000",
        stroke_width=10,
        shadow_offset=(6, 8),
    )
    draw_text_with_effects(
        draw,
        (w, h),
        "CONTENCIÓN",
        (465, 605),
        f_sec,
        text_color="#FF2A2A",  # Crimson alert
        stroke_color="#000000",
        stroke_width=10,
        shadow_offset=(6, 8),
        glow_color=(255, 0, 30, 140),
        glow_radius=18,
    )

    # --- D. Hazard Warning Banner (Above bottom Shorts UI zone) ---
    hazard_y = h - 450
    draw_hazard_stripes(draw, (60, hazard_y, w - 60, hazard_y + 14))

    draw.rounded_rectangle(
        [60, hazard_y + 24, w - 60, hazard_y + 105],
        radius=10,
        fill=(12, 0, 4, 240),
        outline="#FF9900",
        width=3,
    )
    f_alert = get_font(36)
    draw.text((95, hazard_y + 44), "PELIGRO EXTREMO  ·  CLASE: EUCLID", font=f_alert, fill="#FFAA00")

    draw_hazard_stripes(draw, (60, hazard_y + 115, w - 60, hazard_y + 129))

    graded.convert("RGB").save(output_path, "JPEG", quality=96, subsampling=0)
    return output_path


# ==============================================================================
# 2. REDDIT AITA LONGFORM (Horizontal 16:9 - 1920x1080)
# ==============================================================================
def create_aita_impeccable_thumbnail(base_path: str, output_path: str) -> str:
    base = Image.open(base_path).convert("RGBA")
    w, h = 1920, 1080
    base = base.resize((w, h), Image.Resampling.LANCZOS)

    # Grade: rich contrast, warm wedding bokeh against cool decisive heroine
    graded = ImageEnhance.Contrast(base.convert("RGB")).enhance(1.22)
    graded = ImageEnhance.Color(graded).enhance(1.14)
    graded = ImageEnhance.Sharpness(graded).enhance(1.25).convert("RGBA")

    # Dark gradient on left side (behind typography) so the weeping bride & family remain visible
    left_overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    lo_draw = ImageDraw.Draw(left_overlay)
    for x in range(1120):
        alpha = int(230 * (1.0 - (x / 1120) ** 1.35))
        lo_draw.line([(x, 0), (x, h)], fill=(10, 8, 14, alpha))
    graded.paste(left_overlay, (0, 0), left_overlay)

    draw = ImageDraw.Draw(graded)

    # --- A. Authentic Reddit Header Card (Top-Left) ---
    rx, ry = 80, 65
    rw, rh = 720, 95
    # Glassmorphic dark card
    draw.rounded_rectangle([rx, ry, rx + rw, ry + rh], radius=14, fill=(18, 16, 24, 240), outline="#FF4500", width=2)

    # Reddit alien / r/ circle icon
    draw.ellipse([rx + 20, ry + 20, rx + 75, ry + 75], fill="#FF4500")
    f_icon = get_font(34)
    draw.text((rx + 33, ry + 26), "r/", font=f_icon, fill="#FFFFFF")

    # Subreddit name & metadata
    f_sub = get_font(30)
    draw.text((rx + 90, ry + 16), "r/AmItheAsshole", font=f_sub, fill="#FFFFFF")

    f_meta = get_font(20)
    draw.text((rx + 90, ry + 56), "Publicado por u/herencia_legitima · hace 3 horas", font=f_meta, fill="#A5A5A5")

    # Upvotes & comments pill inside card
    draw.rounded_rectangle([rx + rw - 180, ry + 22, rx + rw - 20, ry + rh - 22], radius=8, fill=(35, 25, 45))
    f_stats = get_font(22)
    draw.text((rx + rw - 165, ry + 33), "▲ 38.4k", font=f_stats, fill="#FF4500")

    # --- B. Viral Hook Headline (Left Side) ---
    f_h1 = get_font(124)
    f_h2 = get_font(124)
    f_h3 = get_font(124)

    draw_text_with_effects(
        draw,
        (w, h),
        "¿LA MALA POR",
        (80, 185),
        f_h1,
        text_color="#FFFFFF",
        stroke_color="#000000",
        stroke_width=14,
        shadow_offset=(8, 12),
        shadow_color=(0, 0, 0, 255),
    )

    draw_text_with_effects(
        draw,
        (w, h),
        "NO PAGAR",
        (80, 325),
        f_h2,
        text_color="#FF3838",  # Vibrant dramatic crimson
        stroke_color="#000000",
        stroke_width=14,
        shadow_offset=(8, 12),
        shadow_color=(0, 0, 0, 255),
        glow_color=(255, 30, 40, 160),
        glow_radius=22,
    )

    draw_text_with_effects(
        draw,
        (w, h),
        "SU BODA?",
        (80, 465),
        f_h3,
        text_color="#FFD700",  # Imperial Gold
        stroke_color="#000000",
        stroke_width=14,
        shadow_offset=(8, 12),
        shadow_color=(0, 0, 0, 255),
    )

    # --- C. Dramatic Speech Bubble / Legal Callout (Bottom-Left) ---
    callout_box = [80, 630, 820, 740]
    draw.rounded_rectangle(callout_box, radius=16, fill=(120, 10, 25, 245), outline="#FF4D6D", width=3)

    f_call = get_font(42)
    draw.text((115, 660), "«EXIGEN MI HERENCIA»", font=f_call, fill="#FFFFFF")

    # Subtext tag
    f_subcall = get_font(26)
    draw.text((118, 715), "ACTUALIZACIÓN: LA FAMILIA SE DIVIDE", font=f_subcall, fill="#FFCCD5")

    graded.convert("RGB").save(output_path, "JPEG", quality=96, subsampling=0)
    return output_path


# ==============================================================================
# 3. MOKU HORROR LONGFORM (Horizontal 16:9 - 1920x1080)
# ==============================================================================
def create_horror_impeccable_thumbnail(base_path: str, output_path: str) -> str:
    base = Image.open(base_path).convert("RGB")
    w, h = 1920, 1080

    graded_rgb = apply_analog_horror_grade(
        base,
        target_size=(w, h),
        with_osd=True,
        osd_kwargs={
            "cam_label": "CAM 04 [SUB-LEVEL B]",
            "date_label": "1994-10-31",
            "timecode": "03:42:19:12",
            "battery": 0.65,
        },
        seed=1047,
    )
    graded = graded_rgb.convert("RGBA")

    # Dark gradient over upper sky/window to frame typography perfectly
    sky_overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    so_draw = ImageDraw.Draw(sky_overlay)
    for y in range(650):
        alpha = int(210 * (1.0 - (y / 650) ** 1.3))
        so_draw.line([(0, y), (1200, y)], fill=(3, 5, 8, alpha))
    graded.paste(sky_overlay, (0, 0), sky_overlay)

    draw = ImageDraw.Draw(graded)

    # --- A. Frequency badge (OSD already painted) ---
    draw.rounded_rectangle([680, 48, 1080, 95], radius=8, fill=(5, 20, 10, 240), outline="#00FF88", width=2)
    f_freq = get_font(26)
    draw.text((705, 58), "FREQ: 104.7 MHz  ·  SEÑAL ANÓMALA", font=f_freq, fill="#00FF99")

    # --- B. Master Hook Typography (Upper-Center/Left) ---
    f_h1 = get_font(126)
    f_h2 = get_font(126)
    f_h3 = get_font(92)

    draw_text_with_effects(
        draw,
        (w, h),
        "TRANSMISIÓN",
        (80, 140),
        f_h1,
        text_color="#F8FAFC",
        stroke_color="#000000",
        stroke_width=14,
        shadow_offset=(8, 12),
        shadow_color=(0, 0, 0, 255),
    )

    draw_text_with_effects(
        draw,
        (w, h),
        "PROHIBIDA",
        (80, 275),
        f_h2,
        text_color="#FF2233",  # Blood alert crimson
        stroke_color="#000000",
        stroke_width=14,
        shadow_offset=(8, 12),
        shadow_color=(0, 0, 0, 255),
        glow_color=(255, 0, 30, 180),
        glow_radius=26,
    )

    draw_text_with_effects(
        draw,
        (w, h),
        "ALGUIEN RESPONDIÓ",
        (80, 415),
        f_h3,
        text_color="#00FFAA",  # Eerie phosphor oscilloscope green
        stroke_color="#000000",
        stroke_width=12,
        shadow_offset=(8, 10),
        shadow_color=(0, 0, 0, 255),
        glow_color=(0, 255, 170, 150),
        glow_radius=20,
    )

    # --- C. Classified Tape Callout Badge ---
    draw.rounded_rectangle([80, 545, 680, 625], radius=10, fill=(15, 0, 5, 245), outline="#FF1E27", width=3)
    f_tape = get_font(34)
    draw.text((110, 565), "«NO DEBIÓ SINTONIZARSE»", font=f_tape, fill="#FFFFFF")

    # Heavy dark vignette on outer borders
    vignette = Image.new("L", (w, h), 255)
    v_draw = ImageDraw.Draw(vignette)
    v_draw.ellipse([-w * 0.1, -h * 0.1, w * 1.1, h * 1.1], fill=0)
    vignette = vignette.filter(ImageFilter.GaussianBlur(140))
    black = Image.new("RGB", (w, h), (0, 0, 0))
    graded_rgb = Image.composite(black, graded.convert("RGB"), ImageEnhance.Brightness(vignette).enhance(0.40))

    graded_rgb.save(output_path, "JPEG", quality=96, subsampling=0)
    return output_path


def main():
    output_dir = resolve_thumbnail_output_dir()
    scp_base = REPO_ROOT / "assets" / "thumbnails" / "scp_173_intense_1788482257060.jpg"
    aita_base = REPO_ROOT / "assets" / "thumbnails" / "inheritance_drama_wedding_1788480840010.jpg"
    horror_base = REPO_ROOT / "assets" / "thumbnails" / "abandoned_radio_mountain_1788480856078.jpg"

    scp_out = output_dir / "impeccable_thumb_scp_173.jpg"
    aita_out = output_dir / "impeccable_thumb_aita.jpg"
    horror_out = output_dir / "impeccable_thumb_horror.jpg"

    for base in (scp_base, aita_base, horror_base):
        if not base.exists():
            raise FileNotFoundError(f"Required base artwork does not exist: {base}")

    print("Generating Impeccable SCP-173 thumbnail...")
    create_scp_impeccable_thumbnail(str(scp_base), str(scp_out))
    print(f"-> Saved: {scp_out}")

    print("Generating Impeccable AITA thumbnail...")
    create_aita_impeccable_thumbnail(str(aita_base), str(aita_out))
    print(f"-> Saved: {aita_out}")

    print("Generating Impeccable Horror thumbnail...")
    create_horror_impeccable_thumbnail(str(horror_base), str(horror_out))
    print(f"-> Saved: {horror_out}")

    # Copy to work directories if present in workspace
    for out_path, run_id in [
        (scp_out, "093e7ae9d19c4030bf678e729d796fbf"),
        (aita_out, "29168829ab644b6ca985edd030b41800"),
        (horror_out, "e86b45838f3c466b86042ed276b466b3"),
    ]:
        run_dest = REPO_ROOT / "work" / "cli" / run_id / "thumbnail.jpg"
        if run_dest.parent.exists():
            import shutil
            shutil.copyfile(out_path, run_dest)
            print(f"Copied impeccable thumbnail into {run_dest}")

if __name__ == "__main__":
    main()
