"""
src/media/thumbnails/layouts/analog_horror.py - Analog Horror VHS 16:9 Horizontal Layout.
"""
from __future__ import annotations

from typing import Any, Dict
from PIL import Image, ImageDraw

from src.media.thumbnails.layout import SafeZone
from src.media.thumbnails.layouts.base import BaseThumbnailLayout, LayoutRegistry
from src.media.thumbnails.layouts.cinematic import badge_label, resolve_ctr_fill_color
from src.media.thumbnails.typography import DynamicTypographyEngine


def _osd_requested(metadata: Dict[str, Any]) -> bool:
    raw = metadata.get("osd", metadata.get("with_osd"))
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return raw == 1
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return False


@LayoutRegistry.register("analog", "horror", "vhs", "moku-horror-long", "moku-horror", "moku-long", "moku")
class AnalogHorrorVhsLayout(BaseThumbnailLayout):
    """
    Analog horror layout with a clean CTR type stack:
    - Optional camcorder OSD only when metadata explicitly enables it.
    - Tape warning badge only when a real tape_id is provided.
    - CRT scanlines + cream title, no neon glow.
    """

    def apply_layout(
        self,
        canvas: Image.Image,
        title: str,
        channel_id: str,
        safe_zone: SafeZone,
        metadata: Dict[str, Any],
        **kwargs: Any,
    ) -> Image.Image:
        w, h = canvas.size
        meta = dict(metadata or {})
        draw_img = canvas.copy().convert("RGBA")
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        osd_on = _osd_requested(meta)
        tape_kwargs = {"tape_id": meta["tape_id"]} if "tape_id" in meta else {}
        tape_label = badge_label(None, niche="horror", metadata=meta, **tape_kwargs)

        rec_y = safe_zone.top
        badge_y = rec_y
        badge_h = 0

        if osd_on:
            channel_tag = str(meta.get("channel_tag", "CH 03")).upper()
            fnt_vcr = DynamicTypographyEngine.resolve_font("LiberationSans-Bold.ttf", int(h * 0.035))
            fnt_tape = DynamicTypographyEngine.resolve_font("LiberationSans-Bold.ttf", int(h * 0.024))
            draw.ellipse([safe_zone.left, rec_y, safe_zone.left + 26, rec_y + 26], fill=(255, 30, 30, 255))
            draw.text((safe_zone.left + 36, rec_y + 2), "REC  [SP 0:14:02:18]", font=fnt_vcr, fill=(240, 240, 240, 240))
            tuner_text = f"{channel_tag}  STEREO // HI-FI"
            bbox_tuner = draw.textbbox((0, 0), tuner_text, font=fnt_vcr)
            tuner_w = bbox_tuner[2] - bbox_tuner[0]
            draw.text((safe_zone.right - tuner_w, rec_y + 2), tuner_text, font=fnt_vcr, fill=(0, 255, 102, 230))
            bot_y = safe_zone.bottom - 40
            date_str = str(meta.get("date") or meta.get("timestamp_label") or "OCT 24 1994  11:42 PM").upper()
            draw.text((safe_zone.left, bot_y), date_str, font=fnt_tape, fill=(200, 200, 200, 210))

        if tape_label:
            badge_y = rec_y + (int(h * 0.07) if osd_on else 0)
            badge_w = int(w * 0.48)
            badge_h = int(h * 0.052)
            fnt_badge = DynamicTypographyEngine.resolve_font("Montserrat-Black.ttf", int(h * 0.026))
            draw.rectangle(
                [(safe_zone.left, badge_y), (safe_zone.left + badge_w, badge_y + badge_h)],
                fill=(20, 2, 2, 230),
                outline=(255, 40, 40, 230),
                width=2,
            )
            bbox_b = draw.textbbox((0, 0), tape_label, font=fnt_badge)
            b_tw = bbox_b[2] - bbox_b[0]
            draw.text(
                (safe_zone.left + (badge_w - b_tw) // 2, badge_y + int(badge_h * 0.18)),
                tape_label,
                font=fnt_badge,
                fill=(255, 50, 50, 255),
            )

        for sy in range(0, h, 4):
            draw.line([(0, sy), (w, sy)], fill=(0, 0, 0, 45), width=1)

        img_with_vhs = Image.alpha_composite(draw_img, overlay).convert("RGB")

        if tape_label:
            title_y = badge_y + badge_h + int(h * 0.12)
        else:
            title_y = rec_y + int(h * 0.10)
        title_font_size = int(w * 0.062)
        fill_col = resolve_ctr_fill_color(meta.get("primary_color"))

        final_img = DynamicTypographyEngine.draw_text_with_effects(
            canvas=img_with_vhs,
            text=title,
            pos_x=safe_zone.left,
            pos_y=title_y,
            max_width=int(safe_zone.width * 0.82),
            font_name="Montserrat-Black.ttf",
            font_size=title_font_size,
            fill_color=fill_col,
            stroke_color="#000000",
            stroke_width=12,
            shadow_offset=(8, 12),
            shadow_blur=4,
            glow_color=None,
            glow_radius=0,
            tilt_angle=0.0,
            align="center",
        )
        return final_img
