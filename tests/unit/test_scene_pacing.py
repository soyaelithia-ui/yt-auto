import pytest
from src.media.pacing import SHOT_TARGET_SEC, compute_dynamic_shot_pacing


def test_longform_pacing_scales_appropriately():
    duration = 865.0  # 14.4 minutes
    durations = compute_dynamic_shot_pacing(duration, orientation="horizontal")

    assert all(8.0 <= d <= 15.0 for d in durations), (
        f"shots must be 8–15s, got min={min(durations)} max={max(durations)}"
    )
    expected_n = round(duration / SHOT_TARGET_SEC)
    assert abs(len(durations) - expected_n) <= 3, (
        f"Expected ~{expected_n} shots (total/13), got {len(durations)}"
    )
    assert pytest.approx(sum(durations), rel=1e-3) == duration


def test_short_pacing_scales_appropriately():
    duration = 44.0  # 44 seconds
    durations = compute_dynamic_shot_pacing(duration, orientation="vertical")

    assert 3 <= len(durations) <= 5, f"Expected 3-5 shots, got {len(durations)}"
    assert all(d <= 15.0 for d in durations), f"Found shot > 15s: {max(durations)}"
    assert all(d >= 8.0 for d in durations), f"Found shot < 8s: {min(durations)}"
    assert pytest.approx(sum(durations), rel=1e-3) == duration


def test_edge_cases_and_invalid_durations():
    assert compute_dynamic_shot_pacing(0.0, "horizontal") == []
    assert compute_dynamic_shot_pacing(-5.0, "vertical") == []
    assert compute_dynamic_shot_pacing(5.0, "horizontal") == [5.0]


def test_under_12s_stays_single_shot():
    assert compute_dynamic_shot_pacing(11.9, "horizontal") == [11.9]
    assert compute_dynamic_shot_pacing(12.0, "vertical") == [12.0]


def test_15s_stays_single_shot_16s_splits():
    assert compute_dynamic_shot_pacing(15.0, "horizontal") == [15.0]
    split = compute_dynamic_shot_pacing(16.0, "vertical")
    assert len(split) == 2
    assert pytest.approx(sum(split), abs=1e-3) == 16.0
    assert all(8.0 <= d <= 15.0 for d in split)


def test_over_20s_has_at_least_two_shots():
    shots = compute_dynamic_shot_pacing(21.0, "horizontal")
    assert len(shots) >= 2
    assert all(d <= 15.0 for d in shots)
    assert pytest.approx(sum(shots), abs=1e-3) == 21.0
