"""
tests/unit/test_rendering_engine.py - Unit tests for Shaders, CameraController and CosmicShaderRenderer.
"""
from pathlib import Path
import pytest

from src.narrative.engine import CosmicNarrativeEngine
from src.narrative.schema import NarrativeArchetype, VideoFormat
from src.rendering.camera_controller import CameraController
from src.rendering.renderer import CosmicShaderRenderer, resolve_chrome_path


def test_camera_controller_drift_and_trauma() -> None:
    cam = CameraController(decay_rate=1.2)
    s0 = cam.update(t=0.0)
    assert s0.fov == 60.0

    # Inject trauma
    cam.add_trauma(0.8)
    assert cam.trauma == 0.8

    s1 = cam.update(t=0.033, delta_sec=0.033)
    # Shake should increase FOV and position jitter
    assert s1.fov > 60.0
    assert cam.trauma < 0.8  # Trauma decayed


def test_build_runtime_html_embeds_all_shaders() -> None:
    engine = CosmicNarrativeEngine()
    script = engine.generate_script(
        archetype=NarrativeArchetype.HYDROACOUSTIC_TELEMETRY,
        video_format=VideoFormat.SHORT_VERTICAL,
        duration_sec=30.0,
    )

    renderer = CosmicShaderRenderer()
    html = renderer.build_runtime_html(script, width=1080, height=1920, fps=30)

    assert "RADAR_HYDROACOUSTIC" in html
    assert "MONOLITHS_RAYMARCHING" in html
    assert "GRAVITATIONAL_SINGULARITY" in html
    assert "POSTPROCESS" in html
    assert "crtDistortion" in html
    assert script.telemetry_header in html


def test_render_single_frame_executes() -> None:
    chrome_path = resolve_chrome_path()
    if not chrome_path:
        pytest.skip("No Chrome/Chromium binary found in environment")

    engine = CosmicNarrativeEngine()
    script = engine.generate_script(
        archetype=NarrativeArchetype.HYDROACOUSTIC_TELEMETRY,
        video_format=VideoFormat.SHORT_VERTICAL,
        duration_sec=30.0,
    )

    renderer = CosmicShaderRenderer(chrome_exec_path=chrome_path)
    frame_bytes = renderer.render_single_frame(
        script_contract=script,
        frame_idx=0,
        total_frames=30,
        width=360,
        height=640,
        fps=30,
    )

    assert len(frame_bytes) > 1000
    assert frame_bytes.startswith(b"\x89PNG")
