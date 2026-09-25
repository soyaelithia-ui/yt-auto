"""
Unit tests for SVGOverlayEngine (Declarative vector HUD & overlay rasterization).
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest

from src.media.svg_overlay import SVGOverlayEngine, resvg_py

requires_resvg = pytest.mark.skipif(resvg_py is None, reason="resvg-py optional dependency not installed")


@pytest.fixture
def engine():
    return SVGOverlayEngine()


def test_svg_overlay_init(engine):
    """Verify SVGOverlayEngine initializes with valid assets directory."""
    assert engine.assets_dir.exists()
    assert (engine.assets_dir / "hud_tactical_telemetry.svg").exists()
    assert (engine.assets_dir / "scp_classification_stamp.svg").exists()
    assert (engine.assets_dir / "biometric_wave.svg").exists()


def test_load_template_caching(engine):
    """Verify load_template reads SVG from disk and caches string in memory."""
    assert len(engine._template_cache) == 0
    t1 = engine.load_template("hud_tactical_telemetry")
    assert "<svg" in t1
    assert "hud_tactical_telemetry" in engine._template_cache
    # Second call returns cached string
    t2 = engine.load_template("hud_tactical_telemetry")
    assert t1 is t2


def test_load_template_missing(engine):
    """Verify non-existent preset raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        engine.load_template("nonexistent_preset_xyz")


def test_interpolate_template(engine):
    """Verify parameter interpolation for both double curly braces and single curly braces."""
    raw_svg = '<svg><text>{{telemetry_text}}</text><text>{bpm}</text><text>{{time_sec}}</text></svg>'
    interpolated = engine.interpolate_template(raw_svg, params={"telemetry_text": "ONLINE", "bpm": 75}, time_sec=2.5)
    assert "ONLINE" in interpolated
    assert "75" in interpolated
    assert "2.50" in interpolated


@pytest.mark.parametrize("none_preset", ["none", "NONE", "null", "", None])
def test_render_overlay_none_preset(engine, none_preset):
    """Verify empty or none preset returns all-zero transparent frame."""
    res = engine.render_overlay(none_preset, width=100, height=200)
    assert res.shape == (200, 100, 4)
    assert res.dtype == np.uint8
    assert np.all(res == 0)


@requires_resvg
@pytest.mark.parametrize("preset", ["hud_tactical_telemetry", "scp_classification_stamp", "biometric_wave"])
def test_render_overlay_all_presets(engine, preset):
    """Verify all 3 catalog presets render valid RGBA frames."""
    params = {
        "telemetry_text": "SYSTEM OK",
        "bpm": "72",
        "item_number": "173",
        "classification": "EUCLID",
        "spo2": "98",
    }
    res = engine.render_overlay(preset, width=540, height=960, time_sec=1.0, params=params)
    assert isinstance(res, np.ndarray)
    assert res.shape == (960, 540, 4)
    assert res.dtype == np.uint8
    # Overlay should have some non-transparent pixels
    assert np.any(res[:, :, 3] > 0)


@requires_resvg
def test_render_overlay_zero_allocation_out_buffer(engine):
    """Verify out_buffer is written in-place without reallocation."""
    out_buf = np.zeros((1920, 1080, 4), dtype=np.uint8)
    res = engine.render_overlay(
        "hud_tactical_telemetry",
        width=1080,
        height=1920,
        time_sec=0.0,
        params={"telemetry_text": "ZERO COPY", "bpm": "80"},
        out_buffer=out_buf,
    )
    assert id(res) == id(out_buf)
    assert np.shares_memory(res, out_buf)
    assert np.any(out_buf > 0)


@requires_resvg
def test_render_overlay_raster_caching(engine):
    """Verify identical parameters hit raster cache and avoid re-rasterization."""
    params = {"telemetry_text": "CACHED", "bpm": "60"}
    res1 = engine.render_overlay("hud_tactical_telemetry", width=300, height=300, params=params)
    assert len(engine._raster_cache) == 1
    res2 = engine.render_overlay("hud_tactical_telemetry", width=300, height=300, params=params)
    assert np.array_equal(res1, res2)

    # Different params add a new entry to cache
    params2 = {"telemetry_text": "DIFFERENT", "bpm": "90"}
    res3 = engine.render_overlay("hud_tactical_telemetry", width=300, height=300, params=params2)
    assert len(engine._raster_cache) == 2


def test_render_overlay_invalid_out_buffer(engine):
    """Verify mismatched out_buffer raises ValueError."""
    bad_buf = np.zeros((50, 50, 4), dtype=np.uint8)
    with pytest.raises(ValueError, match="out_buffer"):
        engine.render_overlay("hud_tactical_telemetry", width=100, height=100, out_buffer=bad_buf)


@requires_resvg
def test_render_overlay_arbitrary_aspect_ratios(engine):
    """Verify arbitrary aspect ratios (e.g. 1:1 square, 16:9 widescreen) return exact requested canvas shape."""
    for width, height in [(200, 200), (640, 360), (300, 500)]:
        out_buf = np.zeros((height, width, 4), dtype=np.uint8)
        res_buf = engine.render_overlay("hud_tactical_telemetry", width=width, height=height, out_buffer=out_buf)
        assert res_buf.shape == (height, width, 4)
        assert id(res_buf) == id(out_buf)
        assert np.shares_memory(res_buf, out_buf)

        res_alloc = engine.render_overlay("scp_classification_stamp", width=width, height=height)
        assert res_alloc.shape == (height, width, 4)


def test_svg_overlay_buffer_shape_mismatch(engine):
    """Asserts render_overlay() with buffer having incorrect shape (e.g. (1280, 720, 4) vs 1080x1920) or incorrect dtype raises ValueError."""
    # Shape mismatch: requested 1080x1920 (height=1920, width=1080), buffer is (1280, 720, 4)
    bad_shape_buf = np.zeros((1280, 720, 4), dtype=np.uint8)
    with pytest.raises(ValueError, match="out_buffer"):
        engine.render_overlay("none", width=1080, height=1920, out_buffer=bad_shape_buf)

    # Dtype mismatch: float32 instead of uint8
    bad_dtype_buf = np.zeros((1920, 1080, 4), dtype=np.float32)
    with pytest.raises(ValueError, match="out_buffer"):
        engine.render_overlay("none", width=1080, height=1920, out_buffer=bad_dtype_buf)


def test_svg_overlay_mustache_and_single_brace_interpolation(engine):
    """Asserts interpolate_template() replaces both {{key}} and {key} without residual placeholders."""
    template = '<svg><text>{{title}}</text><subtext>{subtitle}</subtext></svg>'
    result = engine.interpolate_template(template, params={"title": "SCP FOUNDATION", "subtitle": "EUCLID CLASS"})
    assert "{{title}}" not in result
    assert "{subtitle}" not in result
    assert "SCP FOUNDATION" in result
    assert "EUCLID CLASS" in result


def test_svg_overlay_raster_lru_cache_bounds(engine, monkeypatch):
    """Asserts raster cache is bounded at 128 entries to prevent unbounded resident memory growth."""
    import io
    from types import SimpleNamespace
    from PIL import Image
    import src.media.svg_overlay as svg_mod

    dummy_img = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    buf = io.BytesIO()
    dummy_img.save(buf, format="PNG")
    dummy_bytes = buf.getvalue()

    fake_resvg = SimpleNamespace(svg_to_bytes=lambda **kwargs: dummy_bytes)
    monkeypatch.setattr(svg_mod, "resvg_py", fake_resvg)

    for i in range(130):
        engine.render_overlay("hud_tactical_telemetry", width=64, height=64, params={"telemetry_text": f"VAL_{i}"})
    assert len(engine._raster_cache) <= 128
