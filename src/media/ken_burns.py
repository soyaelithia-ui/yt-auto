"""
src/media/ken_burns.py - Canonical Ken Burns Camera Motion and ZoomPan Planning.

Generates atomic single-pass FFmpeg zoompan filter expressions, plans still segment
splits across long durations (12-15s bounds, max 20s split threshold), and calculates
canonical camera motion parameters.
"""
from __future__ import annotations

import math
from typing import List, Tuple

__all__ = [
    "KEN_BURNS_FPS",
    "KEN_BURNS_MIN_DURATION_SEC",
    "KEN_BURNS_PAN_CYCLE",
    "KEN_BURNS_SEGMENT_MAX_SEC",
    "KEN_BURNS_SEGMENT_TARGET_SEC",
    "KEN_BURNS_SPLIT_THRESHOLD_SEC",
    "KEN_BURNS_ZOOM_END",
    "KEN_BURNS_ZOOM_START",
    "MAX_REENCODE_SHOTS_PER_MIN",
    "build_ken_burns_zoompan_filter",
    "canonical_ken_burns_params",
    "max_reencoded_shots",
    "plan_ken_burns_still_segments",
]

# Canonical Ken Burns for still backgrounds (not applied to motion loops).
# Acceptance: zoom 1.00->1.10, duration >=12 s, 30 fps when using defaults / still path.
# A single zoompan must not span >20s; stills longer than that hard-cut at 12-15s.
KEN_BURNS_ZOOM_START: float = 1.00
KEN_BURNS_ZOOM_END: float = 1.10
KEN_BURNS_MIN_DURATION_SEC: float = 12.0
KEN_BURNS_FPS: int = 30
KEN_BURNS_SEGMENT_TARGET_SEC: float = 13.0
KEN_BURNS_SEGMENT_MAX_SEC: float = 15.0
KEN_BURNS_SPLIT_THRESHOLD_SEC: float = 20.0
KEN_BURNS_PAN_CYCLE: Tuple[str, ...] = (
    "center_to_top",
    "left_to_right",
    "center_to_bottom",
    "right_to_left",
)
MAX_REENCODE_SHOTS_PER_MIN: int = 4


def canonical_ken_burns_params(
    *,
    duration_sec: float | None = None,
    fps: int | None = None,
    zoom_start: float | None = None,
    zoom_end: float | None = None,
    enforce_min_duration: bool = False,
) -> tuple[float, int, int, float, float]:
    """Return (duration, fps, total_frames, zoom_start, zoom_end) for still Ken Burns.

    Defaults match acceptance (1.00->1.10 @ 30 fps, >=12 s). Scene renders keep the
    caller duration unless ``enforce_min_duration`` is set (acceptance / smoke).
    """
    base_dur = float(duration_sec) if duration_sec is not None else float(KEN_BURNS_MIN_DURATION_SEC)
    if enforce_min_duration:
        dur = max(float(KEN_BURNS_MIN_DURATION_SEC), base_dur)
    else:
        dur = max(0.5, base_dur)
    use_fps = int(fps) if fps and int(fps) > 0 else int(KEN_BURNS_FPS)
    z0 = float(KEN_BURNS_ZOOM_START if zoom_start is None else zoom_start)
    z1 = float(KEN_BURNS_ZOOM_END if zoom_end is None else zoom_end)
    if z0 <= 0:
        z0 = float(KEN_BURNS_ZOOM_START)
    if z1 <= z0:
        z1 = float(KEN_BURNS_ZOOM_END)
    total_frames = max(1, int(round(dur * use_fps)))
    return dur, use_fps, total_frames, z0, z1


def build_ken_burns_zoompan_filter(
    width: int,
    height: int,
    fps: int,
    total_frames: int,
    zoom_start: float,
    zoom_end: float,
    pan_direction: str,
) -> str:
    """Build an FFmpeg zoompan expression matching camera smoothstep easing.

    Uses the smoothstep easing curve (t^2 * (3 - 2t)).
    """
    denom = max(1, int(total_frames) - 1)
    e = f"(on/{denom})*(on/{denom})*(3-2*(on/{denom}))"
    z0 = float(zoom_start)
    z1 = float(zoom_end)
    z = f"({z0:.6f}+({z1:.6f}-{z0:.6f})*{e})"
    pan = (pan_direction or "static").strip().lower()
    if pan == "left_to_right":
        x = f"(iw-iw/zoom)*{e}"
        y = "(ih-ih/zoom)/2"
    elif pan == "right_to_left":
        x = f"(iw-iw/zoom)*(1-{e})"
        y = "(ih-ih/zoom)/2"
    elif pan == "center_to_top":
        x = "(iw-iw/zoom)/2"
        y = f"(ih-ih/zoom)*(1-0.5*{e})"
    elif pan == "center_to_bottom":
        x = "(iw-iw/zoom)/2"
        y = f"(ih-ih/zoom)*(0.5*{e})"
    else:
        x = "(iw-iw/zoom)/2"
        y = "(ih-ih/zoom)/2"
    return (
        f"zoompan=z='{z}':x='{x}':y='{y}':"
        f"d={int(total_frames)}:s={int(width)}x{int(height)}:fps={int(fps)}"
    )


def max_reencoded_shots(
    duration_sec: float,
    per_minute: int = MAX_REENCODE_SHOTS_PER_MIN,
) -> int:
    """Cap libx264 Ken Burns encodes per minute of output (still path only)."""
    dur = max(0.0, float(duration_sec))
    minutes = 1 if dur <= 0 else int(math.ceil(dur / 60.0))
    return max(1, int(per_minute) * minutes)


def plan_ken_burns_still_segments(
    duration_sec: float,
    fps: int | None = None,
    pan_direction: str = "center_to_top",
) -> List[Tuple[float, int, str]]:
    """Split a still Ken Burns scene into 12-15s zoompan segments (never >20s).

    Catalog motion loops are not Ken-Burned; this planner is still-path only.
    Returns (duration_sec, frame_count, pan_direction) tuples whose durations
    sum to ``duration_sec``.
    """
    dur = max(0.5, float(duration_sec))
    use_fps = int(fps) if fps and int(fps) > 0 else int(KEN_BURNS_FPS)
    pan0 = (pan_direction or "center_to_top").strip().lower()
    if pan0 not in KEN_BURNS_PAN_CYCLE:
        pan0 = "center_to_top"

    if dur <= KEN_BURNS_SEGMENT_MAX_SEC and dur < KEN_BURNS_SPLIT_THRESHOLD_SEC:
        frames = max(1, int(round(dur * use_fps)))
        return [(dur, frames, pan0)]

    n = max(2, int(round(dur / KEN_BURNS_SEGMENT_TARGET_SEC)))
    while dur / n > KEN_BURNS_SEGMENT_MAX_SEC:
        n += 1
    while dur / n < KEN_BURNS_MIN_DURATION_SEC and n > 2:
        n -= 1
    while dur / n > KEN_BURNS_SPLIT_THRESHOLD_SEC:
        n += 1
    cap = max_reencoded_shots(dur)
    if n > cap:
        n = cap
        while dur / n > KEN_BURNS_SPLIT_THRESHOLD_SEC:
            n += 1

    base = round(dur / n, 3)
    durs = [base] * (n - 1)
    durs.append(round(dur - sum(durs), 3))
    start_idx = KEN_BURNS_PAN_CYCLE.index(pan0)
    segs: List[Tuple[float, int, str]] = []
    for i, seg_dur in enumerate(durs):
        pan = KEN_BURNS_PAN_CYCLE[(start_idx + i) % len(KEN_BURNS_PAN_CYCLE)]
        frames = max(1, int(round(float(seg_dur) * use_fps)))
        segs.append((float(seg_dur), frames, pan))
    return segs
