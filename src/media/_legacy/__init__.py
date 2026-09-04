"""
QUARANTINED / LEGACY media backends — NOT part of the production SSOT.

PDF SSOT (v2.4.0): production audiovisual = FFmpeg; thumbnails = Pillow.
WebGPU / wgpu-py / Lavapipe / WGSL shaders live here only so they cannot
creep back onto the hot path (pipeline, compositor, loop_worker, hybrid).

Do not import from this package in production code unless
ENABLE_NATIVE_PROCEDURAL=1 (explicit opt-in experiments).
"""

from __future__ import annotations

__all__: list[str] = []
