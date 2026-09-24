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
    resolve_hybrid_overlay_asset,
)
from src.scene_manifest import (
    CameraMotionConfig,
    HybridAIConfig,
    SceneConfig,
)


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
    bg_file = tmp_path / "bg.png"
    from PIL import Image as PILImage
    PILImage.new("RGB", (320, 180), (50, 50, 50)).save(bg_file)

    engine = HybridVideoEngine()
    sc = SceneConfig(
        scene_index=1,
        scene_id="sc_ffmpeg_default",
        start_sec=0.0,
        duration_sec=0.4,
        tension_level=2,
        engine_type="hybrid_cinematic_ai",
        hybrid_ai_config=HybridAIConfig(
            still_bg=str(bg_file),
            camera_motion=CameraMotionConfig(type="ken_burns_3d", pan_direction="left_to_right"),
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
    bg_file = tmp_path / "bg_crop.png"
    from PIL import Image as PILImage
    PILImage.new("RGB", (320, 180), (50, 50, 50)).save(bg_file)

    engine = HybridVideoEngine()
    sc = SceneConfig(
        scene_index=1,
        scene_id="sc_no_crop_loop",
        start_sec=0.0,
        duration_sec=0.5,
        tension_level=3,
        engine_type="hybrid_cinematic_ai",
        hybrid_ai_config=HybridAIConfig(
            still_bg=str(bg_file),
            camera_motion=CameraMotionConfig(pan_direction="center_to_top"),
        ),
    )
    out_mp4 = tmp_path / "hybrid_precompute.mp4"

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


def test_resolve_hybrid_overlay_asset_prefers_typed_png(tmp_path: Path, monkeypatch):
    from src.media.hybrid_engine import resolve_hybrid_overlay_asset

    overlays = tmp_path / "assets" / "overlays"
    overlays.mkdir(parents=True)
    typed = overlays / "particles_dust_motes.png"
    generic = overlays / "particles.png"
    rays = overlays / "god_rays.png"
    typed.write_bytes(b"x")
    generic.write_bytes(b"y")
    rays.write_bytes(b"z")
    monkeypatch.chdir(tmp_path)
    assert resolve_hybrid_overlay_asset("particles", "dust_motes").name == "particles_dust_motes.png"
    assert resolve_hybrid_overlay_asset("particles", "ember_sparks").name == "particles.png"
    assert resolve_hybrid_overlay_asset("god_rays").name == "god_rays.png"
    assert resolve_hybrid_overlay_asset("particles", "none").name == "particles.png"


def test_resolve_hybrid_overlay_asset_atmospheric_kinds(tmp_path: Path, monkeypatch):
    from src.media.hybrid_engine import (
        ATMOSPHERIC_OVERLAY_OPACITY,
        ATMOSPHERIC_OVERLAY_OPACITY_MAX,
        ATMOSPHERIC_OVERLAY_OPACITY_MIN,
        clamp_atmospheric_overlay_opacity,
        resolve_hybrid_overlay_asset,
    )

    overlays = tmp_path / "assets" / "overlays"
    overlays.mkdir(parents=True)
    (overlays / "film_grain.png").write_bytes(b"g")
    (overlays / "dark_vignette.png").write_bytes(b"v")
    (overlays / "tv_static.gif").write_bytes(b"s")
    (overlays / "tv_static.png").write_bytes(b"p")
    monkeypatch.chdir(tmp_path)
    assert resolve_hybrid_overlay_asset("film_grain").name == "film_grain.png"
    assert resolve_hybrid_overlay_asset("vignette").name == "dark_vignette.png"
    assert resolve_hybrid_overlay_asset("tv_static").name == "tv_static.png"
    op = clamp_atmospheric_overlay_opacity()
    assert ATMOSPHERIC_OVERLAY_OPACITY_MIN <= op <= ATMOSPHERIC_OVERLAY_OPACITY_MAX
    assert op == ATMOSPHERIC_OVERLAY_OPACITY


def _overlay_scene(scene_id: str = "sc_overlay", still_bg: Optional[str] = None) -> SceneConfig:
    return SceneConfig(
        scene_index=1,
        scene_id=scene_id,
        start_sec=0.0,
        duration_sec=0.4,
        tension_level=3,
        engine_type="hybrid_cinematic_ai",
        hybrid_ai_config=HybridAIConfig(
            still_bg=still_bg,
            camera_motion=CameraMotionConfig(pan_direction="left_to_right"),
        ),
    )


def test_default_path_reuses_asset_png_without_imagedraw(tmp_path: Path, monkeypatch):
    from PIL import Image as PILImage

    bg_file = tmp_path / "bg_overlay.png"
    PILImage.new("RGB", (320, 180), (50, 50, 50)).save(bg_file)

    overlays = tmp_path / "overlays"
    overlays.mkdir()
    part_png = overlays / "particles_dust_motes.png"
    god_png = overlays / "god_rays.png"
    PILImage.new("RGBA", (32, 18), (255, 255, 255, 40)).save(part_png)
    PILImage.new("RGBA", (32, 18), (200, 240, 255, 30)).save(god_png)

    def fake_resolve(kind, particle_type=None):
        if kind == "particles":
            return part_png
        if kind in ("god_rays", "god-rays", "rays"):
            return god_png
        return None

    monkeypatch.setattr("src.media.hybrid_engine.resolve_hybrid_overlay_asset", fake_resolve)

    engine = HybridVideoEngine()
    sc = _overlay_scene("sc_asset_png", still_bg=str(bg_file))
    out_mp4 = tmp_path / "hybrid_asset.mp4"
    seen = {"cmds": []}
    draw_calls = {"n": 0}

    from PIL import ImageDraw as PILImageDraw

    orig_draw = PILImageDraw.Draw

    def counting_draw(*a, **k):
        draw_calls["n"] += 1
        return orig_draw(*a, **k)

    def fake_run(cmd, **kwargs):
        seen["cmds"].append(list(cmd))
        out_mp4.write_bytes(b"\0" * 600)
        return MagicMock(returncode=0)

    with patch("src.media.hybrid_engine.ImageDraw.Draw", side_effect=counting_draw):
        with patch("src.media.hybrid_engine.run_ffmpeg", side_effect=fake_run):
            engine.render_scene_segment(
                scene=sc,
                width=320,
                height=180,
                fps=30,
                output_mp4=out_mp4,
                crf=28,
            )

    assert draw_calls["n"] == 0
    joined = " ".join(str(x) for x in seen["cmds"][0])
    assert str(part_png) in joined
    assert str(god_png) in joined
    assert "zoompan=" in joined
    assert "rawvideo" not in seen["cmds"][0]


def test_resolve_hybrid_overlay_skips_gif(tmp_path: Path, monkeypatch):
    from src.media.hybrid_engine import resolve_hybrid_overlay_asset

    overlays = tmp_path / "assets" / "overlays"
    overlays.mkdir(parents=True)
    (overlays / "tv_static.gif").write_bytes(b"s")
    monkeypatch.chdir(tmp_path)
    assert resolve_hybrid_overlay_asset("tv_static") is None


def test_motion_loop_stream_copy_skips_zoompan(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("FORCE_PILLOW_HYBRID_FRAMES", raising=False)
    loop = tmp_path / "catalog_loop.mp4"
    loop.write_bytes(b"\0" * 800)
    engine = HybridVideoEngine()
    sc = SceneConfig(
        scene_index=1,
        scene_id="sc_loop_copy",
        start_sec=0.0,
        duration_sec=24.0,
        tension_level=2,
        engine_type="hybrid_cinematic_ai",
        image_path=str(loop),
        hybrid_ai_config=HybridAIConfig(
            background_image_path=str(loop),
            camera_motion=CameraMotionConfig(pan_direction="center_to_top"),
        ),
    )
    out_mp4 = tmp_path / "loop_planes.mp4"
    seen: dict[str, list] = {"cmds": []}

    def fake_run(cmd, **kwargs):
        seen["cmds"].append(list(cmd))
        target = Path(cmd[-1])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"\0" * 600)
        return MagicMock(returncode=0)

    with patch("src.media.hybrid_engine.loop_matches_target_geometry", return_value=True):
        with patch("src.media.hybrid_engine.run_ffmpeg", side_effect=fake_run):
            engine.render_scene_segment(
                scene=sc,
                width=320,
                height=180,
                fps=30,
                output_mp4=out_mp4,
                crf=28,
            )

    assert seen["cmds"]
    joined = " ".join(str(x) for x in seen["cmds"][0])
    assert "zoompan=" not in joined
    assert "-c:v" in seen["cmds"][0] and "copy" in seen["cmds"][0]
    assert not any("libx264" in c for c in seen["cmds"])


def test_direct_overlays_module_imports():
    from src.media.overlays import (
        ATMOSPHERIC_OVERLAY_OPACITY,
        ATMOSPHERIC_OVERLAY_OPACITY_MAX,
        ATMOSPHERIC_OVERLAY_OPACITY_MIN,
        clamp_atmospheric_overlay_opacity,
        resolve_hybrid_overlay_asset,
        is_motion_loop_path,
        resolve_hybrid_motion_loop,
        _hybrid_overlay_search_roots,
    )
    assert ATMOSPHERIC_OVERLAY_OPACITY_MIN == 0.15
    assert ATMOSPHERIC_OVERLAY_OPACITY_MAX == 0.35
    assert clamp_atmospheric_overlay_opacity(0.01) == 0.15
    assert clamp_atmospheric_overlay_opacity(0.99) == 0.35
    roots = _hybrid_overlay_search_roots("particles")
    assert any("assets/overlays" in str(r) for r in roots)

