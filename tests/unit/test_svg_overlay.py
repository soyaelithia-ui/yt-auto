"""
Unit tests for SVGOverlayEngine (Declarative vector HUD & overlay rasterization).
"""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from PIL import Image
import pytest

from src.media.svg_overlay import SVGOverlayEngine, resvg_py

ALL_8_PRESETS = [
    "rec_analog_hud",
    "cinematic_scope_bars",
    "classified_warning_banner",
    "drama_quote_card",
    "cyber_data_stream",
    "hud_tactical_telemetry",
    "scp_classification_stamp",
    "biometric_wave",
]


@pytest.fixture
def engine():
    return SVGOverlayEngine()


def test_svg_overlay_init(engine):
    """Verify SVGOverlayEngine initializes with valid assets directory."""
    assert engine.assets_dir.exists()
    for preset in ALL_8_PRESETS:
        assert (engine.assets_dir / f"{preset}.svg").exists(), f"Missing template: {preset}.svg"


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


@pytest.mark.parametrize("preset", ALL_8_PRESETS)
def test_render_overlay_all_8_presets(engine, preset):
    """Verify all 8 catalog presets render valid RGBA frames of shape (1920, 1080, 4) and (960, 540, 4)."""
    params = {
        "telemetry_text": "SYSTEM OK",
        "bpm": "72",
        "item_number": "173",
        "classification": "EUCLID",
        "spo2": "98",
        "rec_time": "00:14:32",
        "rec_date": "1994-10-24",
        "battery_pct": "84%",
        "tape_mode": "SP",
        "aspect_ratio_label": "2.39:1 CINEMATIC",
        "classification_tier": "LEVEL 4",
        "warning_message": "RESTRICTED ACCESS",
        "quote_text": "We suffer more often in imagination than in reality.",
        "author_name": "SENECA",
        "source_context": "Letters from a Stoic",
        "node_id": "OMEGA-9",
        "frequency_ghz": "14.28",
        "encryption_cipher": "AES-GCM-256",
        "coordinates": "45.109N 073.587W",
    }
    # Test vertical resolution
    res_v = engine.render_overlay(preset, width=1080, height=1920, time_sec=1.0, params=params)
    assert isinstance(res_v, np.ndarray)
    assert res_v.shape == (1920, 1080, 4)
    assert res_v.dtype == np.uint8

    # Test scaled resolution
    res_s = engine.render_overlay(preset, width=540, height=960, time_sec=1.0, params=params)
    assert isinstance(res_s, np.ndarray)
    assert res_s.shape == (960, 540, 4)
    assert res_s.dtype == np.uint8


def test_render_overlay_graceful_fallback_without_resvg(engine, monkeypatch):
    """Mocks resvg_py = None and verifies SVGOverlayEngine.render_overlay() falls back to Pillow rasterization,
    returning valid uint8 NumPy array without raising RuntimeError."""
    import src.media.svg_overlay as svg_mod

    monkeypatch.setattr(svg_mod, "resvg_py", None)
    res = engine.render_overlay("hud_tactical_telemetry", width=300, height=500)
    assert isinstance(res, np.ndarray)
    assert res.shape == (500, 300, 4)
    assert res.dtype == np.uint8


def test_render_overlay_lru_cache_eviction_at_128(engine, monkeypatch):
    """Renders 130 unique parameter combinations, asserts len(engine._raster_cache) <= 128,
    and verifies the least-recently used entry is evicted."""
    import src.media.svg_overlay as svg_mod

    dummy_img = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    buf = io.BytesIO()
    dummy_img.save(buf, format="PNG")
    dummy_bytes = buf.getvalue()

    fake_resvg = SimpleNamespace(svg_to_bytes=lambda **kwargs: dummy_bytes)
    monkeypatch.setattr(svg_mod, "resvg_py", fake_resvg)

    engine.clear_cache()
    for i in range(130):
        engine.render_overlay("hud_tactical_telemetry", width=64, height=64, params={"telemetry_text": f"VAL_{i}"})
    assert len(engine._raster_cache) == 128
    # The first inserted key ("VAL_0") should have been evicted
    first_key = ("hud_tactical_telemetry", 64, 64, (("telemetry_text", "VAL_0"),))
    assert first_key not in engine._raster_cache
    # The last inserted key ("VAL_129") should be present
    last_key = ("hud_tactical_telemetry", 64, 64, (("telemetry_text", "VAL_129"),))
    assert last_key in engine._raster_cache


def test_render_overlay_cache_info_and_clear(engine):
    """Asserts engine.cache_info() returns hit/miss counters and current size, and engine.clear_cache() flushes cached frames cleanly."""
    engine.clear_cache()
    info0 = engine.cache_info()
    assert info0.hits == 0
    assert info0.misses == 0
    assert info0.currsize == 0
    assert info0.maxsize == 128

    # First call: cache miss
    engine.render_overlay("hud_tactical_telemetry", width=100, height=100, params={"telemetry_text": "INFO_TEST"})
    info1 = engine.cache_info()
    assert info1.misses == 1
    assert info1.currsize == 1

    # Second call with same params: cache hit
    engine.render_overlay("hud_tactical_telemetry", width=100, height=100, params={"telemetry_text": "INFO_TEST"})
    info2 = engine.cache_info()
    assert info2.hits == 1
    assert info2.currsize == 1

    # Clear cache
    engine.clear_cache()
    info3 = engine.cache_info()
    assert info3.currsize == 0
    assert info3.hits == 0
    assert info3.misses == 0


def test_render_overlay_missing_parameters_clean_fallback(engine):
    """Asserts that invoking interpolate_template() with {} retains default text embedded in the SVG XML
    and leaves no residual unreplaced {{param}} or {param} tokens."""
    for preset in ALL_8_PRESETS:
        svg_text = engine.load_template(preset)
        interpolated = engine.interpolate_template(svg_text, params={})
        # Check no {{...}} or {...} dynamic tokens remain unparsed
        import re
        tokens = re.findall(r"\{\{([a-zA-Z0-9_]+)\}\}", interpolated)
        assert len(tokens) == 0, f"{preset} has residual double-brace tokens: {tokens}"


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


def test_render_overlay_raster_caching(engine):
    """Verify identical parameters hit raster cache and avoid re-rasterization."""
    params = {"telemetry_text": "CACHED", "bpm": "60"}
    res1 = engine.render_overlay("hud_tactical_telemetry", width=300, height=300, params=params)
    assert len(engine._raster_cache) >= 1
    res2 = engine.render_overlay("hud_tactical_telemetry", width=300, height=300, params=params)
    assert np.array_equal(res1, res2)


def test_render_overlay_invalid_out_buffer(engine):
    """Verify mismatched out_buffer raises ValueError."""
    bad_buf = np.zeros((50, 50, 4), dtype=np.uint8)
    with pytest.raises(ValueError, match="out_buffer"):
        engine.render_overlay("hud_tactical_telemetry", width=100, height=100, out_buffer=bad_buf)


def test_svg_overlay_buffer_shape_mismatch(engine):
    """Asserts render_overlay() with buffer having incorrect shape or incorrect dtype raises ValueError."""
    bad_shape_buf = np.zeros((1280, 720, 4), dtype=np.uint8)
    with pytest.raises(ValueError, match="out_buffer"):
        engine.render_overlay("none", width=1080, height=1920, out_buffer=bad_shape_buf)

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
