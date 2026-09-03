"""
Unit tests for NativeProceduralEngine (WebGPU & Lavapipe procedural rendering).
"""

from __future__ import annotations

import os
from pathlib import Path
import numpy as np
import pytest

from src.media.native_procedural import NativeProceduralEngine, VALID_ARCHETYPES


@pytest.fixture
def engine():
    eng = NativeProceduralEngine()
    yield eng
    eng.close()


def test_native_procedural_init(engine):
    """Verify NativeProceduralEngine initializes with valid adapter and device."""
    assert engine.adapter is not None
    assert engine.device is not None
    assert len(engine.get_available_archetypes()) == len(VALID_ARCHETYPES)
    for arch in ["arctic_desolation", "cosmic_singularity", "dark_forest", "synaptic_network", "tactical_chamber"]:
        assert arch in engine.get_available_archetypes()


def test_native_procedural_force_software():
    """Verify engine can initialize with force_software=True."""
    with NativeProceduralEngine(force_software=True) as eng:
        assert eng.adapter is not None
        assert eng.device is not None


@pytest.mark.parametrize("archetype_id", list(VALID_ARCHETYPES))
def test_render_frame_all_archetypes(engine, archetype_id):
    """Verify all 4 archetypes render valid RGBA frames of shape (height, width, 4)."""
    width, height = 320, 240
    frame = engine.render_frame(
        width=width,
        height=height,
        time_sec=1.0,
        duration_sec=5.0,
        archetype_id=archetype_id,
        tension=2,
        seed=100,
    )
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (height, width, 4)
    assert frame.dtype == np.uint8
    # RGBA: Alpha channel must be 255 (opaque)
    assert np.all(frame[:, :, 3] == 255)
    # Ensure not completely black (meaningful rendering occurs)
    assert np.any(frame[:, :, :3] > 0)


def test_render_frame_zero_allocation_out_buffer(engine):
    """Verify in-place mutation when out_buffer is provided."""
    width, height = 1080, 1920
    out_buf = np.zeros((height, width, 4), dtype=np.uint8)
    res = engine.render_frame(
        width=width,
        height=height,
        time_sec=0.5,
        duration_sec=3.0,
        archetype_id="cosmic_singularity",
        out_buffer=out_buf,
    )
    assert id(res) == id(out_buf)
    assert np.shares_memory(res, out_buf)
    assert np.any(out_buf > 0)


def test_render_frame_determinism(engine):
    """Verify identical parameters yield bitwise identical output, and differing seeds yield different output."""
    w, h = 128, 128
    f1 = engine.render_frame(w, h, time_sec=2.0, duration_sec=5.0, archetype_id="dark_forest", seed=42, tension=1)
    f2 = engine.render_frame(w, h, time_sec=2.0, duration_sec=5.0, archetype_id="dark_forest", seed=42, tension=1)
    f3 = engine.render_frame(w, h, time_sec=2.0, duration_sec=5.0, archetype_id="dark_forest", seed=99, tension=1)
    assert np.array_equal(f1, f2)
    assert not np.array_equal(f1, f3)


def test_render_frame_time_progression(engine):
    """Verify different timestamps produce distinct frames."""
    w, h = 128, 128
    f_t0 = engine.render_frame(w, h, time_sec=0.0, duration_sec=5.0, archetype_id="synaptic_network", seed=42)
    f_t1 = engine.render_frame(w, h, time_sec=2.5, duration_sec=5.0, archetype_id="synaptic_network", seed=42)
    assert not np.array_equal(f_t0, f_t1)


def test_render_frame_custom_params(engine):
    """Verify custom params dict is passed into uniform buffer without errors."""
    w, h = 128, 128
    params = {
        "noise_scale": 2.5,
        "speed": 1.5,
        "accent_color": (0.2, 0.8, 0.4),
        "distortion": 0.5,
        "glow_intensity": 2.0,
        "custom_1": 1.0,
        "custom_2": 2.0,
        "custom_3": 3.0,
    }
    frame = engine.render_frame(
        w, h, time_sec=1.0, duration_sec=5.0, archetype_id="tactical_chamber", params=params
    )
    assert frame.shape == (h, w, 4)


def test_render_frame_resolution_switch(engine):
    """Verify engine dynamically adapts when consecutive render calls have different resolutions."""
    f1 = engine.render_frame(width=100, height=200, time_sec=0.0, duration_sec=1.0, archetype_id="cosmic_singularity")
    assert f1.shape == (200, 100, 4)
    f2 = engine.render_frame(width=300, height=150, time_sec=0.0, duration_sec=1.0, archetype_id="cosmic_singularity")
    assert f2.shape == (150, 300, 4)


def test_render_frame_invalid_inputs(engine):
    """Verify invalid parameters raise appropriate exceptions."""
    # Invalid dimensions
    with pytest.raises(ValueError, match="dimensions"):
        engine.render_frame(width=0, height=100, time_sec=0.0, duration_sec=1.0, archetype_id="cosmic_singularity")
    with pytest.raises(ValueError, match="dimensions"):
        engine.render_frame(width=100, height=-10, time_sec=0.0, duration_sec=1.0, archetype_id="cosmic_singularity")
    # Invalid duration
    with pytest.raises(ValueError, match="duration_sec"):
        engine.render_frame(width=100, height=100, time_sec=0.0, duration_sec=0.0, archetype_id="cosmic_singularity")
    # Unknown archetype
    with pytest.raises(KeyError, match="Unknown archetype_id"):
        engine.render_frame(width=100, height=100, time_sec=0.0, duration_sec=1.0, archetype_id="nonexistent_galaxy")
    # Mismatched out_buffer
    bad_buf = np.zeros((50, 50, 4), dtype=np.uint8)
    with pytest.raises(ValueError, match="out_buffer"):
        engine.render_frame(width=100, height=100, time_sec=0.0, duration_sec=1.0, archetype_id="cosmic_singularity", out_buffer=bad_buf)


def test_context_manager_and_close():
    """Verify context manager cleanly opens and closes resources."""
    with NativeProceduralEngine() as eng:
        frame = eng.render_frame(width=64, height=64, time_sec=0.0, duration_sec=1.0, archetype_id="cosmic_singularity")
        assert frame.shape == (64, 64, 4)
    assert eng._texture is None
    assert eng._staging_buf is None


def test_tactical_chamber_even_seed_differentiation(engine):
    """Verify tactical_chamber produces distinct output for even seed deltas (e.g. 100 vs 200)."""
    f100 = engine.render_frame(width=256, height=256, time_sec=0.5, duration_sec=5.0, archetype_id="tactical_chamber", seed=100)
    f200 = engine.render_frame(width=256, height=256, time_sec=0.5, duration_sec=5.0, archetype_id="tactical_chamber", seed=200)
    assert not np.array_equal(f100, f200)


def test_tactical_chamber_time_progression_in_strobe_dark_phase(engine):
    """Verify tactical_chamber produces distinct frames between different timestamps even during strobe dark phases."""
    # Test multiple timestamps
    f_t0 = engine.render_frame(width=256, height=256, time_sec=0.1, duration_sec=5.0, archetype_id="tactical_chamber", seed=42)
    f_t1 = engine.render_frame(width=256, height=256, time_sec=0.3, duration_sec=5.0, archetype_id="tactical_chamber", seed=42)
    assert not np.array_equal(f_t0, f_t1)
