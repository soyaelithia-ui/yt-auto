"""Local media assets, stream-copy video composition, and audio/subtitle helpers."""
from __future__ import annotations

from src.media.assets import check_local_templates, search_reference_image_web, generate_ai_image
from src.media.encode_defaults import (
    default_ffmpeg_threads,
    default_render_crf,
    default_render_preset,
    loop_matches_target_geometry,
)
from src.media.interface import (
    BaseVideoCompositor,
    CatalogAssetNotFoundError,
    CompositorError,
    MultiActVisualSpec,
    get_compositor,
)
from src.media.loop_engine import (
    LoopCompositionError,
    LoopVideoAssetError,
    LoopVideoCompositor,
    LoopVideoEngine,
    LoopVideoError,
)
from src.media.subtitles_ass import (
    ASSSubtitleGenerator,
    force_pillow_subtitles_enabled,
    format_ass_timestamp,
    sanitize_timestamps,
    write_ass_from_cues_or_words,
)
from src.media.unified_encoder import UnifiedEncoder

__all__ = [
    "check_local_templates",
    "search_reference_image_web",
    "generate_ai_image",
    "default_ffmpeg_threads",
    "default_render_crf",
    "default_render_preset",
    "loop_matches_target_geometry",
    "BaseVideoCompositor",
    "CatalogAssetNotFoundError",
    "CompositorError",
    "MultiActVisualSpec",
    "get_compositor",
    "LoopVideoEngine",
    "LoopVideoCompositor",
    "LoopVideoError",
    "LoopVideoAssetError",
    "LoopCompositionError",
    "ASSSubtitleGenerator",
    "sanitize_timestamps",
    "format_ass_timestamp",
    "force_pillow_subtitles_enabled",
    "write_ass_from_cues_or_words",
    "UnifiedEncoder",
]


def __dir__() -> list[str]:
    return sorted(__all__)
