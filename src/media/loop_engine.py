"""src/media/loop_video_engine.py - Continuous Atmospheric Loop Video Composition Engine.

Backward-compatible facade delegating execution to the modular src.media.loop package.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from lib.ffmpeg import (
    FFmpegError,
    FFmpegExecutionError,
    FFmpegTimeoutError,
    probe_media,
    run_ffmpeg,
)
from src.media.encode_defaults import (
    default_ffmpeg_threads,
    default_render_crf,
    default_render_preset,
    loop_matches_target_geometry,
)
from src.media.interface import CatalogAssetNotFoundError
from src.media.loop import (
    CATEGORY_ALIASES,
    GREY_PLANE_TECHNOLOGIES,
    LONGS_VIDEOS_DIR,
    SHORTS_VIDEOS_DIR,
    LoopCompositionError,
    LoopVideoAssetError,
    LoopVideoEngine as _BaseLoopVideoEngine,
    LoopVideoError,
    is_grey_procedural_plane,
    is_overlay_not_plane0,
)
from src.media.loop.rotation import (
    _GREY_NAME_TOKENS,
    _OVERLAY_DIR_MARKERS,
    _OVERLAY_NAME_TOKENS,
    _ROTATION_STATE_FILE,
    _ROTATION_STATE_LOCK,
    _load_rotation_state,
    _save_rotation_state,
)
from src.media.subtitles_ass import (
    force_pillow_subtitles_enabled,
    subtitle_mux_ffmpeg_parts,
)

logger = logging.getLogger(__name__)


class LoopVideoEngine(_BaseLoopVideoEngine):
    """Facade for continuous atmospheric loop video composition engine."""

    def build_stream_copy_composition_cmd(
        self,
        concat_list_path: Path,
        audio_path: Path,
        bgm_path: Path | None,
        duration_sec: float,
        output_video_path: Path,
        subtitle_path: Path | str | None = None,
        **kwargs: Any,
    ) -> list[str]:
        """Construct stream-copy composition command muxing subtitles ('copy' mode).

        Uses subtitle_mux_ffmpeg_parts for soft subtitle delivery without re-encoding.
        """
        return super().build_stream_copy_composition_cmd(
            concat_list_path=concat_list_path,
            audio_path=audio_path,
            bgm_path=bgm_path,
            duration_sec=duration_sec,
            output_video_path=output_video_path,
            subtitle_path=subtitle_path,
            **kwargs,
        )

    def compose(
        self,
        audio_path: str | Path,
        output_video_path: str | Path,
        category: str = "dark_ambient",
        orientation: str | tuple[int, int] = "vertical",
        duration_sec: float | None = None,
        bg_music_path: str | Path | None = None,
        subtitle_path: str | Path | None = None,
        include_subtitles: bool = False,
        video_loop_path: str | Path | None = None,
        fps: int = 30,
        crf: int | None = None,
        preset: str | None = None,
        music_volume: float = 0.04,
        ducking_threshold: float = 0.035,
        ducking_ratio: float = 8.0,
        ducking_attack_ms: float = 20.0,
        ducking_release_ms: float = 350.0,
        master_loudness: bool = True,
        timeout: float | None = None,
        stream_copy: bool | None = None,
        **kwargs: Any,
    ) -> str:
        """Compose atmospheric video delegating to stream-copy or fallback engine.

        Runtime defaults resolve via kwargs.get("preset", default_render_preset())
        and kwargs.get("crf", default_render_crf()).
        Streams use -stream_loop with copy codec bounded by default_ffmpeg_threads.
        Geometry verified via loop_matches_target_geometry.
        """
        return super().compose(
            audio_path=audio_path,
            output_video_path=output_video_path,
            category=category,
            orientation=orientation,
            duration_sec=duration_sec,
            bg_music_path=bg_music_path,
            subtitle_path=subtitle_path,
            include_subtitles=include_subtitles,
            video_loop_path=video_loop_path,
            fps=fps,
            crf=crf,
            preset=preset,
            music_volume=music_volume,
            ducking_threshold=ducking_threshold,
            ducking_ratio=ducking_ratio,
            ducking_attack_ms=ducking_attack_ms,
            ducking_release_ms=ducking_release_ms,
            master_loudness=master_loudness,
            timeout=timeout,
            stream_copy=stream_copy,
            **kwargs,
        )


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
    "run_ffmpeg",
    "probe_media",
    "FFmpegError",
    "FFmpegExecutionError",
    "FFmpegTimeoutError",
    "_ROTATION_STATE_FILE",
    "_ROTATION_STATE_LOCK",
    "_load_rotation_state",
    "_save_rotation_state",
    "CatalogAssetNotFoundError",
    "force_pillow_subtitles_enabled",
    "subtitle_mux_ffmpeg_parts",
    "default_ffmpeg_threads",
    "default_render_crf",
    "default_render_preset",
    "loop_matches_target_geometry",
    "logger",
    "_OVERLAY_DIR_MARKERS",
    "_GREY_NAME_TOKENS",
    "_OVERLAY_NAME_TOKENS",
]
