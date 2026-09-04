"""
src/media/thumbnails/layouts/cinematic.py - General Cinematic Editorial Layout (Fallback).
"""
from __future__ import annotations

from typing import Any, Dict
from PIL import Image, ImageDraw

from src.media.thumbnails.layout import SafeZone
from src.media.thumbnails.layouts.base import BaseThumbnailLayout, LayoutRegistry
from src.media.thumbnails.typography import DynamicTypographyEngine


@LayoutRegistry.register_default
@LayoutRegistry.register("cinematic", "general", "default")
class GeneralCinematicLayout(BaseThumbnailLayout):
    """
    High-craft editorial fallback layout:
    - Subtle chiaroscuro vignette lighting.
    - Minimalist documentary badge bar.
    - 3D typography hook rendered strictly within safe zones.
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
        is_vertical = h > w
        draw_img = canvas.copy().convert("RGBA")
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        category = str(metadata.get("category", metadata.get("archetype", "HISTORIA EXCLUSIVA"))).upper()

        fnt_badge = DynamicTypographyEngine.resolve_font("LiberationSans-Bold.ttf", int(h * (0.020 if is_vertical else 0.024)))

        # 1. Subtle Editorial Top Badge
        badge_y = safe_zone.top + int(h * 0.02)
        badge_w = int(safe_zone.width * (0.60 if is_vertical else 0.35))
        badge_h = int(h * (0.035 if is_vertical else 0.045))
        draw.rounded_rectangle(
            [(safe_zone.left, badge_y), (safe_zone.left + badge_w, badge_y + badge_h)],
            radius=8,
            fill=(15, 18, 24, 220),
            outline=(255, 230, 0, 200),
            width=2,
        )
        badge_text = f"• {category} •"
        bbox_b = draw.textbbox((0, 0), badge_text, font=fnt_badge)
        b_tw = bbox_b[2] - bbox_b[0]
        draw.text(
            (safe_zone.left + (badge_w - b_tw) // 2, badge_y + int(badge_h * 0.20)),
            badge_text,
            font=fnt_badge,
            fill=(255, 230, 0, 240),
        )

        # Composite badge overlay
        img_with_badge = Image.alpha_composite(draw_img, overlay).convert("RGB")

        # 2. Render 3D Typography Hook Title
        title_y = badge_y + badge_h + int(h * (0.06 if is_vertical else 0.10))
        title_font_size = int(w * (0.082 if is_vertical else 0.062))
        primary_col = metadata.get("primary_color") or "#FFE600"
        accent_col = metadata.get("accent_color") or "#FF003B"
        tilt = float(metadata.get("tilt_angle", -3.0))

        final_img = DynamicTypographyEngine.draw_text_with_effects(
            canvas=img_with_badge,
            text=title,
            pos_x=safe_zone.left,
            pos_y=title_y,
            max_width=int(safe_zone.width * 0.90),
            font_name="Montserrat-Black.ttf",
            font_size=title_font_size,
            fill_color=primary_col,
            stroke_color="#000000",
            stroke_width=12,
            shadow_offset=(8, 12),
            shadow_blur=4,
            glow_color=accent_col,
            glow_radius=8,
            tilt_angle=tilt,
            align="center",
        )
        return final_img
