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
from src.media.thumbnails.asset_resolver import ThematicAssetResolver
from src.media.thumbnails.extractor import ClimaxFrameExtractor
from src.media.thumbnails.grading import ChiaroscuroColorGrader
from src.media.thumbnails.layout import AspectLayoutManager
from src.media.thumbnails.layouts.base import LayoutRegistry
from src.media.thumbnails.subject_extractor import RimLightCompositor, AdaptiveSubjectCompositor
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
    blur_radius: float = 3.5
    contrast_boost: float = 1.35
    primary_color: Optional[str] = None
    accent_color: Optional[str] = None
    archetype: Optional[str] = None
    template: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ThumbnailEngine:
    """
    Main orchestrator for generating high-CTR YouTube thumbnails:
    - Resolves authentic background imagery via ThematicAssetResolver (3-tier local hierarchy).
    - Applies Chiaroscuro Rec.709 color grading and subtle depth blur.
    - Enhances edge silhouettes and focal depth with rim lighting.
    - Dispatches to specialized niche layouts (SCP HUD, Reddit Drama Card, Analog Horror VHS, or Cinematic).
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
        try:
            channel_prof = ChannelProfileRegistry.get_channel(config.channel_id)
        except KeyError:
            channel_prof = ChannelProfileRegistry.get_channel("moku")
        out_path = Path(config.output_path or "output/thumbnail.jpg").resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        w, h = config.width, config.height

        # 1. Resolve Authentic Thematic Base Image (3-Tier Hierarchy)
        eff_archetype = config.archetype or config.template or config.title or config.channel_id
        base_img = ThematicAssetResolver.resolve_base_image(
            channel_id=config.channel_id,
            archetype=eff_archetype,
            target_size=(w, h),
            explicit_path=base_image_path,
            video_path=video_path,
            manifest_path=manifest_path,
        )

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

        # 3. Enhance Focal Subject with Depth & Subtle Rim Light Glow
        subject_composited = AdaptiveSubjectCompositor.composite_thematic_subject(
            base_img=graded_bg,
            channel_id=config.channel_id,
            archetype=eff_archetype,
            accent_color_hex=accent,
            intensity=0.90,
        )
        rim_lit = self.subject_comp.apply_rim_light_to_frame(
            base_img=subject_composited,
            accent_color_hex=accent,
            intensity=0.6,
        )

        # 4. Dispatch to Niche Layout Engine
        is_vertical = h > w
        layout = LayoutRegistry.get_layout(
            channel_id=config.channel_id,
            archetype=config.archetype,
            template=config.template,
            is_vertical=is_vertical,
        )
        safe_zone = AspectLayoutManager.get_safe_zone(w, h)
        hook_text = config.hook_text or self._extract_hook_text(config.title)

        layout_metadata: Dict[str, Any] = {
            "archetype": config.archetype,
            "template": config.template,
            "primary_color": primary,
            "accent_color": accent,
            "tilt_angle": config.tilt_angle,
            "title_raw": config.title,
        }
        if config.metadata:
            layout_metadata.update(config.metadata)

        final_thumb = layout.apply_layout(
            canvas=rim_lit,
            title=hook_text,
            channel_id=config.channel_id,
            safe_zone=safe_zone,
            metadata=layout_metadata,
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
