"""
src/compositor_interface.py - Compositor Interface and Registry for Video Rendering.

Supports Dual-Engine Multi-Scene Rendering (MultiSceneCompositor), Hybrid Cinematic AI (HybridVideoEngine),
Pure Procedural WebGL/Canvas (ProceduralVideoEngine), and Continuous Loops (LoopVideoEngine).
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional, Union

from src.config import SETTINGS
from src.log import get_logger
from src.scene_manifest import validate_scene_manifest

logger = get_logger("compositor_interface")


class CompositorError(RuntimeError):
    """Raised when a video compositor fails execution."""
    pass


class BaseVideoCompositor(ABC):
    @abstractmethod
    def render(self, manifest_path: Union[Path, str], output_video_path: Union[Path, str], **extra_kwargs: Any) -> Dict[str, Any]:
        """Render a video from a validated scene_manifest.json file."""
        pass


_MULTISCENE_ALIASES = {"multiscene", "multi_scene", "multi_scene_compositor", "dual_engine", "default"}
_HYBRID_ALIASES = {"hybrid", "hybrid_ai", "hybrid_cinematic_ai", "hybrid_video_engine"}
_PROCEDURAL_ALIASES = {"procedural", "pure_procedural", "pure_procedural_webgl", "procedural_video_engine"}
_LOOP_ALIASES = {"loop", "loop_video", "loop_video_engine", "loop_compositor", "ffmpeg_legacy", "motion_canvas", "legacy"}


def get_compositor(name: Optional[str] = None) -> BaseVideoCompositor:
    """
    Return the configured compositor instance.
    Supports 'multiscene' (default), 'hybrid', 'procedural', and 'loop'.
    """
    comp_name = (
        name
        or os.environ.get("VIDEO_ENGINE")
        or os.environ.get("SHORT_COMPOSITOR")
        or os.environ.get("COMPOSITOR")
        or getattr(SETTINGS, "short_compositor", "multiscene")
        or "multiscene"
    ).lower()

    if comp_name in _MULTISCENE_ALIASES:
        from src.media.compositor import MultiSceneCompositor
        return MultiSceneCompositor()

    if comp_name in _HYBRID_ALIASES:
        from src.media.hybrid_engine import HybridVideoEngine
        return HybridVideoEngine()

    if comp_name in _PROCEDURAL_ALIASES:
        from src.media.proc_engine import ProceduralVideoEngine
        return ProceduralVideoEngine()

    if comp_name in _LOOP_ALIASES:
        from src.media.loop_engine import LoopVideoEngine
        return LoopVideoEngine()

    logger.warning(
        "Compositor %r is unrecognized. Defaulting to MultiSceneCompositor.",
        comp_name,
    )
    from src.media.compositor import MultiSceneCompositor
    return MultiSceneCompositor()


def __getattr__(name: str):
    if name in ("MultiSceneCompositor",):
        from src.media.compositor import MultiSceneCompositor
        return MultiSceneCompositor
    if name in ("HybridVideoEngine",):
        from src.media.hybrid_engine import HybridVideoEngine
        return HybridVideoEngine
    if name in ("ProceduralVideoEngine",):
        from src.media.proc_engine import ProceduralVideoEngine
        return ProceduralVideoEngine
    if name in ("LoopVideoEngine", "LoopVideoCompositor"):
        from src.media.loop_engine import LoopVideoEngine
        return LoopVideoEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
