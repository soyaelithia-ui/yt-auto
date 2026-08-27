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
from src.media.web_renderer import (
    WebVideoRenderer,
    RenderSpec,
    THEMATIC_TEMPLATES,
    CATEGORY_TECH_MAP,
)
from src.media.loop_engine import (
    LoopVideoEngine,
    LoopVideoCompositor,
    LoopVideoError,
    LoopVideoAssetError,
    LoopCompositionError,
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
    "WebVideoRenderer",
    "RenderSpec",
    "THEMATIC_TEMPLATES",
    "CATEGORY_TECH_MAP",
    "LoopVideoEngine",
    "LoopVideoCompositor",
    "LoopVideoError",
    "LoopVideoAssetError",
    "LoopCompositionError",
]
