"""Shared low-CPU FFmpeg encode defaults (SSOT with docker-compose / .env).

Production compose pins RENDER_CRF=19 and RENDER_PRESET=veryfast. Media engines
historically hardcoded preset=fast/faster/slow and CRF 18/23, which either burned
CPU (slow) or drifted from the documented quality target. Import these helpers
instead of scattering literals.

Policy (near-zero resource goal):
- Horizontal beats / loop path: prefer ``-c:v copy`` (no video re-encode).
- When re-encode is required: ``veryfast`` + CRF 19 (YouTube-safe, sharper
  finals than CRF 21; avoid ultrafast on delivers; avoid ``slow`` on hot path).
- Pillow/rawvideo frame loops remain opt-in only (FORCE_PILLOW_*).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Union

# YouTube/EBU speech target used by compositor, loop, TTS master, and unified encoder.
LOUDNORM_I = -16.0
LOUDNORM_TP = -1.5
LOUDNORM_LRA = 11.0


def default_render_crf(fallback: int = 19) -> int:
    """Return RENDER_CRF clamped to x264's valid range (0–51)."""
    raw = os.environ.get("RENDER_CRF", "").strip()
    try:
        value = int(raw) if raw else int(fallback)
    except ValueError:
        value = int(fallback)
    return max(0, min(51, value))


def default_render_preset(fallback: str = "veryfast") -> str:
    """Return RENDER_PRESET (default veryfast — matches docker-compose prod)."""
    raw = (os.environ.get("RENDER_PRESET") or "").strip()
    return raw or (fallback or "veryfast")


def default_ffmpeg_threads(fallback: Optional[int] = None) -> int:
    """Return FFMPEG_THREADS capped to a small pool (container cpus≈4)."""
    raw = os.environ.get("FFMPEG_THREADS", "").strip()
    cpu_cap = max(1, min(os.cpu_count() or 2, 4))
    if raw:
        try:
            return max(1, min(int(raw), cpu_cap))
        except ValueError:
            pass
    if fallback is not None:
        return max(1, min(int(fallback), cpu_cap))
    return cpu_cap


def loop_matches_target_geometry(
    loop_path: Union[Path, str],
    width: int,
    height: int,
) -> bool:
    """Return True when probed video WxH equals the target (safe for ``-c:v copy``).

    Shared by procedural segment render (this PR) and director single-pass assembly
    (PR #11 ``MultiSceneCompositor._loop_matches_target``) so merges do not fork
    two incompatible geometry checks. Uses ``probe.primary_video`` (same as
    ``video_streams[0]`` when present).
    """
    try:
        from lib.ffmpeg import probe_media

        probe = probe_media(Path(loop_path))
        vs = probe.primary_video
        if vs is None:
            return False
        return int(vs.width) == int(width) and int(vs.height) == int(height)
    except Exception:
        return False
