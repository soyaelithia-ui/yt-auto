"""
src/cli/visual_inspect.py - Automated Visual QA, Keyframe Extraction, and Anomaly Detection.

Inspects rendered videos for visual regressions, extracts 5 deterministic keyframes (10%-90%),
and detects black screens (blackdetect) and video freezes (freezedetect) via FFmpeg analysis.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.ffmpeg import (
    probe_media,
    run_ffmpeg,
)

logger = logging.getLogger("visual_inspect")


@dataclass
class VisualQAResult:
    video_path: str
    duration_sec: float
    resolution: Tuple[int, int]
    keyframe_paths: List[str]
    black_intervals: List[Dict[str, float]]
    freeze_intervals: List[Dict[str, float]]
    overall_pass: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_keyframe_timestamps(duration_sec: float) -> List[float]:
    """Calculates 5 canonical keyframe timestamps at 10%, 30%, 50%, 70%, and 90% duration."""
    fractions = [0.10, 0.30, 0.50, 0.70, 0.90]
    return [round(duration_sec * f, 4) for f in fractions]


def parse_blackdetect_output(stderr: str, min_duration: float = 0.5) -> List[Dict[str, float]]:
    """Parses FFmpeg blackdetect stderr output and filters intervals >= min_duration."""
    intervals: List[Dict[str, float]] = []
    # Pattern: black_start:14.000000 black_end:15.200000 black_duration:1.200000
    pattern = re.compile(
        r"black_start:\s*([0-9.]+)\s+black_end:\s*([0-9.]+)\s+black_duration:\s*([0-9.]+)"
    )
    for match in pattern.finditer(stderr):
        start = float(match.group(1))
        end = float(match.group(2))
        dur = float(match.group(3))
        if dur >= min_duration:
            intervals.append({
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(dur, 3),
            })
    return intervals


def parse_freezedetect_output(stderr: str, min_duration: float = 2.0) -> List[Dict[str, float]]:
    """Parses FFmpeg freezedetect stderr output and filters intervals >= min_duration."""
    intervals: List[Dict[str, float]] = []
    # lavfi.freezedetect.freeze_start: 20.0
    # lavfi.freezedetect.freeze_duration: 3.5
    # lavfi.freezedetect.freeze_end: 23.5
    start_pattern = re.compile(r"(?:lavfi\.freezedetect\.)?freeze_start:\s*([0-9.]+)")
    dur_pattern = re.compile(r"(?:lavfi\.freezedetect\.)?freeze_duration:\s*([0-9.]+)")
    end_pattern = re.compile(r"(?:lavfi\.freezedetect\.)?freeze_end:\s*([0-9.]+)")

    starts = [float(m.group(1)) for m in start_pattern.finditer(stderr)]
    durs = [float(m.group(1)) for m in dur_pattern.finditer(stderr)]
    ends = [float(m.group(1)) for m in end_pattern.finditer(stderr)]

    count = min(len(starts), len(durs))
    for i in range(count):
        if durs[i] >= min_duration:
            end_t = ends[i] if i < len(ends) else starts[i] + durs[i]
            intervals.append({
                "start": round(starts[i], 3),
                "end": round(end_t, 3),
                "duration": round(durs[i], 3),
            })
    return intervals


def inspect_video_media(
    video_path: Union[str, Path],
    output_dir: Union[str, Path],
    black_threshold_sec: float = 0.5,
    freeze_threshold_sec: float = 2.0,
) -> VisualQAResult:
    """
    Runs automated visual QA inspection over a video file:
    1. Probes duration and resolution
    2. Extracts 5 deterministic keyframe PNG images
    3. Runs FFmpeg blackdetect filter
    4. Runs FFmpeg freezedetect filter
    5. Compiles JSON report
    """
    v_path = Path(video_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not v_path.is_file():
        raise FileNotFoundError(f"Video file not found: {v_path}")

    # 1. Probe Media
    probe_info = probe_media(v_path)
    if isinstance(probe_info, dict):
        fmt = probe_info.get("format") or {}
        duration = float(fmt.get("duration", 0.0))
        streams = probe_info.get("streams") or []
        v_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
        width = int(v_stream.get("width", 1080))
        height = int(v_stream.get("height", 1920))
    else:
        duration = float(getattr(probe_info, "duration", getattr(probe_info, "duration_sec", 0.0)))
        primary_v = getattr(probe_info, "primary_video", None) or (probe_info.video_streams[0] if getattr(probe_info, "video_streams", None) else None)
        width = primary_v.width if primary_v else 1080
        height = primary_v.height if primary_v else 1920

    # 2. Extract 5 Canonical Keyframes
    timestamps = compute_keyframe_timestamps(duration)
    keyframe_paths: List[str] = []

    for idx, ts in enumerate(timestamps, start=1):
        frame_name = f"keyframe_{idx}_{int(ts*1000)}ms.png"
        frame_out = out_dir / frame_name
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-ss", f"{ts:.3f}",
            "-i", str(v_path),
            "-vframes", "1",
            "-s", f"{width}x{height}",
            str(frame_out),
        ]
        try:
            res = run_ffmpeg(cmd, check=False)
            if res.returncode == 0 and frame_out.is_file() and frame_out.stat().st_size > 0:
                keyframe_paths.append(str(frame_out))
        except Exception:
            pass

    # 3. Detect Black Screen Artifacts
    black_cmd = [
        "ffmpeg", "-y", "-v", "info",
        "-i", str(v_path),
        "-vf", f"blackdetect=d={black_threshold_sec}:pic_th=0.98:pix_th=0.10",
        "-f", "null", "-",
    ]
    black_res = run_ffmpeg(black_cmd, check=False)
    black_intervals = parse_blackdetect_output(
        str(black_res.stderr), min_duration=black_threshold_sec
    )

    # 4. Detect Freeze Frame Artifacts
    freeze_cmd = [
        "ffmpeg", "-y", "-v", "info",
        "-i", str(v_path),
        "-vf", f"freezedetect=n=-60dB:d={freeze_threshold_sec}",
        "-f", "null", "-",
    ]
    freeze_res = run_ffmpeg(freeze_cmd, check=False)
    freeze_intervals = parse_freezedetect_output(
        str(freeze_res.stderr), min_duration=freeze_threshold_sec
    )

    # 5. Compile Outcome
    overall_pass = (
        len(black_intervals) == 0
        and len(freeze_intervals) == 0
        and len(keyframe_paths) == 5
        and all(Path(p).is_file() and Path(p).stat().st_size > 0 for p in keyframe_paths)
    )

    result = VisualQAResult(
        video_path=str(v_path),
        duration_sec=round(duration, 3),
        resolution=(width, height),
        keyframe_paths=keyframe_paths,
        black_intervals=black_intervals,
        freeze_intervals=freeze_intervals,
        overall_pass=overall_pass,
    )

    report_file = out_dir / "visual_qa_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, indent=2)

    logger.info("Visual QA completo: %s (Pass: %s)", v_path.name, overall_pass)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Visual QA Media Inspection Tool")
    parser.add_argument("--video", type=str, required=True, help="Input video MP4 path")
    parser.add_argument("--output-dir", type=str, default="output/visual_qa", help="Output directory for keyframes and report")
    parser.add_argument("--black-thresh", type=float, default=0.5, help="Black screen min duration threshold (s)")
    parser.add_argument("--freeze-thresh", type=float, default=2.0, help="Freeze frame min duration threshold (s)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    result = inspect_video_media(
        video_path=args.video,
        output_dir=args.output_dir,
        black_threshold_sec=args.black_thresh,
        freeze_threshold_sec=args.freeze_thresh,
    )

    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
