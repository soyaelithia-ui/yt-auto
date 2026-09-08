"""Canonical Ken Burns params for still backgrounds (not loops)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.media.hybrid_engine import (
    KEN_BURNS_FPS,
    KEN_BURNS_MIN_DURATION_SEC,
    KEN_BURNS_SEGMENT_MAX_SEC,
    KEN_BURNS_SPLIT_THRESHOLD_SEC,
    KEN_BURNS_ZOOM_END,
    KEN_BURNS_ZOOM_START,
    MAX_REENCODE_SHOTS_PER_MIN,
    HybridVideoEngine,
    build_ken_burns_zoompan_filter,
    canonical_ken_burns_params,
    max_reencoded_shots,
    plan_ken_burns_still_segments,
)
from src.scene_manifest import CameraMotionConfig, HybridAIConfig, SceneConfig


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


def test_45s_still_scene_splits_into_ken_burns_segments():
    segs = plan_ken_burns_still_segments(45.0, fps=30, pan_direction="center_to_top")
    assert len(segs) >= 3
    pans = []
    for dur, frames, pan in segs:
        assert dur <= KEN_BURNS_SEGMENT_MAX_SEC + 1e-6
        assert dur <= KEN_BURNS_SPLIT_THRESHOLD_SEC
        assert frames == int(round(dur * 30))
        assert frames <= int(round(KEN_BURNS_SEGMENT_MAX_SEC * 30))
        pans.append(pan)
    assert abs(sum(s[0] for s in segs) - 45.0) < 1e-3
    assert len(set(pans)) >= 2


def test_reencode_cap_per_minute_bounds_still_segments():
    assert max_reencoded_shots(45.0) == MAX_REENCODE_SHOTS_PER_MIN
    assert max_reencoded_shots(60.0) == MAX_REENCODE_SHOTS_PER_MIN
    assert max_reencoded_shots(120.0) == MAX_REENCODE_SHOTS_PER_MIN * 2
    segs = plan_ken_burns_still_segments(180.0, fps=30)
    assert len(segs) <= max_reencoded_shots(180.0)
    assert all(d <= KEN_BURNS_SPLIT_THRESHOLD_SEC for d, _f, _p in segs)


def test_45s_still_render_emits_multiple_zoompan_segments(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("FORCE_PILLOW_HYBRID_FRAMES", raising=False)
    engine = HybridVideoEngine()
    sc = SceneConfig(
        scene_index=1,
        scene_id="sc_kb_45s",
        start_sec=0.0,
        duration_sec=45.0,
        tension_level=2,
        engine_type="hybrid_cinematic_ai",
        hybrid_ai_config=HybridAIConfig(
            camera_motion=CameraMotionConfig(pan_direction="center_to_top"),
        ),
    )
    out_mp4 = tmp_path / "kb_45s.mp4"
    seen: dict[str, list] = {"cmds": []}

    def fake_run(cmd, **kwargs):
        seen["cmds"].append(list(cmd))
        target = Path(cmd[-1])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"\0" * 600)
        return MagicMock(returncode=0)

    with patch("src.media.hybrid_engine.run_ffmpeg", side_effect=fake_run):
        engine.render_scene_segment(
            scene=sc,
            width=320,
            height=180,
            fps=30,
            output_mp4=out_mp4,
            crf=28,
        )

    zoompan_cmds = [c for c in seen["cmds"] if any("zoompan=" in str(x) for x in c)]
    assert len(zoompan_cmds) == 1
    joined = " ".join(str(x) for x in zoompan_cmds[0])
    assert joined.count("zoompan=") >= 3
    assert "concat=n=" in joined
    libx264_cmds = [c for c in seen["cmds"] if "libx264" in c]
    assert len(libx264_cmds) == 1
