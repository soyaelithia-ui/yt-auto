"""
src/media/thumbnails/layouts/__init__.py - Modular Niche Thumbnail Layouts.
"""
from src.media.thumbnails.layouts.base import BaseThumbnailLayout, LayoutRegistry
from src.media.thumbnails.layouts.analog_horror import AnalogHorrorVhsLayout
from src.media.thumbnails.layouts.cinematic import GeneralCinematicLayout

__all__ = [
    "BaseThumbnailLayout",
    "LayoutRegistry",
    "AnalogHorrorVhsLayout",
    "GeneralCinematicLayout",
]
