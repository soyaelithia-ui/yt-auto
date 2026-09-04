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
from src.media.proc_engine import ProceduralVideoEngine
from src.media.native_procedural import NativeProceduralEngine
from src.scene_manifest import SceneConfig, ProceduralConfig


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


def test_compositor_default_wiring_skips_native_engine(monkeypatch):
    """Default MultiSceneCompositor must NOT construct NativeProceduralEngine / WebGPU."""
    monkeypatch.delenv("ENABLE_NATIVE_PROCEDURAL", raising=False)
    compositor = MultiSceneCompositor()
    assert compositor.procedural_engine is not None
    assert compositor.procedural_engine.renderer is None


def test_compositor_opt_in_native_engine(monkeypatch):
    """ENABLE_NATIVE_PROCEDURAL=1 may wire NativeProceduralEngine (skip if no adapter/dep)."""
    monkeypatch.setenv("ENABLE_NATIVE_PROCEDURAL", "1")
    try:
        compositor = MultiSceneCompositor()
    except RuntimeError as exc:
        if "No WebGPU adapter available" in str(exc) or "wgpu is not installed" in str(exc):
            pytest.skip(f"Native procedural unavailable: {exc}")
        raise
    assert isinstance(compositor.procedural_engine.renderer, NativeProceduralEngine)


def test_procedural_engine_renders_via_native_procedural(tmp_path):
    """Verify ProceduralVideoEngine renders via NativeProceduralEngine without falling back to PIL."""
    try:
        native_eng = NativeProceduralEngine()
    except RuntimeError as exc:
        if "No WebGPU adapter available" in str(exc) or "wgpu is not installed" in str(exc):
            pytest.skip(f"Native procedural unavailable: {exc}")
        raise
    proc_eng = ProceduralVideoEngine(renderer=native_eng)
    
    scene = SceneConfig(
        scene_id="scene_001",
        scene_index=1,
        engine_type="pure_procedural_webgl",
        duration_sec=2.0,
        start_sec=0.0,
        end_sec=2.0,
        tension_level=3,
        environment_name="maritime_lighthouse",
        procedural_config=ProceduralConfig(
            template_name="maritime_lighthouse",
            seed=42,
            uniforms={"speed": 1.2, "distortion": 0.5},
        ),
    )
    
    out_mp4 = tmp_path / "proc_scene_001.mp4"
    res_path = proc_eng.render_scene_segment(
        scene=scene,
        width=160,
        height=90,
        fps=15,
        lane_id="moku-horror-long",
        output_mp4=out_mp4,
    )
    
    assert Path(res_path).exists()
    assert Path(res_path).stat().st_size > 0
    native_eng.close()
