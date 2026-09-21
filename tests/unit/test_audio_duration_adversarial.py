"""
Adversarial stress-test and empirical verification suite for lib/tts.py audio duration reader.

Empirically validates Requirement R5:
1. Subprocess Zero-Execution Probe: Mocks/spies on subprocess.run, subprocess.Popen,
   subprocess.call, and lib.tts._run_subproc to assert that get_audio_duration and
   get_wav_duration NEVER fork ffprobe on standard WAV and MP3 files.
2. Latency Benchmark: Measures 500 successive calls to get_audio_duration across WAV
   and MP3 files, asserting average latency is strictly < 1.0 ms.
3. Edge Case Adversarial Battery: Corrupted WAV headers, truncated MP3 streams, zero-byte
   files, non-existent paths, pure ID3 tags without audio, and non-audio files (text/binaries).
4. Fallback Verification: Resilient recovery to 0.0 on unparseable garbage or ffprobe failures.
5. Empirical Bug Reproductions (XFAIL): Uncaught RuntimeError in WAV parser, ID3v2 > 128KB
   duration inflation, and sub-frame truncation false-positives.
"""

from __future__ import annotations

import os
import random
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
# Audio Generators for Controlled Test Inputs
# ==============================================================================

def create_wav_file(
    path: Path,
    duration_sec: float = 1.0,
    framerate: int = 44100,
    channels: int = 1,
    sampwidth: int = 2,
) -> Path:
    """Create a synthetically valid WAV file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sampwidth)
        w.setframerate(framerate)
        nframes = int(duration_sec * framerate)
        w.writeframes(b"\x00" * (nframes * channels * sampwidth))
    return path


def create_mp3_cbr(
    path: Path,
    bitrate_kbps: int = 128,
    sample_rate: int = 44100,
    num_frames: int = 60,
    version: int = 1,
    layer: int = 3,
) -> Path:
    """Create a synthetically valid CBR MP3 file."""
    path.parent.mkdir(parents=True, exist_ok=True)

    # Sync word and header construction
    v_bits = 3 if version == 1 else (2 if version == 2 else 0)
    l_bits = 1 if layer == 3 else (2 if layer == 2 else 3)
    byte2 = 0xE0 | (v_bits << 3) | (l_bits << 1) | 1

    v1_bitrates_l3 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]
    b_idx = v1_bitrates_l3.index(bitrate_kbps) if bitrate_kbps in v1_bitrates_l3 else 9
    sr_table = [44100, 48000, 32000]
    sr_idx = sr_table.index(sample_rate) if sample_rate in sr_table else 0
    byte3 = (b_idx << 4) | (sr_idx << 2)
    byte4 = 0x00  # Stereo, no padding

    header = bytes([0xFF, byte2, byte3, byte4])
    frame_size = int(144 * (bitrate_kbps * 1000) / sample_rate)
    payload = header + b"\x55" * max(0, frame_size - 4)

    with open(path, "wb") as f:
        for _ in range(num_frames):
            f.write(payload)
    return path


def create_mp3_vbr_xing(
    path: Path,
    num_frames: int = 80,
    sample_rate: int = 44100,
    bitrate_kbps: int = 128,
) -> Path:
    """Create a synthetic VBR MP3 with Xing header."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_size = int(144 * (bitrate_kbps * 1000) / sample_rate)
    header = b"\xFF\xFB\x90\x00"  # MPEG-1 Layer 3, 128k, 44.1k, stereo
    padding = b"\x00" * (36 - len(header))
    xing_tag = b"Xing" + struct.pack(">I", 1) + struct.pack(">I", num_frames)
    first_frame = header + padding + xing_tag
    first_frame += b"\xAA" * (frame_size - len(first_frame))

    dummy_frame = header + b"\xBB" * (frame_size - len(header))
    with open(path, "wb") as f:
        f.write(first_frame)
        for _ in range(num_frames - 1):
            f.write(dummy_frame)
    return path


def create_mp3_with_id3v2(
    path: Path,
    num_frames: int = 40,
    tag_size: int = 64,
    has_footer: bool = False,
) -> Path:
    """Create an MP3 file with an ID3v2 tag (and optional 10-byte footer)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = 0x10 if has_footer else 0x00
    s0 = (tag_size >> 21) & 0x7F
    s1 = (tag_size >> 14) & 0x7F
    s2 = (tag_size >> 7) & 0x7F
    s3 = tag_size & 0x7F
    id3_header = bytes([ord("I"), ord("D"), ord("3"), 3, 0, flags, s0, s1, s2, s3])
    id3_payload = b"\x00" * tag_size
    id3_footer = bytes([ord("3"), ord("D"), ord("I"), 3, 0, flags, s0, s1, s2, s3]) if has_footer else b""

    frame_size = 417
    frame_header = b"\xFF\xFB\x90\x00"
    frame_payload = frame_header + b"\xCC" * (frame_size - 4)

    with open(path, "wb") as f:
        f.write(id3_header)
        f.write(id3_payload)
        if id3_footer:
            f.write(id3_footer)
        for _ in range(num_frames):
            f.write(frame_payload)
    return path


# ==============================================================================
# 1. Subprocess Zero-Execution Probe
# ==============================================================================

class TestSubprocessZeroExecutionProbe:
    """Spies on all subprocess spawn entry points to prove zero ffprobe calls for standard audio."""

    @pytest.fixture(autouse=True)
    def spy_subprocesses(self, monkeypatch: pytest.MonkeyPatch):
        self.spawn_calls: list[list] = []

        def spy_run_subproc(*args, **kwargs):
            self.spawn_calls.append(["_run_subproc", args, kwargs])
            return MagicMock(returncode=0, stdout="0.0\n")

        def spy_run(*args, **kwargs):
            self.spawn_calls.append(["subprocess.run", args, kwargs])
            return MagicMock(returncode=0, stdout=b"0.0\n")

        def spy_popen(*args, **kwargs):
            self.spawn_calls.append(["subprocess.Popen", args, kwargs])
            proc = MagicMock()
            proc.communicate.return_value = (b"0.0\n", b"")
            proc.returncode = 0
            return proc

        monkeypatch.setattr(lib.tts, "_run_subproc", spy_run_subproc)
        monkeypatch.setattr(subprocess, "run", spy_run)
        monkeypatch.setattr(subprocess, "Popen", spy_popen)

    def test_zero_subproc_on_standard_wav_varieties(self, tmp_path: Path):
        """Standard WAV variations (sample rates, channels, bit depths) NEVER invoke subprocess."""
        configurations = [
            (0.5, 8000, 1, 1),
            (1.0, 16000, 1, 2),
            (2.5, 44100, 2, 2),
            (3.0, 48000, 2, 2),
            (0.8, 96000, 2, 2),
        ]

        for i, (dur, rate, ch, width) in enumerate(configurations):
            wav_file = tmp_path / f"probe_wav_{i}.wav"
            create_wav_file(wav_file, duration_sec=dur, framerate=rate, channels=ch, sampwidth=width)

            actual_dur = get_audio_duration(wav_file)
            wav_dur = get_wav_duration(wav_file)

            assert abs(actual_dur - dur) < 1e-4, f"Failed duration precision for {wav_file}"
            assert abs(wav_dur - dur) < 1e-4
            assert len(self.spawn_calls) == 0, (
                f"Subprocess was spawned for standard WAV! Calls: {self.spawn_calls}"
            )

    def test_zero_subproc_on_standard_mp3_cbr_varieties(self, tmp_path: Path):
        """Standard MP3 CBR files (32k to 320k) NEVER invoke subprocess."""
        bitrates = [32, 64, 128, 192, 256, 320]
        for kbps in bitrates:
            mp3_file = tmp_path / f"probe_cbr_{kbps}.mp3"
            create_mp3_cbr(mp3_file, bitrate_kbps=kbps, num_frames=50)

            dur = get_audio_duration(mp3_file)
            assert dur > 0.5, f"MP3 {kbps}k failed to return positive duration: {dur}"
            assert len(self.spawn_calls) == 0, (
                f"Subprocess was spawned for {kbps}k CBR MP3! Calls: {self.spawn_calls}"
            )

    def test_zero_subproc_on_mp3_vbr_xing(self, tmp_path: Path):
        """VBR MP3 with Xing header NEVER invokes subprocess."""
        vbr_file = tmp_path / "probe_vbr.mp3"
        create_mp3_vbr_xing(vbr_file, num_frames=120)

        dur = get_audio_duration(vbr_file)
        expected = round(120 * 1152.0 / 44100.0, 4)
        assert abs(dur - expected) < 0.05
        assert len(self.spawn_calls) == 0, (
            f"Subprocess was spawned for Xing VBR MP3! Calls: {self.spawn_calls}"
        )

    def test_zero_subproc_on_mp3_with_id3v2_tag_and_footer(self, tmp_path: Path):
        """MP3 with ID3v2 tags (with and without footer) NEVER invokes subprocess."""
        for has_foot in [False, True]:
            tagged_file = tmp_path / f"tagged_footer_{has_foot}.mp3"
            create_mp3_with_id3v2(tagged_file, num_frames=50, tag_size=128, has_footer=has_foot)

            dur = get_audio_duration(tagged_file)
            assert dur > 0.5
            assert len(self.spawn_calls) == 0, (
                f"Subprocess was spawned for ID3v2 (footer={has_foot}) MP3! Calls: {self.spawn_calls}"
            )

    def test_zero_subproc_on_real_asset_horror_ambient(self):
        """Physical production asset assets/music/horror_ambient.mp3 NEVER invokes subprocess."""
        asset = Path("assets/music/horror_ambient.mp3")
        if not asset.exists():
            pytest.skip("Asset assets/music/horror_ambient.mp3 not found")

        dur = get_audio_duration(asset)
        assert 29.5 < dur < 31.0, f"Unexpected duration {dur} for horror_ambient.mp3"
        assert len(self.spawn_calls) == 0, (
            f"Subprocess was spawned for real production asset! Calls: {self.spawn_calls}"
        )


# ==============================================================================
# 2. Latency Benchmark: 500 Successive Calls < 1.0 ms SLA
# ==============================================================================

class TestAudioDurationLatencyBenchmark:
    """Rigorous 500-call latency benchmark asserting strict sub-millisecond execution."""

    def test_500_successive_calls_wav(self, tmp_path: Path):
        """Measure 500 successive calls on WAV file, asserting average latency < 1.0 ms."""
        wav_file = tmp_path / "bench_500.wav"
        create_wav_file(wav_file, duration_sec=5.0, framerate=44100)

        # Warm up
        for _ in range(10):
            get_audio_duration(wav_file)

        latencies_ms: list[float] = []
        for _ in range(500):
            t0 = time.perf_counter()
            d = get_audio_duration(wav_file)
            t1 = time.perf_counter()
            latencies_ms.append((t1 - t0) * 1000.0)
            assert d > 0

        avg_latency = sum(latencies_ms) / len(latencies_ms)
        p95_latency = sorted(latencies_ms)[int(0.95 * len(latencies_ms))]
        p99_latency = sorted(latencies_ms)[int(0.99 * len(latencies_ms))]
        max_latency = max(latencies_ms)

        print(
            f"\n[BENCHMARK] WAV 500 calls: avg={avg_latency:.4f}ms, "
            f"p95={p95_latency:.4f}ms, p99={p99_latency:.4f}ms, max={max_latency:.4f}ms"
        )
        assert avg_latency < 1.0, f"WAV average latency {avg_latency:.4f}ms exceeded 1.0ms SLA"

    def test_500_successive_calls_mp3_cbr(self, tmp_path: Path):
        """Measure 500 successive calls on MP3 CBR file, asserting average latency < 1.0 ms."""
        mp3_file = tmp_path / "bench_cbr_500.mp3"
        create_mp3_cbr(mp3_file, bitrate_kbps=128, num_frames=80)

        for _ in range(10):
            get_audio_duration(mp3_file)

        latencies_ms: list[float] = []
        for _ in range(500):
            t0 = time.perf_counter()
            d = get_audio_duration(mp3_file)
            t1 = time.perf_counter()
            latencies_ms.append((t1 - t0) * 1000.0)
            assert d > 0

        avg_latency = sum(latencies_ms) / len(latencies_ms)
        p95_latency = sorted(latencies_ms)[int(0.95 * len(latencies_ms))]
        max_latency = max(latencies_ms)

        print(
            f"\n[BENCHMARK] MP3 CBR 500 calls: avg={avg_latency:.4f}ms, "
            f"p95={p95_latency:.4f}ms, max={max_latency:.4f}ms"
        )
        assert avg_latency < 1.0, f"MP3 CBR average latency {avg_latency:.4f}ms exceeded 1.0ms SLA"

    def test_500_successive_calls_mp3_vbr_xing(self, tmp_path: Path):
        """Measure 500 successive calls on MP3 VBR Xing file, asserting average latency < 1.0 ms."""
        vbr_file = tmp_path / "bench_vbr_500.mp3"
        create_mp3_vbr_xing(vbr_file, num_frames=100)

        for _ in range(10):
            get_audio_duration(vbr_file)

        latencies_ms: list[float] = []
        for _ in range(500):
            t0 = time.perf_counter()
            d = get_audio_duration(vbr_file)
            t1 = time.perf_counter()
            latencies_ms.append((t1 - t0) * 1000.0)
            assert d > 0

        avg_latency = sum(latencies_ms) / len(latencies_ms)
        p95_latency = sorted(latencies_ms)[int(0.95 * len(latencies_ms))]
        max_latency = max(latencies_ms)

        print(
            f"\n[BENCHMARK] MP3 VBR 500 calls: avg={avg_latency:.4f}ms, "
            f"p95={p95_latency:.4f}ms, max={max_latency:.4f}ms"
        )
        assert avg_latency < 1.0, f"MP3 VBR average latency {avg_latency:.4f}ms exceeded 1.0ms SLA"

    def test_500_interleaved_calls(self, tmp_path: Path):
        """Measure 500 interleaved/randomized calls across WAV, CBR MP3, and VBR MP3."""
        wav_file = tmp_path / "inter_wav.wav"
        create_wav_file(wav_file, duration_sec=2.0)
        cbr_file = tmp_path / "inter_cbr.mp3"
        create_mp3_cbr(cbr_file, bitrate_kbps=192, num_frames=70)
        vbr_file = tmp_path / "inter_vbr.mp3"
        create_mp3_vbr_xing(vbr_file, num_frames=90)

        files = [wav_file, cbr_file, vbr_file]
        random.seed(42)
        sequence = [random.choice(files) for _ in range(500)]

        latencies_ms: list[float] = []
        for target in sequence:
            t0 = time.perf_counter()
            d = get_audio_duration(target)
            t1 = time.perf_counter()
            latencies_ms.append((t1 - t0) * 1000.0)
            assert d > 0

        avg_latency = sum(latencies_ms) / len(latencies_ms)
        p95_latency = sorted(latencies_ms)[int(0.95 * len(latencies_ms))]
        max_latency = max(latencies_ms)

        print(
            f"\n[BENCHMARK] 500 Interleaved calls: avg={avg_latency:.4f}ms, "
            f"p95={p95_latency:.4f}ms, max={max_latency:.4f}ms"
        )
        assert avg_latency < 1.0, f"Interleaved average latency {avg_latency:.4f}ms exceeded 1.0ms SLA"


# ==============================================================================
# 3. Edge Case Adversarial Battery
# ==============================================================================

class TestEdgeCaseAdversarialBattery:
    """Exhaustive stress tests for corrupted headers, truncated streams, and non-audio files."""

    def test_corrupted_wav_headers(self, tmp_path: Path):
        """Various corrupted WAV headers recover gracefully to 0.0 or ffprobe fallback."""
        # 1. Truncated header < 12 bytes
        f1 = tmp_path / "trunc_4.wav"
        f1.write_bytes(b"RIFF")
        assert get_audio_duration(f1) == 0.0

        f2 = tmp_path / "trunc_11.wav"
        f2.write_bytes(b"RIFF\x00\x00\x00\x00WAV")
        assert get_audio_duration(f2) == 0.0

        # 2. Corrupted RIFF signature
        f3 = tmp_path / "bad_riff.wav"
        f3.write_bytes(b"RAFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00")
        assert get_audio_duration(f3) == 0.0

        # 3. Valid RIFF but invalid format (AVI)
        f4 = tmp_path / "avi_not_wave.wav"
        f4.write_bytes(b"RIFF\x24\x00\x00\x00AVI fmt \x10\x00\x00\x00\x01\x00")
        assert get_audio_duration(f4) == 0.0

        # 4. Truncated fmt chunk
        f5 = tmp_path / "trunc_fmt.wav"
        f5.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")
        assert get_audio_duration(f5) == 0.0

        # 5. Missing data chunk
        f6 = tmp_path / "missing_data.wav"
        f6.write_bytes(b"RIFF\x20\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00")
        assert get_audio_duration(f6) == 0.0

    def test_truncated_mp3_streams_invalid_headers(self, tmp_path: Path):
        """Truncated MP3 streams with invalid header bytes recover gracefully."""
        # 1. Truncated MPEG sync byte
        m1 = tmp_path / "trunc_sync.mp3"
        m1.write_bytes(b"\xFF")
        assert get_audio_duration(m1) == 0.0

        # 2. Incomplete frame header (2 bytes only)
        m2 = tmp_path / "two_bytes.mp3"
        m2.write_bytes(b"\xFF\xFB")
        assert get_audio_duration(m2) == 0.0

        # 3. Reserved/invalid bitrate index (0x0F)
        m3 = tmp_path / "bad_bitrate.mp3"
        m3.write_bytes(b"\xFF\xFB\xF0\x00" + b"\x00" * 200)
        assert get_audio_duration(m3) == 0.0

        # 4. Reserved/invalid sampling rate index (3)
        m4 = tmp_path / "bad_srate.mp3"
        m4.write_bytes(b"\xFF\xFB\x9C\x00" + b"\x00" * 200)
        assert get_audio_duration(m4) == 0.0

    def test_zero_byte_files(self, tmp_path: Path):
        """Zero-byte files return 0.0 instantly without subprocess call."""
        z1 = tmp_path / "empty.wav"
        z1.write_bytes(b"")
        z2 = tmp_path / "empty.mp3"
        z2.write_bytes(b"")
        z3 = tmp_path / "empty.bin"
        z3.write_bytes(b"")

        with patch.object(lib.tts, "_run_subproc") as mock_subproc:
            assert get_audio_duration(z1) == 0.0
            assert get_audio_duration(z2) == 0.0
            assert get_audio_duration(z3) == 0.0
            assert get_wav_duration(z1) == 0.0
            mock_subproc.assert_not_called()

    def test_nonexistent_paths_and_directories(self, tmp_path: Path):
        """Non-existent paths and directories return 0.0 gracefully."""
        missing = tmp_path / "does_not_exist.wav"
        assert get_audio_duration(missing) == 0.0
        assert get_wav_duration(missing) == 0.0

        missing_special = tmp_path / "non_exist [weird name] (1).mp3"
        assert get_audio_duration(missing_special) == 0.0

        # Directory path instead of file
        assert get_audio_duration(tmp_path) == 0.0

    def test_pure_id3_tags_without_audio(self, tmp_path: Path):
        """Pure ID3v2 tags with zero audio bytes recover gracefully."""
        # 1. Valid ID3v2.3 tag with 0 audio frames following
        tag_only = tmp_path / "pure_id3.mp3"
        id3_header = bytes([ord("I"), ord("D"), ord("3"), 3, 0, 0, 0, 0, 0, 20])
        id3_data = b"\x00" * 20
        tag_only.write_bytes(id3_header + id3_data)
        assert get_audio_duration(tag_only) == 0.0

        # 2. Corrupted ID3 size claiming 1MB when file is 30 bytes
        huge_id3 = tmp_path / "corrupt_tag_size.mp3"
        corrupt_header = bytes([ord("I"), ord("D"), ord("3"), 3, 0, 0, 0, 0x40, 0, 0])
        huge_id3.write_bytes(corrupt_header + b"\x00" * 20)
        assert get_audio_duration(huge_id3) == 0.0

        # 3. ID3v1 tag only
        id3v1_only = tmp_path / "pure_id3v1.mp3"
        id3v1_only.write_bytes(b"TAG" + b"\x00" * 125)
        assert get_audio_duration(id3v1_only) == 0.0

    def test_non_audio_files(self, tmp_path: Path):
        """Non-audio files (text, JSON, images, binary blobs) return 0.0."""
        # 1. Text file
        txt_file = tmp_path / "script.txt"
        txt_file.write_text("Hello world this is plain text\nLine 2\n", encoding="utf-8")
        assert get_audio_duration(txt_file) == 0.0

        # 2. JSON file
        json_file = tmp_path / "data.json"
        json_file.write_text('{"type": "story", "content": "horror"}', encoding="utf-8")
        assert get_audio_duration(json_file) == 0.0

        # 3. Fake PNG file
        png_file = tmp_path / "image.png"
        png_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 50)
        assert get_audio_duration(png_file) == 0.0

        # 4. Fake SQLite database
        sqlite_file = tmp_path / "test.db"
        sqlite_file.write_bytes(b"SQLite format 3\x00" + b"\x00" * 100)
        assert get_audio_duration(sqlite_file) == 0.0

    def test_ffprobe_fallback_resilience_on_subproc_exceptions(self, tmp_path: Path):
        """When ffprobe fails or throws SubprocessError/OSError, returns 0.0 safely."""
        corrupt_file = tmp_path / "fallback_stress.bin"
        corrupt_file.write_bytes(b"UNKNOWN_FORMAT_REQUIRING_FALLBACK")

        # Test TimeoutExpired
        with patch.object(lib.tts, "_run_subproc", side_effect=subprocess.TimeoutExpired(cmd="ffprobe", timeout=15)):
            assert get_audio_duration(corrupt_file) == 0.0

        # Test SubprocessError
        with patch.object(lib.tts, "_run_subproc", side_effect=subprocess.SubprocessError("ffprobe crashed")):
            assert get_audio_duration(corrupt_file) == 0.0

        # Test OSError (e.g. binary not found)
        with patch.object(lib.tts, "_run_subproc", side_effect=FileNotFoundError("ffprobe not found")):
            assert get_audio_duration(corrupt_file) == 0.0

        # Test ffprobe returns non-float stdout
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "N/A\n"
        with patch.object(lib.tts, "_run_subproc", return_value=mock_res):
            assert get_audio_duration(corrupt_file) == 0.0


# ==============================================================================
# 4. Empirical Vulnerability Verifications (XFAIL BUG REPRODUCTIONS)
# ==============================================================================

class TestEmpiricalBugReproductions:
    """Documented and empirically reproduced bugs in lib/tts.py audio duration reader."""

    def test_wav_corrupted_chunk_offset_unhandled_runtime_error(self, tmp_path: Path):
        """A corrupted WAV file with chunk size exceeding RIFF container raises unhandled RuntimeError."""
        corrupt_wav = tmp_path / "corrupt_chunk.wav"
        # Header specifies RIFF with length 256, but inner chunk claims length larger than container
        corrupt_wav.write_bytes(
            b"RIFF\x00\x01\x00\x00WAVEcorrupt_chunk" + b"\x00" * 500
        )
        # Should catch and return 0.0; currently crashes with uncaught RuntimeError!
        dur = get_audio_duration(corrupt_wav)
        assert dur == 0.0

    def test_mp3_large_id3v2_tag_duration_overestimation(self, tmp_path: Path):
        """When ID3v2 tag > 131,072 bytes (e.g. 150KB album art), duration is severely inflated."""
        tagged_mp3 = tmp_path / "large_album_art.mp3"
        tag_size = 150000
        s0 = (tag_size >> 21) & 0x7F
        s1 = (tag_size >> 14) & 0x7F
        s2 = (tag_size >> 7) & 0x7F
        s3 = tag_size & 0x7F
        id3_header = bytes([ord("I"), ord("D"), ord("3"), 3, 0, 0, s0, s1, s2, s3])
        id3_payload = b"\x00" * tag_size

        frame_size = 417
        frame_header = b"\xFF\xFB\x90\x00"
        frame_payload = frame_header + b"\x77" * (frame_size - 4)

        num_frames = 250
        with open(tagged_mp3, "wb") as f:
            f.write(id3_header)
            f.write(id3_payload)
            for _ in range(num_frames):
                f.write(frame_payload)

        # Expected audio duration: 250 frames * 1152 samples / 44100 Hz ~= 6.53s
        expected_audio_dur = round(num_frames * 1152.0 / 44100.0, 4)
        calc_dur = get_audio_duration(tagged_mp3)

        # Currently returns ~15.89s (overestimated by 143%) because offset was reset to 0
        assert abs(calc_dur - expected_audio_dur) < 0.2, (
            f"Duration {calc_dur}s distorted from expected {expected_audio_dur}s"
        )

    def test_mp3_sub_frame_truncation_false_positive(self, tmp_path: Path):
        """Files with fewer bytes than 1 full MPEG frame (<417 bytes) must not report fake durations."""
        truncated_mp3 = tmp_path / "sub_frame.mp3"
        header = b"\xFF\xFB\x90\x00"  # 128kbps, 44100Hz -> requires 417 bytes for 1 frame
        # File has only 39 bytes with incomplete Xing tag
        truncated_mp3.write_bytes(header + b"\x00" * 32 + b"Xin")

        # In ffprobe this fails with exit code 1; in lib/tts it returns 0.0024s!
        dur = get_audio_duration(truncated_mp3)
        assert dur == 0.0, f"Sub-frame truncated file returned non-zero duration: {dur}s"
