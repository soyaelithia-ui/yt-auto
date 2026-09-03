"""
tests/unit/test_multi_shot_cadence.py - Unit tests for dynamic multi-camera shot cadence in loop videos.
"""
import math
import pytest


def calculate_shot_cadence(total_audio_sec: float) -> tuple[int, list[float]]:
    """Mirrors the shot partitioning logic implemented in src/pipeline.py."""
    if total_audio_sec > 14.0:
        shot_count = max(2, min(4, int(math.ceil(total_audio_sec / 11.0))))
        per_shot_dur = round(total_audio_sec / shot_count, 3)
        shot_durations = [per_shot_dur] * (shot_count - 1)
        shot_durations.append(round(total_audio_sec - sum(shot_durations), 3))
        return shot_count, shot_durations
    else:
        return 1, [total_audio_sec]


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
        assert durations[0] == 9.0
        assert durations[1] == 9.0

    def test_mid_duration_splits_into_three_shots(self):
        count, durations = calculate_shot_cadence(30.0)
        assert count == 3
        assert len(durations) == 3
        assert sum(durations) == pytest.approx(30.0, abs=1e-3)

    def test_long_short_capped_at_four_shots(self):
        count, durations = calculate_shot_cadence(55.0)
        assert count == 4
        assert len(durations) == 4
        assert sum(durations) == pytest.approx(55.0, abs=1e-3)
        for dur in durations:
            assert 10.0 <= dur <= 16.0

    def test_duration_sum_invariance_across_range(self):
        for sec in [15.1, 22.3, 33.7, 44.2, 59.9]:
            count, durations = calculate_shot_cadence(sec)
            assert sum(durations) == pytest.approx(sec, abs=1e-3)
            assert len(durations) == count
