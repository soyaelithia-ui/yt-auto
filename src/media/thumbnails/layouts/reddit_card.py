"""
src/media/thumbnails/layouts/reddit_card.py - Reddit Drama Card 16:9 Horizontal Layout.
"""
from __future__ import annotations

from typing import Any, Dict
from PIL import Image, ImageDraw

from src.media.thumbnails.layout import SafeZone
from src.media.thumbnails.layouts.base import BaseThumbnailLayout, LayoutRegistry
from src.media.thumbnails.typography import DynamicTypographyEngine


@LayoutRegistry.register("reddit", "aita", "drama", "confession", "aelithia", "aelithia-aita-long")
class RedditDramaCardLayout(BaseThumbnailLayout):
    """
    Renders an authentic Reddit drama card interface:
    - Glassmorphic translucent Reddit post card with subreddit tag and upvotes.
    - Dramatic confession quote / bubble.
    - 3D high-CTR title hook positioned safely avoiding bottom-right timestamp zone.
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

        subreddit = str(metadata.get("subreddit", "r/AmItheAsshole"))
        upvotes = str(metadata.get("upvotes", "28.4k"))
        user_handle = str(metadata.get("author", "u/anon_confession"))

        fnt_sub = DynamicTypographyEngine.resolve_font("LiberationSans-Bold.ttf", int(h * 0.030))
        fnt_meta = DynamicTypographyEngine.resolve_font("LiberationSans-Regular.ttf", int(h * 0.022))
        fnt_upvotes = DynamicTypographyEngine.resolve_font("LiberationSans-Bold.ttf", int(h * 0.028))
        fnt_quote = DynamicTypographyEngine.resolve_font("LiberationSans-Bold.ttf", int(h * 0.028))

        # 1. Left Glassmorphic Reddit Post Card
        card_x = safe_zone.left
        card_y = safe_zone.top + int(h * 0.05)
        card_w = int(w * 0.44)
        card_h = int(h * 0.58)

        # Translucent background with soft border
        draw.rounded_rectangle(
            [(card_x, card_y), (card_x + card_w, card_y + card_h)],
            radius=20,
            fill=(20, 24, 30, 220),
            outline=(255, 87, 34, 180),  # Reddit Orange-Red
            width=3,
        )

        # Reddit Subreddit Icon (Orange circle with white 'r/')
        icon_r = int(h * 0.028)
        icon_cx = card_x + 35 + icon_r
        icon_cy = card_y + 35 + icon_r
        draw.ellipse([icon_cx - icon_r, icon_cy - icon_r, icon_cx + icon_r, icon_cy + icon_r], fill=(255, 69, 0, 255))
        draw.text((icon_cx - 12, icon_cy - 14), "r/", font=fnt_sub, fill=(255, 255, 255, 255))

        # Subreddit Name & Author info
        draw.text((icon_cx + icon_r + 15, card_y + 30), subreddit, font=fnt_sub, fill=(255, 255, 255, 255))
        draw.text((icon_cx + icon_r + 15, card_y + 68), f"Publicado por {user_handle} • 4h", font=fnt_meta, fill=(180, 190, 200, 230))

        # Upvote pill / counter
        pill_x = card_x + 35
        pill_y = card_y + card_h - 75
        pill_w = int(card_w * 0.42)
        pill_h = 50
        draw.rounded_rectangle(
            [(pill_x, pill_y), (pill_x + pill_w, pill_y + pill_h)],
            radius=25,
            fill=(36, 42, 52, 240),
            outline=(255, 87, 34, 200),
            width=2,
        )
        draw.text((pill_x + 20, pill_y + 10), f"⬆  {upvotes}  ⬇", font=fnt_upvotes, fill=(255, 100, 40, 255))

        # Dramatic callout excerpt
        callout_raw = metadata.get("quote") or metadata.get("callout") or metadata.get("excerpt")
        if not callout_raw:
            raw_title = str(metadata.get("title_raw") or title).strip(' "\'')
            if len(raw_title) > 20:
                callout_raw = raw_title
            else:
                callout_raw = "Canceló todo frente a 200 personas... y ahora su familia me culpa a MÍ."

        callout_lines_split = DynamicTypographyEngine.split_title_to_safe_lines(str(callout_raw), max_chars_per_line=30)
        if len(callout_lines_split) == 1:
            callout_lines = [f'"{callout_lines_split[0]}"']
        else:
            callout_lines = [f'"{callout_lines_split[0]}', f'{callout_lines_split[1]}"']

        qy = card_y + 130
        for qline in callout_lines[:2]:
            draw.text((card_x + 35, qy), qline, font=fnt_quote, fill=(240, 240, 250, 240))
            qy += int(h * 0.045)

        # 2. Dramatic Warning / Drama Badge on Right Side
        badge_x = card_x + card_w + int(w * 0.04)
        badge_y = safe_zone.top + int(h * 0.06)
        badge_w = safe_zone.right - badge_x
        badge_h = int(h * 0.055)
        draw.rounded_rectangle(
            [(badge_x, badge_y), (badge_x + badge_w, badge_y + badge_h)],
            radius=12,
            fill=(230, 20, 70, 240),
            outline=(255, 255, 255, 220),
            width=2,
        )
        fnt_badge = DynamicTypographyEngine.resolve_font("Montserrat-Black.ttf", int(h * 0.026))
        b_text = str(metadata.get("category") or metadata.get("badge") or "DRAMA FAMILIAR // CONFESIÓN VIRAL").upper()
        bbox_b = draw.textbbox((0, 0), b_text, font=fnt_badge)
        b_tw = bbox_b[2] - bbox_b[0]
        draw.text(
            (badge_x + (badge_w - b_tw) // 2, badge_y + int(badge_h * 0.20)),
            b_text,
            font=fnt_badge,
            fill=(255, 255, 255, 255),
        )

        # Composite HUD overlay
        img_with_card = Image.alpha_composite(draw_img, overlay).convert("RGB")

        # 3. Render High-CTR 3D Typography Hook Title on Right Side
        title_y = badge_y + badge_h + int(h * 0.08)
        title_font_size = int(w * 0.058)
        primary_col = metadata.get("primary_color") or "#FFE600"
        accent_col = metadata.get("accent_color") or "#FF4081"
        tilt = float(metadata.get("tilt_angle", -3.0))

        final_img = DynamicTypographyEngine.draw_text_with_effects(
            canvas=img_with_card,
            text=title,
            pos_x=badge_x,
            pos_y=title_y,
            max_width=badge_w,
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
