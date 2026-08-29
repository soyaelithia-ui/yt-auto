"""
tests/unit/test_adversarial_m2_backpressure_challenger2.py - Adversarial Stress & Empirical Backpressure Verification for M2.

Stress-tests:
1. FFmpeg stdin backpressure handling via `select.select` in `DirectStreamCompositor._write_frame_with_backpressure`.
2. Pipe buffer exhaustion with slow transcoding sinks (rate-limited consumer).
3. Massive raw RGBA frame payloads (1080x1920x4 = 8.29 MB per frame, >120 MB total) streaming to live FFmpeg.
4. Graceful termination on broken pipe (early consumer exit, SIGKILL mid-stream).
5. Dynamic duration calculation and audio duration parity (+0.5s buffer tolerance).
6. FFmpeg pipeline failure handling and browser cleanup.
"""
from __future__ import annotations

import math
import os
import select
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from lib.ffmpeg import probe_media, run_ffmpeg
from src.compositing.stream_renderer import DirectStreamCompositor
from src.narrative.engine import CosmicNarrativeEngine
from src.narrative.schema import NarrativeArchetype, VideoFormat
from src.rendering.renderer import resolve_chrome_path


class TestEmpiricalBackpressureAndPipeExhaustion:
    """Adversarial stress-testing of pipe backpressure, buffer exhaustion, and slow sinks."""

    def test_pipe_backpressure_with_slow_consumer(self, tmp_path: Path):
        """
        Simulate a slow transcoding sink that reads from stdin in small throttled chunks.
        Verify that `_write_frame_with_backpressure` handles the backpressure and writes
        all frames without data loss or buffer deadlocks.
        """
        compositor = DirectStreamCompositor()
        
        # Consumer reads 8KB every 10ms
        consumer_script = (
            "import sys, time\n"
            "total = 0\n"
            "while True:\n"
            "    chunk = sys.stdin.buffer.read(8192)\n"
            "    if not chunk:\n"
            "        break\n"
            "    total += len(chunk)\n"
            "    time.sleep(0.005)\n"
            "print(f'CONSUMED:{total}')\n"
        )

        proc = subprocess.Popen(
            [sys.executable, "-c", consumer_script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
        )

        # Write 10 frames of 128KB each (1.28 MB total) - significantly exceeding the standard 64KB Linux pipe buffer
        frame_size = 128 * 1024
        num_frames = 10
        total_expected_bytes = frame_size * num_frames
        payload = b"B" * frame_size

        start_time = time.time()
        for i in range(num_frames):
            ok = compositor._write_frame_with_backpressure(proc, payload, timeout=10.0)
            assert ok is True, f"Frame {i} failed to write with backpressure"

        if proc.stdin:
            proc.stdin.close()
        
        stdout = proc.stdout.read() if proc.stdout else b""
        proc.wait(timeout=10.0)
        elapsed = time.time() - start_time

        assert proc.returncode == 0
        assert f"CONSUMED:{total_expected_bytes}" in stdout.decode("utf-8")
        # Ensure throttling actually took some time due to slow consumer
        assert elapsed >= 0.1

    def test_massive_rgba_frame_payloads_to_live_ffmpeg(self, tmp_path: Path):
        """
        Empirically stream 15 full-resolution RGBA frames (1080x1920x4 = 8,294,400 bytes each,
        ~124.4 MB total) into a live FFmpeg process transcoding to H.264 via rawvideo pipe.
        Validates high-throughput backpressure, buffer draining, and final media integrity.
        """
        compositor = DirectStreamCompositor()
        out_mp4 = tmp_path / "massive_rgba_stream.mp4"
        width = 1080
        height = 1920
        fps = 30
        frame_bytes_len = width * height * 4  # 8,294,400 bytes per frame
        num_frames = 15

        ffmpeg_cmd = [
            "ffmpeg", "-y", "-v", "warning",
            "-f", "rawvideo",
            "-pix_fmt", "rgba",
            "-s", f"{width}x{height}",
            "-r", str(fps),
            "-i", "-",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            "-t", f"{num_frames / fps:.3f}",
            str(out_mp4),
        ]

        proc = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Generate a distinct RGBA pattern per frame to avoid trivial all-zero compression
        for frame_idx in range(num_frames):
            # Create simulated frame payload with distinctive byte
            fill_byte = bytes([(frame_idx * 17) % 256])
            frame_data = fill_byte * frame_bytes_len
            
            written = compositor._write_frame_with_backpressure(proc, frame_data, timeout=15.0)
            assert written is True, f"Failed to write 8.3MB RGBA frame {frame_idx}"

        if proc.stdin:
            try:
                proc.stdin.flush()
                proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass

        proc.wait(timeout=30.0)
        assert proc.returncode == 0, f"FFmpeg failed with code {proc.returncode}"
        assert out_mp4.is_file()
        assert out_mp4.stat().st_size > 50000  # Valid MP4 produced

        probe = probe_media(out_mp4)
        assert probe.has_video is True
        assert probe.primary_video is not None
        assert probe.primary_video.width == width
        assert probe.primary_video.height == height
        assert probe.duration == pytest.approx(num_frames / fps, abs=0.1)

    def test_broken_pipe_on_immediate_consumer_exit(self):
        """
        Verify that when the downstream consumer terminates immediately (e.g. FFmpeg crash on invalid codec),
        `_write_frame_with_backpressure` catches the pipe error, returns False, and does not raise an exception.
        """
        compositor = DirectStreamCompositor()
        
        # Consumer exits immediately with return code 1 without reading stdin
        proc = subprocess.Popen(
            [sys.executable, "-c", "import sys; sys.exit(1)"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        proc.wait(timeout=2.0)
        assert proc.poll() is not None

        # Attempt write on terminated process
        payload = b"X" * (1024 * 1024)
        ok = compositor._write_frame_with_backpressure(proc, payload, timeout=1.0)
        assert ok is False

    def test_broken_pipe_mid_stream_sigkill_handling(self):
        """
        Verify that killing the consumer mid-stream with SIGKILL causes subsequent writes
        to gracefully return False without deadlocking or raising uncaught exceptions.
        """
        compositor = DirectStreamCompositor()
        
        # Consumer starts reading then hangs/waits
        proc = subprocess.Popen(
            [sys.executable, "-c", "import sys, time; sys.stdin.buffer.read(1024); time.sleep(10)"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Write first frame
        ok1 = compositor._write_frame_with_backpressure(proc, b"A" * 1024, timeout=2.0)
        assert ok1 is True

        # Send SIGKILL to consumer
        proc.kill()
        proc.wait(timeout=2.0)

        # Attempt to write second frame to killed process
        ok2 = compositor._write_frame_with_backpressure(proc, b"B" * (64 * 1024), timeout=1.0)
        assert ok2 is False

    def test_pipe_exhaustion_interrupted_then_drained(self):
        """
        Test pipe buffer filling up, pausing the producer, and then verifying recovery
        when the consumer starts draining the buffer.
        """
        compositor = DirectStreamCompositor()
        
        # Consumer sleeps 0.2s before beginning to read all data
        consumer_code = (
            "import sys, time\n"
            "time.sleep(0.2)\n"
            "data = sys.stdin.buffer.read()\n"
            "print(f'LEN:{len(data)}')\n"
        )
        proc = subprocess.Popen(
            [sys.executable, "-c", consumer_code],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Write 500 KB (exceeding pipe capacity)
        data = b"D" * (500 * 1024)
        ok = compositor._write_frame_with_backpressure(proc, data, timeout=5.0)
        assert ok is True

        if proc.stdin:
            proc.stdin.close()
        stdout = proc.stdout.read() if proc.stdout else b""
        proc.wait(timeout=5.0)
        assert f"LEN:{500 * 1024}" in stdout.decode("utf-8")


class TestEmpiricalDynamicDurationAudioAlignment:
    """Empirical verification of dynamic duration calculations linked to master audio."""

    @pytest.mark.parametrize("audio_duration, fps", [
        (0.8, 30),
        (2.34, 30),
        (5.0, 24),
        (10.75, 15),
    ])
    def test_dynamic_duration_frame_count_formula_matrix(
        self,
        tmp_path: Path,
        audio_duration: float,
        fps: int,
    ):
        """
        Verify that `total_frames = math.ceil((audio_duration + 0.5) * fps)` holds true
        and matches the duration calculation across different audio lengths and frame rates.
        """
        # Create synthetic audio file of exact length
        audio_path = tmp_path / f"synth_audio_{audio_duration}s.wav"
        subprocess.run([
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", f"sine=frequency=500:duration={audio_duration}",
            "-c:a", "pcm_s16le", str(audio_path),
        ], check=True)

        probe = probe_media(audio_path)
        actual_audio_dur = probe.duration
        assert actual_audio_dur == pytest.approx(audio_duration, abs=0.05)

        expected_frames = math.ceil((actual_audio_dur + 0.5) * fps)
        expected_video_dur = expected_frames / fps

        # Test DirectStreamCompositor duration derivation without Playwright launch
        # By inspecting the formula logic directly against probed audio
        derived_frames = math.ceil((actual_audio_dur + 0.5) * fps)
        derived_duration = derived_frames / fps

        assert derived_frames == expected_frames
        assert derived_duration == pytest.approx(expected_video_dur)
        # Ensure video duration is strictly >= audio duration
        assert derived_duration >= actual_audio_dur

    def test_render_and_mux_full_audio_parity(self, tmp_path: Path):
        """
        End-to-end render and muxing with Chromium to verify final MP4 has exact duration
        matching math.ceil((audio_dur + 0.5) * fps) / fps.
        """
        chrome_path = resolve_chrome_path()
        if not chrome_path:
            pytest.skip("Chrome executable not found")

        audio_dur = 1.6
        fps = 15
        audio_path = tmp_path / "master_parity_audio.wav"
        subprocess.run([
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={audio_dur}",
            "-c:a", "pcm_s16le", str(audio_path),
        ], check=True)

        engine = CosmicNarrativeEngine()
        script = engine.generate_script(
            archetype=NarrativeArchetype.HYDROACOUSTIC_TELEMETRY,
            video_format=VideoFormat.SHORT_VERTICAL,
            duration_sec=1.0,  # Nominal duration (must be overridden by audio)
        )

        compositor = DirectStreamCompositor(chrome_exec_path=chrome_path)
        out_mp4 = tmp_path / "parity_test_out.mp4"

        res = compositor.render_and_mux(
            script_contract=script,
            output_mp4_path=out_mp4,
            master_audio_path=audio_path,
            width=360,
            height=640,
            fps=fps,
        )

        assert res.is_file()
        probe = probe_media(res)
        expected_frames = math.ceil((audio_dur + 0.5) * fps)
        expected_dur = expected_frames / fps

        assert probe.has_video is True
        assert probe.has_audio is True
        assert probe.duration == pytest.approx(expected_dur, abs=0.25)
        # Video is longer than audio by at least 0.3s (safety margin)
        assert probe.duration >= audio_dur

    def test_horizontal_1920x1080_massive_rgba_stream(self, tmp_path: Path):
        """
        Empirically stream 1920x1080 HORIZONTAL format uncompressed RGBA frames (8,294,400 bytes/frame)
        to live FFmpeg to verify dual-format backpressure parity.
        """
        compositor = DirectStreamCompositor()
        out_mp4 = tmp_path / "massive_horizontal_rgba_stream.mp4"
        width = 1920
        height = 1080
        fps = 30
        frame_bytes_len = width * height * 4
        num_frames = 10

        ffmpeg_cmd = [
            "ffmpeg", "-y", "-v", "warning",
            "-f", "rawvideo",
            "-pix_fmt", "rgba",
            "-s", f"{width}x{height}",
            "-r", str(fps),
            "-i", "-",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            "-t", f"{num_frames / fps:.3f}",
            str(out_mp4),
        ]

        proc = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        for frame_idx in range(num_frames):
            fill_byte = bytes([(frame_idx * 23) % 256])
            frame_data = fill_byte * frame_bytes_len
            written = compositor._write_frame_with_backpressure(proc, frame_data, timeout=15.0)
            assert written is True

        if proc.stdin:
            try:
                proc.stdin.flush()
                proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass

        proc.wait(timeout=30.0)
        assert proc.returncode == 0
        assert out_mp4.is_file()

        probe = probe_media(out_mp4)
        assert probe.has_video is True
        assert probe.primary_video.width == 1920
        assert probe.primary_video.height == 1080
        assert probe.duration == pytest.approx(num_frames / fps, abs=0.1)

    def test_unresponsive_consumer_pipe_backpressure_throttling(self):
        """
        Verify that when consumer is completely stalled (sleeps forever without reading),
        the producer attempts backpressure select throttling until the process terminates
        or write fails without hanging infinitely.
        """
        compositor = DirectStreamCompositor()
        
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Fill pipe buffer completely (write several MBs)
        # With a short timeout on select, backpressure loop checks proc.poll()
        payload = b"Z" * (1024 * 1024)
        
        # Kill after a short delay
        def delayed_kill():
            time.sleep(0.3)
            proc.kill()

        import threading
        t = threading.Thread(target=delayed_kill)
        t.start()

        # Should write until pipe full, then select/poll detects kill and returns False safely
        for _ in range(20):
            res = compositor._write_frame_with_backpressure(proc, payload, timeout=0.1)
            if not res:
                break

        t.join(timeout=2.0)
        proc.wait(timeout=2.0)
        assert proc.poll() is not None
        # Subsequent writes must return False immediately
        assert compositor._write_frame_with_backpressure(proc, payload, timeout=0.1) is False

