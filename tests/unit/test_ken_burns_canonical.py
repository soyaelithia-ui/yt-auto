"""Canonical Ken Burns params for still backgrounds (not loops)."""

from __future__ import annotations

from src.media.hybrid_engine import (
    KEN_BURNS_FPS,
    KEN_BURNS_MIN_DURATION_SEC,
    KEN_BURNS_ZOOM_END,
    KEN_BURNS_ZOOM_START,
    build_ken_burns_zoompan_filter,
    canonical_ken_burns_params,
)
from src.scene_manifest import CameraMotionConfig


def test_camera_motion_defaults_match_canonical_zoom():
    cam = CameraMotionConfig()
    assert cam.start_zoom == KEN_BURNS_ZOOM_START
    assert cam.end_zoom == KEN_BURNS_ZOOM_END


def test_canonical_ken_burns_acceptance_defaults():
    dur, fps, frames, z0, z1 = canonical_ken_burns_params(enforce_min_duration=True)
    assert dur >= KEN_BURNS_MIN_DURATION_SEC
    assert fps == KEN_BURNS_FPS
    assert frames == int(round(dur * fps))
    assert z0 == KEN_BURNS_ZOOM_START
    assert z1 == KEN_BURNS_ZOOM_END


def test_build_ken_burns_zoompan_filter_canonical_12s_30fps():
    dur, fps, frames, z0, z1 = canonical_ken_burns_params(
        duration_sec=12.0,
        fps=30,
        zoom_start=1.0,
        zoom_end=1.10,
        enforce_min_duration=True,
    )
    assert dur >= 12.0
    assert fps == 30
    filt = build_ken_burns_zoompan_filter(
        width=1920,
        height=1080,
        fps=fps,
        total_frames=frames,
        zoom_start=z0,
        zoom_end=z1,
        pan_direction="center_to_top",
    )
    assert filt.startswith("zoompan=")
    assert "fps=30" in filt
    assert f"d={frames}" in filt
    assert "1.000000" in filt
    assert "1.100000" in filt


def test_canonical_keeps_scene_duration_without_enforce():
    dur, fps, frames, z0, z1 = canonical_ken_burns_params(
        duration_sec=4.0, fps=30, enforce_min_duration=False
    )
    assert dur == 4.0
    assert frames == 120
    assert z0 == KEN_BURNS_ZOOM_START
    assert z1 == KEN_BURNS_ZOOM_END
