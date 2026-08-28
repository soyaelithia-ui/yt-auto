"""
src/media/thumbnails/engine.py - Master Professional Thumbnail Engine for yt-auto.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Union

from PIL import Image

from src.core.channel_profile import ChannelProfile, ChannelProfileRegistry
from src.media.thumbnails.extractor import ClimaxFrameExtractor
from src.media.thumbnails.grading import ChiaroscuroColorGrader
from src.media.thumbnails.layout import AspectLayoutManager
from src.media.thumbnails.subject_extractor import RimLightCompositor
from src.media.thumbnails.typography import DynamicTypographyEngine

logger = logging.getLogger("thumbnail_engine")


@dataclass
class ThumbnailConfig:
    title: str
    channel_id: str = "moku"
    hook_text: Optional[str] = None
    output_path: Optional[Union[str, Path]] = None
    width: int = 1920
    height: int = 1080
    tilt_angle: float = -3.5
    blur_radius: float = 5.0
    contrast_boost: float = 1.35
    primary_color: Optional[str] = None
    accent_color: Optional[str] = None


class ThumbnailEngine:
    """
    Main orchestrator for generating high-CTR YouTube thumbnails:
    - Extracts the climax keyframe from the rendered video.
    - Applies Chiaroscuro Rec.709 color grading and Gaussian depth blur.
    - Enhances edge silhouettes with rim lighting.
    - Renders bold, angled, high-contrast typography in safe zones.
    """

    def __init__(self) -> None:
        self.extractor = ClimaxFrameExtractor()
        self.grader = ChiaroscuroColorGrader()
        self.subject_comp = RimLightCompositor()
        self.typography = DynamicTypographyEngine()

    def generate(
        self,
        config: ThumbnailConfig,
        video_path: Optional[Union[str, Path]] = None,
        manifest_path: Optional[Union[str, Path]] = None,
        base_image_path: Optional[Union[str, Path]] = None,
    ) -> Path:
        channel_prof = ChannelProfileRegistry.get_channel(config.channel_id)
        out_path = Path(config.output_path or "output/thumbnail.jpg").resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        w, h = config.width, config.height
        is_vertical = h > w

        # 1. Acquire Base Frame
        base_img: Optional[Image.Image] = None
        if base_image_path and Path(base_image_path).is_file():
            try:
                base_img = Image.open(str(base_image_path)).convert("RGB")
            except Exception as e:
                logger.warning("Failed opening base_image_path: %s", e)

        if base_img is None and video_path and Path(video_path).is_file():
            v_path = Path(video_path)
            tmp_extract_dir = out_path.parent / "thumb_tmp"
            climax_t = self.extractor.resolve_climax_timestamp(
                manifest_path=Path(manifest_path) if manifest_path else None
            )
            cand_frames = self.extractor.extract_candidate_frames(
                video_path=v_path,
                center_timestamp=climax_t,
                output_dir=tmp_extract_dir,
                count=5,
            )
            best_frame_path = self.extractor.select_best_frame(cand_frames)
            if best_frame_path and best_frame_path.is_file():
                try:
                    base_img = Image.open(best_frame_path).convert("RGB")
                except Exception as e:
                    logger.warning("Failed loading best frame: %s", e)

        # Fallback if no video frame could be acquired
        if base_img is None:
            base_img = Image.new("RGB", (w, h), (4, 8, 14))

        # 2. Apply Chiaroscuro Grading & Gaussian Depth Blur
        accent = config.accent_color or channel_prof.visual.palette.accent
        primary = config.primary_color or channel_prof.visual.palette.highlight or "#FFE600"
        
        graded_bg = self.grader.process_background(
            base_img=base_img,
            target_w=w,
            target_h=h,
            blur_radius=config.blur_radius,
            contrast_boost=config.contrast_boost,
            vignette_strength=channel_prof.visual.vignette_default_strength,
            accent_color_hex=accent,
        )

        # 3. Enhance Focal Subject with Rim Light Glow
        rim_lit = self.subject_comp.apply_rim_light_to_frame(
            base_img=graded_bg,
            accent_color_hex=accent,
            intensity=1.1,
        )

        # 4. Render Dynamic Typography
        hook_text = config.hook_text or self._extract_hook_text(config.title)
        safe_zone = AspectLayoutManager.get_safe_zone(w, h)
        pos_x, pos_y = AspectLayoutManager.get_hook_text_position(w, h, text_height=int(h * 0.22))

        final_thumb = self.typography.render_hook_title(
            canvas=rim_lit,
            text=hook_text,
            pos_x=pos_x,
            pos_y=pos_y,
            max_width=safe_zone.width,
            font_name=channel_prof.visual.typography.font_bold,
            primary_color=primary,
            accent_color=accent,
            tilt_angle=config.tilt_angle,
        )

        # Save Final JPEG
        final_thumb.save(str(out_path), "JPEG", quality=95)
        logger.info("High-CTR Thumbnail successfully generated at: %s (%dx%d)", out_path, w, h)
        return out_path

    @staticmethod
    def _extract_hook_text(title: str) -> str:
        """Extracts 2-4 punchy, high-impact uppercase words from the title."""
        t = title.replace("[REGISTRO CLASIFICADO]", "").replace("[CONFESIÓN]", "").replace("|", ":")
        parts = [p.strip() for p in t.split(":") if p.strip()]
        candidate = parts[0] if parts else title
        words = candidate.split()
        if len(words) > 4:
            return " ".join(words[:4]).upper()
        return candidate.upper()
