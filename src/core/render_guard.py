"""Bounded concurrency semaphores for FFmpeg video rendering.

Isolates heavy longform FFmpeg encoding (N=1) from lightweight stream-copy
Short composition (N=2) so pipeline stages (ingest, TTS, QA, upload) run
concurrently without head-of-line blocking.
"""

from __future__ import annotations

from src.core.concurrency import (
    FFMPEG_ENCODE_MAX_THREADS,
    FFMPEG_PROBE_THREADS,
    RESOURCE_CPU_CEILING_CORES,
    RESOURCE_RAM_CEILING_GIB,
    _LONG_RENDER_SEMAPHORE,
    _SHORT_RENDER_SEMAPHORE,
    _SYNTHESIS_SEMAPHORE,
    acquire_render_guard,
)

__all__ = [
    "FFMPEG_ENCODE_MAX_THREADS",
    "FFMPEG_PROBE_THREADS",
    "RESOURCE_CPU_CEILING_CORES",
    "RESOURCE_RAM_CEILING_GIB",
    "_LONG_RENDER_SEMAPHORE",
    "_SHORT_RENDER_SEMAPHORE",
    "_SYNTHESIS_SEMAPHORE",
    "acquire_render_guard",
]

