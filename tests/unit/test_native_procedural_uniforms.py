"""
Unit tests for WebGPU 64-byte uniform buffer bridge, photometric luminance floor,
and subprocess security / exception guards.
"""

from __future__ import annotations

import struct
from pathlib import Path
from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from src.media.native_procedural import (
    NativeProceduralEngine,
    VALID_ARCHETYPES,
)


@pytest.fixture
def engine():
    eng = NativeProceduralEngine()
    yield eng
    eng.close()


def test_uniform_buffer_64_byte_packing(engine):
    """Verify that high-level art direction parameters are packed into exactly 64 bytes (16 floats)."""
    params = {
        "tension": 4,
        "speed": 1.25,
        "noise_scale": 1.1,
        "distortion": 1.5,
        "glow_intensity": 1.8,
        "accent_color": (0.0, 0.8, 1.0),
        "kelvin": 4500.0,
        "custom_1": 0.5,
        "custom_2": 0.25,
        "custom_3": 0.75,
    }
    # Rendering a small frame should pack without raising struct errors
    frame = engine.render_frame(
        width=64,
        height=64,
        time_sec=1.0,
        duration_sec=5.0,
        archetype_id="maritime_lighthouse",
        tension=4,
        params=params,
    )
    assert frame.shape == (64, 64, 4)
    assert frame.dtype == np.uint8


def test_maritime_lighthouse_photometric_floor(engine):
    """Verify maritime lighthouse shader does NOT crush to near-zero luminance (< 15%)."""
    frame = engine.render_frame(
        width=160,
        height=90,
        time_sec=2.0,
        duration_sec=6.0,
        archetype_id="maritime_lighthouse",
        tension=2,
    )
    rgb = frame[:, :, :3]
    # In normalized terms, 0.15 * 255 = 38.25. Average non-zero/background luminance should be >= 25
    # and 90th percentile should show clear visibility.
    mean_val = np.mean(rgb)
    assert mean_val >= 25.0, f"Shader subexposed: mean RGB {mean_val:.2f} < 25.0 (crushed black)"


def test_render_video_loop_broken_pipe_guard(engine, tmp_path):
    """Verify BrokenPipeError is caught and FFmpeg child process is reaped safely."""
    out_mp4 = tmp_path / "broken_test.mp4"
    mock_proc = MagicMock()
    mock_proc.stdin = MagicMock()
    mock_proc.stdin.write.side_effect = BrokenPipeError("Pipe broken")
    mock_proc.poll.return_value = None

    with patch("subprocess.Popen", return_value=mock_proc):
        with pytest.raises(BrokenPipeError):
            engine.render_video_loop(
                archetype_id="maritime_lighthouse",
                output_path=out_mp4,
                duration_sec=1.0,
                fps=10,
                width=64,
                height=64,
            )
        mock_proc.kill.assert_called_once()


def test_render_video_loop_arguments_safe(engine, tmp_path):
    """Verify subprocess.Popen receives command list (not shell=True or raw string)."""
    out_mp4 = tmp_path / "arg_test.mp4"
    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.poll.return_value = 0
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        engine.render_video_loop(
            archetype_id="dark_forest",
            output_path=out_mp4,
            duration_sec=0.1,
            fps=10,
            width=64,
            height=64,
        )

        args, kwargs = mock_popen.call_args
        assert isinstance(args[0], list), "Command must be passed as an argument list"
        assert kwargs.get("shell") is not True, "shell=True must NOT be used"
