"""
src/media/thumbnails/grading.py - Chiaroscuro Grading, Rec.709 S-Curve, Depth Blur and Vignette.
"""
from __future__ import annotations

import math
from typing import Dict, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter


class ChiaroscuroColorGrader:
    """
    Applies Rec.709 S-curve contrast boost, selective saturation, Gaussian depth blur,
    and chiaroscuro light scrims to establish deep cinematic depth on background plates.
    """

    @staticmethod
    def process_background(
        base_img: Image.Image,
        target_w: int,
        target_h: int,
        blur_radius: float = 6.0,
        contrast_boost: float = 1.35,
        vignette_strength: float = 0.45,
        accent_color_hex: str = "#00FF66",
    ) -> Image.Image:
        # Resize to target canvas
        img = base_img.convert("RGB")
        if img.size != (target_w, target_h):
            img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)

        # 1. Apply Gaussian Depth Blur to separate background from foreground text/subject
        if blur_radius > 0:
            bg_blurred = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
            # Blend sharp and blurred (keeping 40% sharp details)
            img = Image.blend(img, bg_blurred, 0.65)

        # 2. Contrast S-Curve boost
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(contrast_boost)

        # 3. Saturation tuning
        sat_enhancer = ImageEnhance.Color(img)
        img = sat_enhancer.enhance(1.15)

        # 4. Chiaroscuro Optical Vignette & Scrim Gradient
        overlay = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Dark scrim at bottom/edges to guarantee maximum text readability
        for y in range(int(target_h * 0.45), target_h):
            fac = (y - int(target_h * 0.45)) / (target_h * 0.55)
            alpha = int(220 * math.pow(fac, 1.6))
            draw.line([(0, y), (target_w, y)], fill=(2, 4, 8, alpha))

        # Radial vignette mask
        arr = np.zeros((target_h, target_w), dtype=np.float32)
        cx, cy = target_w * 0.5, target_h * 0.5
        y_coords, x_coords = np.ogrid[:target_h, :target_w]
        dist = np.sqrt(((x_coords - cx) / target_w) ** 2 + ((y_coords - cy) / target_h) ** 2)
        vig_mask = np.clip((dist - 0.25) * 2.2 * vignette_strength, 0.0, 0.85)
        vig_alpha = (vig_mask * 255).astype(np.uint8)

        vig_img = Image.fromarray(vig_alpha, "L")
        dark_plate = Image.new("RGBA", (target_w, target_h), (1, 3, 6, 255))
        overlay.paste(dark_plate, (0, 0), vig_img)

        # Composite overlay
        img_rgba = img.convert("RGBA")
        graded = Image.alpha_composite(img_rgba, overlay).convert("RGB")
        return graded
