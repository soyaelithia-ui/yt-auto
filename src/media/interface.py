"""
src/media/interface.py - Compositor Interface and Registry for Video Rendering.

The production runtime accepts only local video assets and stream-copy assembly.
No real-time graphics compositor is registered here.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional, Union

from dataclasses import dataclass, field
from src.config import SETTINGS
from src.log import get_logger

logger = get_logger("compositor_interface")


@dataclass(slots=True, frozen=True)
class MultiActVisualSpec:
    """Strongly typed visual plan compiled by Stage 04 for multi-act stream-copy."""
    video_engine: str
    stream_copy: bool
    lane_id: str
    orientation: str
    total_duration_sec: float
    scene_bg_list: list[str]
    shot_durations: list[float]
    act_titles: list[str]
    act_tensions: list[int]
    is_killswitch_active: bool = False

    def to_dict(self) -> dict[str, Any]:
        scenes = [
            {
                "source": bg,
                "image_path": bg,
                "duration": dur,
                "duration_sec": dur,
            }
            for bg, dur in zip(self.scene_bg_list, self.shot_durations)
        ]
        return {
            "video_engine": self.video_engine,
            "stream_copy": self.stream_copy,
            "is_loop": True,
            "lane_id": self.lane_id,
            "orientation": self.orientation,
            "total_duration_sec": self.total_duration_sec,
            "covered_seconds": self.total_duration_sec,
            "duration_sec": self.total_duration_sec,
            "scene_bg_list": list(self.scene_bg_list),
            "shot_durations": list(self.shot_durations),
            "act_titles": list(self.act_titles),
            "act_tensions": list(self.act_tensions),
            "scenes": scenes,
            "is_killswitch_active": self.is_killswitch_active,
        }


class CompositorError(RuntimeError):
    """Raised when a video compositor fails execution."""
    pass


class CatalogAssetNotFoundError(CompositorError):
    """Raised when a required catalog loop or image asset cannot be found on disk."""
    pass


class BaseVideoCompositor(ABC):
    @abstractmethod
    def render(self, manifest_path: Union[Path, str], output_video_path: Union[Path, str], **extra_kwargs: Any) -> Dict[str, Any]:
        """Render a video from a validated scene_manifest.json file."""
        pass


_LOOP_ALIASES = {
    "loop",
    "loop_video",
    "loop_video_engine",
    "loop_compositor",
    "video_loop",
    "ffmpeg_legacy",
    "default",
    "legacy",
    "motion_canvas",
    # Deprecated configuration aliases now resolve to local loop composition.
    "multiscene",
    "multi_scene",
    "catalog",
    "dual_engine",
}


def get_compositor(name: Optional[str] = None) -> BaseVideoCompositor:
    """Return the local asset stream-copy compositor.

    ``name`` is retained as a compatibility input, but every accepted value
    resolves to ``LoopVideoEngine``. Retired graphical engines fail closed.
    """
    comp_name = (
        name
        or os.environ.get("VIDEO_ENGINE")
        or os.environ.get("SHORT_COMPOSITOR")
        or os.environ.get("COMPOSITOR")
        or getattr(SETTINGS, "short_compositor", "loop")
        or "loop"
    ).lower()
    if comp_name not in _LOOP_ALIASES:
        raise ValueError(
            f"Unsupported video engine {comp_name!r}; only local asset loop composition is available"
        )
    from src.media.loop_engine import LoopVideoEngine
    return LoopVideoEngine()


def __getattr__(name: str):
    if name in ("LoopVideoEngine", "LoopVideoCompositor"):
        from src.media.loop_engine import LoopVideoEngine
        return LoopVideoEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
