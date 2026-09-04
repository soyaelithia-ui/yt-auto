"""
src/media/thumbnails/layouts/scp_hud.py - SCP Foundation Found Footage 9:16 Vertical Layout.
"""
from __future__ import annotations

from typing import Any, Dict
from PIL import Image, ImageDraw

from src.media.thumbnails.layout import SafeZone
from src.media.thumbnails.layouts.base import BaseThumbnailLayout, LayoutRegistry
from src.media.thumbnails.typography import DynamicTypographyEngine


@LayoutRegistry.register("scp", "scp-hud", "found-footage", "moku-scp-shorts")
class ScpFoundFootageLayout(BaseThumbnailLayout):
    """
    Renders an authentic SCP Foundation security camera / found-footage HUD:
    - Camcorder REC indicator and timestamp.
    - Camera locator (CAM-04 // SITE-19).
    - Top classification bar and yellow/black hazard chevrons.
    - Containment anomaly alert badge (EUCLID / KETER / APOLLYON).
    - 3D hook title rendered strictly inside the Shorts safe zone.
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

        hazard_level = str(metadata.get("hazard_level", "EUCLID")).upper()
        site_id = str(metadata.get("site", "SITE-19")).upper()
        cam_id = str(metadata.get("cam", "CAM-04")).upper()

        fnt_hud = DynamicTypographyEngine.resolve_font("LiberationSans-Bold.ttf", int(h * 0.018))
        fnt_badge = DynamicTypographyEngine.resolve_font("Montserrat-Black.ttf", int(h * 0.024))
        fnt_banner = DynamicTypographyEngine.resolve_font("LiberationSans-Bold.ttf", int(h * 0.015))

        # 1. Top Security HUD Bar
        hud_y = safe_zone.top
        # Red REC indicator dot
        draw.ellipse([safe_zone.left, hud_y, safe_zone.left + 22, hud_y + 22], fill=(255, 30, 30, 255))
        draw.text((safe_zone.left + 32, hud_y + 2), "REC [00:14:28:09]", font=fnt_hud, fill=(240, 240, 240, 230))

        cam_text = f"{cam_id} // {site_id}"
        bbox_cam = draw.textbbox((0, 0), cam_text, font=fnt_hud)
        cam_w = bbox_cam[2] - bbox_cam[0]
        if cam_w > safe_zone.width - 340:
            cam_text = f"{cam_id[:10]} // {site_id[:10]}"
            bbox_cam = draw.textbbox((0, 0), cam_text, font=fnt_hud)
            cam_w = bbox_cam[2] - bbox_cam[0]
        draw.text((safe_zone.right - cam_w, hud_y + 2), cam_text, font=fnt_hud, fill=(200, 220, 220, 200))

        # 2. Foundation Classification Banner
        banner_y = hud_y + int(h * 0.035)
        banner_w = safe_zone.width
        banner_h = int(h * 0.032)
        draw.rectangle(
            [(safe_zone.left, banner_y), (safe_zone.left + banner_w, banner_y + banner_h)],
            fill=(10, 15, 20, 220),
            outline=(255, 200, 0, 220),
            width=2,
        )
        banner_text = "TOP SECRET // CLASIFICACIÓN DE CONTENCIÓN // ARCHIVO O5"
        bbox_ban = draw.textbbox((0, 0), banner_text, font=fnt_banner)
        ban_w = bbox_ban[2] - bbox_ban[0]
        draw.text(
            (safe_zone.left + (banner_w - ban_w) // 2, banner_y + int(banner_h * 0.18)),
            banner_text,
            font=fnt_banner,
            fill=(255, 220, 50, 240),
        )

        # 3. Hazard Chevrons / Warning Bar
        chevron_y = banner_y + banner_h + 4
        chevron_h = int(h * 0.012)
        draw.rectangle(
            [(safe_zone.left, chevron_y), (safe_zone.left + banner_w, chevron_y + chevron_h)],
            fill=(20, 20, 20, 255),
        )
        step = int(h * 0.02)
        for cx in range(safe_zone.left, safe_zone.left + banner_w, step):
            draw.polygon([
                (cx, chevron_y + chevron_h),
                (cx + step // 2, chevron_y),
                (cx + step // 2 + 8, chevron_y),
                (cx + 8, chevron_y + chevron_h),
            ], fill=(255, 210, 0, 255))

        # 4. Containment Anomaly Alert Badge
        badge_y = chevron_y + chevron_h + int(h * 0.025)
        badge_w = int(safe_zone.width * 0.65)
        badge_h = int(h * 0.045)
        badge_x = safe_zone.left + (safe_zone.width - badge_w) // 2
        badge_bg = (180, 20, 20, 235) if hazard_level in ("KETER", "APOLLYON") else (200, 140, 0, 235)
        draw.rectangle(
            [(badge_x, badge_y), (badge_x + badge_w, badge_y + badge_h)],
            fill=badge_bg,
            outline=(255, 255, 255, 240),
            width=3,
        )
        badge_text = f"ALERTA: CLASE {hazard_level}"
        bbox_badge = draw.textbbox((0, 0), badge_text, font=fnt_badge)
        b_text_w = bbox_badge[2] - bbox_badge[0]
        draw.text(
            (badge_x + (badge_w - b_text_w) // 2, badge_y + int(badge_h * 0.18)),
            badge_text,
            font=fnt_badge,
            fill=(255, 255, 255, 255),
        )

        # 5. Framing Brackets on 4 corners of safe zone
        corner_len = int(w * 0.08)
        c_w = 4
        bracket_col = (180, 220, 220, 180)
        # Top-Left
        draw.line([(safe_zone.left, safe_zone.top), (safe_zone.left + corner_len, safe_zone.top)], fill=bracket_col, width=c_w)
        draw.line([(safe_zone.left, safe_zone.top), (safe_zone.left, safe_zone.top + corner_len)], fill=bracket_col, width=c_w)
        # Top-Right
        draw.line([(safe_zone.right, safe_zone.top), (safe_zone.right - corner_len, safe_zone.top)], fill=bracket_col, width=c_w)
        draw.line([(safe_zone.right, safe_zone.top), (safe_zone.right, safe_zone.top + corner_len)], fill=bracket_col, width=c_w)
        # Bottom-Left
        draw.line([(safe_zone.left, safe_zone.bottom), (safe_zone.left + corner_len, safe_zone.bottom)], fill=bracket_col, width=c_w)
        draw.line([(safe_zone.left, safe_zone.bottom), (safe_zone.left, safe_zone.bottom - corner_len)], fill=bracket_col, width=c_w)
        # Bottom-Right
        draw.line([(safe_zone.right, safe_zone.bottom), (safe_zone.right - corner_len, safe_zone.bottom)], fill=bracket_col, width=c_w)
        draw.line([(safe_zone.right, safe_zone.bottom), (safe_zone.right, safe_zone.bottom - corner_len)], fill=bracket_col, width=c_w)

        # 6. Subtle CRT Scanlines
        scanline_step = 6
        for sy in range(0, h, scanline_step):
            draw.line([(0, sy), (w, sy)], fill=(0, 0, 0, 35), width=1)

        # Composite HUD overlay
        img_with_hud = Image.alpha_composite(draw_img, overlay).convert("RGB")

        # 7. Render 3D Typography Hook Title
        title_y = badge_y + badge_h + int(h * 0.05)
        title_font_size = int(w * 0.085)
        primary_col = metadata.get("primary_color") or "#FFE600"
        accent_col = metadata.get("accent_color") or "#FF003B"
        tilt = float(metadata.get("tilt_angle", -3.0))

        final_img = DynamicTypographyEngine.draw_text_with_effects(
            canvas=img_with_hud,
            text=title,
            pos_x=safe_zone.left,
            pos_y=title_y,
            max_width=safe_zone.width,
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
