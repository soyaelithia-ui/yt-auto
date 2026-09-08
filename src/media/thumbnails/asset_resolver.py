"""
src/media/thumbnails/asset_resolver.py - Deterministic 3-Tier Thematic Asset Resolver.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple, Union

from PIL import Image, ImageDraw, ImageOps

from src.media.thumbnails.extractor import ClimaxFrameExtractor
from src.media.thumbnails.grading import ChiaroscuroColorGrader

logger = logging.getLogger("thematic_asset_resolver")

# Finished title-card / baked-text folders — never use as video or thumb bases.
_EXCLUDED_VISUAL_BANK_MARKERS = (
    "_quarantine_title_cards",
    "quarantine_title_cards",
    "title_cards",
    "prebaked",
    "ambient_gifs",
    "overlays",
)


def _is_clean_visual_candidate(path: Path) -> bool:
    """Reject quarantined title cards and non-scenery visual_bank layers."""
    parts = {p.lower() for p in Path(path).parts}
    if any(m.lower() in parts for m in _EXCLUDED_VISUAL_BANK_MARKERS):
        return False
    return True


def _list_scenery_candidates(scenery_dir: Path, exts: tuple[str, ...]) -> list[Path]:
    if not scenery_dir.is_dir():
        return []
    out: list[Path] = []
    for ext in exts:
        out.extend(sorted(scenery_dir.glob(ext)))
    return [p for p in out if p.is_file() and _is_clean_visual_candidate(p)]


REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
TEMPLATES_DIR = REPO_ROOT / "assets" / "thumbnails" / "templates"
VISUAL_BANK_DIR = REPO_ROOT / "assets" / "visual_bank"


class _ThematicAssetResolverMeta(type):
    """Allow monkeypatching either the class or module-level directories seamlessly."""

    @property
    def VISUAL_BANK_DIR(cls) -> Path:
        if "_custom_visual_bank_dir" in cls.__dict__:
            return cls.__dict__["_custom_visual_bank_dir"]
        import src.media.thumbnails.asset_resolver as mod
        return mod.VISUAL_BANK_DIR

    @VISUAL_BANK_DIR.setter
    def VISUAL_BANK_DIR(cls, val: Path) -> None:
        cls._custom_visual_bank_dir = Path(val)

    @property
    def TEMPLATES_DIR(cls) -> Path:
        if "_custom_templates_dir" in cls.__dict__:
            return cls.__dict__["_custom_templates_dir"]
        import src.media.thumbnails.asset_resolver as mod
        return mod.TEMPLATES_DIR

    @TEMPLATES_DIR.setter
    def TEMPLATES_DIR(cls, val: Path) -> None:
        cls._custom_templates_dir = Path(val)


class ThematicAssetResolver(metaclass=_ThematicAssetResolverMeta):
    """
    Resolves background imagery through a strict 3-tier local hierarchy:
    - Tier 1: Explicit image path (if specified and valid).
    - Tier 2: Curated local asset bank (assets/thumbnails/templates/ or assets/visual_bank/).
    - Tier 3: Climax keyframe extracted from video with Chiaroscuro grading.
    - Default Fallback: High-contrast chiaroscuro cinematic gradient (zero stick-figure silhouettes).
    """

    @classmethod
    def resolve_base_image(
        cls,
        channel_id: str,
        archetype: str,
        target_size: Tuple[int, int],
        explicit_path: Optional[Union[str, Path]] = None,
        video_path: Optional[Union[str, Path]] = None,
        manifest_path: Optional[Union[str, Path]] = None,
    ) -> Image.Image:
        w, h = target_size

        # ---------------------------------------------------------
        # Tier 1: Explicit Path
        # ---------------------------------------------------------
        if explicit_path:
            p = Path(explicit_path).resolve()
            if p.is_file():
                try:
                    img = Image.open(p).convert("RGB")
                    return ImageOps.fit(img, (w, h), method=Image.Resampling.LANCZOS)
                except Exception as exc:
                    logger.warning("Tier 1 resolution failed loading %s: %s", p, exc)

        # ---------------------------------------------------------
        # Tier 2: Curated Local Asset Bank (Archetype-specific)
        # ---------------------------------------------------------
        norm_arch = str(archetype or "").lower()
        norm_chan = str(channel_id or "").lower()
        visual_bank_dir = Path(cls.VISUAL_BANK_DIR)
        templates_dir = Path(cls.TEMPLATES_DIR)

        # Map archetype first to specific template folders
        template_keys = []
        if any(k in norm_arch for k in ("scp", "found-footage", "anomaly")):
            template_keys.append("scp")
        elif any(k in norm_arch for k in ("aita", "drama", "confession")):
            template_keys.append("aita")
        elif any(k in norm_arch for k in ("horror", "vhs", "analog")):
            template_keys.append("horror")
        elif norm_arch:
            template_keys.append(norm_arch)

        for t_key in template_keys:
            t_dir = templates_dir / t_key
            if t_dir.is_dir():
                for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
                    candidates = sorted(t_dir.glob(ext))
                    if candidates:
                        try:
                            img = Image.open(candidates[0]).convert("RGB")
                            return ImageOps.fit(img, (w, h), method=Image.Resampling.LANCZOS)
                        except Exception as exc:
                            logger.warning("Failed loading template backdrop from %s: %s", candidates[0], exc)

        # ---------------------------------------------------------
        # Tier 3: Climax Keyframe Fallback from Video
        # (Prioritized when archetype has no curated template bank)
        # ---------------------------------------------------------
        if video_path and Path(video_path).is_file():
            v_p = Path(video_path)
            try:
                extractor = ClimaxFrameExtractor()
                climax_t = extractor.resolve_climax_timestamp(
                    manifest_path=Path(manifest_path) if manifest_path else None
                )
                tmp_dir = v_p.parent / "thumb_candidates"
                cand_frames = extractor.extract_candidate_frames(
                    video_path=v_p,
                    center_timestamp=climax_t,
                    output_dir=tmp_dir,
                    count=3,
                )
                best_frame = extractor.select_best_frame(cand_frames)
                if best_frame and best_frame.is_file():
                    raw_frame = Image.open(best_frame).convert("RGB")
                    return ImageOps.fit(raw_frame, (w, h), method=Image.Resampling.LANCZOS)
            except Exception as exc:
                logger.warning("Tier 3 video climax extraction failed: %s", exc)

        # ---------------------------------------------------------
        # Tier 2 (Fallback): Curated Channel Defaults / Visual Bank
        # ---------------------------------------------------------
        chan_keys = []
        is_vertical = h > w
        if any(k in norm_chan for k in ("scp", "found-footage")):
            chan_keys.append("scp")
        elif any(k in norm_chan for k in ("aita", "drama", "aelithia")):
            chan_keys.append("aita")
        elif any(k in norm_chan for k in ("horror", "vhs", "analog")):
            chan_keys.append("horror")
        elif "moku" in norm_chan:
            chan_keys.append("scp" if is_vertical else "horror")

        for c_key in chan_keys:
            c_dir = templates_dir / c_key
            if c_dir.is_dir():
                for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
                    candidates = sorted(c_dir.glob(ext))
                    if candidates:
                        try:
                            img = Image.open(candidates[0]).convert("RGB")
                            return ImageOps.fit(img, (w, h), method=Image.Resampling.LANCZOS)
                        except Exception as exc:
                            logger.warning("Failed loading channel template backdrop from %s: %s", candidates[0], exc)

        # Also check assets/visual_bank/<channel>/scenery/ (clean stills only)
        chan_prefix = "moku" if "moku" in norm_chan else ("aelithia" if "aelithia" in norm_chan else norm_chan)
        visual_scenery_dir = visual_bank_dir / chan_prefix / "scenery"
        candidates = _list_scenery_candidates(visual_scenery_dir, ("*.jpg", "*.jpeg", "*.png"))
        if candidates:
            try:
                img = Image.open(candidates[0]).convert("RGB")
                return ImageOps.fit(img, (w, h), method=Image.Resampling.LANCZOS)
            except Exception as exc:
                logger.warning("Failed loading visual bank image from %s: %s", candidates[0], exc)

        # Also check generic assets/background.jpg
        generic_bg = REPO_ROOT / "assets" / "background.jpg"
        if generic_bg.is_file():
            try:
                img = Image.open(generic_bg).convert("RGB")
                return ImageOps.fit(img, (w, h), method=Image.Resampling.LANCZOS)
            except Exception:
                pass

        # ---------------------------------------------------------
        # Default Fallback: Clean Atmospheric Chiaroscuro Gradient
        # with Controlled Film Grain Noise (Zero primitive stick-figures)
        # ---------------------------------------------------------
        return cls.create_atmospheric_noise_background(w, h)

    @classmethod
    def resolve_scene_asset_path(
        cls,
        channel_id: str,
        archetype: str = "",
        scene_idx: int = 1,
        explicit_path: Optional[Union[str, Path]] = None,
        is_vertical: bool = False,
    ) -> Path:
        """Resolve a concrete asset Path for multi-act scenes; rotate to avoid dominance."""
        if explicit_path:
            p = Path(explicit_path).resolve()
            if p.is_file():
                return p

        norm_arch = str(archetype or "").lower()
        norm_chan = str(channel_id or "").lower()
        idx = max(1, int(scene_idx))
        visual_bank_dir = Path(cls.VISUAL_BANK_DIR)
        templates_dir = Path(cls.TEMPLATES_DIR)

        # 1. Clean visual-bank scenery only (never quarantine / overlays / GIFs).
        # Prefer motion (.mp4) over stills so scenes are not frozen title cards.
        chan_prefix = "moku" if ("moku" in norm_chan or "scp" in norm_arch or "horror" in norm_arch) else "aelithia"
        if "aelithia" in norm_chan or "aita" in norm_arch or "drama" in norm_arch:
            chan_prefix = "aelithia"
        scenery_dir = visual_bank_dir / chan_prefix / "scenery"
        motion = _list_scenery_candidates(scenery_dir, ("*.mp4", "*.webm"))
        stills = _list_scenery_candidates(scenery_dir, ("*.jpg", "*.jpeg", "*.png"))
        scenery_candidates = motion or stills
        if scenery_candidates:
            return scenery_candidates[(idx - 1) % len(scenery_candidates)]

        # 2. Motion loops before static thumbnail templates (avoids frozen-cover videos).
        try:
            from src.core.catalog import LoopCatalogRepository
            from src.media.loop_engine import CATEGORY_ALIASES

            repo = LoopCatalogRepository()
            raw_theme = str(norm_arch or "dark_ambient").strip().lower().replace("-", "_").replace(" ", "_")
            cat = CATEGORY_ALIASES.get(raw_theme, raw_theme) or "dark_ambient"
            orient = "vertical" if is_vertical else "horizontal"
            loop_rec = repo.get_best_loop(category=cat, orientation=orient)
            if loop_rec and loop_rec.file_path and Path(loop_rec.file_path).is_file():
                return Path(loop_rec.file_path)
        except Exception as exc:
            logger.debug("LoopCatalogRepository resolution failed: %s", exc)

        proc_dir = REPO_ROOT / "assets" / "loops" / "web_procedural"
        if proc_dir.is_dir():
            proc_candidates = sorted(p for p in proc_dir.glob("**/*.mp4") if p.is_file())
            if proc_candidates:
                return proc_candidates[(idx - 1) % len(proc_candidates)]

        # 3. Curated template stills (thumbnail backdrops) — last resort for video scenes
        target_keys: list[str] = []
        if any(k in norm_arch or k in norm_chan for k in ("scp", "found-footage", "anomaly")):
            target_keys.append("scp")
        elif any(k in norm_arch or k in norm_chan for k in ("aita", "drama", "confession", "aelithia")):
            target_keys.append("aita")
        elif any(k in norm_arch or k in norm_chan for k in ("horror", "vhs", "analog")):
            target_keys.append("horror")
        elif norm_arch:
            target_keys.append(norm_arch)

        for key in target_keys:
            t_dir = templates_dir / key
            if t_dir.is_dir():
                candidates: list[Path] = []
                for ext in ("*.mp4", "*.webm", "*.jpg", "*.jpeg", "*.png"):
                    candidates.extend(sorted(t_dir.glob(ext)))
                if candidates:
                    return candidates[(idx - 1) % len(candidates)]

        bg = REPO_ROOT / "assets" / "background.jpg"
        if bg.is_file():
            return bg

        horror_backdrop = templates_dir / "horror" / "master_backdrop.jpg"
        if horror_backdrop.is_file():
            return horror_backdrop
        return TEMPLATES_DIR / "horror" / "master_backdrop.jpg"

    @classmethod
    def resolve_thumbnail_asset_path(
        cls,
        channel_id: str,
        archetype: str = "",
        explicit_path: Optional[Union[str, Path]] = None,
        video_path: Optional[Union[str, Path]] = None,
        is_vertical: bool = False,
    ) -> Optional[Path]:
        """Resolves the concrete asset path for a thumbnail backdrop if one exists on disk."""
        if explicit_path:
            p = Path(explicit_path).resolve()
            if p.is_file():
                try:
                    with Image.open(p) as test_img:
                        test_img.verify()
                    return p
                except Exception:
                    pass

        norm_arch = str(archetype or "").lower()
        norm_chan = str(channel_id or "").lower()
        templates_dir = Path(cls.TEMPLATES_DIR)
        visual_bank_dir = Path(cls.VISUAL_BANK_DIR)

        # 1. Check templates by archetype
        template_keys = []
        if any(k in norm_arch for k in ("scp", "found-footage", "anomaly")):
            template_keys.append("scp")
        elif any(k in norm_arch for k in ("aita", "drama", "confession")):
            template_keys.append("aita")
        elif any(k in norm_arch for k in ("horror", "vhs", "analog")):
            template_keys.append("horror")
        elif norm_arch:
            template_keys.append(norm_arch)

        for t_key in template_keys:
            t_dir = templates_dir / t_key
            if t_dir.is_dir():
                for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
                    candidates = sorted(t_dir.glob(ext))
                    if candidates:
                        return candidates[0]

        # 2. Check channel templates
        chan_keys = []
        if any(k in norm_chan for k in ("scp", "found-footage")):
            chan_keys.append("scp")
        elif any(k in norm_chan for k in ("aita", "drama", "aelithia")):
            chan_keys.append("aita")
        elif any(k in norm_chan for k in ("horror", "vhs", "analog")):
            chan_keys.append("horror")
        elif "moku" in norm_chan:
            chan_keys.append("scp" if is_vertical else "horror")

        for c_key in chan_keys:
            c_dir = templates_dir / c_key
            if c_dir.is_dir():
                for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
                    candidates = sorted(c_dir.glob(ext))
                    if candidates:
                        return candidates[0]

        # 3. Clean visual bank scenery only (never pre-baked title cards)
        chan_prefix = "moku" if "moku" in norm_chan else ("aelithia" if "aelithia" in norm_chan else norm_chan)
        visual_scenery_dir = visual_bank_dir / chan_prefix / "scenery"
        candidates = _list_scenery_candidates(visual_scenery_dir, ("*.jpg", "*.jpeg", "*.png"))
        if candidates:
            return candidates[0]

        generic_bg = REPO_ROOT / "assets" / "background.jpg"
        if generic_bg.is_file():
            return generic_bg

        return None

    @staticmethod
    def create_atmospheric_noise_background(
        width: int,
        height: int,
        accent_color_hex: Optional[str] = None,
        noise_opacity: int = 22,
    ) -> Image.Image:
        """
        Generates a high-craft dark atmospheric gradient background with controlled noise
        (film grain) as a resilient safeguard against missing or corrupted visual assets.
        """
        w, h = width, height
        bg = Image.new("RGB", (w, h), (10, 14, 20))
        draw = ImageDraw.Draw(bg)

        ar, ag, ab = (12, 16, 24)
        if accent_color_hex:
            try:
                from PIL import ImageColor
                ac = ImageColor.getrgb(accent_color_hex)
                ar, ag, ab = int(ac[0] * 0.15), int(ac[1] * 0.15), int(ac[2] * 0.15)
            except Exception:
                pass

        step = 2 if h <= 1080 else 4
        for y in range(0, h, step):
            ratio = y / max(1, h)
            r = min(255, int(8 + (12 + ar) * ratio))
            g = min(255, int(10 + (14 + ag) * ratio))
            b = min(255, int(14 + (20 + ab) * ratio))
            draw.rectangle([(0, y), (w, min(h, y + step))], fill=(r, g, b))

        try:
            import os
            noise_bytes = os.urandom(w * h)
            noise_l = Image.frombytes("L", (w, h), noise_bytes)
            noise_rgba = Image.merge("RGBA", (
                noise_l,
                noise_l,
                noise_l,
                Image.new("L", (w, h), min(255, max(5, noise_opacity))),
            ))
            bg_rgba = bg.convert("RGBA")
            return Image.alpha_composite(bg_rgba, noise_rgba).convert("RGB")
        except Exception:
            return bg


