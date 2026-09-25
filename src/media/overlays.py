"""
src/media/overlays.py - Atmospheric and Motion Loop Overlay Resolution and Clamping.

Handles discovery, resolution, validation, and opacity clamping for visual overlays
(particles, god rays, film grain, vignettes, TV static) and catalog motion loops.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from src.scene_manifest import HybridAIConfig, SceneConfig

__all__ = [
    "ANIMATED_OVERLAY_SUFFIXES",
    "ATMOSPHERIC_OVERLAY_OPACITY",
    "ATMOSPHERIC_OVERLAY_OPACITY_MAX",
    "ATMOSPHERIC_OVERLAY_OPACITY_MIN",
    "MOTION_LOOP_SUFFIXES",
    "_hybrid_overlay_search_roots",
    "clamp_atmospheric_overlay_opacity",
    "is_motion_loop_path",
    "resolve_hybrid_motion_loop",
    "resolve_hybrid_overlay_asset",
]

MOTION_LOOP_SUFFIXES: set[str] = {".mp4", ".webm", ".mov", ".mkv"}
ANIMATED_OVERLAY_SUFFIXES: set[str] = {".gif", ".webp", ".mp4", ".webm", ".mov"}

ATMOSPHERIC_OVERLAY_OPACITY_MIN: float = 0.15
ATMOSPHERIC_OVERLAY_OPACITY_MAX: float = 0.35
ATMOSPHERIC_OVERLAY_OPACITY: float = 0.25


def _hybrid_overlay_search_roots(kind_norm: str) -> List[Path]:
    """CWD + repo assets/overlays, plus visual_bank overlays (PNG only)."""
    from src.config import BASE_DIR

    roots: List[Path] = [Path("assets/overlays")]
    repo_overlays = BASE_DIR / "assets" / "overlays"
    if repo_overlays not in roots:
        roots.append(repo_overlays)
    vb = BASE_DIR / "assets" / "visual_bank"
    if vb.is_dir():
        try:
            channels = sorted(p for p in vb.iterdir() if p.is_dir() and not p.name.startswith("_"))
        except OSError:
            channels = []
        for chan in channels:
            roots.append(chan / "overlays")
            # Never scan ambient_gifs: full-frame GIF decode is banned on the hot path.
    seen: set[str] = set()
    out: List[Path] = []
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        out.append(root)
    return out


def resolve_hybrid_overlay_asset(
    kind: str,
    particle_type: Optional[str] = None,
) -> Optional[Path]:
    """Return a pre-made static overlay PNG (never a principal-plane background).

    Conventions:
    - particles: ``assets/overlays/particles_<type>.png`` then ``particles.png``
    - god_rays: ``assets/overlays/god_rays.png``
    - film_grain / vignette / tv_static: ``assets/overlays`` then
      ``assets/visual_bank/*/overlays`` (PNG only; GIFs are skipped)
    """
    kind_norm = (kind or "").strip().lower()
    candidates: List[Path] = []
    for root in _hybrid_overlay_search_roots(kind_norm):
        if kind_norm == "particles":
            ptype = (particle_type or "none").strip().lower()
            if ptype and ptype != "none":
                candidates.append(root / f"particles_{ptype}.png")
            candidates.append(root / "particles.png")
        elif kind_norm in ("god_rays", "god-rays", "rays"):
            candidates.append(root / "god_rays.png")
        elif kind_norm in ("film_grain", "grain"):
            candidates.append(root / "film_grain.png")
        elif kind_norm in ("vignette", "dark_vignette"):
            candidates.extend(
                [
                    root / "dark_vignette.png",
                    root / "vignette.png",
                    root / "soft_vignette.png",
                ]
            )
        elif kind_norm in ("tv_static", "tv-static", "static"):
            candidates.append(root / "tv_static.png")
        else:
            return None
    for cand in candidates:
        try:
            if cand.suffix.lower() in ANIMATED_OVERLAY_SUFFIXES:
                continue
            if cand.is_file() and cand.stat().st_size > 0:
                return cand.resolve()
        except OSError:
            continue
    return None


def clamp_atmospheric_overlay_opacity(opacity: float | None = None) -> float:
    """Keep film_grain / vignette / tv_static in the 15-35% overlay band."""
    val = ATMOSPHERIC_OVERLAY_OPACITY if opacity is None else float(opacity)
    return max(ATMOSPHERIC_OVERLAY_OPACITY_MIN, min(ATMOSPHERIC_OVERLAY_OPACITY_MAX, val))


def is_motion_loop_path(path: Union[Path, str, None]) -> bool:
    """True when ``path`` is a non-empty motion video (never a still)."""
    if not path:
        return False
    p = Path(path)
    try:
        return (
            p.is_file()
            and p.suffix.lower() in MOTION_LOOP_SUFFIXES
            and p.stat().st_size > 0
        )
    except OSError:
        return False


def resolve_hybrid_motion_loop(
    scene: SceneConfig,
    extra: Optional[Dict[str, Any]] = None,
) -> Optional[Path]:
    """Pick a catalog/scenery motion loop for stream-copy planes (skip grey/overlays)."""
    extra = extra or {}
    cfg = scene.hybrid_ai_config or HybridAIConfig()
    candidates: List[Any] = [
        extra.get("video_loop_path"),
        extra.get("loop_path"),
        extra.get("background_video_path"),
        cfg.background_image_path,
        scene.image_path,
        scene.asset_path,
    ]
    extra_loops = extra.get("loop_paths")
    if isinstance(extra_loops, (list, tuple)):
        candidates.extend(extra_loops)
    seen: set[str] = set()
    for raw in candidates:
        if not raw:
            continue
        p = Path(str(raw))
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        if not is_motion_loop_path(p):
            continue
        try:
            from src.media.loop_engine import is_grey_procedural_plane, is_overlay_not_plane0

            if is_overlay_not_plane0(p) or is_grey_procedural_plane(path=p):
                continue
        except Exception:
            pass
        return p.resolve()
    return None
