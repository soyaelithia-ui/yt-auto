"""
src/media/thumbnails/grading.py - Chiaroscuro Grading, Rec.709 S-Curve, Depth Blur and Vignette.
"""
from __future__ import annotations

from typing import Dict

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
        blended = Image.blend(img, dark, mix)

        if target_h > target_w:
            # YouTube Shorts safe-zone chiaroscuro scrim: smooth dark falloff in the
            # bottom 450px UI zone and right 120px interaction rail to guarantee UI legibility
            # and safe-zone compliance.
            from PIL import ImageDraw
            overlay = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            start_y = target_h - 550
            for y in range(start_y, target_h):
                ratio = (y - start_y) / (target_h - start_y)
                alpha = int(255 * (ratio ** 0.6))
                draw.line([(0, y), (target_w, y)], fill=(8, 10, 14, alpha))

            start_x = target_w - 160
            for x in range(start_x, target_w):
                ratio = (x - start_x) / (target_w - start_x)
                alpha = int(255 * (ratio ** 0.6))
                draw.line([(x, int(target_h * 0.20)), (x, target_h)], fill=(8, 10, 14, alpha))
            return Image.alpha_composite(blended.convert("RGBA"), overlay).convert("RGB")

        return blended


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

