"""
src/media/__init__.py - Media engines, compositors, and video renderers.
"""
from __future__ import annotations

from typing import Any

from src.media.assets import (
    check_local_templates,
    search_reference_image_web,
    generate_ai_image,
)
from src.media.encode_defaults import (
    default_ffmpeg_threads,
    default_render_crf,
    default_render_preset,
    loop_matches_target_geometry,
)
from src.media.interface import (
    BaseVideoCompositor,
    CompositorError,
    CatalogAssetNotFoundError,
    get_compositor,
)
from src.media.hybrid_engine import (
    HybridVideoEngine,
    HybridVideoError,
    build_ken_burns_zoompan_filter,
    canonical_ken_burns_params,
    plan_ken_burns_still_segments,
    max_reencoded_shots,
    is_motion_loop_path,
    resolve_hybrid_motion_loop,
    KEN_BURNS_MIN_DURATION_SEC,
    KEN_BURNS_ZOOM_START,
    KEN_BURNS_ZOOM_END,
    KEN_BURNS_FPS,
    KEN_BURNS_SEGMENT_MAX_SEC,
    KEN_BURNS_SPLIT_THRESHOLD_SEC,
    MAX_REENCODE_SHOTS_PER_MIN,
    ATMOSPHERIC_OVERLAY_OPACITY,
    resolve_hybrid_overlay_asset,
)
from src.media.compositor import (
    MultiSceneCompositor,
    MultiSceneCompositorError,
)
from src.media.loop_engine import (
    LoopVideoEngine,
    LoopVideoCompositor,
    LoopVideoError,
    LoopVideoAssetError,
    LoopCompositionError,
)
from src.media.svg_overlay import (
    SVGOverlayEngine,
)
from src.media.inmemory_compositor import (
    InMemoryCompositor,
)
from src.media.subtitles_ass import (
    ASSSubtitleGenerator,
    sanitize_timestamps,
    format_ass_timestamp,
    force_pillow_subtitles_enabled,
    write_ass_from_cues_or_words,
)
from src.media.unified_encoder import (
    UnifiedEncoder,
)

__all__ = [
    "check_local_templates",
    "search_reference_image_web",
    "generate_ai_image",
    "BaseVideoCompositor",
    "CompositorError",
    "CatalogAssetNotFoundError",
    "get_compositor",
    "HybridVideoEngine",
    "HybridVideoError",
    "default_ffmpeg_threads",
    "default_render_crf",
    "default_render_preset",
    "loop_matches_target_geometry",
    "build_ken_burns_zoompan_filter",
    "canonical_ken_burns_params",
    "plan_ken_burns_still_segments",
    "max_reencoded_shots",
    "is_motion_loop_path",
    "resolve_hybrid_motion_loop",
    "KEN_BURNS_MIN_DURATION_SEC",
    "MAX_REENCODE_SHOTS_PER_MIN",
    "KEN_BURNS_ZOOM_START",
    "KEN_BURNS_ZOOM_END",
    "KEN_BURNS_FPS",
    "KEN_BURNS_SEGMENT_MAX_SEC",
    "KEN_BURNS_SPLIT_THRESHOLD_SEC",
    "ATMOSPHERIC_OVERLAY_OPACITY",
    "resolve_hybrid_overlay_asset",
    "MultiSceneCompositor",
    "MultiSceneCompositorError",
    "LoopVideoEngine",
    "LoopVideoCompositor",
    "LoopVideoError",
    "LoopVideoAssetError",
    "LoopCompositionError",
    "SVGOverlayEngine",
    "InMemoryCompositor",
    "ASSSubtitleGenerator",
    "sanitize_timestamps",
    "format_ass_timestamp",
    "force_pillow_subtitles_enabled",
    "write_ass_from_cues_or_words",
    "UnifiedEncoder",
]


def __dir__() -> list[str]:
    return sorted(__all__)
