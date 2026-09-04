"""
src/media/thumbnails/subject_extractor.py - Thematic Atmospheric Depth & Rim Light Compositor.

Applies authentic atmospheric chiaroscuro focal shading and accent rim lighting
enhancing the narrative backdrop without rudimentary vector stick-figure silhouettes.
"""
from __future__ import annotations

from typing import Tuple
from PIL import Image, ImageDraw, ImageFilter, ImageOps


class AdaptiveSubjectCompositor:
    """
    Applies atmospheric chiaroscuro focal shading and accent depth lighting
    to the base image, enhancing thematic mood without primitive stick-figure silhouettes.
    """

    @staticmethod
    def hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
        h = hex_str.lstrip("#")
        if len(h) == 6:
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return (0, 255, 102)

    @classmethod
    def composite_thematic_subject(
        cls,
        base_img: Image.Image,
        channel_id: str = "moku",
        archetype: str = "tactical_chamber",
        accent_color_hex: str = "#00FF66",
        intensity: float = 0.90,
    ) -> Image.Image:
        """
        Enhances focal depth and atmospheric presence without primitive vector silhouettes.
        Applies directional chiaroscuro grading and accent focal lighting.
        """
        w, h = base_img.size
        r_col, g_col, b_col = cls.hex_to_rgb(accent_color_hex)

        base_rgba = base_img.convert("RGBA")
        vignette_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw_vig = ImageDraw.Draw(vignette_layer)

        # Bottom atmospheric ground shadow / mist
        ground_h = int(h * 0.35)
        for gy in range(ground_h):
            y_pos = h - ground_h + gy
            alpha = int(140 * (gy / ground_h) * intensity)
            draw_vig.line([(0, y_pos), (w, y_pos)], fill=(8, 10, 14, alpha))

        # Accent color rim / ambient glow around lower third
        accent_glow = Image.new("RGBA", (w, h), (r_col, g_col, b_col, 0))
        draw_glow = ImageDraw.Draw(accent_glow)
        glow_h = int(ground_h * 0.5)
        for gy in range(glow_h):
            y_pos = h - glow_h + gy
            alpha = int(35 * (1.0 - gy / max(1, glow_h)) * intensity)
            draw_glow.line([(0, y_pos), (w, y_pos)], fill=(r_col, g_col, b_col, alpha))

        composite = Image.alpha_composite(base_rgba, vignette_layer)
        composite = Image.alpha_composite(composite, accent_glow)
        return composite.convert("RGB")


class RimLightCompositor:
    """Applies edge rim light glow based on frame luminance boundaries."""

    @staticmethod
    def hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
        return AdaptiveSubjectCompositor.hex_to_rgb(hex_str)

    @classmethod
    def apply_rim_light_to_frame(
        cls,
        base_img: Image.Image,
        accent_color_hex: str = "#00FF66",
        intensity: float = 1.0,
    ) -> Image.Image:
        r_col, g_col, b_col = cls.hex_to_rgb(accent_color_hex)
        w, h = base_img.size

        gray = base_img.convert("L")
        edges = gray.filter(ImageFilter.FIND_EDGES)
        edges = ImageOps.autocontrast(edges, cutoff=15)

        edge_glow = edges.filter(ImageFilter.GaussianBlur(radius=8))

        glow_rgba = Image.new("RGBA", (w, h), (r_col, g_col, b_col, 0))
        glow_mask = edge_glow.point(lambda p: int(p * 0.45 * intensity))
        glow_rgba.putalpha(glow_mask)

        base_rgba = base_img.convert("RGBA")
        return Image.alpha_composite(base_rgba, glow_rgba).convert("RGB")
