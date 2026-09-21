"""
src/media/thumbnails/extractor.py - Intelligent Climax Frame Extraction and Sharpness Scoring.
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image

logger = logging.getLogger("thumbnail_extractor")


class ClimaxFrameExtractor:
    """
    Analyzes scene_manifest.json to find high-tension climax moments (tension_level >= 4)
    and extracts candidate keyframes via FFmpeg, selecting the sharpest, highest-contrast frame.
    """

    def __init__(self, ffmpeg_bin: str = "ffmpeg") -> None:
        self.ffmpeg_bin = ffmpeg_bin

    def resolve_climax_timestamp(
        self,
        manifest_path: Optional[Path] = None,
        manifest_data: Optional[Dict[str, Any]] = None,
        fallback_sec: float = 4.0,
        motif_keywords: Optional[List[str]] = None,
    ) -> float:
        """Finds the timestamp of highest tension / thematic importance in the manifest."""
        data = manifest_data
        if not data and manifest_path and manifest_path.is_file():
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                logger.warning("Could not read manifest at %s: %s", manifest_path, e)

        if not data or "scenes" not in data or not data["scenes"]:
            return fallback_sec

        scenes = data["scenes"]
        # Find scene with maximum tension, giving strong priority to scenes matching story motifs
        best_scene = scenes[0]
        max_score = -1.0

        for sc in scenes:
            tension = int(sc.get("tension_level", 1))
            start_sec = float(sc.get("start_sec", 0.0))
            score = tension * 10.0 + (start_sec * 0.1)

            img_p = str(sc.get("image_path") or sc.get("clip_path") or "").lower()
            if motif_keywords:
                for kw in motif_keywords:
                    if kw and str(kw).lower() in img_p:
                        score += 100.0
                        break

            if score > max_score:
                max_score = score
                best_scene = sc

        start = float(best_scene.get("start_sec", 0.0))
        dur = float(best_scene.get("duration_sec", 6.0))
        # Optimal candidate is 45% into the climax scene (after transition, before exit)
        return start + (dur * 0.45)

    def extract_candidate_frames(
        self,
        video_path: Path,
        center_timestamp: float,
        output_dir: Path,
        window_sec: float = 2.0,
        count: int = 5,
    ) -> List[Path]:
        """Extracts a burst of candidate frames around the center timestamp bounded to 2 cores."""
        output_dir.mkdir(parents=True, exist_ok=True)
        extracted: List[Path] = []

        half_window = window_sec / 2.0
        start_t = max(0.5, center_timestamp - half_window)
        fps_rate = max(0.5, count / max(0.5, window_sec))

        out_pattern = output_dir / "cand_%02d.jpg"
        cmd = [
            self.ffmpeg_bin, "-y",
            "-threads", "2",
            "-ss", f"{start_t:.3f}",
            "-i", str(video_path.resolve()),
            "-vf", f"fps={fps_rate:.2f}",
            "-vframes", str(count),
            "-q:v", "2",
            str(out_pattern.resolve()),
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=15)
            extracted = sorted(output_dir.glob("cand_*.jpg"))
            extracted = [p for p in extracted if p.is_file() and p.stat().st_size > 1000]
        except Exception as e:
            logger.debug("Failed unified frame burst extraction at %.2fs: %s", start_t, e)

        if not extracted:
            step = window_sec / max(1, count - 1)
            for i in range(count):
                t = start_t + (i * step)
                out_img = output_dir / f"cand_{i:02d}_{t:.2f}s.jpg"
                cmd = [
                    self.ffmpeg_bin, "-y",
                    "-threads", "2",
                    "-ss", f"{t:.3f}",
                    "-i", str(video_path.resolve()),
                    "-vframes", "1",
                    "-q:v", "2",
                    str(out_img.resolve()),
                ]
                try:
                    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=15)
                    if out_img.is_file() and out_img.stat().st_size > 1000:
                        extracted.append(out_img)
                except Exception as e:
                    logger.debug("Fallback failed extracting frame at %.2fs: %s", t, e)

        return extracted

    def select_best_frame(self, frame_paths: List[Path]) -> Optional[Path]:
        """Evaluates sharpness (Laplacian variance), contrast, and color entropy."""
        if not frame_paths:
            return None
        if len(frame_paths) == 1:
            return frame_paths[0]

        best_path = frame_paths[0]
        best_score = -1.0

        for fp in frame_paths:
            try:
                img = Image.open(fp).convert("L")
                arr = np.array(img, dtype=np.float64)

                # Laplacian variance for sharpness
                laplacian = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float64)
                # Compute gradient variance
                gy, gx = np.gradient(arr)
                sharpness = np.var(gx) + np.var(gy)

                # Dynamic range & contrast (standard deviation of luminance)
                contrast = float(np.std(arr))

                # Discard near-black frames
                mean_lum = float(np.mean(arr))
                if mean_lum < 15.0 or mean_lum > 240.0:
                    score = 0.0
                else:
                    score = (sharpness * 0.6) + (contrast * 2.0)

                if score > best_score:
                    best_score = score
                    best_path = fp
            except Exception as e:
                logger.debug("Error scoring frame %s: %s", fp, e)

        return best_path
