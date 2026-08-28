"""
src/media/thumbnails/subject_extractor.py - Focal Subject Extraction and Rim Light Edge Glow Compositing.
"""
from __future__ import annotations

from typing import Tuple
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps


class RimLightCompositor:
    """
    Isolates focal silhouette and generates an edge glow / rim light contour in the channel's accent color.
    """

    @staticmethod
    def hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
        h = hex_str.lstrip("#")
        if len(h) == 6:
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return (0, 255, 102)

    @classmethod
    def apply_rim_light_to_frame(
        cls,
        base_img: Image.Image,
        accent_color_hex: str = "#00FF66",
        intensity: float = 1.0,
    ) -> Image.Image:
        """
        Enhances edge contrast and casts an accent rim glow around central high-contrast elements.
        """
        r_col, g_col, b_col = cls.hex_to_rgb(accent_color_hex)
        w, h = base_img.size

        # Extract high-pass edges
        gray = base_img.convert("L")
        edges = gray.filter(ImageFilter.FIND_EDGES)
        edges = ImageEnhance_edges = ImageOps.autocontrast(edges, cutoff=15)

        # Blur edges to create atmospheric glow
        edge_glow = edges.filter(ImageFilter.GaussianBlur(radius=8))

        # Colorize edge glow
        glow_rgba = Image.new("RGBA", (w, h), (r_col, g_col, b_col, 0))
        glow_mask = edge_glow.point(lambda p: int(p * 0.45 * intensity))
        glow_rgba.putalpha(glow_mask)

        # Composite glow onto base
        base_rgba = base_img.convert("RGBA")
        result = Image.alpha_composite(base_rgba, glow_rgba).convert("RGB")
        return result
