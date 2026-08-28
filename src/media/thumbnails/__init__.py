"""
src/media/thumbnails/ - High-CTR YouTube Thumbnail Generation Engine.
"""
from src.media.thumbnails.engine import ThumbnailConfig, ThumbnailEngine
from src.media.thumbnails.extractor import ClimaxFrameExtractor
from src.media.thumbnails.grading import ChiaroscuroColorGrader
from src.media.thumbnails.layout import AspectLayoutManager, SafeZone
from src.media.thumbnails.subject_extractor import RimLightCompositor
from src.media.thumbnails.typography import DynamicTypographyEngine

__all__ = [
    "ThumbnailEngine",
    "ThumbnailConfig",
    "ClimaxFrameExtractor",
    "ChiaroscuroColorGrader",
    "RimLightCompositor",
    "DynamicTypographyEngine",
    "AspectLayoutManager",
    "SafeZone",
]
