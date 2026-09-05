"""
tests/integration/test_unified_encoder.py - Comprehensive Integration Tests for Unified FFmpeg Encoder.
Covers F11 (Unified Atomic FFmpeg Encoder Pipeline).
"""

from __future__ import annotations

import os
import struct
import subprocess
import wave
from pathlib import Path
import numpy as np
import pytest

from src.media.unified_encoder import UnifiedEncoder


def create_synthetic_wav(
    filepath: Path,
    duration_sec: float = 1.0,
    sample_rate: int = 44100,
    channels: int = 2,
    freq: float = 440.0,
) -> Path:
    """Generate a clean synthetic sine wave WAV file for testing."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    num_samples = int(duration_sec * sample_rate)
    with wave.open(str(filepath), "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        frames = bytearray()
        for i in range(num_samples):
            t = float(i) / sample_rate
            value = int(16000.0 * np.sin(2.0 * np.pi * freq * t))
            sample_bytes = struct.pack("<h", max(-32767, min(32767, value)))
            for _ in range(channels):
                frames.extend(sample_bytes)
        wav_file.writeframes(frames)
    return filepath


# ==============================================================================
# F11: UnifiedEncoder Command Generation & Audio Filtergraph Tests
# ==============================================================================

def test_encoder_command_construction_complete_graph(tmp_path: Path):
    """Verify UnifiedEncoder builds a complete single-pass -filter_complex command with all audio/video filters."""
    out_mp4 = tmp_path / "master.mp4"
    voice_wav = create_synthetic_wav(tmp_path / "voice.wav", duration_sec=1.0, freq=440.0)
    drone_wav = create_synthetic_wav(tmp_path / "drone.wav", duration_sec=1.0, freq=110.0)
    sfx1_wav = create_synthetic_wav(tmp_path / "sfx1.wav", duration_sec=0.5, freq=880.0)
    sfx2_wav = create_synthetic_wav(tmp_path / "sfx2.wav", duration_sec=0.5, freq=1200.0)

    ass_file = tmp_path / "subs.ass"
    ass_file.write_text("[Script Info]\nTitle: Test\n", encoding="utf-8")
    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)

    sfx_cues = [
        (sfx1_wav, 0.25, 0.8),
        (sfx2_wav, 0.75, 0.6),
    ]

    encoder = UnifiedEncoder(
        output_mp4=out_mp4,
        width=1080,
        height=1920,
        fps=30,
        crf=18,
        preset="fast",
        voice_wav=voice_wav,
        drone_wav=drone_wav,
        sfx_wavs=sfx_cues,
        ass_subtitle_path=ass_file,
        fonts_dir=fonts_dir,
    )

    cmd = encoder.build_ffmpeg_command()
    cmd_str = " ".join(cmd)

    # Video checks
    assert "-f rawvideo" in cmd_str
    assert "-pix_fmt rgba" in cmd_str
    assert "1080x1920" in cmd_str
    assert "-filter_complex" in cmd
    assert "ass=" in cmd_str
    assert "fontsdir=" in cmd_str

    # Audio graph checks
    assert "sidechaincompress" in cmd_str
    assert "adelay=250|250" in cmd_str
    assert "adelay=750|750" in cmd_str
    assert "volume=0.80" in cmd_str
    assert "volume=0.60" in cmd_str
    assert "amix=inputs=4" in cmd_str
    assert "loudnorm=I=-14:TP=-1.5:LRA=11" in cmd_str

    # Container / output checks
    assert "-c:a aac" in cmd_str
    assert "-c:v libx264" in cmd_str
    assert "-pix_fmt yuv420p" in cmd_str
    assert "-movflags +faststart" in cmd_str
    assert str(out_mp4) in cmd


def test_encoder_ass_filter_is_unquoted_for_ffmpeg_61(tmp_path: Path):
    """UnifiedEncoder must emit unquoted ass=filename= (FFmpeg 6.1 libass)."""
    ass_file = tmp_path / "subs.ass"
    ass_file.write_text("[Script Info]\n", encoding="utf-8")
    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir()
    encoder = UnifiedEncoder(
        output_mp4=tmp_path / "out.mp4",
        ass_subtitle_path=ass_file,
        fonts_dir=fonts_dir,
    )
    cmd = encoder.build_ffmpeg_command()
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "ass=filename=" in fc
    assert "ass='" not in fc
    assert "ass=filename='" not in fc
    assert "fontsdir='" not in fc
    assert f"filename={ass_file}" in fc
    assert f"fontsdir={fonts_dir}" in fc


def test_encoder_audio_variations(tmp_path: Path):
    """Verify filtergraph builds properly across various audio input combinations."""
    out_mp4 = tmp_path / "test.mp4"
    voice_wav = create_synthetic_wav(tmp_path / "v.wav")
    drone_wav = create_synthetic_wav(tmp_path / "d.wav")
    sfx_wav = create_synthetic_wav(tmp_path / "s.wav")

    # 1. Voice only
    enc_voice = UnifiedEncoder(output_mp4=out_mp4, voice_wav=voice_wav)
    cmd_v = " ".join(enc_voice.build_ffmpeg_command())
    assert "loudnorm" in cmd_v
    assert "sidechaincompress" not in cmd_v
    assert "-map [a]" in cmd_v

    # 2. Drone only
    enc_drone = UnifiedEncoder(output_mp4=out_mp4, drone_wav=drone_wav)
    cmd_d = " ".join(enc_drone.build_ffmpeg_command())
    assert "loudnorm" in cmd_d
    assert "sidechaincompress" not in cmd_d
    assert "-map [a]" in cmd_d

    # 3. Voice + SFX
    enc_vs = UnifiedEncoder(output_mp4=out_mp4, voice_wav=voice_wav, sfx_wavs=[(sfx_wav, 0.1, 1.0)])
    cmd_vs = " ".join(enc_vs.build_ffmpeg_command())
    assert "amix=inputs=2" in cmd_vs
    assert "loudnorm" in cmd_vs

    # 4. Silent / Video only
    enc_silent = UnifiedEncoder(output_mp4=out_mp4)
    cmd_silent = " ".join(enc_silent.build_ffmpeg_command())
    assert "null[v]" in cmd_silent
    assert "-map [a]" not in cmd_silent


# ==============================================================================
# F11: End-to-End Transcode, Streaming, and Lifecycle Tests
# ==============================================================================

def test_encoder_real_transcode_with_frame_streaming(tmp_path: Path):
    """Verify live FFmpeg transcode consumes raw RGBA frames and produces valid MP4 container."""
    out_mp4 = tmp_path / "rendered.mp4"
    voice_wav = create_synthetic_wav(tmp_path / "v.wav", duration_sec=0.5)

    width = 128
    height = 128
    fps = 30
    num_frames = 15

    with UnifiedEncoder(
        output_mp4=out_mp4,
        width=width,
        height=height,
        fps=fps,
        voice_wav=voice_wav,
    ) as encoder:
        for i in range(num_frames):
            # Generate solid color RGBA frames
            frame = np.full((height, width, 4), fill_value=(i * 15, 100, 200, 255), dtype=np.uint8)
            encoder.write_frame(frame)

    assert out_mp4.exists()
    assert out_mp4.stat().st_size > 500  # Valid MP4 container


def test_encoder_async_stderr_drain_captures_logs(tmp_path: Path):
    """Verify asynchronous stderr thread drains logs into ring buffer without blocking."""
    out_mp4 = tmp_path / "drain_test.mp4"
    with UnifiedEncoder(output_mp4=out_mp4, width=64, height=64, fps=30) as encoder:
        for _ in range(10):
            frame_bytes = bytes(64 * 64 * 4)
            encoder.write_frame(frame_bytes)

    assert out_mp4.exists()
    assert encoder._stderr_thread is not None
    assert not encoder._stderr_thread.is_alive()


def test_encoder_frame_size_mismatch_raises_value_error(tmp_path: Path):
    """Verify writing wrong frame byte count raises ValueError."""
    out_mp4 = tmp_path / "mismatch.mp4"
    encoder = UnifiedEncoder(output_mp4=out_mp4, width=100, height=100, fps=30)
    with pytest.raises(ValueError, match="Frame size mismatch"):
        encoder.write_frame(b"SHORT_DATA")


def test_encoder_context_manager_exception_kills_process(tmp_path: Path):
    """Verify exception inside context manager safely terminates FFmpeg without orphaned processes."""
    out_mp4 = tmp_path / "aborted.mp4"
    try:
        with UnifiedEncoder(output_mp4=out_mp4, width=64, height=64, fps=30) as encoder:
            encoder.write_frame(bytes(64 * 64 * 4))
            raise RuntimeError("Simulated pipeline worker crash")
    except RuntimeError:
        pass

    # Subprocess should be killed cleanly
    if encoder.proc:
        assert encoder.proc.poll() is not None
