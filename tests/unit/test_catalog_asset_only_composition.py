"""Tests enforcing catalog asset-only composition and fail-closed semantics."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.media.interface import CatalogAssetNotFoundError
from src.media.loop_engine import LoopVideoEngine
from src.media.hybrid_engine import HybridVideoEngine, HybridAIConfig
from src.media.compositor import MultiSceneCompositor
from src.scene_manifest import SceneConfig, CameraMotionConfig


@pytest.fixture
def dummy_scene():
    return SceneConfig(
        scene_index=1,
        scene_id="scene_001",
        engine_type="catalog_loop",
        start_sec=0.0,
        duration_sec=3.0,
        tension_level=2,
        environment_name="nonexistent_alien_dimension_xyz",
    )


def test_loop_engine_missing_asset_raises_catalog_asset_not_found(tmp_path, dummy_scene):
    """LoopVideoEngine must fail closed with CatalogAssetNotFoundError if asset is missing."""
    engine = LoopVideoEngine()
    out_path = tmp_path / "out.mp4"

    with pytest.raises(CatalogAssetNotFoundError) as exc_info:
        engine.render_scene_segment(
            dummy_scene,
            1080,
            1920,
            30,
            "unknown_lane_no_match",
            out_path,
        )
    assert "Catalog loop not found on disk" in str(exc_info.value)


def test_hybrid_engine_missing_still_raises_catalog_asset_not_found(tmp_path):
    """HybridVideoEngine must fail closed with CatalogAssetNotFoundError if still_bg does not exist."""
    engine = HybridVideoEngine()
    scene = SceneConfig(
        scene_index=1,
        scene_id="scene_hybrid_001",
        engine_type="hybrid_cinematic_ai",
        start_sec=0.0,
        duration_sec=2.5,
        tension_level=2,
        hybrid_ai_config=HybridAIConfig(
            still_bg=str(tmp_path / "missing_background.png"),
            camera_motion=CameraMotionConfig(motion_type="pan_right"),
        ),
    )
    out_path = tmp_path / "out_hybrid.mp4"

    with pytest.raises(CatalogAssetNotFoundError) as exc_info:
        engine.render_scene_segment(
            scene,
            1080,
            1920,
            30,
            out_path,
            lane_id="moku",
        )
    assert "Background image not found on disk" in str(exc_info.value)


def test_loop_engine_valid_asset_no_generative_math_filters(tmp_path):
    """Verify that when a valid asset is provided, LoopVideoEngine does not generate procedural lavfi filters."""
    engine = LoopVideoEngine()
    dummy_mp4 = tmp_path / "test_loop.mp4"
    dummy_mp4.write_bytes(b"\x00" * 1024)

    scene = SceneConfig(
        scene_index=1,
        scene_id="scene_valid_001",
        engine_type="catalog_loop",
        start_sec=0.0,
        duration_sec=4.0,
        tension_level=2,
        asset_path=str(dummy_mp4),
        environment_name="cosmic_horror",
    )
    out_path = tmp_path / "out_valid.mp4"

    mock_probe = MagicMock()
    mock_probe.primary_video = MagicMock(duration=5.0, width=1080, height=1920)
    mock_probe.duration = 5.0

    with patch.object(engine, "resolve_loop_video", return_value=dummy_mp4), \
         patch("src.media.loop_engine.probe_media", return_value=mock_probe), \
         patch("src.media.loop_engine.run_ffmpeg") as mock_run_ffmpeg:
        mock_run_ffmpeg.return_value = MagicMock(returncode=0, stdout="", stderr="")

        engine.render_scene_segment(
            scene,
            1080,
            1920,
            30,
            "moku",
            out_path,
        )

        assert mock_run_ffmpeg.called
        cmd_args = mock_run_ffmpeg.call_args[0][0]
        cmd_str = " ".join(str(c) for c in cmd_args)
        assert "gradients=" not in cmd_str
        assert "mandelbrot" not in cmd_str
        assert "cellauto" not in cmd_str
        assert "ffmpeg" in cmd_str


def test_compositor_fail_closed_on_missing_scene_asset(tmp_path):
    """MultiSceneCompositor must fail closed when any scene lacks its backing asset."""
    compositor = MultiSceneCompositor()
    manifest_file = tmp_path / "scene_manifest.json"
    dummy_audio = tmp_path / "audio.mp3"
    dummy_audio.write_bytes(b"\x00" * 100)

    manifest_data = {
        "manifest_version": "2.0",
        "story_id": "test_fail_closed",
        "lane_id": "moku",
        "channel_name": "moku",
        "resolution": [1080, 1920],
        "safe_area": {"top": 100, "bottom": 100, "left": 50, "right": 50},
        "fps": 30,
        "total_duration_sec": 3.0,
        "audio_tracks": {
            "narration_path": str(dummy_audio),
        },
        "scenes": [
            {
                "scene_index": 1,
                "scene_id": "sc_01",
                "engine_type": "catalog_loop",
                "start_sec": 0.0,
                "duration_sec": 3.0,
                "tension_level": 2,
                "environment_name": "totally_absent_category_xyz",
            }
        ],
    }
    manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")
    out_video = tmp_path / "final.mp4"

    with patch.object(compositor.loop_engine, "resolve_loop_video", return_value=None):
        with pytest.raises(CatalogAssetNotFoundError):
            compositor.render(manifest_path=manifest_file, output_video_path=out_video)
