"""
src/media/thumbnails/asset_resolver.py - Deterministic 3-Tier Thematic Asset Resolver.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Optional, Tuple, Union

from PIL import Image, ImageOps


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

# Baked Spanish title-card chrome tokens (BITÁCORA / ADVERTENCIA) — never as bg.
_EXCLUDED_NAME_TOKENS = (
    "bitácora",
    "bitacora",
    "advertencia",
)


def _is_clean_visual_candidate(path: Path) -> bool:
    """Reject quarantined title cards and non-scenery visual_bank layers."""
    parts = {p.lower() for p in Path(path).parts}
    if any(m.lower() in parts for m in _EXCLUDED_VISUAL_BANK_MARKERS):
        return False
    hay = f"{Path(path).stem.lower()} {Path(path).name.lower()}"
    if any(tok in hay for tok in _EXCLUDED_NAME_TOKENS):
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

    @property
    def REPO_ROOT(cls) -> Path:
        if "_custom_repo_root" in cls.__dict__:
            return cls.__dict__["_custom_repo_root"]
        import src.media.thumbnails.asset_resolver as mod
        return mod.REPO_ROOT

    @REPO_ROOT.setter
    def REPO_ROOT(cls, val: Path) -> None:
        cls._custom_repo_root = Path(val)


class ThematicAssetResolver(metaclass=_ThematicAssetResolverMeta):
    """
    Resolves background imagery through a strict 3-tier local hierarchy:
    - Tier 1: Explicit image path (if specified and valid).
    - Tier 2: Curated local asset bank (assets/thumbnails/templates/ or assets/visual_bank/).
    - Tier 3: Catalog loop or clean local scenery asset.
    - Missing assets: fail closed; no synthetic or procedural image is generated.
    """

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
        root = Path(cls.REPO_ROOT).resolve()

        # 1. Clean visual-bank motion scenery first (never quarantine / overlays / GIFs).
        if any(k in norm_chan or k in norm_arch for k in ("drama", "aita")):
            chan_prefix = "drama"
        elif any(k in norm_chan or k in norm_arch for k in ("scifi", "singularidad")):
            chan_prefix = "scifi"
        else:
            chan_prefix = "horror"
        scenery_dir = visual_bank_dir / chan_prefix / "scenery"
        motion = _list_scenery_candidates(scenery_dir, ("*.mp4", "*.webm"))
        stills = _list_scenery_candidates(scenery_dir, ("*.jpg", "*.jpeg", "*.png"))
        if motion:
            return motion[(idx - 1) % len(motion)]

        # 2. Prefer catalog loops over scenery stills for video scenes.
        try:
            from src.core.catalog import LoopCatalogRepository
            from src.media.loop_engine import CATEGORY_ALIASES

            repo = LoopCatalogRepository()
            raw_theme = str(norm_arch or "dark_ambient").strip().lower().replace("-", "_").replace(" ", "_")
            cat = CATEGORY_ALIASES.get(raw_theme, raw_theme) or "dark_ambient"
            orient = "vertical" if is_vertical else "horizontal"
            loop_rec = repo.get_best_loop(category=cat, orientation=orient, seed=idx)
            if loop_rec and loop_rec.file_path:
                lp = Path(loop_rec.file_path)
                if lp.is_file():
                    try:
                        if lp.resolve().is_relative_to(root):
                            return lp
                    except (OSError, ValueError):
                        pass
        except Exception as exc:
            logger.debug("LoopCatalogRepository resolution failed: %s", exc)

        # 3. Clean scenery stills only after catalog loops are exhausted.
        if stills:
            return stills[(idx - 1) % len(stills)]

        # 4. Curated template stills (thumbnail backdrops) — last resort for video scenes
        target_keys: list[str] = []
        if any(k in norm_arch or k in norm_chan for k in ("scp", "found-footage", "anomaly")):
            target_keys.append("scp")
        elif any(k in norm_arch or k in norm_chan for k in ("aita", "drama", "confession")):
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

        bg = root / "assets" / "background.jpg"
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
        """Resolve a concrete local thumbnail asset; video frames are never extracted."""
        del video_path
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
        elif any(k in norm_chan for k in ("aita", "drama")):
            chan_keys.append("aita")
        elif any(k in norm_chan for k in ("horror", "vhs", "analog")):
            chan_keys.append("horror")
        elif any(k in norm_chan for k in ("scifi", "singularidad")):
            chan_keys.append("scifi")

        for c_key in chan_keys:
            c_dir = templates_dir / c_key
            if c_dir.is_dir():
                for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
                    candidates = sorted(c_dir.glob(ext))
                    if candidates:
                        return candidates[0]

        # 3. Clean visual bank scenery only (never pre-baked title cards)
        if any(k in norm_chan for k in ("drama", "aita")):
            chan_prefix = "drama"
        elif any(k in norm_chan for k in ("scifi", "singularidad")):
            chan_prefix = "scifi"
        else:
            chan_prefix = "horror"
        visual_scenery_dir = visual_bank_dir / chan_prefix / "scenery"
        candidates = _list_scenery_candidates(visual_scenery_dir, ("*.jpg", "*.jpeg", "*.png"))
        if candidates:
            return candidates[0]

        generic_bg = REPO_ROOT / "assets" / "background.jpg"
        if generic_bg.is_file():
            return generic_bg

        return None


