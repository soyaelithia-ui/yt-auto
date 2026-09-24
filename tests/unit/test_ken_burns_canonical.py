"""Canonical Ken Burns params for still backgrounds (not loops)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

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
    from PIL import Image
    dummy_bg = tmp_path / "test_bg.jpg"
    Image.new("RGB", (320, 180), color=(20, 30, 40)).save(dummy_bg)
    sc = SceneConfig(
        scene_index=1,
        scene_id="sc_kb_45s",
        start_sec=0.0,
        duration_sec=45.0,
        tension_level=2,
        engine_type="hybrid_cinematic_ai",
        image_path=str(dummy_bg),
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


def test_direct_ken_burns_module_imports():
    from src.media.ken_burns import (
        KEN_BURNS_FPS,
        KEN_BURNS_MIN_DURATION_SEC,
        KEN_BURNS_SEGMENT_MAX_SEC,
        KEN_BURNS_SPLIT_THRESHOLD_SEC,
        KEN_BURNS_ZOOM_END,
        KEN_BURNS_ZOOM_START,
        MAX_REENCODE_SHOTS_PER_MIN,
        build_ken_burns_zoompan_filter,
        canonical_ken_burns_params,
        max_reencoded_shots,
        plan_ken_burns_still_segments,
    )
    assert KEN_BURNS_FPS == 30
    assert KEN_BURNS_ZOOM_START == 1.00
    assert KEN_BURNS_ZOOM_END == 1.10
    filt = build_ken_burns_zoompan_filter(
        width=1920,
        height=1080,
        fps=30,
        total_frames=60,
        zoom_start=1.0,
        zoom_end=1.1,
        pan_direction="center_to_top",
    )
    assert "zoompan=" in filt


def test_ken_burns_zoompan_smoothstep_expression():
    """Asserts generated zoompan contains smoothstep expression (on/{denom})*(on/{denom})*(3-2*(on/{denom})) and valid coordinate formulas."""
    from src.media.ken_burns import build_ken_burns_zoompan_filter
    total_frames = 120
    denom = 119
    expected_e = f"(on/{denom})*(on/{denom})*(3-2*(on/{denom}))"
    filt = build_ken_burns_zoompan_filter(
        width=1080,
        height=1920,
        fps=30,
        total_frames=total_frames,
        zoom_start=1.0,
        zoom_end=1.1,
        pan_direction="center_to_top",
    )
    assert expected_e in filt
    assert "zoompan=z=" in filt
    assert "d=120" in filt
    assert "s=1080x1920" in filt


def test_ken_burns_zoompan_pan_cycle_directions():
    """Asserts correct x and y formulas for all directions in KEN_BURNS_PAN_CYCLE."""
    from src.media.ken_burns import KEN_BURNS_PAN_CYCLE, build_ken_burns_zoompan_filter
    total_frames = 60
    denom = 59
    e = f"(on/{denom})*(on/{denom})*(3-2*(on/{denom}))"

    for direction in KEN_BURNS_PAN_CYCLE:
        filt = build_ken_burns_zoompan_filter(
            width=1080,
            height=1920,
            fps=30,
            total_frames=total_frames,
            zoom_start=1.0,
            zoom_end=1.1,
            pan_direction=direction,
        )
        if direction == "left_to_right":
            assert f"x='(iw-iw/zoom)*{e}'" in filt
            assert "y='(ih-ih/zoom)/2'" in filt
        elif direction == "right_to_left":
            assert f"x='(iw-iw/zoom)*(1-{e})'" in filt
            assert "y='(ih-ih/zoom)/2'" in filt
        elif direction == "center_to_top":
            assert "x='(iw-iw/zoom)/2'" in filt
            assert f"y='(ih-ih/zoom)*(1-0.5*{e})'" in filt
        elif direction == "center_to_bottom":
            assert "x='(iw-iw/zoom)/2'" in filt
            assert f"y='(ih-ih/zoom)*(0.5*{e})'" in filt


def test_ken_burns_zoompan_degenerate_frames():
    """Asserts total_frames <= 1 clamps denominator to 1 to prevent division by zero."""
    from src.media.ken_burns import build_ken_burns_zoompan_filter
    for tf in [0, 1, -5]:
        filt = build_ken_burns_zoompan_filter(
            width=1080,
            height=1920,
            fps=30,
            total_frames=tf,
            zoom_start=1.0,
            zoom_end=1.1,
            pan_direction="center_to_top",
        )
        assert "(on/1)*(on/1)*(3-2*(on/1))" in filt


def test_ken_burns_still_segments_split_threshold():
    """Asserts still image of exactly 20.0s splits into 2 segments of 10.0s each;
    still image > 15.0s splits into sub-segments between 10.0s and 15.0s with alternating pan directions;
    still image of 9.0s remains 1 unsplit segment."""
    from src.media.ken_burns import plan_ken_burns_still_segments

    # 9.0s remains unsplit
    segs_9 = plan_ken_burns_still_segments(9.0, fps=30)
    assert len(segs_9) == 1
    assert segs_9[0][0] == pytest.approx(9.0)

    # 20.0s splits into 2 segments of 10.0s each
    segs_20 = plan_ken_burns_still_segments(20.0, fps=30)
    assert len(segs_20) == 2
    assert segs_20[0][0] == pytest.approx(10.0)
    assert segs_20[1][0] == pytest.approx(10.0)
    assert segs_20[0][2] != segs_20[1][2]

    # > 15.0s (e.g. 18.0s) splits into sub-segments between 10.0s and 15.0s with alternating directions
    segs_18 = plan_ken_burns_still_segments(18.0, fps=30)
    assert len(segs_18) >= 2
    for dur, _frames, _pan in segs_18:
        assert 8.0 <= dur <= 15.0
    pans_18 = [p for _d, _f, p in segs_18]
    assert len(set(pans_18)) >= 2


