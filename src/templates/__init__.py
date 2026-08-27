"""
Template system package for video creation presets.
"""
from src.templates.template_manager import (
    VideoTemplate,
    SubtitleStyle,
    AudioStyle,
    VisualEffectStyle,
    ThumbnailStyle,
    TemplateRegistry,
    get_template,
)

__all__ = [
    "VideoTemplate",
    "SubtitleStyle",
    "AudioStyle",
    "VisualEffectStyle",
    "ThumbnailStyle",
    "TemplateRegistry",
    "get_template",
]
