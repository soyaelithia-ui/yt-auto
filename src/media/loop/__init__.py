"""Continuous atmospheric loop video composition subsystem."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from src.config import BASE_DIR, DEFAULT_DB_PATH
from src.core.catalog import LoopCatalogRepository
from src.log import get_logger
from src.media.interface import BaseVideoCompositor
from src.media.loop.audio import LoopAudioMixin
from lib.ffmpeg import (
    FFmpegError,
    FFmpegExecutionError,
    FFmpegTimeoutError,
    probe_media,
    run_ffmpeg,
)
from src.media.loop.exceptions import (
    LoopCompositionError,
    LoopVideoAssetError,
    LoopVideoError,
)
from src.media.loop.filtergraph import LoopFilterGraphMixin
from src.media.loop.rotation import (
    CATEGORY_ALIASES,
    GREY_PLANE_TECHNOLOGIES,
    LONGS_VIDEOS_DIR,
    SHORTS_VIDEOS_DIR,
    LoopRotationMixin,
    is_grey_procedural_plane,
    is_overlay_not_plane0,
)
from src.media.loop.stream_copy import LoopStreamCopyMixin

logger = get_logger("loop_engine")


class LoopVideoEngine(
    LoopRotationMixin,
    LoopFilterGraphMixin,
    LoopAudioMixin,
    LoopStreamCopyMixin,
    BaseVideoCompositor,
):
    """
    Continuous atmospheric loop video composition engine.
    Renders narration audio with categorized video loops, background ambient music,
    sidechain audio ducking, and dual-format aspect ratios (9:16 and 16:9).
    """

    def __init__(
        self,
        loops_root_dir: str | Path | None = None,
        default_fallback_dir: str | Path | None = None,
        default_fallback_image: str | Path | None = None,
        db_path: str | None = None,
        catalog: Optional[LoopCatalogRepository] = None,
        enable_live_synth: bool = False,
        shorts_videos_dir: str | Path | None = None,
        longs_videos_dir: str | Path | None = None,
    ) -> None:
        """
        Initializes the LoopVideoEngine with asset directories and loop catalog database.
        """
        env_loops = os.environ.get("LOOPS_DIR")
        if loops_root_dir is not None:
            self.loops_root_dir = Path(loops_root_dir).expanduser().resolve()
        elif env_loops:
            self.loops_root_dir = Path(env_loops).expanduser().resolve()
        else:
            self.loops_root_dir = (BASE_DIR / "assets" / "loops").resolve()

        if default_fallback_dir is not None:
            self.default_fallback_dir = Path(default_fallback_dir).expanduser().resolve()
        else:
            self.default_fallback_dir = (BASE_DIR / "assets" / "backgrounds").resolve()

        if default_fallback_image is not None:
            self.default_fallback_image = Path(default_fallback_image).expanduser().resolve()
        else:
            self.default_fallback_image = (BASE_DIR / "assets" / "background.jpg").resolve()

        catalog_default = (BASE_DIR / "data" / "loop_catalog.db").resolve()
        if db_path is not None:
            resolved_db = str(db_path)
        elif catalog_default.is_file():
            resolved_db = str(catalog_default)
        else:
            resolved_db = DEFAULT_DB_PATH

        self.db_path = resolved_db
        self._custom_catalog = catalog is not None
        self.catalog = catalog or LoopCatalogRepository(db_path=resolved_db)
        self.enable_live_synth = enable_live_synth or (
            os.environ.get("ENABLE_LIVE_LOOP_SYNTH", "0").lower() in ("1", "true", "yes")
        )
        if shorts_videos_dir is not None:
            self.shorts_videos_dir = Path(shorts_videos_dir).expanduser().resolve()
        elif loops_root_dir is not None:
            self.shorts_videos_dir = (self.loops_root_dir / "shorts").resolve()
        else:
            self.shorts_videos_dir = SHORTS_VIDEOS_DIR

        if longs_videos_dir is not None:
            self.longs_videos_dir = Path(longs_videos_dir).expanduser().resolve()
        elif loops_root_dir is not None:
            self.longs_videos_dir = (self.loops_root_dir / "longs").resolve()
        else:
            self.longs_videos_dir = LONGS_VIDEOS_DIR


LoopVideoCompositor = LoopVideoEngine

__all__ = [
    "LoopVideoEngine",
    "LoopVideoCompositor",
    "LoopVideoError",
    "LoopVideoAssetError",
    "LoopCompositionError",
    "is_grey_procedural_plane",
    "is_overlay_not_plane0",
    "GREY_PLANE_TECHNOLOGIES",
    "SHORTS_VIDEOS_DIR",
    "LONGS_VIDEOS_DIR",
    "CATEGORY_ALIASES",
    "LoopRotationMixin",
    "LoopFilterGraphMixin",
    "LoopAudioMixin",
    "LoopStreamCopyMixin",
    "run_ffmpeg",
    "probe_media",
    "FFmpegError",
    "FFmpegExecutionError",
    "FFmpegTimeoutError",
]
