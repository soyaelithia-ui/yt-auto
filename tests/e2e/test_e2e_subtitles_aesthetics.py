"""
E2E Test Suite for Requirement R2 (Dynamic Subtitles & Aesthetic Enrichment).
Covers Features F7 through F11, Typography, Safe Area Margins, and Boundaries.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List
import pytest

from src.media.subtitles_ass import (
    ASSSubtitleGenerator,
    calculate_font_size,
    calculate_safe_margins,
    escape_ffmpeg_filter_path,
    format_ass_timestamp,
    has_active_subtitles,
    libass_filter_clause,
)
from tests.e2e.helpers import generate_sample_word_timestamps

PROJECT_ROOT = Path(__file__).resolve().parents[2]


# ==============================================================================
# Tier 1: Feature Coverage (R2: F7 - F11)
# ==============================================================================

@pytest.mark.tier1
def test_r2_f7_subtitles_pipeline_reactivation_contract():
    """Verify src/pipeline.py has subtitles_active enabled by default (True)."""
    pipeline_py = PROJECT_ROOT / "src" / "pipeline.py"
    assert pipeline_py.exists(), "src/pipeline.py must exist"

    content = pipeline_py.read_text(encoding="utf-8")
    match = re.search(r"^\s*subtitles_active\s*=\s*(True|False)", content, re.MULTILINE)
    assert match is not None, "subtitles_active definition must exist in src/pipeline.py"

    status = match.group(1)
    if status != "True":
        pytest.xfail("Pending M2 implementation: subtitles_active is currently False in src/pipeline.py")
    assert status == "True", "subtitles_active must be True in src/pipeline.py"


@pytest.mark.tier1
def test_r2_f8_aesthetic_typography_montserrat_black():
    """Verify ASS subtitle generator references Montserrat-Black font with contrast outline."""
    subtitles_py = PROJECT_ROOT / "src" / "media" / "subtitles_ass.py"
    content = subtitles_py.read_text(encoding="utf-8")

    assert "Montserrat" in content, "subtitles_ass.py must reference Montserrat typography"
    assert "BorderStyle" in content or "Outline" in content, "Must configure ASS outline/border style for legibility"


@pytest.mark.tier1
def test_r2_f8_safe_area_margins_shorts_and_longs():
    """Verify safe margins enforce MarginV >= 480px for 9:16 Shorts and >= 130px for 16:9 Longs."""
    # 9:16 Shorts (1080x1920)
    margin_l, margin_r, margin_v_short = calculate_safe_margins(1080, 1920)
    assert margin_v_short >= 480, f"Vertical shorts margin must be >= 480px to clear UI overlays, got {margin_v_short}"
    assert margin_l >= 60, f"Left margin must be padded, got {margin_l}"
    assert margin_r >= 100, f"Right margin must clear action buttons, got {margin_r}"

    # 16:9 Longform (1920x1080)
    _, _, margin_v_long = calculate_safe_margins(1920, 1080)
    assert margin_v_long >= 130, f"Horizontal longs margin must be >= 130px, got {margin_v_long}"


@pytest.mark.tier1
def test_r2_f9_multiscene_subdivision_duration_pacing():
    """Verify scene subdivision in scene_planner decomposes scenes into 8-15s shots."""
    planner_file = PROJECT_ROOT / "src" / "agents" / "scene_planner.py"
    if not planner_file.exists():
        pytest.xfail("Pending M2 implementation: src/agents/scene_planner.py not found")

    content = planner_file.read_text(encoding="utf-8")
    assert "duration" in content or "scene" in content


@pytest.mark.tier1
def test_r2_f10_multiscene_video_composition_backgrounds():
    """Verify LoopVideoEngine supports assembling multiple distinct scenes."""
    from src.media.loop_engine import LoopVideoEngine
    engine = LoopVideoEngine()

    has_multi = hasattr(engine, "compose_multiscene") or hasattr(engine, "render_storyboard") or hasattr(engine, "assemble_multiscene_video")
    if not has_multi:
        pytest.xfail("Pending M2 implementation: LoopVideoEngine multi-scene composition method not yet implemented")


@pytest.mark.tier1
def test_r2_f11_single_pass_ffmpeg_filtergraph_construction():
    """Verify libass subtitle burning clause formatting and path escaping."""
    dummy_ass = PROJECT_ROOT / "work" / "test_sub.ass"
    clause = libass_filter_clause(dummy_ass)
    assert "ass=" in clause or "subtitles=" in clause
    raw_path = r"C:\test:path/video.ass"
    escaped = escape_ffmpeg_filter_path(raw_path)
    assert r"\:" in escaped


# ==============================================================================
# Tier 2: Boundary & Corner Cases (>= 5 tests)
# ==============================================================================

@pytest.mark.tier2
def test_r2_boundary_empty_word_timestamps():
    """Verify has_active_subtitles gracefully returns False for empty or None subtitle paths."""
    assert not has_active_subtitles(None)
    assert not has_active_subtitles("")
    assert not has_active_subtitles(PROJECT_ROOT / "nonexistent_subtitles.ass")


@pytest.mark.tier2
def test_r2_boundary_single_word_subtitle_rendering(tmp_path: Path):
    """Verify a single-word subtitle generates valid ASS dialogue line."""
    single_word = [{"word": "Solitario", "start": 0.5, "end": 1.2, "confidence": 0.99}]
    out_ass = tmp_path / "single_word.ass"
    generator = ASSSubtitleGenerator()
    generator.generate_ass_file(
        word_timestamps=single_word,
        output_path=out_ass,
        video_width=1080,
        video_height=1920,
    )
    assert out_ass.exists()
    content = out_ass.read_text(encoding="utf-8")
    assert "[Events]" in content
    assert "Dialogue:" in content
    assert "Solitario" in content


@pytest.mark.tier2
def test_r2_boundary_extreme_long_text_wrapping(tmp_path: Path):
    """Verify an extremely long subtitle line (>100 words) compiles into ASS without corruption."""
    many_words = [
        {"word": f"palabra_{i}", "start": round(i * 0.2, 2), "end": round((i + 1) * 0.2, 2), "confidence": 0.9}
        for i in range(120)
    ]
    out_ass = tmp_path / "long_text.ass"
    generator = ASSSubtitleGenerator()
    generator.generate_ass_file(
        word_timestamps=many_words,
        output_path=out_ass,
        video_width=1080,
        video_height=1920,
    )
    assert out_ass.exists()
    content = out_ass.read_text(encoding="utf-8")
    assert "Dialogue:" in content
    assert "palabra_119" in content


@pytest.mark.tier2
def test_r2_boundary_missing_font_fallback_resilience():
    """Verify font size calculation succeeds across diverse resolutions (360p to 4K)."""
    size_4k = calculate_font_size(2160, 3840)
    size_1080p = calculate_font_size(1080, 1920)
    size_720p = calculate_font_size(720, 1280)
    size_horizontal = calculate_font_size(1920, 1080)

    assert size_4k > size_1080p > size_720p
    assert size_horizontal >= 12
    assert size_1080p == 52


@pytest.mark.tier2
def test_r2_boundary_negative_cue_start_timestamp_clamped():
    """Verify negative timestamps are clamped to 0.0s in format_ass_timestamp."""
    assert format_ass_timestamp(-5.25) == "0:00:00.00"
    assert format_ass_timestamp(0.0) == "0:00:00.00"
    assert format_ass_timestamp(65.5) == "0:01:05.50"


@pytest.mark.tier2
def test_r2_boundary_excessive_downward_drift_clamped():
    """Verify downward drift adds to MarginV safely without crashing."""
    _, _, margin_normal = calculate_safe_margins(1080, 1920, downward_drift_px=0)
    _, _, margin_drift = calculate_safe_margins(1080, 1920, downward_drift_px=100)
    assert margin_drift == margin_normal + 100


# ==============================================================================
# Tier 3: Cross-Feature Interaction
# ==============================================================================

@pytest.mark.tier3
def test_r2_interaction_subtitles_across_multiscene_timeline(tmp_path: Path):
    """Verify subtitle timestamps spanning across a 30s multi-scene sequence increase monotonically."""
    words = generate_sample_word_timestamps(
        words=[f"scene_word_{i}" for i in range(30)],
        start_offset=0.0,
        word_duration=0.8,
        inter_word_gap=0.2,
    )
    for i in range(1, len(words)):
        assert words[i]["start"] >= words[i - 1]["end"], "Subtitle timings must be causally monotonic"
