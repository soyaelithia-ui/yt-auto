"""
src/media/thumbnail_engine.py - Resilient High-CTR Thumbnail Generation Engine.

Features:
- Dynamic font discovery with graceful TrueType fallbacks (LiberationSans, DejaVu, KaTeX).
- Strict validation preventing unreadable default bitmap fonts.
- Multi-layer composition: background artwork / gradient, dark contrast scrim, classification badge.
- UTF-8 safe rendering for accented characters (á, é, í, ó, ú, ñ).
- High-contrast typography with drop shadows and highlight accents.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List, Optional, Tuple, Union

from PIL import Image, ImageDraw, ImageFont, ImageFilter

logger = logging.getLogger("thumbnail_engine")

SYSTEM_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/opt/hermes/hermes-webui/static/vendor/katex/0.16.22/fonts/KaTeX_SansSerif-Bold.ttf",
    "/opt/hermes/hermes-webui/static/vendor/katex/0.16.22/fonts/KaTeX_Main-Bold.ttf",
]


class ResilientThumbnailEngine:
    """Engine for producing 720p high-impact YouTube thumbnails (1080p opt-in)."""

    def __init__(self, custom_font_paths: Optional[List[str]] = None) -> None:
        self.font_candidates = (custom_font_paths or []) + SYSTEM_FONT_CANDIDATES

    def resolve_font(self, size: int) -> ImageFont.FreeTypeFont:
        """Finds and loads the first valid TrueType font at the specified size."""
        for candidate in self.font_candidates:
            if candidate and Path(candidate).is_file():
                try:
                    font = ImageFont.truetype(candidate, size)
                    return font
                except Exception as e:
                    logger.debug("Failed loading font %s: %s", candidate, e)
                    continue

        # If none of the explicit candidates exist, search system paths
        for root, _, files in os.walk("/usr/share/fonts"):
            for f in files:
                if f.endswith(".ttf") or f.endswith(".otf"):
                    full_p = os.path.join(root, f)
                    try:
                        return ImageFont.truetype(full_p, size)
                    except Exception:
                        continue

        raise RuntimeError(
            f"No valid TrueType font found on the system. Tested: {self.font_candidates}"
        )

    def generate(
        self,
        output_path: Union[Path, str],
        title_main: str = "SCP-2000",
        title_sub: str = "DEUS EX MACHINA",
        highlight_box: str = "EL REINICIO DE LA HUMANIDAD",
        badge_text: str = "NIVEL 5 // CLASIFICADO // TOP SECRET",
        background_image: Optional[Union[Path, str]] = None,
        accent_color: Tuple[int, int, int] = (0, 255, 180),
        subtitle_color: Tuple[int, int, int] = (255, 255, 255),
        badge_color: Tuple[int, int, int] = (190, 25, 35),
        width: int = 1280,
        height: int = 720,
    ) -> Path:
        """Generates a 1280x720 high-contrast cinematic thumbnail (720p default)."""
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        w, h = width, height

        # 1. Base Canvas / Background
        if background_image and Path(background_image).is_file():
            base_img = Image.open(background_image).convert("RGBA")
            base_img = base_img.resize((w, h), Image.Resampling.LANCZOS)
        else:
            base_img = Image.new("RGBA", (w, h), color=(3, 10, 18, 255))
            draw_bg = ImageDraw.Draw(base_img)
            # Create atmospheric gradient
            for y in range(h):
                r = int(3 + (y / h) * 10)
                g = int(10 + (y / h) * 25)
                b = int(18 + (y / h) * 45)
                draw_bg.line([(0, y), (w, y)], fill=(r, g, b, 255))

            # Draw geometric tech grid / radar aesthetic
            cx, cy = int(w * 0.72), int(h * 0.52)
            for rad in [140, 260, 380, 500]:
                draw_bg.ellipse(
                    [cx - rad, cy - rad, cx + rad, cy + rad],
                    outline=(accent_color[0], accent_color[1], accent_color[2], 60),
                    width=3,
                )
            draw_bg.line(
                [(cx - 520, cy), (cx + 520, cy)],
                fill=(accent_color[0], accent_color[1], accent_color[2], 70),
                width=2,
            )
            draw_bg.line(
                [(cx, cy - 520), (cx, cy + 520)],
                fill=(accent_color[0], accent_color[1], accent_color[2], 70),
                width=2,
            )

        # 2. Add Left Scrim / Dark Gradient for High Text Contrast
        scrim_overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw_scrim = ImageDraw.Draw(scrim_overlay)
        # Horizontal dark gradient from left (alpha 230) to center (alpha 0)
        for x in range(int(w * 0.75)):
            alpha = int(230 * (1.0 - (x / (w * 0.75))))
            draw_scrim.line([(x, 0), (x, h)], fill=(0, 0, 0, alpha))

        # Composite base and scrim
        composite = Image.alpha_composite(base_img, scrim_overlay)
        draw = ImageDraw.Draw(composite)

        # 3. Load Verified TrueType Fonts
        font_badge = self.resolve_font(34)
        font_main = self.resolve_font(118)
        font_sub = self.resolve_font(56)
        font_highlight = self.resolve_font(52)
        font_footer = self.resolve_font(30)

        # 4. Classification Badge Box
        badge_x, badge_y = 80, 80
        badge_w, badge_h = 760, 68
        draw.rectangle(
            [(badge_x, badge_y), (badge_x + badge_w, badge_y + badge_h)],
            fill=badge_color + (255,),
            outline=(255, 75, 85, 255),
            width=3,
        )
        draw.text(
            (badge_x + 25, badge_y + 14),
            badge_text,
            fill=(255, 255, 255, 255),
            font=font_badge,
        )

        # 5. Main Title with Strong Drop Shadow & Glow
        main_x, main_y = 80, 195
        # Shadow
        draw.text(
            (main_x + 6, main_y + 6),
            title_main,
            fill=(0, 0, 0, 255),
            font=font_main,
        )
        draw.text(
            (main_x + 3, main_y + 3),
            title_main,
            fill=(0, int(accent_color[1] * 0.3), int(accent_color[2] * 0.3), 255),
            font=font_main,
        )
        # Main text
        draw.text(
            (main_x, main_y),
            title_main,
            fill=accent_color + (255,),
            font=font_main,
        )

        # 6. Subtitle with Shadow
        sub_x, sub_y = 80, 345
        draw.text(
            (sub_x + 4, sub_y + 4),
            title_sub,
            fill=(0, 0, 0, 255),
            font=font_sub,
        )
        draw.text(
            (sub_x, sub_y),
            title_sub,
            fill=subtitle_color + (255,),
            font=font_sub,
        )

        # 7. Highlight Accent Box
        if highlight_box:
            hl_x, hl_y = 80, 445
            # Measure text width
            bbox = font_highlight.getbbox(highlight_box)
            text_w = bbox[2] - bbox[0]
            box_w = max(900, text_w + 50)
            box_h = 85

            draw.rectangle(
                [(hl_x, hl_y), (hl_x + box_w, hl_y + box_h)],
                fill=(0, 35, 25, 240),
                outline=accent_color + (255,),
                width=3,
            )
            draw.text(
                (hl_x + 25, hl_y + 14),
                highlight_box,
                fill=accent_color + (255,),
                font=font_highlight,
            )

        # 8. Footer Metadata Tags
        draw.text(
            (80, 890),
            "• ARCHIVO CONFIDENCIAL // FUNDACIÓN SCP",
            fill=(180, 220, 210, 230),
            font=font_footer,
        )
        draw.text(
            (80, 938),
            "• INSTALACIÓN SECRETA DE YELLOWSTONE",
            fill=(180, 220, 210, 230),
            font=font_footer,
        )

        # Convert to RGB and save high quality JPEG
        final_img = composite.convert("RGB")
        final_img.save(str(out_p), quality=95, optimize=True)
        logger.info(
            "Thumbnail successfully generated: %s (%dx%d, %.2f KB)",
            out_p.name,
            w,
            h,
            out_p.stat().st_size / 1024,
        )
        return out_p