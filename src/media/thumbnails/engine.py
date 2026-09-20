"""
src/media/thumbnails/engine.py - Master Professional Thumbnail Engine for yt-auto.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Union

from PIL import Image

from src.core.channel_profile import ChannelProfile, ChannelProfileRegistry
from src.media.thumbnails.asset_resolver import ThematicAssetResolver
from src.media.thumbnails.grading import ChiaroscuroColorGrader
from src.media.thumbnails.layout import AspectLayoutManager
from src.media.thumbnails.layouts.base import LayoutRegistry

logger = logging.getLogger("thumbnail_engine")

THUMB_LONGFORM_SIZE = (1280, 720)
THUMB_SHORT_SIZE = (720, 1280)


def default_thumbnail_canvas(*, vertical: bool = False, full_hd: bool = False) -> tuple[int, int]:
    """Default thumb canvas: 1280×720 / 720×1280. Full HD only when explicitly requested."""
    if full_hd:
        return (1080, 1920) if vertical else (1920, 1080)
    return THUMB_SHORT_SIZE if vertical else THUMB_LONGFORM_SIZE


@dataclass
class ThumbnailConfig:
    title: str
    channel_id: str = "moku"
    lane_id: Optional[str] = None
    hook_text: Optional[str] = None
    output_path: Optional[Union[str, Path]] = None
    width: int = THUMB_LONGFORM_SIZE[0]
    height: int = THUMB_LONGFORM_SIZE[1]
    tilt_angle: float = -3.5
    blur_radius: float = 0.0
    contrast_boost: float = 1.35
    primary_color: Optional[str] = None
    accent_color: Optional[str] = None
    text_box_style: Optional[str] = None
    subject_contrast: Optional[float] = None
    archetype: Optional[str] = None
    template: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    cover_prompt: Optional[str] = None
    focal_subject: Optional[str] = None


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
        self.grader = ChiaroscuroColorGrader()

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
                prefer_climax = False
                if config.metadata and isinstance(config.metadata, dict):
                    prefer_climax = bool(config.metadata.get("prefer_video_climax", False))
                elif getattr(config, "prefer_video_climax", False):
                    prefer_climax = True

                base_img = ThematicAssetResolver.resolve_base_image(
                    channel_id=eff_channel,
                    archetype=eff_archetype,
                    target_size=(w, h),
                    explicit_path=None,
                    video_path=video_path,
                    manifest_path=manifest_path,
                    prefer_video_climax=prefer_climax,
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

        graded_bg = self.grader.process_background(
            base_img=base_img,
            target_w=w,
            target_h=h,
            blur_radius=config.blur_radius,
            contrast_boost=contrast_boost,
            vignette_strength=channel_prof.visual.vignette_default_strength,
            accent_color_hex=accent,
        )

        # Layout only. Rim-light + subject compositor were a green bar and Gaussian cost.

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
            "cover_prompt": config.cover_prompt,
            "focal_subject": config.focal_subject,
            # metadata without text_box_style must not inject None ("none" disables the badge).
            "text_box_style": config.text_box_style
            or (config.metadata.get("text_box_style") if config.metadata else None)
            or "badge",
            "subject_contrast": config.subject_contrast or (config.metadata.get("subject_contrast") if config.metadata else None),
            "resolved_asset_path": str(resolved_asset_path) if resolved_asset_path else None,
            "asset_path": str(resolved_asset_path) if resolved_asset_path else None,
        }
        if config.metadata:
            layout_metadata.update(config.metadata)

        try:
            final_thumb = layout.apply_layout(
                canvas=graded_bg,
                title=hook_text,
                channel_id=eff_channel,
                safe_zone=safe_zone,
                metadata=layout_metadata,
                lane_id=eff_lane,
                resolved_asset_path=resolved_asset_path,
            )
        except TypeError:
            final_thumb = layout.apply_layout(
                canvas=graded_bg,
                title=hook_text,
                channel_id=eff_channel,
                safe_zone=safe_zone,
                metadata=layout_metadata,
            )

        # Save Final JPEG with Huffman table optimization for reduced file weight and fast upload
        final_thumb.save(str(out_path), "JPEG", quality=90, optimize=True)
        logger.info("High-CTR Thumbnail successfully generated at: %s (%dx%d)", out_path, w, h)
        return out_path

    _BRACKET_RE = re.compile(r"\[[^\]]*\]")
    _SCP_RE = re.compile(r"(SCP-\d+)\s*:?\s*(.*)", re.IGNORECASE)

    @staticmethod
    def _extract_hook_text(title: str) -> str:
        """Hook is the phrase, not the ID. SCP-173: la estatua... → LA ESTATUA..."""
        if not title or not str(title).strip():
            return "HISTORIA EXCLUSIVA"
        t = ThumbnailEngine._BRACKET_RE.sub(" ", str(title))
        if "|" in t:
            t = t.split("|")[0]
        t = " ".join(t.replace("\n", " ").split())
        m = ThumbnailEngine._SCP_RE.search(t)
        if m:
            rest = (m.group(2) or "").strip(" .:-")
            if rest:
                return rest.split(".")[0].strip().upper()
            return m.group(1).upper()
        if ":" in t:
            left, right = t.split(":", 1)
            right = right.strip()
            if right:
                return right.split(".")[0].strip().upper()
            t = left.strip()

        t_low = t.lower()
        # High-CTR relationship & drama thematic hooks
        if any(w in t_low for w in ("boda", "matrimonio", "casamiento")):
            return "¿ARRUINÉ SU BODA?"
        if any(w in t_low for w in ("apartamento", "herencia", "heredado")):
            return "¿VENDER MI CASA?"
        if any(w in t_low for w in ("deuda", "deudas", "fianza", "prestamo", "préstamo")):
            return "¿PAGAR SUS DEUDAS?"
        if any(w in t_low for w in ("infiel", "infidelidad", "amante", "engaño", "engano")):
            return "¿TRAICIÓN O VENGANZA?"

        # Strip standard AITA boilerplate prefixes
        for prefix in (
            "¿soy la mala por ", "¿soy el malo por ",
            "soy la mala por ", "soy el malo por ",
            "¿soy la mala ", "¿soy el malo ",
            "aita por ", "aita for ", "aita: ", "aita ",
        ):
            if t_low.startswith(prefix):
                t = t[len(prefix):].strip().rstrip("?")
                t_low = t.lower()
                break

        # Bound length to 6 words or ~38 chars max to prevent safe zone overflow on thumbnail plates
        words = t.split()
        if len(words) > 6 or len(t) > 38:
            short_words = []
            curr_len = 0
            for w in words[:6]:
                if curr_len + len(w) + (1 if short_words else 0) <= 38:
                    short_words.append(w)
                    curr_len += len(w) + (1 if len(short_words) > 1 else 0)
                else:
                    break
            if short_words:
                t = " ".join(short_words)

        return (t or "HISTORIA EXCLUSIVA").upper()
