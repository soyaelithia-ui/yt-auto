"""
src/visual_integrity.py - Visual Integrity and Frame ROI Detail Verifier.
"""
from __future__ import annotations

import logging
import math
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import numpy as np
from PIL import Image, ImageFilter

from src.log import get_logger

logger = get_logger("visual_integrity")


class VisualIntegrityVerifier:
    """Verifies visual detail, entropy, and edge density across video keyframes."""

    def __init__(self, sample_fps: float = 1.0) -> None:
        self.sample_fps = float(sample_fps)

    def extract_frames(
        self,
        video_path: Union[str, Path, None],
        output_dir: Union[str, Path, None],
        fps: Optional[float] = None,
        max_sample_frames: int = 12,
    ) -> List[Path]:
        """Extracts sample frames from video using FFmpeg, bounded to max_sample_frames."""
        if not video_path or not output_dir:
            return []
        try:
            v_path = Path(video_path).resolve()
            if not v_path.is_file() or v_path.stat().st_size == 0:
                return []
        except Exception:
            return []

        try:
            out_dir = Path(output_dir).resolve()
            out_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            return []

        # Probe video duration to calculate bounded sample rate
        dur = 0.0
        try:
            cmd_probe = [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(v_path),
            ]
            res = subprocess.run(cmd_probe, capture_output=True, text=True, timeout=5.0)
            if res.returncode == 0 and res.stdout.strip():
                dur = float(res.stdout.strip())
        except Exception:
            dur = 0.0

        target_frames = max(1, int(max_sample_frames))
        base_fps = float(fps) if fps is not None else self.sample_fps
        if dur > 0:
            effective_fps = min(base_fps, max(0.005, target_frames / dur))
        else:
            effective_fps = base_fps

        pattern = out_dir / "frame_%04d.png"
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-threads", "2",
            "-i", str(v_path),
            "-an",
            "-vf", f"fps={effective_fps}",
            "-vframes", str(target_frames),
            "-pix_fmt", "rgb24",
            str(pattern),
        ]
        try:
            subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=60.0,
            )
        except Exception as exc:
            logger.debug("Frame extraction failed for %s: %s", v_path, exc)
            return []

        frames = sorted(list(out_dir.glob("frame_*.png")))
        return frames

    def analyze_frame_roi(self, im: Optional[Image.Image]) -> Dict[str, float]:
        """Calculates Shannon entropy and edge density for a frame."""
        if im is None:
            return {"entropy": 0.0, "edge_density": 0.0}
        try:
            gray = im.convert("L")
            arr = np.array(gray, dtype=np.float32)
            if arr.size == 0:
                return {"entropy": 0.0, "edge_density": 0.0}

            # 1. Shannon Entropy
            hist, _ = np.histogram(arr, bins=256, range=(0, 256), density=True)
            hist = hist[hist > 0]
            entropy = -float(np.sum(hist * np.log2(hist))) if len(hist) > 0 else 0.0

            # 2. Edge Density using Laplacian / Sobel magnitude
            edges = gray.filter(ImageFilter.FIND_EDGES)
            edge_arr = np.array(edges, dtype=np.float32)
            edge_density = float(np.mean(edge_arr)) if edge_arr.size > 0 else 0.0

            if math.isnan(entropy) or math.isinf(entropy):
                entropy = 0.0
            if math.isnan(edge_density) or math.isinf(edge_density):
                edge_density = 0.0

            return {
                "entropy": float(entropy),
                "edge_density": float(edge_density),
            }
        except Exception as exc:
            logger.debug("Frame ROI analysis failed: %s", exc)
            return {"entropy": 0.0, "edge_density": 0.0}
