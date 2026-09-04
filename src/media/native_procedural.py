"""
DEPRECATED / QUARANTINED shim.

Implementation lives in ``src.media._legacy.native_procedural``.
Production SSOT (PDF v2.4.0): FFmpeg + Pillow thumbs only — no wgpu / Lavapipe on the
hot path. Importing this module from pipeline/compositor/loop_worker/hybrid/proc_engine
without ``ENABLE_NATIVE_PROCEDURAL=1`` raises RuntimeError (fail-closed).

Prefer importing archetypes from ``src.core.scenic_detector`` on production paths.
"""

from __future__ import annotations

import inspect
import os
import warnings

_PRODUCTION_IMPORTERS = (
    "src.pipeline",
    "src.media.compositor",
    "src.media.loop_worker",
    "src.media.hybrid_engine",
    "src.media.proc_engine",
    "src.media.multi_act_renderer",
)


def _native_procedural_opt_in_enabled() -> bool:
    return os.environ.get("ENABLE_NATIVE_PROCEDURAL", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _guard_production_import() -> None:
    """Fail closed if a production module imports this shim without opt-in."""
    if _native_procedural_opt_in_enabled():
        return
    for frame_info in inspect.stack()[1:]:
        mod = frame_info.frame.f_globals.get("__name__", "") or ""
        if any(mod == f or mod.startswith(f + ".") for f in _PRODUCTION_IMPORTERS):
            raise RuntimeError(
                "DEPRECATED: src.media.native_procedural is quarantined under "
                "src.media._legacy. Production modules "
                "(pipeline/compositor/loop_worker/hybrid/proc_engine) must not import "
                "it without ENABLE_NATIVE_PROCEDURAL=1. "
                "SSOT: FFmpeg audiovisual + Pillow thumbs only (no wgpu/Lavapipe)."
            )


_guard_production_import()

warnings.warn(
    "src.media.native_procedural is DEPRECATED and quarantined under "
    "src.media._legacy; production SSOT is FFmpeg + Pillow thumbs "
    "(ENABLE_NATIVE_PROCEDURAL opt-in only).",
    DeprecationWarning,
    stacklevel=2,
)

from src.media._legacy.native_procedural import (  # noqa: E402
    DEFAULT_ACCENT_COLORS,
    DEFAULT_SHADERS_DIR,
    VALID_ARCHETYPES,
    NativeProceduralEngine,
    pack_uniform_bytes,
)

__all__ = [
    "DEFAULT_ACCENT_COLORS",
    "DEFAULT_SHADERS_DIR",
    "VALID_ARCHETYPES",
    "NativeProceduralEngine",
    "pack_uniform_bytes",
    "_native_procedural_opt_in_enabled",
]
