"""
src/media/thumbnails/grading.py - Chiaroscuro Grading, Rec.709 S-Curve, Depth Blur and Vignette.
"""
from __future__ import annotations

from typing import Dict, Tuple

from PIL import Image, ImageEnhance, ImageFilter


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

        if blur_radius and blur_radius > 0.4:
            img = img.filter(ImageFilter.GaussianBlur(radius=min(float(blur_radius), 1.2)))
        img = ImageEnhance.Contrast(img).enhance(contrast_boost)
        img = ImageEnhance.Brightness(img).enhance(0.72)
        dark = Image.new("RGB", (target_w, target_h), (6, 8, 10))
        mix = min(0.38, max(0.14, float(vignette_strength or 0.45) * 0.45))
        return Image.blend(img, dark, mix)


    @staticmethod
    def process_analog_horror(
        base_img: Image.Image,
        target_w: int,
        target_h: int,
        *,
        with_osd: bool = False,
        osd_kwargs: Dict | None = None,
        seed: int = 42,
    ) -> Image.Image:
        """Found-footage grade aligned to Aelithia quality ref (VHS/CCTV)."""
        from src.media.thumbnails.analog_horror import apply_analog_horror_grade

        return apply_analog_horror_grade(
            base_img,
            target_size=(target_w, target_h),
            with_osd=with_osd,
            osd_kwargs=osd_kwargs,
            seed=seed,
        )

