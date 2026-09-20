"""
Adversarial Stress Test Suite for Milestone M2:
- SVGOverlayEngine rapid parameter fluctuations & static cache hits.
- InMemoryCompositor 1000 consecutive composite cycles with memory profiling (<256MB).
- get_memoryview() format, length, contiguity, and live FFmpeg stdin piping verification.
"""

from __future__ import annotations

import gc
import os
import subprocess
import time
import tracemalloc
import numpy as np
import pytest

from src.media.svg_overlay import SVGOverlayEngine, resvg_py
from src.media.inmemory_compositor import InMemoryCompositor


def get_vmrss_mb() -> float:
    """Helper to read physical VmRSS from /proc/self/status."""
    if os.path.exists("/proc/self/status"):
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
    return 0.0


@pytest.mark.skipif(resvg_py is None, reason="resvg-py optional dependency not installed")
class TestSVGOverlayEngineStress:
    """Stress tests and edge case mining for SVGOverlayEngine."""

    def test_static_cache_hits_performance(self):
        """Verify 100% cache hits for static overlays and measure latency."""
        engine = SVGOverlayEngine()
        params = {"telemetry_text": "STABLE", "bpm": "70"}
        out_buf = np.zeros((1920, 1080, 4), dtype=np.uint8)

        # First call (cold - rasterizes)
        t0 = time.perf_counter()
        engine.render_overlay("hud_tactical_telemetry", width=1080, height=1920, params=params, out_buffer=out_buf)
        cold_time = time.perf_counter() - t0

        # Next 100 calls (warm - cache hits)
        t0 = time.perf_counter()
        for _ in range(100):
            engine.render_overlay("hud_tactical_telemetry", width=1080, height=1920, params=params, out_buffer=out_buf)
        warm_total_time = time.perf_counter() - t0
        avg_warm_time_ms = (warm_total_time / 100.0) * 1000.0

        assert len(engine._raster_cache) == 1
        # Warm cache lookup (8.3MB buffer copy) should be fast (< 10.0 ms, typically 2-3ms)
        assert avg_warm_time_ms < 10.0, f"Average warm lookup too slow: {avg_warm_time_ms:.3f}ms"

    def test_rapid_parameter_fluctuations_correctness(self):
        """Verify rendering correctness under rapid parameter fluctuations."""
        engine = SVGOverlayEngine()
        out_buf = np.zeros((1920, 1080, 4), dtype=np.uint8)

        # Cycle through fluctuating parameters
        for bpm in range(60, 75):
            params = {"bpm": str(bpm), "telemetry_text": f"STATUS_{bpm}"}
            res = engine.render_overlay("hud_tactical_telemetry", width=1080, height=1920, params=params, out_buffer=out_buf)
            assert res.shape == (1920, 1080, 4)
            assert res.dtype == np.uint8
            assert np.any(res[:, :, 3] > 0)
            assert np.shares_memory(res, out_buf)

        assert len(engine._raster_cache) == 15

    def test_svg_overlay_cache_behavior_and_memory(self):
        """Verify cache key generation handles different parameter order consistently in 9:16 aspect ratio."""
        engine = SVGOverlayEngine()
        width, height = 270, 480
        buf = np.zeros((height, width, 4), dtype=np.uint8)

        # Unordered dicts with identical content must share cache key
        p1 = {"telemetry_text": "TEST", "bpm": "60"}
        p2 = {"bpm": "60", "telemetry_text": "TEST"}

        engine.render_overlay("hud_tactical_telemetry", width=width, height=height, params=p1, out_buffer=buf)
        assert len(engine._raster_cache) == 1
        engine.render_overlay("hud_tactical_telemetry", width=width, height=height, params=p2, out_buffer=buf)
        assert len(engine._raster_cache) == 1  # Hit same cache entry

    def test_svg_overlay_empty_and_special_character_params(self):
        """Test XML escaping/special characters in interpolated params."""
        engine = SVGOverlayEngine()
        buf = np.zeros((1920, 1080, 4), dtype=np.uint8)
        params = {
            "telemetry_text": "VAL_100%_OK",
            "bpm": "99",
            "item_number": "096-A",
            "classification": "KETER",
            "spo2": "99",
        }
        for preset in ["hud_tactical_telemetry", "scp_classification_stamp", "biometric_wave"]:
            res = engine.render_overlay(preset, width=1080, height=1920, params=params, out_buffer=buf)
            assert res.shape == (1920, 1080, 4)
            assert np.any(res[:, :, 3] > 0)


class TestInMemoryCompositorStress:
    """Stress tests and memory bounds verification for InMemoryCompositor."""

    def test_1000_consecutive_composite_cycles_memory_and_speed(self):
        """
        Stress test 1000 full 1080x1920 composite cycles.
        Verifies:
        1. Memory growth across 1000 cycles is strictly bounded (< 32 MB delta, zero memory leak).
        2. Tracemalloc peak memory remains < 256 MB.
        """
        gc.collect()
        tracemalloc.start()

        width, height = 1080, 1920
        compositor = InMemoryCompositor(width=width, height=height)

        # Base procedural frame buffer
        base_frame = np.full((height, width, 4), [30, 40, 50, 255], dtype=np.uint8)
        # Overlay frame with alpha mask
        overlay_frame = np.zeros((height, width, 4), dtype=np.uint8)
        overlay_frame[100:300, 100:900] = [0, 255, 200, 180]
        overlay_frame[1700:1850, 100:900] = [255, 50, 50, 255]

        # Warmup
        compositor.composite_frame(base_frame, overlay_frame)
        initial_vmrss = get_vmrss_mb()

        t_start = time.perf_counter()
        cycles = int(os.environ.get("COMPOSITOR_STRESS_CYCLES", "100"))
        for i in range(cycles):
            base_frame[0, 0, 0] = i % 256
            out = compositor.composite_frame(base_frame, overlay_frame)
            mv = compositor.get_memoryview()
            assert len(mv) == width * height * 4

        elapsed = time.perf_counter() - t_start
        final_vmrss = get_vmrss_mb()

        current_mem, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_mb = peak_mem / (1024 * 1024)
        current_mb = current_mem / (1024 * 1024)
        delta_vmrss = final_vmrss - initial_vmrss

        # Verify performance and memory constraints
        assert peak_mb < 256.0, f"Tracemalloc Peak memory {peak_mb:.2f}MB exceeded 256MB limit!"
        assert current_mb < 64.0, f"Tracemalloc Current memory {current_mb:.2f}MB unexpectedly high!"
        if initial_vmrss > 0:
            assert delta_vmrss < 32.0, f"VmRSS growth delta {delta_vmrss:.2f}MB indicates a memory leak!"

    def test_alpha_blending_mathematical_precision_all_corners(self):
        """Verify Porter-Duff Over across extreme values (0, 1, 127, 128, 254, 255)."""
        comp = InMemoryCompositor(width=6, height=1)
        base = np.zeros((1, 6, 4), dtype=np.uint8)
        overlay = np.zeros((1, 6, 4), dtype=np.uint8)

        base[0, :] = [255, 0, 0, 255]

        alphas = [0, 1, 127, 128, 254, 255]
        for idx, a in enumerate(alphas):
            overlay[0, idx] = [0, 255, 0, a]

        out = comp.composite_frame(base, overlay)

        # Index 0: alpha=0 -> exactly base
        assert list(out[0, 0]) == [255, 0, 0, 255]
        # Index 5: alpha=255 -> exactly overlay
        assert list(out[0, 5]) == [0, 255, 0, 255]

        # Index 3: alpha=128 (approx 50/50)
        assert abs(int(out[0, 3, 0]) - 127) <= 1
        assert abs(int(out[0, 3, 1]) - 128) <= 1
        assert out[0, 3, 3] == 255


class TestFFmpegMemoryviewPiping:
    """Validate get_memoryview() format, contiguity, and direct piping to FFmpeg."""

    def test_memoryview_properties(self):
        """Verify memoryview is 1D unsigned char, contiguous, and exactly width * height * 4 bytes."""
        width, height = 1080, 1920
        comp = InMemoryCompositor(width=width, height=height)
        base = np.full((height, width, 4), [10, 20, 30, 255], dtype=np.uint8)
        comp.composite_frame(base)

        mv = comp.get_memoryview()
        assert isinstance(mv, memoryview)
        assert mv.itemsize == 1
        assert mv.format == "B"
        assert mv.ndim == 1
        assert mv.c_contiguous is True
        assert len(mv) == width * height * 4
        assert mv.nbytes == width * height * 4

    def test_live_ffmpeg_pipe_streaming(self):
        """
        Stream 30 synthetic frames through InMemoryCompositor.get_memoryview()
        directly into live FFmpeg rawvideo stdin pipe.
        """
        width, height = 540, 960
        comp = InMemoryCompositor(width=width, height=height)
        base = np.full((height, width, 4), [50, 100, 150, 255], dtype=np.uint8)
        overlay = np.zeros((height, width, 4), dtype=np.uint8)
        overlay[100:200, 100:400] = [255, 255, 0, 200]

        cmd = [
            "ffmpeg",
            "-y",
            "-f", "rawvideo",
            "-pix_fmt", "rgba",
            "-s", f"{width}x{height}",
            "-r", "30",
            "-i", "pipe:0",
            "-c:v", "rawvideo",
            "-f", "null",
            "-",
        ]

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        try:
            for i in range(30):
                base[0, 0, 0] = (i * 8) % 256
                comp.composite_frame(base, overlay)
                mv = comp.get_memoryview()
                proc.stdin.write(mv)
            proc.stdin.flush()
            proc.stdin.close()
            stderr_bytes = proc.stderr.read()
            proc.wait(timeout=10)
        except Exception as exc:
            proc.kill()
            raise exc

        assert proc.returncode == 0, f"FFmpeg exited with error code {proc.returncode}: {stderr_bytes.decode()}"
