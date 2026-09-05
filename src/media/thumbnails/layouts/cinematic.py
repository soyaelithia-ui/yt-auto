"""
src/media/thumbnails/layouts/cinematic.py - General Cinematic Editorial Layout (Fallback).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Union
from PIL import Image, ImageDraw, ImageEnhance, ImageColor

from src.media.thumbnails.layout import AspectLayoutManager, SafeZone
from src.media.thumbnails.layouts.base import BaseThumbnailLayout, LayoutRegistry
from src.media.thumbnails.typography import DynamicTypographyEngine

logger = logging.getLogger("cinematic_layout")


@LayoutRegistry.register_default
@LayoutRegistry.register(
    "cinematic",
    "general",
    "default",
    "parametric",
    # Former scp_hud / reddit_card lane keys — modules deleted; fall back here.
    "scp",
    "scp-hud",
    "found-footage",
    "moku-scp-shorts",
    "reddit",
    "aita",
    "drama",
    "confession",
    "aelithia",
    "aelithia-aita-long",
)
class GeneralCinematicLayout(BaseThumbnailLayout):
    """
    Parametric high-craft editorial thumbnail layout:
    - Resolves dynamic channel palette (accent, highlight) with neutral high-contrast fallback.
    - Parametric text box styling: badge, boxed, outline, banner, minimal.
    - Parametric subject contrast adjustment.
    - Strict YouTube safe-zone positioning for both 16:9 (1280x720 / 1920x1080) and 9:16 (1080x1920).
    - Resilient degradation for empty or atypical text hooks.
    """

    @staticmethod
    def _is_valid_color(col: Any) -> bool:
        if not col or not isinstance(col, str):
            return False
        c = col.strip()
        if c.startswith("#") and len(c) in (4, 7, 9):
            try:
                int(c[1:], 16)
                return True
            except ValueError:
                return False
        try:
            ImageColor.getrgb(c)
            return True
        except Exception:
            return False

    @classmethod
    def resolve_channel_palette(
        cls,
        channel_id: Optional[str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """
        Resolves primary and accent colors directly from ChannelProfileRegistry.
        Degrades gracefully to a neutral high-contrast palette if channel is missing or invalid.
        """
        meta = metadata or {}
        neutral = {
            "primary": "#FFE600",
            "accent": "#FF003B",
            "highlight": "#FFFFFF",
            "shadow": "#000000",
        }

        channel_primary = None
        channel_accent = None

        chan_key = str(channel_id or meta.get("channel_id", "")).strip().lower()
        base_key = chan_key.split("-")[0] if "-" in chan_key else chan_key

        if chan_key or base_key:
            try:
                from src.core.channel_profile import ChannelProfileRegistry
                prof = None
                for k in [chan_key, base_key]:
                    if k:
                        try:
                            prof = ChannelProfileRegistry.get_channel(k)
                            break
                        except KeyError:
                            continue

                if prof and hasattr(prof, "visual") and hasattr(prof.visual, "palette"):
                    pal = prof.visual.palette
                    if cls._is_valid_color(pal.highlight):
                        channel_primary = pal.highlight
                    elif cls._is_valid_color(pal.primary):
                        channel_primary = pal.primary
                    if cls._is_valid_color(pal.accent):
                        channel_accent = pal.accent
            except Exception as exc:
                logger.debug("Failed reading ChannelProfileRegistry for '%s': %s", chan_key, exc)

        meta_primary = meta.get("primary_color")
        meta_accent = meta.get("accent_color")

        primary = meta_primary if cls._is_valid_color(meta_primary) else (channel_primary or neutral["primary"])
        accent = meta_accent if cls._is_valid_color(meta_accent) else (channel_accent or neutral["accent"])

        return {
            "primary": primary,
            "accent": accent,
            "highlight": neutral["highlight"],
            "shadow": neutral["shadow"],
        }

    def apply_layout(
        self,
        canvas: Image.Image,
        title: str,
        channel_id: str,
        safe_zone: SafeZone,
        metadata: Optional[Dict[str, Any]] = None,
        lane_id: Optional[str] = None,
        resolved_asset_path: Optional[Union[str, Any]] = None,
        **kwargs: Any,
    ) -> Image.Image:
        w, h = canvas.size
        is_vertical = h > w
        meta = dict(metadata or {})
        if lane_id:
            meta["lane_id"] = lane_id
        if resolved_asset_path:
            meta["resolved_asset_path"] = str(resolved_asset_path)

        if safe_zone is None:
            safe_zone = AspectLayoutManager.get_safe_zone(w, h)

        draw_img = canvas.copy().convert("RGBA")

        # 1. Subject Contrast Enhancement (Parametric)
        subj_contrast = meta.get("subject_contrast", meta.get("contrast_level"))
        if subj_contrast is not None:
            try:
                c_val = float(subj_contrast)
                if 0.1 <= c_val <= 4.0 and c_val != 1.0:
                    enhancer = ImageEnhance.Contrast(draw_img)
                    draw_img = enhancer.enhance(c_val)
            except (ValueError, TypeError):
                pass

        # 2. Resolve Palette (Directly from ChannelProfileRegistry with neutral fallback)
        palette = self.resolve_channel_palette(channel_id=channel_id, metadata=meta)
        primary_col = palette["primary"]
        accent_col = palette["accent"]

        try:
            accent_rgb = ImageColor.getrgb(accent_col)[:3]
        except Exception:
            accent_rgb = (255, 0, 59)

        # 3. Clean and sanitize title (Graceful handling of atypical strings)
        clean_title = (title or "").strip()
        if not clean_title:
            clean_title = str(meta.get("title_raw", meta.get("category", "HISTORIA EXCLUSIVA"))).strip()
            if not clean_title:
                clean_title = "HISTORIA EXCLUSIVA"

        category = str(meta.get("category", meta.get("archetype", "HISTORIA EXCLUSIVA"))).upper().strip()
        if not category:
            category = "HISTORIA EXCLUSIVA"

        text_box_style = str(meta.get("text_box_style", "badge")).lower()
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # 4. Badges and Text Box Styling
        badge_h = int(h * (0.035 if is_vertical else 0.045))
        badge_y = safe_zone.top + int(h * (0.015 if is_vertical else 0.02))

        fnt_badge = DynamicTypographyEngine.resolve_font(
            "LiberationSans-Bold.ttf",
            int(h * (0.020 if is_vertical else 0.024))
        )

        badge_w = int(safe_zone.width * (0.60 if is_vertical else 0.35))
        if text_box_style in ("badge", "boxed", "banner", "default", "editorial"):
            badge_text = f"• {category} •"
            draw.rounded_rectangle(
                [(safe_zone.left, badge_y), (safe_zone.left + badge_w, badge_y + badge_h)],
                radius=8,
                fill=(15, 18, 24, 220),
                outline=(*accent_rgb, 220),
                width=2,
            )
            bbox_b = draw.textbbox((0, 0), badge_text, font=fnt_badge)
            b_tw = bbox_b[2] - bbox_b[0]
            draw.text(
                (safe_zone.left + max(4, (badge_w - b_tw) // 2), badge_y + int(badge_h * 0.20)),
                badge_text,
                font=fnt_badge,
                fill=(*accent_rgb, 240),
            )

        # 5. Position 3D Typography Hook Title strictly within safe zones
        if text_box_style in ("minimal", "outline"):
            title_y = safe_zone.top + int(h * (0.03 if is_vertical else 0.05))
        else:
            title_y = badge_y + badge_h + int(h * (0.04 if is_vertical else 0.06))

        title_font_size = int(w * (0.080 if is_vertical else 0.060))
        max_title_w = int(safe_zone.width * 0.92)

        # Estimate lines and height to ensure bounding inside safe zones
        estimated_lines = 1
        if len(clean_title) > 35:
            estimated_lines = 3
        elif len(clean_title) > 18:
            estimated_lines = 2
        estimated_text_h = int(estimated_lines * title_font_size * 1.15)

        # Guard against safe-zone bottom collision
        if title_y + estimated_text_h > safe_zone.bottom:
            excess = (title_y + estimated_text_h) - safe_zone.bottom
            title_y = max(safe_zone.top + badge_h + 10, title_y - excess)

        # Draw decorative background box/banner if requested
        if text_box_style in ("boxed", "outline", "banner"):
            box_y0 = max(safe_zone.top, title_y - 10)
            box_y1 = min(safe_zone.bottom, title_y + estimated_text_h + 18)

            if text_box_style == "boxed":
                draw.rounded_rectangle(
                    [(safe_zone.left, box_y0), (safe_zone.left + max_title_w, box_y1)],
                    radius=12,
                    fill=(12, 16, 22, 210),
                    outline=(*accent_rgb, 200),
                    width=3,
                )
            elif text_box_style == "outline":
                draw.rounded_rectangle(
                    [(safe_zone.left, box_y0), (safe_zone.left + max_title_w, box_y1)],
                    radius=12,
                    fill=(0, 0, 0, 0),
                    outline=(*accent_rgb, 220),
                    width=3,
                )
            elif text_box_style == "banner":
                draw.rectangle(
                    [(safe_zone.left, box_y0), (safe_zone.right, box_y1)],
                    fill=(10, 14, 20, 220),
                    outline=(*accent_rgb, 180),
                    width=2,
                )

        img_with_overlay = Image.alpha_composite(draw_img, overlay).convert("RGB")

        # 6. Render 3D Typography
        tilt = float(meta.get("tilt_angle", -3.0))
        final_img = DynamicTypographyEngine.draw_text_with_effects(
            canvas=img_with_overlay,
            text=clean_title,
            pos_x=safe_zone.left,
            pos_y=title_y,
            max_width=max_title_w,
            font_name="Montserrat-Black.ttf",
            font_size=title_font_size,
            fill_color=primary_col,
            stroke_color="#000000",
            stroke_width=12 if not is_vertical else 10,
            shadow_offset=(8, 12) if not is_vertical else (6, 10),
            shadow_blur=4,
            glow_color=accent_col,
            glow_radius=8,
            tilt_angle=tilt,
            align="center",
        )
        return final_img
