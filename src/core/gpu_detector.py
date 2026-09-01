"""Intelligent GPU & Chromium Hardware Acceleration Detector (yt-auto v3.1).

Architectural Rule:
- Headless VPS / standard container environments WITHOUT a dedicated physical GPU device
  MUST use '--disable-gpu' to prevent Chromium GPU-process crashes.
- Dedicated hardware with accessible '/dev/dri/renderD128' DRI/EGL devices enables
  hardware acceleration flags.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

DRI_RENDER_DEVICE = "/dev/dri/renderD128"
DRI_CARD_DEVICE = "/dev/dri/card0"


def has_hardware_acceleration_support(device_path: str = DRI_RENDER_DEVICE) -> bool:
    """Check if direct DRI/EGL hardware rendering device exists and is accessible."""
    dev = Path(device_path)
    return dev.exists() and os.access(dev, os.R_OK | os.W_OK)


def resolve_chromium_gpu_flags(
    force_software: bool = False,
    custom_device: Optional[str] = None,
) -> List[str]:
    """Return optimal Chromium CLI launch flags for the host environment."""
    if force_software or os.environ.get("FORCE_SOFTWARE_RENDER", "0") == "1":
        return ["--disable-gpu", "--disable-software-rasterizer"]

    target_dev = custom_device or DRI_RENDER_DEVICE
    if has_hardware_acceleration_support(target_dev):
        return [
            "--use-gl=egl",
            "--enable-gpu-rasterization",
            f"--gpu-sandbox-failures-fatal=no",
        ]

    # Default fail-safe for headless Linux VPS
    return ["--disable-gpu", "--disable-dev-shm-usage"]


def get_gpu_environment_status() -> Dict[str, Any]:
    """Inspection dictionary for runtime logging and diagnostics."""
    has_gpu = has_hardware_acceleration_support()
    flags = resolve_chromium_gpu_flags()
    return {
        "has_hardware_gpu": has_gpu,
        "render_device": DRI_RENDER_DEVICE if has_gpu else None,
        "recommended_flags": flags,
        "headless_safe": True,
    }
