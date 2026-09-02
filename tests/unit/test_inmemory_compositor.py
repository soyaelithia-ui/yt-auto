"""
Unit tests for InMemoryCompositor (Zero-allocation SIMD Porter-Duff Over frame compositor).
"""

from __future__ import annotations

import numpy as np
import pytest

from src.media.inmemory_compositor import InMemoryCompositor


@pytest.fixture
def compositor():
    return InMemoryCompositor(width=1080, height=1920)


def test_compositor_init(compositor):
    """Verify InMemoryCompositor allocates contiguous buffers of shape (height, width, 4)."""
    assert compositor.width == 1080
    assert compositor.height == 1920
    assert compositor.out_buffer.shape == (1920, 1080, 4)
    assert compositor.base_buffer.shape == (1920, 1080, 4)
    assert compositor.overlay_buffer.shape == (1920, 1080, 4)
    assert compositor.out_buffer.dtype == np.uint8


def test_composite_no_overlay(compositor):
    """Verify fast-path when overlay_rgba is None."""
    base = np.full((1920, 1080, 4), [120, 140, 160, 255], dtype=np.uint8)
    out = compositor.composite_frame(base, None)
    assert id(out) == id(compositor.out_buffer)
    assert np.array_equal(out, base)


def test_composite_transparent_overlay(compositor):
    """Verify fast-path when overlay has alpha == 0 everywhere."""
    base = np.full((1920, 1080, 4), [255, 128, 64, 255], dtype=np.uint8)
    overlay = np.zeros((1920, 1080, 4), dtype=np.uint8)
    out = compositor.composite_frame(base, overlay)
    assert id(out) == id(compositor.out_buffer)
    assert np.array_equal(out, base)


def test_composite_fully_opaque_overlay(compositor):
    """Verify fast-path when overlay has alpha == 255 everywhere."""
    base = np.full((1920, 1080, 4), [255, 0, 0, 255], dtype=np.uint8)
    overlay = np.full((1920, 1080, 4), [0, 0, 255, 255], dtype=np.uint8)
    out = compositor.composite_frame(base, overlay)
    assert id(out) == id(compositor.out_buffer)
    assert np.array_equal(out, overlay)


def test_composite_partial_solid_overlay(compositor):
    """Verify fast-path for non-zero pixels that are 100% opaque."""
    base = np.full((10, 10, 4), [200, 200, 200, 255], dtype=np.uint8)
    overlay = np.zeros((10, 10, 4), dtype=np.uint8)
    overlay[0:5, 0:5] = [255, 0, 0, 255]  # Top-left quadrant solid red

    out = compositor.composite_frame(base, overlay)
    assert np.array_equal(out[0:5, 0:5], overlay[0:5, 0:5])
    assert np.array_equal(out[5:10, 5:10], base[5:10, 5:10])


def test_composite_alpha_blending_mathematics():
    """Verify accurate Porter-Duff Over blending with fractional alpha."""
    comp = InMemoryCompositor(width=4, height=4)
    # Base: Solid Red (200, 0, 0, 255)
    base = np.full((4, 4, 4), [200, 0, 0, 255], dtype=np.uint8)
    # Overlay: 50% Green (0, 200, 0, 128)
    overlay = np.full((4, 4, 4), [0, 200, 0, 128], dtype=np.uint8)

    out = comp.composite_frame(base, overlay)
    # alpha_over = 128/255 ~ 0.50196
    # expected_red = 200 * (1 - 0.50196) = 99.6 ~ 100
    # expected_green = 200 * 0.50196 = 100.4 ~ 100
    assert 95 <= out[0, 0, 0] <= 105
    assert 95 <= out[0, 0, 1] <= 105
    assert out[0, 0, 2] == 0
    assert out[0, 0, 3] == 255


def test_get_memoryview_for_ffmpeg_stdin():
    """Verify get_memoryview returns 1D byte memoryview of length width * height * 4."""
    comp = InMemoryCompositor(width=64, height=48)
    base = np.full((48, 64, 4), [10, 20, 30, 255], dtype=np.uint8)
    comp.composite_frame(base)
    mv = comp.get_memoryview()
    assert isinstance(mv, memoryview)
    assert len(mv) == 64 * 48 * 4
    assert mv.itemsize == 1
    # Verify content match
    assert bytes(mv[:4]) == bytes([10, 20, 30, 255])


def test_dynamic_resolution_adaptation():
    """Verify compositor handles frames with dynamically varying resolutions."""
    comp = InMemoryCompositor(width=100, height=100)
    frame1 = np.full((100, 100, 4), [1, 2, 3, 255], dtype=np.uint8)
    out1 = comp.composite_frame(frame1)
    assert out1.shape == (100, 100, 4)

    # Change to 50x75
    frame2 = np.full((75, 50, 4), [4, 5, 6, 255], dtype=np.uint8)
    out2 = comp.composite_frame(frame2)
    assert out2.shape == (75, 50, 4)
    assert comp.width == 50
    assert comp.height == 75
    assert len(comp.get_memoryview()) == 50 * 75 * 4
