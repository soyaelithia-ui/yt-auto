"""
src/rendering/camera_controller.py - Cinematic Camera Drift and Trauma Shake Engine.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple


def pseudo_perlin_1d(t: float, seed: float = 0.0) -> float:
    """Computes smooth continuous 1D pseudo-Perlin noise via harmonic summation."""
    val = (
        math.sin(t * 1.0 + seed) * 0.50 +
        math.sin(t * 2.3 + seed * 1.7) * 0.25 +
        math.sin(t * 4.7 + seed * 3.1) * 0.15 +
        math.sin(t * 9.1 + seed * 5.9) * 0.10
    )
    return val


@dataclass
class CameraState:
    pos_x: float
    pos_y: float
    pos_z: float
    rot_x: float
    rot_y: float
    rot_z: float
    fov: float


class CameraController:
    """
    Computes cinematic camera movement:
    1. Organic slow drift (pseudo-Perlin on position & Z-rotation)
    2. Trauma & Shake Decay (shake = trauma^2 with exponential decay rate = 1.2)
    """

    def __init__(self, decay_rate: float = 1.2, base_fov: float = 60.0) -> None:
        self.decay_rate = decay_rate
        self.base_fov = base_fov
        self.trauma: float = 0.0

    def add_trauma(self, amount: float) -> None:
        """Injects trauma [0.0, 1.0] from explosions, seismic anomalies or spatial tears."""
        self.trauma = min(1.0, self.trauma + max(0.0, float(amount)))

    def update(self, t: float, delta_sec: float = 0.033, seed: float = 42.0) -> CameraState:
        """
        Updates camera transform at time `t`.
        """
        # 1. Smooth Organic Drift
        drift_x = pseudo_perlin_1d(t * 0.18, seed=seed) * 0.35
        drift_y = pseudo_perlin_1d(t * 0.14, seed=seed + 10.0) * 0.25
        drift_z = -t * 0.45
        rot_drift_z = pseudo_perlin_1d(t * 0.12, seed=seed + 20.0) * 0.035

        # 2. Trauma Shake: shake = trauma^2
        shake = (self.trauma ** 2)
        shake_x = 0.0
        shake_y = 0.0
        shake_rot_z = 0.0

        if shake > 0.001:
            # High frequency jitter
            freq = 32.0
            shake_x = math.sin(t * freq) * shake * 0.45
            shake_y = math.cos(t * freq * 1.3) * shake * 0.45
            shake_rot_z = math.sin(t * freq * 0.8) * shake * 0.08

            # Exponential decay
            self.trauma = max(0.0, self.trauma - self.decay_rate * delta_sec)

        return CameraState(
            pos_x=drift_x + shake_x,
            pos_y=drift_y + shake_y,
            pos_z=drift_z,
            rot_x=0.0,
            rot_y=0.0,
            rot_z=rot_drift_z + shake_rot_z,
            fov=self.base_fov + shake * 4.0,
        )
