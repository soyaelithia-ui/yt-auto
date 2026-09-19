"""
Template system package for video creation presets.
"""
from src.templates.loader import clear_template_cache, load_template_json, render_paragraphs
from src.templates.template_manager import (
    AudioStyle,
    SubtitleStyle,
    TemplateRegistry,
    ThumbnailStyle,
    VideoTemplate,
    VisualEffectStyle,
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
    "load_template_json",
    "clear_template_cache",
    "render_paragraphs",
]
