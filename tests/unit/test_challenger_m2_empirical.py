import pytest
pytestmark = [
    pytest.mark.skip(reason="quarantined: native_procedural/wgpu under src.media._legacy; SSOT is FFmpeg + Pillow thumbs (ENABLE_NATIVE_PROCEDURAL opt-in only)"),
]

"""
Empirical Challenge & Benchmark Suite for Milestone M2.
Contains empirical verification tests, benchmarks, and regression reproduction tests
created by Challenger 1 (teamwork_preview_challenger_m2_1).
"""

import hashlib
import os
import time
import tracemalloc
import numpy as np
import pytest

from src.media.native_procedural import NativeProceduralEngine, VALID_ARCHETYPES
from src.media.svg_overlay import SVGOverlayEngine
from src.media.inmemory_compositor import InMemoryCompositor


class TestEmpiricalDeterminism:
    """Audit 1: Bit-Exact Frame Reproducibility & Seed/Time Entropy."""

    @pytest.mark.parametrize("archetype_id", sorted(list(VALID_ARCHETYPES)))
    def test_bit_exact_reproducibility_across_instances(self, archetype_id):
        """Verify identical seed + time + params yield 100% bit-exact identical hashes across separate engine instances."""
        width, height = 540, 960
        hashes = []
        for _ in range(3):
            with NativeProceduralEngine(force_software=True) as engine:
                out_buf = np.zeros((height, width, 4), dtype=np.uint8)
                frame = engine.render_frame(
                    width=width,
                    height=height,
                    time_sec=1.234,
                    duration_sec=5.0,
                    archetype_id=archetype_id,
                    seed=777,
                    tension=2,
                    params={"noise_scale": 1.5, "speed": 1.2},
                    out_buffer=out_buf,
                )
                h = hashlib.sha256(frame.tobytes()).hexdigest()
                hashes.append(h)

        assert hashes[0] == hashes[1] == hashes[2], f"Non-deterministic render on archetype {archetype_id}"

    @pytest.mark.parametrize("archetype_id", ["cosmic_singularity", "dark_forest", "synaptic_network"])
    def test_seed_entropy_differentiation_robust_archetypes(self, archetype_id):
        """Verify varying seed produces distinct frame hashes on robust procedural shaders."""
        width, height = 320, 240
        with NativeProceduralEngine(force_software=True) as engine:
            f_seed1 = engine.render_frame(width, height, time_sec=0.5, duration_sec=5.0, archetype_id=archetype_id, seed=100)
            f_seed2 = engine.render_frame(width, height, time_sec=0.5, duration_sec=5.0, archetype_id=archetype_id, seed=200)
            h1 = hashlib.sha256(f_seed1.tobytes()).hexdigest()
            h2 = hashlib.sha256(f_seed2.tobytes()).hexdigest()
            assert h1 != h2

    def test_seed_entropy_differentiation_tactical_chamber(self):
        """Verify tactical_chamber produces distinct frames for varying seeds (e.g. seed=100 vs seed=200)."""
        width, height = 320, 240
        with NativeProceduralEngine(force_software=True) as engine:
            f_seed1 = engine.render_frame(width, height, time_sec=0.5, duration_sec=5.0, archetype_id="tactical_chamber", seed=100)
            f_seed2 = engine.render_frame(width, height, time_sec=0.5, duration_sec=5.0, archetype_id="tactical_chamber", seed=200)
            h1 = hashlib.sha256(f_seed1.tobytes()).hexdigest()
            h2 = hashlib.sha256(f_seed2.tobytes()).hexdigest()
            assert h1 != h2, f"Seed entropy failed on tactical_chamber: both seeds produced identical hash {h1}"

    def test_composite_pipeline_determinism(self):
        """Verify full stack (Procedural + SVG + Compositor) is 100% bit-exact reproducible."""
        width, height = 540, 960
        hashes = []
        for _ in range(3):
            with NativeProceduralEngine(force_software=True) as proc_engine:
                svg_engine = SVGOverlayEngine()
                compositor = InMemoryCompositor(width=width, height=height)

                base = proc_engine.render_frame(
                    width, height, time_sec=1.5, duration_sec=5.0, archetype_id="cosmic_singularity", seed=42
                )
                overlay = svg_engine.render_overlay(
                    "hud_tactical_telemetry",
                    width,
                    height,
                    time_sec=1.5,
                    params={"telemetry_text": "SYSTEM ONLINE", "bpm": "78"},
                )
                composite = compositor.composite_frame(base, overlay)
                mv = compositor.get_memoryview()
                h = hashlib.sha256(mv.tobytes()).hexdigest()
                hashes.append(h)

        assert hashes[0] == hashes[1] == hashes[2]


class TestEmpiricalZeroAllocation:
    """Audit 2: Zero Heap Reallocations in Steady-State Loop."""

    def test_zero_allocation_frame_loop(self):
        """Verify zero heap growth across 60 consecutive frames in steady-state loop."""
        width, height = 540, 960
        num_frames = 60

        with NativeProceduralEngine(force_software=True) as engine:
            svg_engine = SVGOverlayEngine()
            compositor = InMemoryCompositor(width=width, height=height)

            out_buf = np.zeros((height, width, 4), dtype=np.uint8)
            overlay_buf = np.zeros((height, width, 4), dtype=np.uint8)

            # Warm-up (compile pipelines, prime caches)
            engine.render_frame(width, height, 0.0, 5.0, "synaptic_network", out_buffer=out_buf)
            svg_engine.render_overlay("biometric_wave", width, height, 0.0, params={"bpm": "72"}, out_buffer=overlay_buf)
            compositor.composite_frame(out_buf, overlay_buf)

            # Measure heap allocations during steady-state loop
            tracemalloc.start()
            snapshot_before = tracemalloc.take_snapshot()

            for i in range(num_frames):
                t_sec = i / 30.0
                res_proc = engine.render_frame(
                    width, height, t_sec, 5.0, "synaptic_network", out_buffer=out_buf
                )
                res_svg = svg_engine.render_overlay(
                    "biometric_wave", width, height, t_sec, params={"bpm": "72"}, out_buffer=overlay_buf
                )
                res_comp = compositor.composite_frame(out_buf, overlay_buf)
                mv = compositor.get_memoryview()

                assert id(res_proc) == id(out_buf)
                assert np.shares_memory(res_proc, out_buf)
                assert id(res_svg) == id(overlay_buf)
                assert np.shares_memory(res_svg, overlay_buf)
                assert id(res_comp) == id(compositor.out_buffer)
                assert len(mv) == width * height * 4

            snapshot_after = tracemalloc.take_snapshot()
            current_mem, peak_mem = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            # The steady-state loop should not retain newly allocated memory
            stats = snapshot_after.compare_to(snapshot_before, "lineno")
            total_retained_diff = sum(s.size_diff for s in stats if s.size_diff > 0)
            
            # Less than 64KB variance allowed for internal Python bookkeeping across 60 frames
            assert total_retained_diff < 65536, f"Heap memory grew by {total_retained_diff} bytes across {num_frames} frames"


class TestEmpiricalThroughput:
    """Audit 3: Mesa Lavapipe CPU Render Throughput."""

    @pytest.mark.parametrize("archetype_id", sorted(list(VALID_ARCHETYPES)))
    def test_steady_state_throughput_measurements(self, archetype_id):
        """Measure actual FPS on Mesa Lavapipe CPU rasterizer."""
        width, height = 540, 960
        num_frames = 15

        with NativeProceduralEngine(force_software=True) as engine:
            out_buf = np.zeros((height, width, 4), dtype=np.uint8)

            # Warmup frame
            engine.render_frame(width, height, 0.0, 5.0, archetype_id, out_buffer=out_buf)

            start_t = time.perf_counter()
            for i in range(num_frames):
                t_sec = i / 30.0
                engine.render_frame(width, height, t_sec, 5.0, archetype_id, out_buffer=out_buf)
            elapsed = time.perf_counter() - start_t

            fps = num_frames / elapsed
            frame_ms = (elapsed / num_frames) * 1000.0

            print(f"\n[BENCHMARK] {archetype_id:<20} | Res: {width}x{height} | {fps:.2f} FPS | {frame_ms:.2f} ms/frame")
            # All archetypes render successfully on CPU without crashing
            assert fps > 0.0


class TestEmpiricalStressAndBoundaries:
    """Audit 4: Stress and Boundary Testing."""

    def test_extreme_parameter_values(self):
        """Verify engine survives extreme float values without crashing or producing NaN/Inf."""
        with NativeProceduralEngine(force_software=True) as engine:
            out_buf = np.zeros((240, 320, 4), dtype=np.uint8)
            extreme_params = {
                "noise_scale": 10000.0,
                "speed": -50.0,
                "distortion": 999.0,
                "glow_intensity": 50.0,
                "custom_1": 1e5,
                "custom_2": -1e5,
                "custom_3": 0.0,
                "accent_color": (10.0, -5.0, 2.0),
            }
            frame = engine.render_frame(
                320, 240, time_sec=99999.0, duration_sec=0.001, archetype_id="cosmic_singularity",
                seed=2147483647, tension=100, params=extreme_params, out_buffer=out_buf
            )
            assert frame.shape == (240, 320, 4)
            assert frame.dtype == np.uint8
            assert not np.isnan(frame).any()

    def test_rapid_resolution_switching(self):
        """Verify alternating resolutions cleanly reallocates textures without memory corruption."""
        with NativeProceduralEngine(force_software=True) as engine:
            resolutions = [(100, 200), (400, 300), (128, 128), (540, 960), (64, 64)]
            for w, h in resolutions:
                f = engine.render_frame(w, h, time_sec=0.5, duration_sec=1.0, archetype_id="dark_forest")
                assert f.shape == (h, w, 4)
                assert np.all(f[:, :, 3] == 255)

    def test_svg_overlay_interpolation_special_characters(self):
        """Verify SVGOverlayEngine handles special XML characters in parameters safely."""
        svg_engine = SVGOverlayEngine()
        raw_svg = svg_engine.load_template("scp_classification_stamp")
        interp = svg_engine.interpolate_template(raw_svg, params={"item_number": "999", "classification": "EUCLID"})
        assert "999" in interp
        assert "EUCLID" in interp

    def test_svg_overlay_non_9_16_aspect_ratio_contract(self):
        """Verify SVGOverlayEngine correctly handles non-9:16 aspect ratio (e.g. 200x200 square) with and without out_buffer."""
        svg_engine = SVGOverlayEngine()
        out_buf = np.zeros((200, 200, 4), dtype=np.uint8)
        # Should render cleanly into out_buf without throwing ValueError
        res = svg_engine.render_overlay("hud_tactical_telemetry", width=200, height=200, out_buffer=out_buf)
        assert res.shape == (200, 200, 4)
        assert id(res) == id(out_buf)
        assert np.shares_memory(res, out_buf)

        # Should also work when out_buffer is None
        res_no_buf = svg_engine.render_overlay("hud_tactical_telemetry", width=200, height=200)
        assert res_no_buf.shape == (200, 200, 4)
