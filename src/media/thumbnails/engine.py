"""Text-free thumbnail renderer backed by the local AI asset bank."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Union

from PIL import Image, ImageOps

from src.core.channel_profile import ChannelProfileRegistry
from src.media.thumbnails.ai_bank import LocalAIThumbnailBank
from src.media.thumbnails.asset_resolver import ThematicAssetResolver
from src.media.thumbnails.grading import ChiaroscuroColorGrader

logger = logging.getLogger("thumbnail_engine")

THUMB_LONGFORM_SIZE = (1280, 720)
THUMB_SHORT_SIZE = (720, 1280)


def default_thumbnail_canvas(*, vertical: bool = False, full_hd: bool = False) -> tuple[int, int]:
    """Default thumbnail canvas: 1280×720 / 720×1280."""
    if full_hd:
        return (1080, 1920) if vertical else (1920, 1080)
    return THUMB_SHORT_SIZE if vertical else THUMB_LONGFORM_SIZE


@dataclass
class ThumbnailConfig:
    """Compatibility input for a text-free local image selection."""

    title: str
    channel_id: str = "horror"
    lane_id: Optional[str] = None
    hook_text: Optional[str] = None  # retained for callers; never rendered
    output_path: Optional[Union[str, Path]] = None
    width: int = THUMB_LONGFORM_SIZE[0]
    height: int = THUMB_LONGFORM_SIZE[1]
    tilt_angle: float = 0.0
    blur_radius: float = 0.0
    contrast_boost: float = 1.5
    primary_color: Optional[str] = None
    accent_color: Optional[str] = None
    text_box_style: Optional[str] = None  # retained for callers; never rendered
    subject_contrast: Optional[float] = None
    archetype: Optional[str] = None
    template: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    cover_prompt: Optional[str] = None
    focal_subject: Optional[str] = None
    text_free: bool = True


class ThumbnailEngine:
    """Select, grade, and export a local AI thumbnail without drawing text."""

    def __init__(self, bank: Optional[LocalAIThumbnailBank] = None) -> None:
        self.grader = ChiaroscuroColorGrader()
        self.bank = bank or LocalAIThumbnailBank()
        self.last_asset: Optional[Path] = None

    @staticmethod
    def _load(path: Path, size: tuple[int, int]) -> Optional[Image.Image]:
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                return ImageOps.fit(image.convert("RGB"), size, method=Image.Resampling.LANCZOS)
        except (OSError, ValueError) as exc:
            logger.warning("Ignoring invalid thumbnail asset %s: %s", path, exc)
            return None

    def _resolve_asset(self, config: ThumbnailConfig, base_image_path: Optional[Union[str, Path]]) -> Optional[Image.Image]:
        size = (int(config.width), int(config.height))
        lane = config.lane_id or config.channel_id
        archetype = config.archetype or config.template or lane
        if base_image_path:
            explicit = Path(base_image_path).resolve()
            image = self._load(explicit, size) if explicit.is_file() else None
            if image is not None:
                self.last_asset = explicit
                return image

        selected = self.bank.resolve(
            channel_id=config.channel_id,
            archetype=archetype,
            selection_key=config.title,
        )
        if selected is not None:
            image = self._load(selected.path, size)
            if image is not None:
                self.last_asset = selected.path
                return image

        fallback_path = ThematicAssetResolver.resolve_thumbnail_asset_path(
            channel_id=config.channel_id,
            archetype=archetype,
            explicit_path=None,
            video_path=None,
            is_vertical=config.height > config.width,
        )
        if fallback_path:
            image = self._load(Path(fallback_path), size)
            if image is not None:
                self.last_asset = Path(fallback_path)
                return image
        return None

    def generate(
        self,
        config: ThumbnailConfig,
        video_path: Optional[Union[str, Path]] = None,
        manifest_path: Optional[Union[str, Path]] = None,
        base_image_path: Optional[Union[str, Path]] = None,
    ) -> Path:
        if not config.text_free:
            raise ValueError("ThumbnailConfig.text_free must remain true; printed cover text is retired")
        channel = config.channel_id
        try:
            profile = ChannelProfileRegistry.get_channel(channel)
        except KeyError:
            profile = ChannelProfileRegistry.get_channel(channel.split("-")[0] if "-" in channel else "horror")

        out_path = Path(config.output_path or "output/thumbnail.jpg").resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        accent = config.accent_color or profile.visual.palette.accent
        image = self._resolve_asset(config, base_image_path)
        if image is None:
            raise FileNotFoundError(
                "No valid local text-free thumbnail asset is available; "
                "populate assets/thumbnails/ai_bank or the curated local templates"
            )

        contrast = float(config.contrast_boost)
        if config.subject_contrast is not None:
            contrast *= float(config.subject_contrast)
        graded = self.grader.process_background(
            base_img=image,
            target_w=int(config.width),
            target_h=int(config.height),
            blur_radius=float(config.blur_radius),
            contrast_boost=contrast,
            vignette_strength=profile.visual.vignette_default_strength,
            accent_color_hex=accent,
        )
        # Deliberately no layout, typography, watermark, badge, or title pass.
        graded.save(str(out_path), "JPEG", quality=92, optimize=True)
        logger.info("Text-free local AI thumbnail exported: %s", out_path)
        return out_path
