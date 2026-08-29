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
class CameraTransform:
    """2.5D camera drift and transformation parameters."""
    offset_x: float = 0.0
    offset_y: float = 0.0
    rotation_deg: float = 0.0
    zoom_scale: float = 1.0

    def to_dict(self) -> dict:
        return {
            "offset_x": float(self.offset_x),
            "offset_y": float(self.offset_y),
            "rotation_deg": float(self.rotation_deg),
            "zoom_scale": float(self.zoom_scale),
        }

    @classmethod
    def from_dict(cls, data: dict) -> CameraTransform:
        return cls(
            offset_x=float(data.get("offset_x", 0.0)),
            offset_y=float(data.get("offset_y", 0.0)),
            rotation_deg=float(data.get("rotation_deg", 0.0)),
            zoom_scale=float(data.get("zoom_scale", 1.0)),
        )


@dataclass
class CameraState:
    pos_x: float
    pos_y: float
    pos_z: float
    rot_x: float
    rot_y: float
    rot_z: float
    fov: float
    zoom: float = 1.0


class CameraController:
    """
    Computes cinematic camera movement:
    1. Organic slow drift (pseudo-Perlin on position & Z-rotation, zoom in [1.00, 1.15])
    2. 2.5D transformation bounds (dx, dy <= 8%, roll <= 1.5 deg)
    3. Trauma & Shake Decay (shake = trauma^2 with exponential decay rate = 1.2)
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
        # 1. Smooth Organic Drift (dx, dy <= 8%, roll <= 1.5 deg, zoom in [1.00, 1.15])
        drift_x = pseudo_perlin_1d(t * 0.18, seed=seed) * 0.35
        drift_y = pseudo_perlin_1d(t * 0.14, seed=seed + 10.0) * 0.25
        drift_z = -t * 0.45
        rot_drift_z = pseudo_perlin_1d(t * 0.12, seed=seed + 20.0) * 0.026  # ~1.5 deg (0.026 rad)
        zoom = 1.0 + max(0.0, min(0.15, (pseudo_perlin_1d(t * 0.10, seed=seed + 30.0) + 1.0) * 0.075))

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
            shake_rot_z = math.sin(t * freq * 0.8) * shake * 0.05

            # Exponential decay
            self.trauma = max(0.0, self.trauma - self.decay_rate * delta_sec)

        # 3. Canvas boundary clamping
        pos_x = max(-0.85, min(0.85, drift_x + shake_x))
        pos_y = max(-0.85, min(0.85, drift_y + shake_y))
        rot_z = max(-0.06, min(0.06, rot_drift_z + shake_rot_z))

        return CameraState(
            pos_x=pos_x,
            pos_y=pos_y,
            pos_z=drift_z,
            rot_x=0.0,
            rot_y=0.0,
            rot_z=rot_z,
            fov=self.base_fov + shake * 4.0,
            zoom=zoom,
        )

    def get_transform(self, t: float, delta_sec: float = 0.033, seed: float = 42.0) -> CameraTransform:
        """Computes 2.5D CameraTransform (offset_x/y in [-0.08, 0.08], rotation_deg <= 1.5, zoom [1.00, 1.15])."""
        state = self.update(t=t, delta_sec=delta_sec, seed=seed)
        norm_offset_x = max(-0.08, min(0.08, state.pos_x * (0.08 / 0.35)))
        norm_offset_y = max(-0.08, min(0.08, state.pos_y * (0.08 / 0.25)))
        rot_deg = max(-1.5, min(1.5, state.rot_z * (180.0 / math.pi)))
        return CameraTransform(
            offset_x=norm_offset_x,
            offset_y=norm_offset_y,
            rotation_deg=rot_deg,
            zoom_scale=state.zoom,
        )
