"""
src/media/pacing.py - Dynamic Scene Shot Pacing Engine.

Calculates adaptive shot distribution across narrative acts, avoiding static
caps and ensuring visually varied, cinematic pacing for longform and short video formats.

SSOT: both orientations use ~13s targets with 8–15s bounds. Totals under 12s may
stay a single shot; 12–15s stay one shot; anything above 15s splits (and totals
over 20s always have at least two shots).
"""
from __future__ import annotations

from typing import List

SHOT_TARGET_SEC = 13.0
SHOT_MIN_SEC = 8.0
SHOT_MAX_SEC = 15.0
SINGLE_SHOT_MAX_SEC = 15.0
SINGLE_SHOT_KEEP_UNDER_SEC = 12.0


def compute_dynamic_shot_pacing(
    total_duration_sec: float,
    orientation: str = "horizontal",
) -> List[float]:
    """Compute dynamic shot durations for a video production.

    - Both orientations: target ~13s per shot (bounds: 8.0s–15.0s).
    - Totals < 12s may stay 1 shot; 12–15s stay 1 shot; >15s split.
    - Totals > 20s always produce at least 2 shots.
    - Sum of shot durations exactly matches total_duration_sec.
    """
    total = round(float(total_duration_sec), 3)
    if total <= 0.0:
        return []

    # Orientation is accepted for call-site compatibility; bounds are shared.
    _ = str(orientation or "").lower().strip()

    if total < SINGLE_SHOT_KEEP_UNDER_SEC:
        return [total]
    if total <= SINGLE_SHOT_MAX_SEC:
        return [total]

    estimated_shots = max(2, int(round(total / SHOT_TARGET_SEC)))
    shot_len = total / estimated_shots
    while shot_len > SHOT_MAX_SEC:
        estimated_shots += 1
        shot_len = total / estimated_shots
    while shot_len < SHOT_MIN_SEC and estimated_shots > 2:
        estimated_shots -= 1
        shot_len = total / estimated_shots

    base_duration = round(total / estimated_shots, 3)
    durations = [base_duration] * (estimated_shots - 1)
    remainder = round(total - sum(durations), 3)
    durations.append(remainder)
    return durations
