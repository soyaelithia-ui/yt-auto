"""
src/media/thumbnails/layouts/cinematic.py - General Cinematic Editorial Layout (Fallback).
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional, Union
from PIL import Image, ImageDraw, ImageEnhance, ImageColor

from src.media.thumbnails.layout import AspectLayoutManager, SafeZone
from src.media.thumbnails.layouts.base import BaseThumbnailLayout, LayoutRegistry
from src.media.thumbnails.typography import DynamicTypographyEngine

logger = logging.getLogger("cinematic_layout")

_UNSET = object()
CTR_TITLE_FILL = "#F5F0E6"
GENERIC_HOOK_TITLE = "HISTORIA EXCLUSIVA"
INVALID_BADGE_LABELS = frozenset({
    "",
    "NONE",
    "NULL",
    "N/A",
    "NA",
    "HISTORIA EXCLUSIVA",
})
AITA_VERDICTS = frozenset({"YTA", "NTA", "ESH", "INFO"})
SCP_CLASSES = frozenset({"SAFE", "EUCLID", "KETER"})
AITA_NICHES = frozenset({"aita", "reddit", "aelithia"})
SCP_NICHES = frozenset({"scp"})
HORROR_NICHES = frozenset({"horror", "analog", "vhs", "moku"})
_NONE_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])NONE(?![A-Za-z0-9])", re.IGNORECASE)


def _contains_none_token(value: Any) -> bool:
    if value is None:
        return True
    return bool(_NONE_TOKEN_RE.search(str(value)))


def detect_thumbnail_niche(
    channel_id: Optional[str] = None,
    lane_id: Optional[str] = None,
    archetype: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Resolve aita / scp / horror / other from ids and metadata."""
    meta = metadata or {}
    blob = " ".join(
        str(x or "")
        for x in (
            channel_id,
            lane_id,
            archetype,
            meta.get("channel_id"),
            meta.get("lane_id"),
            meta.get("archetype"),
            meta.get("template"),
            meta.get("niche"),
        )
    ).lower()
    if any(key in blob for key in ("aita", "reddit", "aelithia")):
        return "aita"
    if "scp" in blob:
        return "scp"
    if any(key in blob for key in ("horror", "analog", "vhs")) or "moku" in blob:
        return "horror"
    return "other"


def _normalize_badge_text(category: Any) -> Optional[str]:
    if category is None:
        return None
    label = str(category).strip().upper()
    if label in INVALID_BADGE_LABELS:
        return None
    if _contains_none_token(label):
        return None
    return label


def badge_label(
    category: Any,
    niche: Optional[str] = None,
    *,
    channel_id: Optional[str] = None,
    lane_id: Optional[str] = None,
    archetype: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    tape_id: Any = _UNSET,
) -> Optional[str]:
    """Return a drawable badge string, or None to omit the badge entirely."""
    meta = dict(metadata or {})
    niche_key = (
        niche
        or detect_thumbnail_niche(
            channel_id=channel_id or meta.get("channel_id"),
            lane_id=lane_id or meta.get("lane_id"),
            archetype=archetype or meta.get("archetype"),
            metadata=meta,
        )
    ).strip().lower()

    if tape_id is _UNSET and "tape_id" in meta:
        tape_id = meta.get("tape_id")

    if niche_key in HORROR_NICHES:
        if tape_id is _UNSET or tape_id is None:
            return None
        tape = str(tape_id).strip()
        if not tape or _contains_none_token(tape):
            return None
        return f"ADVERTENCIA · {tape.upper()}"

    label = _normalize_badge_text(category)
    if label is None:
        return None
    if niche_key in AITA_NICHES:
        return label if label in AITA_VERDICTS else None
    if niche_key in SCP_NICHES:
        return label if label in SCP_CLASSES else None
    return label


def _is_cream_or_white(col: Any) -> bool:
    if not col or not isinstance(col, str):
        return False
    try:
        r, g, b = ImageColor.getrgb(col.strip())[:3]
    except Exception:
        return False
    mx, mn = max(r, g, b), min(r, g, b)
    if mx < 220 or mn < 170:
        return False
    return (mx - mn) <= 80


def resolve_ctr_fill_color(primary: Any) -> str:
    if _is_cream_or_white(primary):
        return str(primary).strip()
    return CTR_TITLE_FILL


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

        # 3. Clean title. Empty hook stays generic; never promote category/NONE into a badge.
        clean_title = (title or "").strip()
        if not clean_title:
            raw = meta.get("title_raw")
            raw_s = str(raw).strip() if raw is not None else ""
            clean_title = raw_s if raw_s else GENERIC_HOOK_TITLE

        niche = detect_thumbnail_niche(
            channel_id=channel_id,
            lane_id=meta.get("lane_id") or lane_id,
            archetype=meta.get("archetype"),
            metadata=meta,
        )
        tape_kwargs = {"tape_id": meta["tape_id"]} if "tape_id" in meta else {}
        label = badge_label(
            meta.get("category"),
            niche=niche,
            channel_id=channel_id,
            lane_id=meta.get("lane_id") or lane_id,
            archetype=meta.get("archetype"),
            metadata=meta,
            **tape_kwargs,
        )

        text_box_style = str(meta.get("text_box_style") or "badge").lower()
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # 4. Optional badge only. text_box_style "badge" still omits the pill when label is None.
        badge_h = int(h * (0.035 if is_vertical else 0.045))
        badge_y = safe_zone.top + int(h * (0.015 if is_vertical else 0.02))
        draw_badge = bool(label) and text_box_style in ("badge", "boxed", "banner", "default", "editorial")

        if draw_badge:
            fnt_badge = DynamicTypographyEngine.resolve_font(
                "LiberationSans-Bold.ttf",
                int(h * (0.020 if is_vertical else 0.024))
            )
            badge_w = int(safe_zone.width * (0.60 if is_vertical else 0.35))
            badge_text = f"• {label} •"
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

        scp_id = None
        raw_title = str(meta.get("title_raw") or title or "")
        scp_m = re.search(r"(SCP-\d+)", raw_title, re.IGNORECASE)
        if scp_m:
            scp_id = scp_m.group(1).upper()

        title_font_size = int(w * (0.118 if is_vertical else 0.060))
        title_x = safe_zone.left
        max_title_w = int(safe_zone.width * 0.92)
        if is_vertical:
            max_title_w = min(int(w * 0.84), max(64, w - 260))
            title_x = (w - max_title_w) // 2
        estimated_lines = 2 if len(clean_title) > 16 else 1
        estimated_text_h = int(estimated_lines * title_font_size * (1.08 if is_vertical else 1.12))

        if is_vertical:
            ui_bot = min(450, max(1, int(round(h * 450 / 1920))))
            ui_rail = min(120, max(1, int(round(w * 120 / 1080))))
            title_y = max(safe_zone.top, min(safe_zone.bottom, h - ui_bot - 10) - estimated_text_h)
            # Clean safe area positioning without hard geometric bounding box artifacts
            if scp_id:
                fnt_id = DynamicTypographyEngine.resolve_font(
                    "Montserrat-Black.ttf", int(h * 0.064)
                )
                id_bbox = draw.textbbox((0, 0), scp_id, font=fnt_id)
                id_w = id_bbox[2] - id_bbox[0]
                draw.text(
                    ((w - id_w) // 2, safe_zone.top),
                    scp_id,
                    font=fnt_id,
                    fill=(255, 255, 255, 255),
                    stroke_width=5,
                    stroke_fill=(0, 0, 0, 255),
                )
        elif text_box_style in ("minimal", "outline") or not draw_badge:
            title_y = safe_zone.top + int(h * 0.05)
        else:
            title_y = badge_y + badge_h + int(h * 0.06)

        if not is_vertical and title_y + estimated_text_h > safe_zone.bottom:
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

        # 6. CTR type: cream fill, black stroke, no neon glow, no tilt clip
        fill_col = "#FFFFFF" if is_vertical else resolve_ctr_fill_color(meta.get("primary_color") or primary_col)
        final_img = DynamicTypographyEngine.draw_text_with_effects(
            canvas=img_with_overlay,
            text=clean_title,
            pos_x=title_x,
            pos_y=title_y,
            max_width=max_title_w,
            font_name="Montserrat-Black.ttf",
            font_size=title_font_size,
            fill_color=fill_col,
            stroke_color="#000000",
            stroke_width=8 if is_vertical else 5,
            shadow_offset=(0, 0) if is_vertical else (3, 4),
            shadow_blur=0,
            glow_color=None,
            glow_radius=0,
            tilt_angle=0.0,
            align="center",
            line_spacing_mult=1.02 if is_vertical else 1.15,
        )
        return final_img
