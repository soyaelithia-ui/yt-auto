"""
Unit tests for fast audio duration probing in lib/tts.py.

Validates Milestone 1 (F01 / R5):
- Instant WAV duration reading via stdlib wave.open (zero subprocesses).
- Instant MP3 duration reading via pure-Python binary header parser
  (ID3v2 tags, MPEG frame sync 0xFFE/0xFFF, Xing/Info VBR header, CBR bitrate).
- Fallback to ffprobe subprocess when header parsing fails or for non-standard containers.
- Resilient error handling for zero-byte, missing, or corrupt audio files.
- Sub-5ms execution latency benchmark on local audio files (< 1ms target).
"""

from __future__ import annotations

import os
import struct
import subprocess
import time
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import lib.tts
from lib.tts import get_audio_duration, get_wav_duration


# ==============================================================================
# Helper Functions for Audio Synthesis
# ==============================================================================

def _generate_wav(path: Path, duration_sec: float = 1.0, framerate: int = 44100, channels: int = 1) -> Path:
    """Generate a valid PCM WAV audio file with specified duration and framerate."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)  # 16-bit
        w.setframerate(framerate)
        nframes = int(duration_sec * framerate)
        # 16-bit PCM silence: 2 bytes per sample per channel
        w.writeframes(b"\x00" * (nframes * channels * 2))
    return path


def _generate_synthetic_cbr_mp3(path: Path, bitrate_kbps: int = 128, sample_rate: int = 44100, num_frames: int = 50) -> Path:
    """Generate a synthetic CBR MP3 file with MPEG-1 Layer III frame headers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # MPEG-1 Layer III frame header:
    # 0xFF: sync byte 1
    # 0xFB: sync byte 2 (11111011 = MPEG-1, Layer III, no protection)
    # 0x90: bitrate index 9 (128 kbps), sample rate index 0 (44100 Hz), no padding
    # 0x00: stereo channel mode
    frame_size = int(144 * (bitrate_kbps * 1000) / sample_rate)  # 417 bytes for 128k/44.1k
    frame_header = b"\xFF\xFB\x90\x00"
    payload = frame_header + b"\x55" * (frame_size - 4)
    with open(path, "wb") as f:
        for _ in range(num_frames):
            f.write(payload)
    return path


def _generate_synthetic_vbr_mp3(path: Path, num_frames: int = 100, sample_rate: int = 44100) -> Path:
    """Generate a synthetic VBR MP3 file containing a Xing header with frame count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_size = 417
    # MPEG-1 Layer III stereo header
    frame_header = b"\xFF\xFB\x90\x00"
    # Offset to Xing for MPEG-1 stereo is 36 bytes from sync
    pad_len = 36 - len(frame_header)
    padding = b"\x00" * pad_len
    # Xing tag + flags (0x01 = frames field present) + frames count (big-endian 4 bytes)
    xing_tag = b"Xing" + struct.pack(">I", 1) + struct.pack(">I", num_frames)
    first_frame = frame_header + padding + xing_tag
    first_frame += b"\xAA" * (frame_size - len(first_frame))

    dummy_frame = frame_header + b"\xBB" * (frame_size - len(frame_header))
    with open(path, "wb") as f:
        f.write(first_frame)
        for _ in range(num_frames - 1):
            f.write(dummy_frame)
    return path


def _generate_synthetic_id3v2_mp3(path: Path, bitrate_kbps: int = 128, sample_rate: int = 44100, num_frames: int = 30) -> Path:
    """Generate an MP3 file prepended with an ID3v2 header."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # ID3v2.3 header: "ID3", version 3.0, flags 0, synchsafe size 20 bytes
    id3_header = b"ID3\x03\x00\x00\x00\x00\x00\x14"
    id3_data = b"TIT2\x00\x00\x00\x0a\x00\x00\x00Test Track"
    # Pad to 20 bytes
    id3_data = id3_data[:20].ljust(20, b"\x00")

    frame_size = int(144 * (bitrate_kbps * 1000) / sample_rate)
    frame_header = b"\xFF\xFB\x90\x00"
    frame_payload = frame_header + b"\x77" * (frame_size - 4)

    with open(path, "wb") as f:
        f.write(id3_header)
        f.write(id3_data)
        for _ in range(num_frames):
            f.write(frame_payload)
    return path


# ==============================================================================
# Test Suite: Fast Audio Duration Probing
# ==============================================================================

class TestAudioDurationFast:
    """Comprehensive test suite for fast audio duration readers without ffprobe."""

    def test_wav_duration_fast_no_subproc(self, tmp_path):
        """WAV duration is read via stdlib wave.open with zero ffprobe subprocess invocations."""
        durations_to_test = [0.25, 1.0, 2.5, 5.0]
        framerates = [8000, 16000, 44100, 48000]

        for i, (expected_dur, rate) in enumerate(zip(durations_to_test, framerates)):
            wav_file = tmp_path / f"test_{i}_{rate}hz.wav"
            _generate_wav(wav_file, duration_sec=expected_dur, framerate=rate)

            with patch.object(lib.tts, "_run_subproc") as mock_subproc, \
                 patch("subprocess.run") as mock_run, \
                 patch("subprocess.Popen") as mock_popen:

                actual_dur = get_audio_duration(wav_file)
                wav_dur = get_wav_duration(wav_file)

                # Subprocess must NEVER be called for WAV files
                mock_subproc.assert_not_called()
                mock_run.assert_not_called()
                mock_popen.assert_not_called()

                assert abs(actual_dur - expected_dur) < 1e-4, (
                    f"Expected WAV duration {expected_dur}s, got {actual_dur}s"
                )
                assert abs(wav_dur - expected_dur) < 1e-4

    def test_wav_duration_stereo_channels(self, tmp_path):
        """Multi-channel stereo WAV files calculate duration correctly without subprocess."""
        wav_file = tmp_path / "stereo_test.wav"
        expected_dur = 3.5
        _generate_wav(wav_file, duration_sec=expected_dur, framerate=48000, channels=2)

        with patch.object(lib.tts, "_run_subproc") as mock_subproc:
            actual_dur = get_audio_duration(wav_file)
            mock_subproc.assert_not_called()
            assert abs(actual_dur - expected_dur) < 1e-4

    def test_mp3_duration_horror_ambient_asset_no_subproc(self):
        """Physical test asset assets/music/horror_ambient.mp3 is parsed with binary parser and 0 subprocesses."""
        asset_path = Path("assets/music/horror_ambient.mp3")
        if not asset_path.exists():
            pytest.skip("Test asset assets/music/horror_ambient.mp3 not found")

        with patch.object(lib.tts, "_run_subproc") as mock_subproc, \
             patch("subprocess.run") as mock_run, \
             patch("subprocess.Popen") as mock_popen:

            dur = get_audio_duration(asset_path)

            mock_subproc.assert_not_called()
            mock_run.assert_not_called()
            mock_popen.assert_not_called()

            # horror_ambient.mp3 is known to be ~30.12s
            assert 29.5 < dur < 31.0, f"Unexpected duration {dur} for horror_ambient.mp3"

    def test_mp3_duration_synthetic_cbr_no_subproc(self, tmp_path):
        """Synthetic CBR MP3 file is parsed via bitrate and file size with zero subprocess calls."""
        cbr_file = tmp_path / "synthetic_cbr.mp3"
        bitrate_kbps = 128
        sample_rate = 44100
        num_frames = 60
        _generate_synthetic_cbr_mp3(cbr_file, bitrate_kbps=bitrate_kbps, sample_rate=sample_rate, num_frames=num_frames)

        with patch.object(lib.tts, "_run_subproc") as mock_subproc:
            dur = get_audio_duration(cbr_file)
            mock_subproc.assert_not_called()

            # Each MPEG-1 Layer III frame is 1152 samples: num_frames * 1152 / 44100 ~= 1.566s
            expected = (num_frames * 1152) / sample_rate
            assert abs(dur - expected) < 0.1, f"Expected approx {expected:.2f}s, got {dur:.2f}s"

    def test_mp3_duration_synthetic_vbr_xing_no_subproc(self, tmp_path):
        """Synthetic VBR MP3 with Xing header is parsed with zero subprocess calls."""
        vbr_file = tmp_path / "synthetic_vbr.mp3"
        num_frames = 100
        sample_rate = 44100
        _generate_synthetic_vbr_mp3(vbr_file, num_frames=num_frames, sample_rate=sample_rate)

        with patch.object(lib.tts, "_run_subproc") as mock_subproc:
            dur = get_audio_duration(vbr_file)
            mock_subproc.assert_not_called()

            # Xing frames * 1152 / sample_rate = 100 * 1152 / 44100 = 2.6122s
            expected_dur = round(num_frames * 1152.0 / sample_rate, 4)
            assert abs(dur - expected_dur) < 0.05, f"Expected Xing duration {expected_dur}s, got {dur}s"

    def test_mp3_duration_synthetic_with_id3v2_tag(self, tmp_path):
        """MP3 file with ID3v2 header skips tag and parses frame sync without ffprobe."""
        id3_file = tmp_path / "tagged.mp3"
        _generate_synthetic_id3v2_mp3(id3_file, bitrate_kbps=128, sample_rate=44100, num_frames=40)

        with patch.object(lib.tts, "_run_subproc") as mock_subproc:
            dur = get_audio_duration(id3_file)
            mock_subproc.assert_not_called()
            assert dur > 0.5, f"Expected duration > 0.5s for tagged MP3, got {dur}"

    def test_fallback_to_ffprobe_on_nonstandard_container(self, tmp_path):
        """Non-standard audio container (e.g. OGG/FLAC/AAC) falls back to ffprobe subprocess."""
        ogg_file = tmp_path / "sample.ogg"
        ogg_file.write_bytes(b"OggS\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00" + b"\x00" * 100)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "14.250000\n"

        with patch.object(lib.tts, "_run_subproc", return_value=mock_result) as mock_subproc:
            dur = get_audio_duration(ogg_file)

            # Verifies fallback to ffprobe was executed
            mock_subproc.assert_called_once()
            called_args = mock_subproc.call_args[0][0]
            assert "ffprobe" in called_args
            assert str(ogg_file) in called_args
            assert dur == 14.25

    def test_fallback_to_ffprobe_on_corrupted_mp3_header(self, tmp_path):
        """Corrupted MP3 frame sync / invalid bitrate index falls back to ffprobe."""
        corrupt_mp3 = tmp_path / "corrupt_sync.mp3"
        # 0xFF followed by 0xFE has reserved/invalid layer index
        corrupt_mp3.write_bytes(b"\xFF\xFE\xF0\x00" + b"\x00" * 500)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "6.789\n"

        with patch.object(lib.tts, "_run_subproc", return_value=mock_result) as mock_subproc:
            dur = get_audio_duration(corrupt_mp3)

            mock_subproc.assert_called_once()
            assert dur == 6.789

    def test_error_handling_zero_byte_file(self, tmp_path):
        """Zero-byte file returns 0.0 without unhandled exception."""
        empty_file = tmp_path / "empty.wav"
        empty_file.write_bytes(b"")

        assert get_audio_duration(empty_file) == 0.0
        assert get_wav_duration(empty_file) == 0.0

    def test_error_handling_nonexistent_file(self, tmp_path):
        """Non-existent file path returns 0.0 without raising."""
        nonexistent = tmp_path / "missing_file_never_created.wav"
        assert get_audio_duration(nonexistent) == 0.0
        assert get_wav_duration(nonexistent) == 0.0

    def test_error_handling_corrupt_payload_ffprobe_failure(self, tmp_path):
        """Arbitrary binary garbage returns 0.0 gracefully when ffprobe also fails."""
        garbage = tmp_path / "garbage.bin"
        garbage.write_bytes(os.urandom(256))

        # ffprobe returns non-zero error code
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch.object(lib.tts, "_run_subproc", return_value=mock_result):
            assert get_audio_duration(garbage) == 0.0

    def test_error_handling_subprocess_exception_returns_zero(self, tmp_path):
        """SubprocessError during ffprobe fallback is caught and returns 0.0."""
        unrecognized = tmp_path / "unrecognized.bin"
        unrecognized.write_bytes(b"DATA_WITHOUT_RECOGNIZED_HEADER")

        with patch.object(lib.tts, "_run_subproc", side_effect=subprocess.SubprocessError("ffprobe timeout")):
            dur = get_audio_duration(unrecognized)
            assert dur == 0.0

    def test_benchmark_latency_under_5ms(self, tmp_path):
        """get_audio_duration executes in < 5 ms (and typically < 1 ms) on local WAV and MP3 files."""
        wav_file = tmp_path / "bench.wav"
        _generate_wav(wav_file, duration_sec=2.0)

        cbr_file = tmp_path / "bench.mp3"
        _generate_synthetic_cbr_mp3(cbr_file, num_frames=50)

        # Warm up
        get_audio_duration(wav_file)
        get_audio_duration(cbr_file)

        # Benchmark WAV (50 iterations)
        wav_latencies = []
        for _ in range(50):
            t0 = time.perf_counter()
            d = get_audio_duration(wav_file)
            t1 = time.perf_counter()
            wav_latencies.append(t1 - t0)
            assert d > 0

        # Benchmark MP3 (50 iterations)
        mp3_latencies = []
        for _ in range(50):
            t0 = time.perf_counter()
            d = get_audio_duration(cbr_file)
            t1 = time.perf_counter()
            mp3_latencies.append(t1 - t0)
            assert d > 0

        max_wav_ms = max(wav_latencies) * 1000.0
        avg_wav_ms = (sum(wav_latencies) / len(wav_latencies)) * 1000.0
        max_mp3_ms = max(mp3_latencies) * 1000.0
        avg_mp3_ms = (sum(mp3_latencies) / len(mp3_latencies)) * 1000.0

        # Enforce SLA: individual calls < 5ms, average < 1ms
        assert max_wav_ms < 5.0, f"WAV duration max latency {max_wav_ms:.3f}ms exceeded 5ms SLA"
        assert avg_wav_ms < 1.0, f"WAV duration average latency {avg_wav_ms:.3f}ms exceeded 1ms SLA"
        assert max_mp3_ms < 5.0, f"MP3 duration max latency {max_mp3_ms:.3f}ms exceeded 5ms SLA"
        assert avg_mp3_ms < 1.0, f"MP3 duration average latency {avg_mp3_ms:.3f}ms exceeded 1ms SLA"
