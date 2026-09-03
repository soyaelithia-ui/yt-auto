import pytest
from src.media.pacing import compute_dynamic_shot_pacing


def test_longform_pacing_scales_appropriately():
    duration = 865.0  # 14.4 minutes
    durations = compute_dynamic_shot_pacing(duration, orientation="horizontal")
    
    # Requirement: Between 15 and 45 shots
    assert 15 <= len(durations) <= 45, f"Expected 15-45 shots, got {len(durations)}"
    
    # Requirement: No shot exceeds 45s
    assert all(d <= 45.0 for d in durations), f"Found shot > 45s: {max(durations)}"
    assert all(d >= 10.0 for d in durations), f"Found shot < 10s: {min(durations)}"
    
    # Requirement: Total duration exact sum
    assert pytest.approx(sum(durations), rel=1e-3) == duration


def test_short_pacing_scales_appropriately():
    duration = 44.0  # 44 seconds
    durations = compute_dynamic_shot_pacing(duration, orientation="vertical")
    
    # Requirement: Between 3 and 5 shots
    assert 3 <= len(durations) <= 5, f"Expected 3-5 shots, got {len(durations)}"
    
    # Requirement: No shot exceeds 15s
    assert all(d <= 15.0 for d in durations), f"Found shot > 15s: {max(durations)}"
    assert all(d >= 5.0 for d in durations), f"Found shot < 5s: {min(durations)}"
    
    # Requirement: Total duration exact sum
    assert pytest.approx(sum(durations), rel=1e-3) == duration


def test_edge_cases_and_invalid_durations():
    assert compute_dynamic_shot_pacing(0.0, "horizontal") == []
    assert compute_dynamic_shot_pacing(-5.0, "vertical") == []
    assert compute_dynamic_shot_pacing(5.0, "horizontal") == [5.0]
