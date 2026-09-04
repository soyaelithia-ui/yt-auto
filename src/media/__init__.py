"""
src/media/__init__.py - Media engines, compositors, and video renderers.
"""
from src.media.assets import (
    check_local_templates,
    search_reference_image_web,
    generate_ai_image,
)
from src.media.hybrid_engine import (
    HybridVideoEngine,
    HybridVideoError,
    cubic_bezier_ease,
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
from src.media.native_procedural import (
    NativeProceduralEngine,
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
    "HybridVideoEngine",
    "HybridVideoError",
    "cubic_bezier_ease",
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
