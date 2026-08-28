"""
src/export/presets.py - Export Presets and Format Configuration Rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple
from src.narrative.schema import VideoFormat


@dataclass
class ExportPreset:
    name: str
    format: VideoFormat
    width: int
    height: int
    fps: int
    min_duration_sec: float
    max_duration_sec: float
    default_duration_sec: float
    require_subtitles: bool
    enable_seamless_loop: bool
    enable_interstitials: bool


PRESET_SHORT_VERTICAL = ExportPreset(
    name="YouTube Shorts Vertical (9:16)",
    format=VideoFormat.SHORT_VERTICAL,
    width=1080,
    height=1920,
    fps=30,
    min_duration_sec=25.0,
    max_duration_sec=58.0,
    default_duration_sec=35.0,
    require_subtitles=True,
    enable_seamless_loop=True,
    enable_interstitials=False,
)

PRESET_LONG_HORIZONTAL = ExportPreset(
    name="Longform Horizontal (16:9)",
    format=VideoFormat.LONG_HORIZONTAL,
    width=1920,
    height=1080,
    fps=30,
    min_duration_sec=180.0,
    max_duration_sec=600.0,
    default_duration_sec=240.0,
    require_subtitles=True,
    enable_seamless_loop=False,
    enable_interstitials=True,
)


def get_preset_for_format(video_format: VideoFormat) -> ExportPreset:
    if video_format == VideoFormat.SHORT_VERTICAL:
        return PRESET_SHORT_VERTICAL
    return PRESET_LONG_HORIZONTAL
