"""
src/media/__init__.py - Media engines, compositors, and video renderers.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

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
from src.media.hybrid_engine import (
    HybridVideoEngine,
    HybridVideoError,
    cubic_bezier_ease,
    force_pillow_hybrid_frames_enabled,
    force_pillow_particles_enabled,
    build_ken_burns_zoompan_filter,
    resolve_hybrid_overlay_asset,
)
from src.media.proc_engine import (
    ProceduralVideoEngine,
    ProceduralVideoError,
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

# NativeProceduralEngine is QUARANTINED under src.media._legacy (wgpu opt-in only).
# Keep it lazy so `import src.media` never requires wgpu.
if TYPE_CHECKING:
    from src.media._legacy.native_procedural import NativeProceduralEngine as NativeProceduralEngine

__all__ = [
    "check_local_templates",
    "search_reference_image_web",
    "generate_ai_image",
    "HybridVideoEngine",
    "HybridVideoError",
    "cubic_bezier_ease",
    "default_ffmpeg_threads",
    "default_render_crf",
    "default_render_preset",
    "loop_matches_target_geometry",
    "force_pillow_hybrid_frames_enabled",
    "force_pillow_particles_enabled",
    "build_ken_burns_zoompan_filter",
    "resolve_hybrid_overlay_asset",
    "ProceduralVideoEngine",
    "ProceduralVideoError",
    "MultiSceneCompositor",
    "MultiSceneCompositorError",
    "LoopVideoEngine",
    "LoopVideoCompositor",
    "LoopVideoError",
    "LoopVideoAssetError",
    "LoopCompositionError",
    "NativeProceduralEngine",
    "SVGOverlayEngine",
    "InMemoryCompositor",
    "ASSSubtitleGenerator",
    "sanitize_timestamps",
    "format_ass_timestamp",
    "force_pillow_subtitles_enabled",
    "write_ass_from_cues_or_words",
    "UnifiedEncoder",
]


def __getattr__(name: str) -> Any:
    if name == "NativeProceduralEngine":
        # Quarantined: DEPRECATED shim (guarded) -> src.media._legacy.
        from src.media.native_procedural import NativeProceduralEngine

        return NativeProceduralEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)
