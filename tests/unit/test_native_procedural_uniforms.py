"""
Unit tests for WebGPU 64-byte uniform buffer bridge, photometric luminance floor,
and subprocess security / exception guards.
"""

from __future__ import annotations

import struct
from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from src.media.native_procedural import (
    NativeProceduralEngine,
    pack_uniform_bytes,
)


def _make_engine(**kwargs):
    """Construct engine or skip cleanly when no WebGPU/Lavapipe adapter exists."""
    try:
        return NativeProceduralEngine(**kwargs)
    except RuntimeError as exc:
        if "No WebGPU adapter available" in str(exc):
            pytest.skip(f"WebGPU/Lavapipe adapter unavailable: {exc}")
        raise


@pytest.fixture
def engine():
    eng = _make_engine()
    yield eng
    eng.close()


def test_uniform_buffer_64_byte_packing():
    """Verify art-direction params pack into exactly 64 bytes (16 floats) without a GPU device."""
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
    blob = pack_uniform_bytes(
        width=64,
        height=64,
        time_sec=1.0,
        duration_sec=5.0,
        seed=42,
        tension=4,
        archetype_id="maritime_lighthouse",
        params=params,
    )
    assert isinstance(blob, (bytes, bytearray))
    assert len(blob) == 64
    fields = struct.unpack("16f", blob)
    assert fields[0] == 64.0
    assert fields[1] == 64.0
    assert fields[2] == 1.0
    assert fields[3] == 5.0
    assert fields[4] == 42.0
    assert fields[5] == 4.0
    assert fields[6] == pytest.approx(1.1)
    assert fields[7] == pytest.approx(1.25)
    assert fields[8:11] == pytest.approx((0.0, 0.8, 1.0))
    assert fields[11] == pytest.approx(1.5)
    assert fields[12] == pytest.approx(1.8)
    assert fields[13] == pytest.approx(0.45)
    assert fields[14] == pytest.approx(0.25)
    assert fields[15] == pytest.approx(0.75)


def test_uniform_buffer_default_accent_without_gpu():
    """Default accent colors must apply when params omit accent_color."""
    blob = pack_uniform_bytes(
        width=32,
        height=32,
        time_sec=0.0,
        duration_sec=1.0,
        seed=1,
        tension=1,
        archetype_id="dark_forest",
        params=None,
    )
    fields = struct.unpack("16f", blob)
    assert fields[8:11] == pytest.approx((0.1, 0.9, 0.4))


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
