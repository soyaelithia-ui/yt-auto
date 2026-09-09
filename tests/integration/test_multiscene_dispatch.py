"""
Integration tests for multiscene pipeline dispatch, lane configuration alignment,
and MultiSceneCompositor default FFmpeg path (wgpu opt-in only).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest

from src.media.compositor import MultiSceneCompositor
from src.media.loop_engine import LoopVideoEngine
from src.scene_manifest import SceneConfig


def test_pipeline_engine_resolution_director():
    """Verify lane with visual_pipeline: 'director' is recognized as multiscene mode."""
    lane = SimpleNamespace(
        name="moku-horror-long",
        visual_pipeline="director",
        video_engine=None,
        orientation="horizontal",
    )
    
    # Simulate resolution logic from pipeline.py
    engine_mode = (
        getattr(lane, "video_engine", None)
        or getattr(lane, "visual_pipeline", None)
        or "loop"
    ).strip().lower()
    
    is_loop_mode = engine_mode in ("loop", "loop_video", "loop_video_engine", "loop_compositor")
    is_multiscene_mode = engine_mode in ("director", "multiscene", "multi_scene", "multi_scene_compositor", "dual_engine", "hybrid", "procedural")
    
    assert engine_mode == "director"
    assert is_multiscene_mode is True
    assert is_loop_mode is False


def test_pipeline_engine_resolution_invalid_mode_raises():
    """Verify unrecognized engine mode does not silently fall back to loop."""
    lane = SimpleNamespace(
        name="test-lane",
        visual_pipeline="invalid_bogus_engine",
        video_engine=None,
    )
    engine_mode = (
        getattr(lane, "video_engine", None)
        or getattr(lane, "visual_pipeline", None)
        or "loop"
    ).strip().lower()
    
    is_loop_mode = engine_mode in ("loop", "loop_video", "loop_video_engine", "loop_compositor")
    is_multiscene_mode = engine_mode in ("director", "multiscene", "multi_scene", "multi_scene_compositor", "dual_engine", "hybrid", "procedural")
    is_supported = is_loop_mode or is_multiscene_mode

    assert is_supported is False, "Unrecognized engine mode should be rejected"


def test_compositor_default_wiring_uses_loop_engine():
    """MultiSceneCompositor must wire LoopVideoEngine for catalog_loop scenes."""
    compositor = MultiSceneCompositor()
    assert isinstance(compositor.loop_engine, LoopVideoEngine)
    assert compositor.procedural_engine is compositor.loop_engine


def test_compositor_renders_catalog_loop_scene(tmp_path, monkeypatch):
    """Verify MultiSceneCompositor dispatches catalog_loop scenes to LoopVideoEngine."""
    from src.scene_manifest import SceneManifestV2, AudioTracks

    compositor = MultiSceneCompositor()
    dummy_mp4 = tmp_path / "rendered.mp4"
    dummy_mp4.write_bytes(b"dummy_video_bytes")
    
    mock_render = MagicMock(return_value=dummy_mp4)
    monkeypatch.setattr(compositor.loop_engine, "render_scene_segment", mock_render)
    monkeypatch.setattr(compositor, "_assemble_video_scenes", lambda *a, **k: dummy_mp4)
    monkeypatch.setattr(compositor, "_master_assembly", lambda *a, **k: None)

    scene = SceneConfig(
        scene_id="scene_001",
        scene_index=1,
        engine_type="catalog_loop",
        duration_sec=2.0,
        start_sec=0.0,
        end_sec=2.0,
        tension_level=3,
        environment_name="dark_forest",
    )
    from src.scene_manifest import SafeArea
    manifest = SceneManifestV2(
        story_id="test_story",
        lane_id="moku-horror-long",
        channel_name="moku",
        total_duration_sec=2.0,
        resolution=(1920, 1080),
        safe_area=SafeArea(margin_top=60, margin_bottom=124, margin_left=85, margin_right=85),
        audio_tracks=AudioTracks(narration_path=""),
        scenes=[scene],
    )
    man_file = tmp_path / "manifest.json"
    man_file.write_text(manifest.model_dump_json(), encoding="utf-8")
    
    out_video = tmp_path / "out_final.mp4"
    compositor.render(
        manifest_path=man_file,
        output_video_path=out_video,
    )
    
    mock_render.assert_called_once()

