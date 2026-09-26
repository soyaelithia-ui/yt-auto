"""Unit test suite for Visual Coherence SSOT (timing scales, color curves, safe zones, and continuity)."""

from types import SimpleNamespace
import pytest

from src.media.visual_coherence import (
    build_coherent_color_grade,
    enforce_shorts_safe_zone,
    harmonize_scene_transitions,
    timing_scales_to_audio,
    validate_visual_continuity,
)


class TestVisualCoherenceTimingAndColor:
    """Tests for timing_scales_to_audio, build_coherent_color_grade, enforce_shorts_safe_zone, and continuity."""

    def test_timing_scales_to_audio_proportional(self):
        """Validates that raw durations [3.0, 4.0, 5.0] scaled to 15.0s yield [3.75, 5.0, 6.25],
        sum equals 15.0 within +-0.05s, and each duration >= 1.0s."""
        raw = [3.0, 4.0, 5.0]
        target = 15.0
        scaled = timing_scales_to_audio(raw, target)
        assert scaled == [3.75, 5.0, 6.25]
        assert abs(sum(scaled) - target) <= 0.05
        assert all(d >= 1.0 for d in scaled)

    def test_timing_scales_to_audio_rounding_residual(self):
        """Asserts that fractional rounding discrepancies (e.g. [3.33, 3.33, 3.33] to 10.0s)
        are fully absorbed by the final scene to equal exactly 10.00s."""
        raw = [3.33, 3.33, 3.33]
        target = 10.0
        scaled = timing_scales_to_audio(raw, target)
        assert sum(scaled) == pytest.approx(10.0, abs=1e-5)
        assert round(sum(scaled), 2) == 10.00

    def test_timing_scales_to_audio_degenerate(self):
        """Ensures target_duration of None, 0.0, or negative returns raw durations safely without raising ZeroDivisionError."""
        raw = [3.0, 4.0]
        assert timing_scales_to_audio(raw, None) == [3.0, 4.0]
        assert timing_scales_to_audio(raw, 0.0) == [3.0, 4.0]
        assert timing_scales_to_audio(raw, -5.0) == [3.0, 4.0]

    def test_build_coherent_color_grade_horror(self):
        """Channel 'horror' or default generates eq=contrast=1.06:saturation=0.88 and cool shadow colorbalance=rs=-0.02:gs=0.01:bs=0.02."""
        grade_horror = build_coherent_color_grade(channel="horror")
        grade_default = build_coherent_color_grade()
        for g in (grade_horror, grade_default):
            assert "eq=contrast=1.06:saturation=0.88" in g
            assert "colorbalance=rs=-0.02:gs=0.01:bs=0.02" in g

    def test_build_coherent_color_grade_drama(self):
        """Channel 'drama' generates eq=contrast=1.05:saturation=0.96:brightness=0.01 and warm skin balance colorbalance=rs=0.02:gs=0.01:bs=-0.03."""
        grade_drama = build_coherent_color_grade(channel="drama")
        assert "eq=contrast=1.05:saturation=0.96:brightness=0.01" in grade_drama
        assert "colorbalance=rs=0.02:gs=0.01:bs=-0.03" in grade_drama

    def test_build_coherent_color_grade_scifi(self):
        """Channel 'scifi' or 'singularidad' generates eq=contrast=1.08:saturation=0.92:brightness=-0.01 and cyan/blue lift bs=0.04:rh=-0.02:gh=0.02:bh=0.05."""
        grade_scifi = build_coherent_color_grade(channel="scifi")
        grade_sing = build_coherent_color_grade(channel="singularidad")
        for g in (grade_scifi, grade_sing):
            assert "eq=contrast=1.08:saturation=0.92:brightness=-0.01" in g
            assert "bs=0.04:rh=-0.02:gh=0.02:bh=0.05" in g

    def test_build_coherent_color_grade_fallback(self):
        """Unknown channel 'unknown_niche' or empty string defaults safely to dark ambient horror color grading without KeyError."""
        grade_unk = build_coherent_color_grade(channel="unknown_niche")
        grade_empty = build_coherent_color_grade(channel="")
        for g in (grade_unk, grade_empty):
            assert "eq=contrast=1.06:saturation=0.88" in g

    def test_enforce_shorts_safe_zone_vertical(self):
        """Resolution 1080x1920 enforces bottom >= 460, top >= 180, right >= 130, left >= 64,
        safe_width == 1080 - (left + right), and safe_height == 1920 - (top + bottom)."""
        sz = enforce_shorts_safe_zone(1080, 1920)
        assert sz["bottom"] >= 460
        assert sz["top"] >= 180
        assert sz["right"] >= 130
        assert sz["left"] >= 64
        assert sz["safe_width"] == 1080 - (sz["left"] + sz["right"])
        assert sz["safe_height"] == 1920 - (sz["top"] + sz["bottom"])

    def test_enforce_shorts_safe_zone_horizontal(self):
        """Resolution 1920x1080 enforces bottom >= 120, top >= 80, left >= 80, right >= 80, and safe_width == 1760."""
        sz = enforce_shorts_safe_zone(1920, 1080)
        assert sz["bottom"] >= 120
        assert sz["top"] >= 80
        assert sz["left"] >= 80
        assert sz["right"] >= 80
        assert sz["safe_width"] == 1760

    def test_enforce_shorts_safe_zone_arbitrary_aspect(self):
        """Resolution 720x1280 scales margins dynamically (25% bottom, 10% top) with positive integer dimensions."""
        sz = enforce_shorts_safe_zone(720, 1280)
        assert sz["bottom"] == max(460, int(1280 * 0.25))
        assert sz["top"] == max(180, int(1280 * 0.10))
        assert sz["safe_width"] > 0
        assert sz["safe_height"] > 0
        assert isinstance(sz["safe_width"], int)
        assert isinstance(sz["safe_height"], int)

    def test_validate_visual_continuity_valid(self):
        """Sequence of 4 scenes with durations [4.0, 5.0, 3.5, 6.0] returns valid: True,
        scene_count == 4, total_duration == 18.5, and 3 transition values."""
        scenes = [
            SimpleNamespace(duration_sec=4.0, tension_level=2),
            SimpleNamespace(duration_sec=5.0, tension_level=3),
            SimpleNamespace(duration_sec=3.5, tension_level=1),
            SimpleNamespace(duration_sec=6.0, tension_level=2),
        ]
        res = validate_visual_continuity(scenes)
        assert res["valid"] is True
        assert res["scene_count"] == 4
        assert res["total_duration"] == pytest.approx(18.5)
        assert len(res["recommended_transitions"]) == 3

    def test_validate_visual_continuity_zero_or_negative_duration(self):
        """Sequence containing duration 0.0 or -2.5 returns valid: False with reason 'zero_or_negative_duration'."""
        scenes1 = [
            SimpleNamespace(duration_sec=4.0, tension_level=2),
            SimpleNamespace(duration_sec=0.0, tension_level=2),
        ]
        res1 = validate_visual_continuity(scenes1)
        assert res1["valid"] is False
        assert res1["reason"] == "zero_or_negative_duration"

        scenes2 = [
            SimpleNamespace(duration_sec=-2.5, tension_level=2),
        ]
        res2 = validate_visual_continuity(scenes2)
        assert res2["valid"] is False
        assert res2["reason"] == "zero_or_negative_duration"

    def test_validate_visual_continuity_empty(self):
        """Empty sequence [] returns valid: False with reason 'empty_scenes'."""
        res = validate_visual_continuity([])
        assert res["valid"] is False
        assert res["reason"] == "empty_scenes"

    def test_harmonize_scene_transitions_tension_differential(self):
        """Adjacent scenes with Delta T = 3 return short crossfade (0.20 - 0.35s);
        steady tension Delta T = 0 returns gradual dissolve (0.35 - 0.75s);
        shorter scene capped at 30%; single scene returns []."""
        # Delta T = 3
        s_jump = [
            SimpleNamespace(duration_sec=5.0, tension_level=1),
            SimpleNamespace(duration_sec=5.0, tension_level=4),
        ]
        t_jump = harmonize_scene_transitions(s_jump)
        assert len(t_jump) == 1
        assert 0.20 <= t_jump[0] <= 0.35

        # Delta T = 0
        s_steady = [
            SimpleNamespace(duration_sec=5.0, tension_level=2),
            SimpleNamespace(duration_sec=5.0, tension_level=2),
        ]
        t_steady = harmonize_scene_transitions(s_steady)
        assert len(t_steady) == 1
        assert 0.35 <= t_steady[0] <= 0.75

        # Shorter scene capped at 30%
        s_short = [
            SimpleNamespace(duration_sec=0.8, tension_level=2),
            SimpleNamespace(duration_sec=5.0, tension_level=2),
        ]
        t_short = harmonize_scene_transitions(s_short)
        assert len(t_short) == 1
        assert t_short[0] <= 0.8 * 0.30 + 1e-4

        # Single scene returns empty
        assert harmonize_scene_transitions([SimpleNamespace(duration_sec=5.0, tension_level=2)]) == []
