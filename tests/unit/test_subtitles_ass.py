"""
tests/unit/test_subtitles_ass.py - Comprehensive Unit Tests for ASS Subtitles and Monotonic Sanitizer.
Covers F09 (ASS Subtitle Generator with Karaoke) and F10 (Monotonic Timestamp Sanitizer).
"""

from __future__ import annotations

import math
from pathlib import Path
import pytest

from src.media.subtitles_ass import (
    ASSSubtitleGenerator,
    calculate_font_size,
    calculate_safe_margins,
    escape_ffmpeg_filter_path,
    format_ass_timestamp,
    has_active_subtitles,
    sanitize_timestamps,
)


# ==============================================================================
# UT-F10: Unit Tests for Monotonic Timestamp Sanitizer (15 Scenarios)
# ==============================================================================

def test_ut_f10_01_empty_and_falsy_inputs():
    """Verify empty list, None, and dicts without words return empty list."""
    assert sanitize_timestamps([]) == []
    assert sanitize_timestamps(None) == []
    assert sanitize_timestamps([{}, {"word": ""}, {"word": "   "}, {"text": ""}]) == []
    assert sanitize_timestamps("invalid_string_input") == []  # type: ignore


def test_ut_f10_02_single_word_normal():
    """Verify single valid word timestamp is preserved."""
    raw = [{"word": "Singularity", "start": 1.25, "end": 2.0}]
    res = sanitize_timestamps(raw)
    assert len(res) == 1
    assert res[0]["word"] == "Singularity"
    assert res[0]["start"] == 1.25
    assert res[0]["end"] == 2.0


def test_ut_f10_03_negative_timestamps():
    """Verify negative start/end times are clamped to >= 0.0 with positive duration."""
    raw = [{"word": "Negative", "start": -2.5, "end": -1.0}]
    res = sanitize_timestamps(raw)
    assert len(res) == 1
    assert res[0]["start"] >= 0.0
    assert res[0]["end"] > res[0]["start"]
    assert res[0]["end"] - res[0]["start"] >= 0.08


def test_ut_f10_04_zero_duration_word():
    """Verify zero duration cue (start == end) is expanded to min_word_duration."""
    raw = [{"word": "Instant", "start": 3.0, "end": 3.0}]
    res = sanitize_timestamps(raw, min_word_duration=0.08)
    assert len(res) == 1
    assert res[0]["start"] == 3.0
    assert res[0]["end"] >= 3.08


def test_ut_f10_05_inverted_duration():
    """Verify inverted cue (end < start) is repaired with positive duration."""
    raw = [{"word": "Glitch", "start": 4.5, "end": 3.2}]
    res = sanitize_timestamps(raw, min_word_duration=0.1)
    assert len(res) == 1
    assert res[0]["start"] == 4.5
    assert res[0]["end"] >= 4.6


def test_ut_f10_06_overlapping_consecutive_words():
    """Verify overlapping words are shifted forward so start[n] >= end[n-1]."""
    raw = [
        {"word": "The", "start": 0.0, "end": 0.5},
        {"word": "Dark", "start": 0.3, "end": 0.8},   # Overlaps at 0.3
        {"word": "Forest", "start": 0.7, "end": 1.4}, # Overlaps at 0.7
    ]
    res = sanitize_timestamps(raw)
    assert len(res) == 3
    for i in range(1, len(res)):
        assert res[i]["start"] >= res[i-1]["end"], f"Causality violation at index {i}"


def test_ut_f10_07_completely_nested_overlap():
    """Verify word fully enclosed inside preceding word's duration is pushed past it."""
    raw = [
        {"word": "LongWord", "start": 0.0, "end": 3.0},
        {"word": "Inside", "start": 1.0, "end": 1.5},
    ]
    res = sanitize_timestamps(raw)
    assert len(res) == 2
    assert res[0]["start"] == 0.0
    assert res[0]["end"] == 3.0
    assert res[1]["start"] >= 3.0
    assert res[1]["end"] > res[1]["start"]


def test_ut_f10_08_identical_timestamps():
    """Verify multiple words with identical timestamps are serialized consecutively."""
    raw = [
        {"word": "A", "start": 1.0, "end": 1.0},
        {"word": "B", "start": 1.0, "end": 1.0},
        {"word": "C", "start": 1.0, "end": 1.0},
    ]
    res = sanitize_timestamps(raw, min_word_duration=0.08)
    assert len(res) == 3
    assert res[0]["start"] == 1.0
    assert res[1]["start"] >= res[0]["end"]
    assert res[2]["start"] >= res[1]["end"]


def test_ut_f10_09_out_of_order_timestamps():
    """Verify out-of-order sequence enforces monotonicity without backward time jumps."""
    raw = [
        {"word": "First", "start": 5.0, "end": 6.0},
        {"word": "Second", "start": 1.0, "end": 2.0},
    ]
    # Default (sort_by_time=False) preserves narrative text order
    res = sanitize_timestamps(raw, sort_by_time=False)
    assert len(res) == 2
    assert res[0]["word"] == "First"
    assert res[0]["start"] == 5.0
    assert res[1]["word"] == "Second"
    assert res[1]["start"] >= res[0]["end"]

    # sort_by_time=True sorts chronologically
    res_sorted = sanitize_timestamps(raw, sort_by_time=True)
    assert len(res_sorted) == 2
    assert res_sorted[0]["word"] == "Second"
    assert res_sorted[1]["word"] == "First"
    assert res_sorted[1]["start"] >= res_sorted[0]["end"]


def test_ut_f10_10_total_audio_duration_clamp():
    """Verify timestamps extending past total_audio_duration are compressed/clamped."""
    raw = [
        {"word": "One", "start": 0.0, "end": 2.0},
        {"word": "Two", "start": 2.0, "end": 4.0},
        {"word": "Three", "start": 4.0, "end": 6.0},
    ]
    res = sanitize_timestamps(raw, total_audio_duration=5.0)
    assert len(res) == 3
    assert res[-1]["end"] <= 5.0
    for i in range(1, len(res)):
        assert res[i]["start"] >= res[i-1]["end"]


def test_ut_f10_11_micro_durations():
    """Verify micro-durations (<10ms) are clamped so centisecond karaoke tags are >= 1cs."""
    raw = [{"word": "Micro", "start": 1.0, "end": 1.002}]
    res = sanitize_timestamps(raw, min_word_duration=0.08)
    dur = res[0]["end"] - res[0]["start"]
    assert int(round(dur * 100)) >= 1


def test_ut_f10_12_extreme_workload_scaling():
    """Verify performance and memory stability on 10,000 words in O(N)."""
    raw = [{"word": f"w{i}", "start": i * 0.1, "end": (i + 1) * 0.1} for i in range(10000)]
    res = sanitize_timestamps(raw)
    assert len(res) == 10000
    assert res[-1]["end"] >= 1000.0


def test_ut_f10_13_ass_special_characters_pruning():
    """Verify ASS override tags like {\\b1} or backslashes are escaped safely."""
    raw = [{"word": "{danger}\\tag}", "start": 0.0, "end": 1.0}]
    res = sanitize_timestamps(raw)
    assert len(res) == 1
    assert "{" not in res[0]["word"]
    assert "}" not in res[0]["word"]
    assert "\\" not in res[0]["word"]


def test_ut_f10_14_format_ass_timestamp_boundaries():
    """Verify ASS timestamp formatting across boundary values."""
    assert format_ass_timestamp(0.0) == "0:00:00.00"
    assert format_ass_timestamp(0.009) == "0:00:00.01"
    assert format_ass_timestamp(59.994) == "0:00:59.99"
    assert format_ass_timestamp(60.0) == "0:01:00.00"
    assert format_ass_timestamp(3599.99) == "0:59:59.99"
    assert format_ass_timestamp(3600.0) == "1:00:00.00"
    assert format_ass_timestamp(3661.05) == "1:01:01.05"
    assert format_ass_timestamp(7325.43) == "2:02:05.43"
    assert format_ass_timestamp(-5.0) == "0:00:00.00"


def test_ut_f10_15_ass_generator_integration(tmp_path: Path):
    """Verify ASSSubtitleGenerator produces valid .ass script with sanitized cues and karaoke tags."""
    generator = ASSSubtitleGenerator()
    out_file = tmp_path / "test.ass"
    raw = [
        {"word": "Hello", "start": 0.0, "end": 0.5},
        {"word": "World", "start": 0.4, "end": 0.9},  # Overlapping
    ]
    res_path = generator.generate_ass_file(raw, out_file, theme_name="scp_emerald")
    assert res_path.exists()
    content = res_path.read_text(encoding="utf-8")
    assert "[Script Info]" in content
    assert "[V4+ Styles]" in content
    assert "[Events]" in content
    assert "PlayResX: 1080" in content
    assert "PlayResY: 1920" in content
    assert ",480," in content or ",480" in content  # Canonical MarginV >= 480 for 1080x1920
    assert r"{\kf" in content
    assert "Dialogue:" in content


# ==============================================================================
# UT-F09: Unit Tests for ASS Themes, Palettes, Font Fallbacks, and Cue Grouping
# ==============================================================================

def test_ut_f09_theme_palettes(tmp_path: Path):
    """Verify all theme palettes inject correct BGR hex color codes into Style definition."""
    generator = ASSSubtitleGenerator()

    themes_to_check = {
        "scp_emerald": "&H0000FF00",
        "amber_crt": "&H0000A5FF",
        "cyber_cyan": "&H00FFFF00",
        "crimson_alert": "&H000000FF",
        "default": "&H0000FFFF",
    }

    for theme_name, expected_primary in themes_to_check.items():
        out_file = tmp_path / f"{theme_name}.ass"
        generator.generate_ass_file(
            word_timestamps=[{"word": "Test", "start": 0.0, "end": 1.0}],
            output_path=out_file,
            theme_name=theme_name,
        )
        content = out_file.read_text(encoding="utf-8")
        assert expected_primary in content, f"Theme {theme_name} missing {expected_primary}"


def test_ut_f09_font_hermetic_fallback(tmp_path: Path):
    """Verify generator falls back to Montserrat Black when Inter Bold font file is absent."""
    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir(parents=True)
    # Create fake Montserrat-Black.ttf on disk
    (fonts_dir / "Montserrat-Black.ttf").write_bytes(b"dummy font data")

    generator = ASSSubtitleGenerator(fonts_dir=fonts_dir)
    out_file = tmp_path / "fallback.ass"

    # Request Inter Bold which is absent in fonts_dir
    generator.generate_ass_file(
        word_timestamps=[{"word": "Fallback", "start": 0.0, "end": 1.0}],
        output_path=out_file,
        font_name="Inter Bold",
    )
    content = out_file.read_text(encoding="utf-8")
    assert "Montserrat Black" in content


def test_ut_f09_empty_word_timestamps_produces_valid_ass_header(tmp_path: Path):
    """Verify empty input creates valid ASS file with styles and 0 dialogue events."""
    generator = ASSSubtitleGenerator()
    out_file = tmp_path / "empty.ass"
    generator.generate_ass_file([], out_file)
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "[Script Info]" in content
    assert "[V4+ Styles]" in content
    assert "[Events]" in content
    assert "Dialogue:" not in content


def test_ut_f09_words_per_cue_chunking(tmp_path: Path):
    """Verify words_per_cue partitions words into predictable chunk sizes."""
    generator = ASSSubtitleGenerator()
    out_file = tmp_path / "chunks.ass"
    words = [{"word": f"word{i}", "start": i * 0.5, "end": (i + 1) * 0.5} for i in range(6)]

    # 6 words with words_per_cue=2 -> exactly 3 dialogue cues
    generator.generate_ass_file(words, out_file, words_per_cue=2)
    content = out_file.read_text(encoding="utf-8")
    dialogue_lines = [l for l in content.splitlines() if l.startswith("Dialogue:")]
    assert len(dialogue_lines) == 3


# ==============================================================================
# Phase 1: ASS Safe Zones, Dynamic Margins, Sentinel, and Escaping
# ==============================================================================

def test_calculate_safe_margins_portrait_and_drift():
    """1.1 RED: 1080x1920 portrait MarginV >= 480, MarginR >= 130, MarginL >= 64; +30px drift MarginV >= 510."""
    margin_l, margin_r, margin_v = calculate_safe_margins(1080, 1920)
    assert margin_v >= 480
    assert margin_r >= 130
    assert margin_l >= 64
    assert (margin_l, margin_r, margin_v) == (64, 130, 480)

    # Downward procedural camera drift +30px
    margin_l_drift, margin_r_drift, margin_v_drift = calculate_safe_margins(1080, 1920, downward_drift_px=30)
    assert margin_v_drift >= 510
    assert margin_v_drift == 510
    assert margin_r_drift >= 130
    assert margin_l_drift >= 64


def test_calculate_safe_margins_landscape():
    """1.1 RED: 1920x1080 landscape MarginV >= 130, MarginL/R >= 40."""
    margin_l, margin_r, margin_v = calculate_safe_margins(1920, 1080)
    assert margin_v >= 130
    assert margin_l >= 40
    assert margin_r >= 40
    assert (margin_l, margin_r, margin_v) == (40, 40, 130)


def test_calculate_font_size_adaptive():
    """1.2 RED: 52px at 1920h portrait, 38px at 1080h landscape."""
    assert calculate_font_size(1080, 1920) == 52
    assert calculate_font_size(1920, 1080) == 38


def test_has_active_subtitles_matrix(tmp_path: Path):
    """1.3 RED: Sentinel checks None, missing path, 0-byte file, header-only, whitespace Dialogue, valid Dialogue."""
    # 1. None
    assert has_active_subtitles(None) is False

    # 2. Missing path
    assert has_active_subtitles(tmp_path / "nonexistent.ass") is False

    # 3. 0-byte file
    empty_file = tmp_path / "empty.ass"
    empty_file.write_bytes(b"")
    assert has_active_subtitles(empty_file) is False

    # 4. Header-only file (no Dialogue:)
    header_only = tmp_path / "header_only.ass"
    header_only.write_text(
        "[Script Info]\nTitle: Test\n\n[V4+ Styles]\nFormat: Name, Fontname\nStyle: Default,Arial\n\n[Events]\nFormat: Layer, Start, End, Text\n",
        encoding="utf-8",
    )
    assert has_active_subtitles(header_only) is False

    # 5. Whitespace-only Dialogue:
    ws_dialogue = tmp_path / "ws_dialogue.ass"
    ws_dialogue.write_text(
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,   \n"
        "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,\t\n",
        encoding="utf-8",
    )
    assert has_active_subtitles(ws_dialogue) is False

    # 6. Valid Dialogue line
    valid_file = tmp_path / "valid.ass"
    valid_file.write_text(
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,Active subtitle content\n",
        encoding="utf-8",
    )
    assert has_active_subtitles(valid_file) is True

    # 7. SRT with cue text is active; header/timestamp-only SRT is not
    srt_active = tmp_path / "cue.srt"
    srt_active.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
    assert has_active_subtitles(srt_active) is True
    srt_empty = tmp_path / "empty_cues.srt"
    srt_empty.write_text("1\n00:00:00,000 --> 00:00:01,000\n\n", encoding="utf-8")
    assert has_active_subtitles(srt_empty) is False


def test_escape_ffmpeg_filter_path_threat_matrix():
    """1.4 RED: Threat matrix escaping colons, single quotes, and backslashes."""
    # Windows path backslashes converted to forward slashes
    win_path = r"C:\media\video\track.ass"
    assert escape_ffmpeg_filter_path(win_path) == "C\\:/media/video/track.ass"

    # Colons escaped with \:
    colon_path = "subtitle:final:v1.ass"
    assert escape_ffmpeg_filter_path(colon_path) == "subtitle\\:final\\:v1.ass"

    # Single quotes escaped with \'
    quote_path = "user's_file.ass"
    assert escape_ffmpeg_filter_path(quote_path) == "user\\'s_file.ass"

    # Combined complex injection path
    complex_path = r"C:\subtitles\user's:cut.ass"
    assert escape_ffmpeg_filter_path(complex_path) == "C\\:/subtitles/user\\'s\\:cut.ass"

    # Path object input
    path_obj = Path("simple_path/track.ass")
    assert escape_ffmpeg_filter_path(path_obj) == "simple_path/track.ass"


def test_generator_uses_dynamic_safe_margins_and_adaptive_font(tmp_path: Path):
    """1.6 RED: ASSSubtitleGenerator uses dynamic margins (MarginV >= 480 for 1080x1920) and adaptive font (52)."""
    generator = ASSSubtitleGenerator()
    out_portrait = tmp_path / "portrait.ass"
    generator.generate_ass_file(
        word_timestamps=[{"word": "Hello", "start": 0.0, "end": 1.0}],
        output_path=out_portrait,
        video_width=1080,
        video_height=1920,
    )
    content_p = out_portrait.read_text(encoding="utf-8")
    # MarginL=64, MarginR=130, MarginV=480, Fontsize=52
    assert "Style: Default,Montserrat Black,52," in content_p
    assert ",64,130,480,0" in content_p

    # Landscape 1920x1080: MarginL=40, MarginR=40, MarginV=130, Fontsize=38
    out_landscape = tmp_path / "landscape.ass"
    generator.generate_ass_file(
        word_timestamps=[{"word": "Hello", "start": 0.0, "end": 1.0}],
        output_path=out_landscape,
        video_width=1920,
        video_height=1080,
    )
    content_l = out_landscape.read_text(encoding="utf-8")
    assert "Style: Default,Montserrat Black,38," in content_l
    assert ",40,40,130,0" in content_l


def test_generator_safe_cue_chunking_clamped_to_max_3(tmp_path: Path):
    """1.2/1.6 RED: Cues chunk words into <= 3 words per event even if words_per_cue > 3 is requested."""
    generator = ASSSubtitleGenerator()
    out_file = tmp_path / "clamped_chunks.ass"
    words = [{"word": f"word{i}", "start": i * 0.5, "end": (i + 1) * 0.5} for i in range(6)]

    # Requesting 5 words per cue should be clamped to 3 -> 2 dialogue cues of 3 words each
    generator.generate_ass_file(words, out_file, words_per_cue=5)
    content = out_file.read_text(encoding="utf-8")
    dialogue_lines = [l for l in content.splitlines() if l.startswith("Dialogue:")]
    assert len(dialogue_lines) == 2


def test_libass_filter_clause_is_unquoted_for_ffmpeg_61(tmp_path: Path):
    """FFmpeg 6.1 libass rejects quote-wrapped filter paths; clause must stay unquoted."""
    import src.media.subtitles_ass as mod

    assert hasattr(mod, "libass_filter_clause")
    ass_path = tmp_path / "subs.ass"
    ass_path.write_text("[Script Info]\n", encoding="utf-8")
    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir()

    clause = mod.libass_filter_clause(ass_path, fonts_dir)
    assert clause.startswith("ass=filename=")
    assert "'" not in clause
    assert "ass=filename='" not in clause
    assert "fontsdir='" not in clause
    assert f"filename={ass_path}" in clause
    assert f"fontsdir={fonts_dir}" in clause



