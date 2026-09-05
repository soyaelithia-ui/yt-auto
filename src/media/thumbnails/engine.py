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
    lane_id: Optional[str] = None
    hook_text: Optional[str] = None
    output_path: Optional[Union[str, Path]] = None
    width: int = 1920
    height: int = 1080
    tilt_angle: float = -3.5
    blur_radius: float = 3.5
    contrast_boost: float = 1.35
    primary_color: Optional[str] = None
    accent_color: Optional[str] = None
    text_box_style: Optional[str] = None
    subject_contrast: Optional[float] = None
    archetype: Optional[str] = None
    template: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ThumbnailEngine:
    """
    Main orchestrator for generating high-CTR YouTube thumbnails:
    - Resolves authentic background imagery via ThematicAssetResolver (3-tier local hierarchy).
    - Resilient safeguard: Generates dark atmospheric gradient with controlled noise when assets are missing/corrupt.
    - Applies Chiaroscuro Rec.709 color grading and subtle depth blur.
    - Enhances edge silhouettes and focal depth with rim lighting.
    - Dispatches to specialized niche layouts passing lane_id, title, and resolved visual asset path.
    """

    def __init__(self) -> None:
        self.extractor = ClimaxFrameExtractor()
        self.grader = ChiaroscuroColorGrader()
        self.subject_comp = RimLightCompositor()
        self.typography = DynamicTypographyEngine()

    @staticmethod
    def create_atmospheric_noise_background(
        width: int,
        height: int,
        accent_color_hex: Optional[str] = None,
        noise_opacity: int = 22,
    ) -> Image.Image:
        """Resilient fallback generator for dark atmospheric gradient with controlled noise."""
        return ThematicAssetResolver.create_atmospheric_noise_background(
            width=width,
            height=height,
            accent_color_hex=accent_color_hex,
            noise_opacity=noise_opacity,
        )

    def generate(
        self,
        config: ThumbnailConfig,
        video_path: Optional[Union[str, Path]] = None,
        manifest_path: Optional[Union[str, Path]] = None,
        base_image_path: Optional[Union[str, Path]] = None,
    ) -> Path:
        eff_lane = config.lane_id or config.channel_id
        eff_channel = config.channel_id
        try:
            channel_prof = ChannelProfileRegistry.get_channel(eff_channel)
        except KeyError:
            base_chan = eff_channel.split("-")[0] if "-" in eff_channel else eff_channel
            try:
                channel_prof = ChannelProfileRegistry.get_channel(base_chan)
            except KeyError:
                channel_prof = ChannelProfileRegistry.get_channel("moku")

        out_path = Path(config.output_path or "output/thumbnail.jpg").resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        w, h = config.width, config.height
        is_vertical = h > w
        accent = config.accent_color or channel_prof.visual.palette.accent
        primary = config.primary_color or channel_prof.visual.palette.highlight or "#FFE600"
        eff_archetype = config.archetype or config.template or config.title or eff_lane

        # 1. Resolve Thematic Base Image (with resilient dark atmospheric noise safeguard)
        base_img: Optional[Image.Image] = None
        resolved_asset_path: Optional[Path] = None

        if base_image_path:
            p = Path(base_image_path).resolve()
            if p.is_file():
                try:
                    with Image.open(p) as test_img:
                        test_img.verify()
                    from PIL import ImageOps
                    raw_img = Image.open(p).convert("RGB")
                    base_img = ImageOps.fit(raw_img, (w, h), method=Image.Resampling.LANCZOS)
                    resolved_asset_path = p
                except Exception as exc:
                    logger.warning("Corrupted or invalid base_image_path '%s': %s", p, exc)
                    base_img = None
                    resolved_asset_path = None

        if base_img is None:
            try:
                base_img = ThematicAssetResolver.resolve_base_image(
                    channel_id=eff_channel,
                    archetype=eff_archetype,
                    target_size=(w, h),
                    explicit_path=None,
                    video_path=video_path,
                    manifest_path=manifest_path,
                )
            except Exception as exc:
                logger.warning("ThematicAssetResolver resolution failed: %s", exc)
                base_img = None

        if base_img is None:
            logger.info("Engaging controlled noise dark atmospheric gradient safeguard.")
            base_img = self.create_atmospheric_noise_background(w, h, accent_color_hex=accent)

        if not resolved_asset_path:
            resolved_asset_path = ThematicAssetResolver.resolve_thumbnail_asset_path(
                channel_id=eff_channel,
                archetype=eff_archetype,
                explicit_path=base_image_path,
                video_path=video_path,
                is_vertical=is_vertical,
            )

        # 2. Apply Chiaroscuro Grading & Gaussian Depth Blur
        contrast_boost = config.contrast_boost
        if config.subject_contrast is not None:
            try:
                contrast_boost = float(config.contrast_boost) * float(config.subject_contrast)
            except (ValueError, TypeError):
                pass
        elif config.metadata and "subject_contrast" in config.metadata:
            try:
                contrast_boost = float(config.contrast_boost) * float(config.metadata["subject_contrast"])
            except (ValueError, TypeError):
                pass

        # Analog-horror lanes (moku / scp / vhs) use found-footage grade; else chiaroscuro.
        arch_key = f"{eff_archetype} {eff_lane} {eff_channel}".lower()
        use_analog = any(
            k in arch_key
            for k in ("horror", "scp", "vhs", "analog", "creepy", "moku", "nosleep")
        ) and "aita" not in arch_key
        if use_analog:
            graded_bg = self.grader.process_analog_horror(
                base_img=base_img,
                target_w=w,
                target_h=h,
                with_osd=True,
                osd_kwargs={
                    "cam_label": "CAM 04 [SUB-LEVEL B]",
                    "date_label": "1994-10-31",
                },
                seed=abs(hash(eff_lane)) % (2**31),
            )
        else:
            graded_bg = self.grader.process_background(
                base_img=base_img,
                target_w=w,
                target_h=h,
                blur_radius=config.blur_radius,
                contrast_boost=contrast_boost,
                vignette_strength=channel_prof.visual.vignette_default_strength,
                accent_color_hex=accent,
            )

        # 3. Enhance Focal Subject with Depth & Subtle Rim Light Glow
        subject_composited = AdaptiveSubjectCompositor.composite_thematic_subject(
            base_img=graded_bg,
            channel_id=eff_channel,
            archetype=eff_archetype,
            accent_color_hex=accent,
            intensity=0.90,
        )
        rim_lit = self.subject_comp.apply_rim_light_to_frame(
            base_img=subject_composited,
            accent_color_hex=accent,
            intensity=0.6,
        )

        # 4. Dispatch to Niche Layout Engine Passing lane_id, title, resolved_asset_path
        layout = LayoutRegistry.get_layout(
            channel_id=eff_channel,
            archetype=config.archetype,
            template=config.template,
            is_vertical=is_vertical,
            lane_id=eff_lane,
        )
        safe_zone = AspectLayoutManager.get_safe_zone(w, h)
        hook_text = config.hook_text or self._extract_hook_text(config.title)

        layout_metadata: Dict[str, Any] = {
            "lane_id": eff_lane,
            "channel_id": eff_channel,
            "archetype": config.archetype,
            "template": config.template,
            "primary_color": primary,
            "accent_color": accent,
            "tilt_angle": config.tilt_angle,
            "title_raw": config.title,
            "text_box_style": config.text_box_style or (config.metadata.get("text_box_style") if config.metadata else "badge"),
            "subject_contrast": config.subject_contrast or (config.metadata.get("subject_contrast") if config.metadata else None),
            "resolved_asset_path": str(resolved_asset_path) if resolved_asset_path else None,
            "asset_path": str(resolved_asset_path) if resolved_asset_path else None,
        }
        if config.metadata:
            layout_metadata.update(config.metadata)

        try:
            final_thumb = layout.apply_layout(
                canvas=rim_lit,
                title=hook_text,
                channel_id=eff_channel,
                safe_zone=safe_zone,
                metadata=layout_metadata,
                lane_id=eff_lane,
                resolved_asset_path=resolved_asset_path,
            )
        except TypeError:
            final_thumb = layout.apply_layout(
                canvas=rim_lit,
                title=hook_text,
                channel_id=eff_channel,
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
        if not title:
            return "HISTORIA EXCLUSIVA"
        t = str(title).replace("[REGISTRO CLASIFICADO]", "").replace("[CONFESIÓN]", "").replace("|", ":")
        parts = [p.strip() for p in t.split(":") if p.strip()]
        candidate = parts[0] if parts else title
        words = candidate.split()
        if not words:
            return "HISTORIA EXCLUSIVA"
        if len(words) > 4:
            return " ".join(words[:4]).upper()
        return candidate.upper()
