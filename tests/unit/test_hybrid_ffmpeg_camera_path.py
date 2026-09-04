"""
Prove hybrid_engine default path uses FFmpeg Ken Burns (zoompan) instead of the
Pillow rawvideo per-frame crop/resize loop. Legacy path remains opt-in via
FORCE_PILLOW_HYBRID_FRAMES.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.media.hybrid_engine import (
    HybridVideoEngine,
    build_ken_burns_zoompan_filter,
    force_pillow_hybrid_frames_enabled,
)
from src.scene_manifest import (
    CameraMotionConfig,
    HybridAIConfig,
    LightingConfig,
    ParticleConfig,
    SceneConfig,
)


def test_force_pillow_hybrid_frames_disabled_by_default(monkeypatch):
    monkeypatch.delenv("FORCE_PILLOW_HYBRID_FRAMES", raising=False)
    assert force_pillow_hybrid_frames_enabled() is False
    assert force_pillow_hybrid_frames_enabled({}) is False
    assert force_pillow_hybrid_frames_enabled({"force_pillow_hybrid_frames": False}) is False


def test_force_pillow_hybrid_frames_opt_in_env_and_kwarg(monkeypatch):
    monkeypatch.setenv("FORCE_PILLOW_HYBRID_FRAMES", "1")
    assert force_pillow_hybrid_frames_enabled() is True
    monkeypatch.delenv("FORCE_PILLOW_HYBRID_FRAMES", raising=False)
    assert force_pillow_hybrid_frames_enabled({"force_pillow_hybrid_frames": True}) is True


@pytest.mark.parametrize(
    "pan_dir",
    ["center_to_top", "center_to_bottom", "left_to_right", "right_to_left", "static"],
)
def test_build_ken_burns_zoompan_filter_contains_zoompan(pan_dir):
    vf = build_ken_burns_zoompan_filter(
        width=1280,
        height=720,
        fps=30,
        total_frames=90,
        zoom_start=1.0,
        zoom_end=1.08,
        pan_direction=pan_dir,
    )
    assert "zoompan=" in vf
    assert "s=1280x720" in vf
    assert "fps=30" in vf
    assert "d=90" in vf


def test_default_hybrid_path_uses_ffmpeg_zoompan_not_rawvideo(tmp_path: Path, monkeypatch):
    """Default HybridAIConfig must not open a Pillow rawvideo stdin pipe."""
    monkeypatch.delenv("FORCE_PILLOW_HYBRID_FRAMES", raising=False)
    monkeypatch.delenv("FORCE_PILLOW_SUBTITLES", raising=False)

    engine = HybridVideoEngine()
    sc = SceneConfig(
        scene_index=1,
        scene_id="sc_ffmpeg_default",
        start_sec=0.0,
        duration_sec=0.4,
        tension_level=2,
        engine_type="hybrid_cinematic_ai",
        hybrid_ai_config=HybridAIConfig(
            camera_motion=CameraMotionConfig(type="ken_burns_3d", pan_direction="left_to_right"),
            # Defaults: particles=none, no volumetric rays, no flicker.
        ),
    )
    out_mp4 = tmp_path / "hybrid_ffmpeg.mp4"
    seen = {"cmds": []}

    real_popen = __import__("subprocess").Popen

    def tracking_popen(cmd, *a, **k):
        seen["cmds"].append(list(cmd))
        return real_popen(cmd, *a, **k)

    with patch("src.media.hybrid_engine.subprocess.Popen", side_effect=tracking_popen):
        with patch("src.media.hybrid_engine.run_ffmpeg") as run_ff:

            def fake_run(cmd, **kwargs):
                seen["cmds"].append(list(cmd))
                # Produce a tiny valid mp4 so callers see an output file.
                import subprocess as sp

                sp.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-f",
                        "lavfi",
                        "-i",
                        "color=c=black:s=320x180:d=0.2",
                        "-c:v",
                        "libx264",
                        "-pix_fmt",
                        "yuv420p",
                        "-t",
                        "0.2",
                        str(out_mp4),
                    ],
                    check=True,
                    capture_output=True,
                )
                return MagicMock(returncode=0)

            run_ff.side_effect = fake_run
            engine.render_scene_segment(
                scene=sc,
                width=320,
                height=180,
                fps=30,
                output_mp4=out_mp4,
                crf=28,
            )

    assert seen["cmds"], "expected FFmpeg invocation via run_ffmpeg"
    joined = " ".join(str(x) for x in seen["cmds"][0])
    assert "zoompan=" in joined
    assert "rawvideo" not in seen["cmds"][0]
    # Default path must not spawn the legacy stdin rawvideo Popen encoder.
    assert not any(
        ("rawvideo" in c) for c in seen["cmds"]
    ), f"rawvideo must not appear on default path: {seen['cmds']}"


def test_default_path_skips_per_frame_pillow_crop(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("FORCE_PILLOW_HYBRID_FRAMES", raising=False)
    engine = HybridVideoEngine()
    sc = SceneConfig(
        scene_index=1,
        scene_id="sc_no_crop_loop",
        start_sec=0.0,
        duration_sec=0.5,
        tension_level=3,
        engine_type="hybrid_cinematic_ai",
        hybrid_ai_config=HybridAIConfig(
            camera_motion=CameraMotionConfig(pan_direction="center_to_top"),
            lighting=LightingConfig(volumetric_rays=True, intensity=0.3),
            particles=ParticleConfig(type="dust_motes", density=10),
        ),
    )
    out_mp4 = tmp_path / "hybrid_precompute.mp4"
    from PIL import Image as PILImage

    crop_calls = {"n": 0}
    orig_crop = PILImage.Image.crop

    def counting_crop(self, *a, **k):
        crop_calls["n"] += 1
        return orig_crop(self, *a, **k)

    with patch.object(PILImage.Image, "crop", counting_crop):
        engine.render_scene_segment(
            scene=sc,
            width=320,
            height=180,
            fps=30,
            output_mp4=out_mp4,
            crf=28,
        )

    total_frames = int(round(0.5 * 30))
    assert out_mp4.exists() and out_mp4.stat().st_size > 500
    # Legacy path crops once per frame; FFmpeg path must not.
    assert crop_calls["n"] < total_frames, (
        f"expected no per-frame Pillow crop loop, got {crop_calls['n']} crops "
        f"for {total_frames} frames"
    )


def test_pillow_fallback_still_available(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FORCE_PILLOW_HYBRID_FRAMES", "1")
    engine = HybridVideoEngine()
    sc = SceneConfig(
        scene_index=1,
        scene_id="sc_pillow_fallback",
        start_sec=0.0,
        duration_sec=0.4,
        tension_level=2,
        engine_type="hybrid_cinematic_ai",
        hybrid_ai_config=HybridAIConfig(
            camera_motion=CameraMotionConfig(pan_direction="right_to_left"),
        ),
    )
    out_mp4 = tmp_path / "hybrid_pillow.mp4"
    engine.render_scene_segment(
        scene=sc,
        width=320,
        height=180,
        fps=30,
        output_mp4=out_mp4,
        crf=28,
    )
    assert out_mp4.exists() and out_mp4.stat().st_size > 500
