"""
src/media/thumbnails/layouts/analog_horror.py - Analog Horror VHS 16:9 Horizontal Layout.
"""
from __future__ import annotations

from typing import Any, Dict
from PIL import Image, ImageDraw

from src.media.thumbnails.layout import SafeZone
from src.media.thumbnails.layouts.base import BaseThumbnailLayout, LayoutRegistry
from src.media.thumbnails.typography import DynamicTypographyEngine


@LayoutRegistry.register("analog", "horror", "vhs", "moku-horror-long")
class AnalogHorrorVhsLayout(BaseThumbnailLayout):
    """
    Renders an authentic 90s Analog Horror VHS aesthetic:
    - Camcorder REC indicator and VCR timecode (SP 0:14:02:18).
    - Audio frequency tuner badge (CH 03 STEREO // HI-FI).
    - Horizontal CRT scanlines and chromatic aberration.
    - Classified VHS tape alert badge.
    - 3D hook title rendered with eerie neon green glow and deep drop shadows.
    """

    def apply_layout(
        self,
        canvas: Image.Image,
        title: str,
        channel_id: str,
        safe_zone: SafeZone,
        metadata: Dict[str, Any],
    ) -> Image.Image:
        w, h = canvas.size
        draw_img = canvas.copy().convert("RGBA")
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        tape_id = str(metadata.get("tape_id", "TAPE-04 // ARCHIVE")).upper()
        channel_tag = str(metadata.get("channel_tag", "CH 03")).upper()

        fnt_vcr = DynamicTypographyEngine.resolve_font("LiberationSans-Bold.ttf", int(h * 0.035))
        fnt_badge = DynamicTypographyEngine.resolve_font("Montserrat-Black.ttf", int(h * 0.026))
        fnt_tape = DynamicTypographyEngine.resolve_font("LiberationSans-Bold.ttf", int(h * 0.024))

        # 1. VHS Header Bar
        # Top-Left: REC indicator and PLAY timecode
        rec_y = safe_zone.top
        draw.ellipse([safe_zone.left, rec_y, safe_zone.left + 26, rec_y + 26], fill=(255, 30, 30, 255))
        draw.text((safe_zone.left + 36, rec_y + 2), "REC  [SP 0:14:02:18]", font=fnt_vcr, fill=(240, 240, 240, 240))

        # Top-Right: Tuner and Audio channel
        tuner_text = f"{channel_tag}  STEREO // HI-FI"
        bbox_tuner = draw.textbbox((0, 0), tuner_text, font=fnt_vcr)
        tuner_w = bbox_tuner[2] - bbox_tuner[0]
        draw.text((safe_zone.right - tuner_w, rec_y + 2), tuner_text, font=fnt_vcr, fill=(0, 255, 102, 230))

        # 2. Classified Tape Warning Badge
        badge_y = rec_y + int(h * 0.07)
        badge_w = int(w * 0.48)
        badge_h = int(h * 0.052)
        draw.rectangle(
            [(safe_zone.left, badge_y), (safe_zone.left + badge_w, badge_y + badge_h)],
            fill=(20, 2, 2, 230),
            outline=(255, 40, 40, 230),
            width=2,
        )
        badge_text = f"ADVERTENCIA // {tape_id}"
        bbox_b = draw.textbbox((0, 0), badge_text, font=fnt_badge)
        b_tw = bbox_b[2] - bbox_b[0]
        draw.text(
            (safe_zone.left + (badge_w - b_tw) // 2, badge_y + int(badge_h * 0.18)),
            badge_text,
            font=fnt_badge,
            fill=(255, 50, 50, 255),
        )

        # 3. Bottom-Left Tape Date / Metadata (Clearing bottom-right timestamp)
        bot_y = safe_zone.bottom - 40
        date_str = str(metadata.get("date") or metadata.get("timestamp_label") or "OCT 24 1994  11:42 PM").upper()
        draw.text((safe_zone.left, bot_y), date_str, font=fnt_tape, fill=(200, 200, 200, 210))

        # 4. CRT Horizontal Scanlines Overlay
        for sy in range(0, h, 4):
            draw.line([(0, sy), (w, sy)], fill=(0, 0, 0, 45), width=1)

        # Composite HUD overlay
        img_with_vhs = Image.alpha_composite(draw_img, overlay).convert("RGB")

        # 5. Render 3D Typography Hook Title
        title_y = badge_y + badge_h + int(h * 0.12)
        title_font_size = int(w * 0.062)
        primary_col = metadata.get("primary_color") or "#FFE600"
        accent_col = metadata.get("accent_color") or "#00FF66"
        tilt = float(metadata.get("tilt_angle", -3.0))

        final_img = DynamicTypographyEngine.draw_text_with_effects(
            canvas=img_with_vhs,
            text=title,
            pos_x=safe_zone.left,
            pos_y=title_y,
            max_width=int(safe_zone.width * 0.82),  # Keep away from bottom-right timestamp zone
            font_name="Montserrat-Black.ttf",
            font_size=title_font_size,
            fill_color=primary_col,
            stroke_color="#000000",
            stroke_width=12,
            shadow_offset=(8, 12),
            shadow_blur=4,
            glow_color=accent_col,  # Toxic Night-Vision Glow
            glow_radius=8,
            tilt_angle=tilt,
            align="center",
        )
        return final_img
