"""
tests/unit/test_multi_shot_cadence.py - Unit tests for dynamic multi-camera shot cadence.

SSOT is src.media.pacing.compute_dynamic_shot_pacing (pipeline imports the same helper).
"""
import pytest

from src.media.pacing import compute_dynamic_shot_pacing


def calculate_shot_cadence(
    total_audio_sec: float, orientation: str = "vertical"
) -> tuple[int, list[float]]:
    """Delegates to the pipeline SSOT so shorts >14s follow 8–15s cuts."""
    durations = compute_dynamic_shot_pacing(total_audio_sec, orientation=orientation)
    return len(durations), durations


class TestMultiShotCadence:
    def test_short_audio_stays_single_shot(self):
        count, durations = calculate_shot_cadence(12.5)
        assert count == 1
        assert durations == [12.5]

    def test_threshold_15s_splits_into_two_shots(self):
        count, durations = calculate_shot_cadence(18.0)
        assert count == 2
        assert len(durations) == 2
        assert sum(durations) == pytest.approx(18.0, abs=1e-3)
        assert all(8.0 <= d <= 15.0 for d in durations)

    def test_mid_duration_splits_into_two_or_more_shots(self):
        count, durations = calculate_shot_cadence(30.0)
        assert count >= 2
        assert len(durations) == count
        assert sum(durations) == pytest.approx(30.0, abs=1e-3)
        assert all(8.0 <= d <= 15.0 for d in durations)

    def test_long_short_respects_8_15s_band(self):
        count, durations = calculate_shot_cadence(55.0)
        assert count >= 2
        assert len(durations) == count
        assert sum(durations) == pytest.approx(55.0, abs=1e-3)
        for dur in durations:
            assert 8.0 <= dur <= 15.0

    def test_duration_sum_invariance_across_range(self):
        for sec in [15.1, 22.3, 33.7, 44.2, 59.9]:
            count, durations = calculate_shot_cadence(sec)
            assert sum(durations) == pytest.approx(sec, abs=1e-3)
            assert len(durations) == count
            assert count >= 2
            assert all(d <= 15.0 for d in durations)
