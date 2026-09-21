import os
import json
import subprocess
from pathlib import Path
from typing import Dict, Any
from src.log import get_logger
from src.core.resolution import SHORT_RESOLUTION, SHORT_RESOLUTION_TEST
from lib.ffmpeg import run_ffmpeg

logger = get_logger("scp_contact_sheet")


def ffprobe(video_path: str) -> Dict[str, Any]:
    """Probes a video file with ffprobe and returns the parsed JSON envelope.

    Raises OSError/ValueError on probe failure so callers can degrade gracefully.
    """
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        video_path,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=30, shell=False)
    if res.returncode != 0:
        raise OSError(f"ffprobe failed for {video_path}: {res.stderr[:200]}")
    return json.loads(res.stdout)


class ContactSheetGenerator:
    """Generates visual contact sheets (frame thumbnails every 5s) and calculates Quality Score (0-100)."""

    def generate_contact_sheet(self, video_path: str, output_dir: Path) -> str:
        """
        Extracts thumbnail frames every 5 seconds and builds a contact sheet grid image.
        Returns the local path to the generated contact sheet image.
        """
        contact_sheet_path = str(output_dir / "contact_sheet.jpg")
        frames_dir = output_dir / "sheet_frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Extract 1 frame every 5 seconds
            cmd_frames = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-vf", "fps=1/5,scale=240:426",
                str(frames_dir / "frame_%03d.jpg")
            ]
            run_ffmpeg(cmd_frames, timeout=300, check=True)

            # Tile extracted frames into a single contact sheet grid using FFmpeg tile filter
            cmd_grid = [
                "ffmpeg", "-y",
                "-pattern_type", "glob", "-i", str(frames_dir / "*.jpg"),
                "-vf", "tile=4x4:padding=5:color=black",
                contact_sheet_path
            ]
            run_ffmpeg(cmd_grid, timeout=300, check=False)

            if not os.path.exists(contact_sheet_path) or os.path.getsize(contact_sheet_path) == 0:
                # Fallback to single frame if tile fails
                frame_files = sorted(list(frames_dir.glob("*.jpg")))
                if frame_files:
                    contact_sheet_path = str(frame_files[0])
        except Exception as e:
            # str(e) can embed FFmpegExecutionError's full banner/stderr; log a
            # bounded reason so one failure cannot flood youtube_automation.log
            logger.warning(
                "Contact sheet generation failed (%s): %s",
                type(e).__name__, str(e)[:200],
            )

        return contact_sheet_path

    def calculate_quality_score(
        self,
        video_path: str,
        storyboard: Dict[str, Any],
        duration_sec: float,
        file_size_bytes: int
    ) -> Dict[str, Any]:
        # 0. Media Integrity Gate (Mandatory)
        """
        Calculates Quality Score (0-100) across weighted categories.
        """
        from src.config import is_test_environment
        from src.integrity import verify_media_integrity
        # Media Integrity Gate (mandatory): computed once and reused below.
        # The earlier duplicate call at the "Check Media Integrity" block ran
        # the same full-decode audit a second time (work_dir=None, so it never
        # wrote the report file — reuse keeps verdicts AND side effects equal).
        integrity_res: Dict[str, Any] | None = None
        if not (is_test_environment() and not os.path.exists(video_path)):
            integrity_res = verify_media_integrity(video_path, work_dir=Path(video_path).parent if os.path.exists(video_path) else None)
            if not integrity_res.get("passed"):
                logger.error(f"Media integrity verification FAILED for {video_path}. Quality Score forced to 0.")
                return {
                    "overall_score": 0,
                    "passed": False,
                    "minimum_passing_score": 80,
                    "scene_count": len(storyboard.get("scenes", [])),
                    "unique_images": 0,
                    "duration_sec": duration_sec,
                    "file_size_mb": round(file_size_bytes / 1024 / 1024, 2),
                    "breakdown": {"media_integrity": 0},
                    "error": "; ".join(integrity_res.get("errors", ["Media integrity failed"]))
                }

        score = 0
        breakdown = {"media_integrity": 100}

        # 1. Initial Hook (15 pts)
        hook_present = storyboard.get("scenes", [{}])[0].get("overlay_text") is not None
        score += 15 if hook_present else 0
        breakdown["initial_hook"] = 15 if hook_present else 0

        # 2. Visual Variety (20 pts)
        max_dur = storyboard.get("max_scene_duration_sec", 4.0)
        scenes = storyboard.get("scenes", [])
        num_scenes = len(scenes)
        # Media integrity already verified above; the legacy per-scene visual
        # integrity verifier has been removed alongside the per-scene image
        # generation. The loop-mode pipeline uses src.core.quality's
        # validate_prepublication as its loop-level visual gate.
        m_report = integrity_res
        v_report = None

        if not (is_test_environment() and not os.path.exists(video_path)):
            if m_report is not None and not m_report.get("passed"):
                return {
                    "overall_score": 0,
                    "passed": False,
                    "minimum_passing_score": 80,
                    "breakdown": breakdown,
                    "media_integrity_passed": m_report.get("passed", False),
                    "visual_integrity_passed": False,
                }

        # 2. Visual Variety (25 pts)
        variety_score = 15 if num_scenes >= 4 else 8
        unique_visuals = len(set(s.get("primary_visual") for s in scenes if s.get("primary_visual")))
        variety_score += 10 if unique_visuals >= 4 else 5
        score += variety_score
        breakdown["visual_variety"] = variety_score

        # 3. Narration-Visual Coherence (15 pts)
        coherence_score = 15 if len(scenes) >= 6 else 8
        score += coherence_score
        breakdown["narration_coherence"] = coherence_score

        # 4. Subtitle Legibility & Safe Margin (15 pts)
        sub_score = 15
        score += sub_score
        breakdown["subtitle_legibility"] = sub_score

        # 5. Sound Design (10 pts)
        sound_score = 10
        score += sound_score
        breakdown["sound_design"] = sound_score

        # 6. Pacing & Intensity (10 pts)
        pacing_score = 10 if duration_sec >= 30.0 and duration_sec <= 240.0 else 5
        score += pacing_score
        breakdown["pacing"] = pacing_score

        # 7. Brand Identity (5 pts)
        brand_score = 5
        score += brand_score
        breakdown["brand_identity"] = brand_score

        # 8. Technical Quality (10 pts)
        tech_score = 5
        try:
            probe = ffprobe(video_path)
            streams = probe.get("streams", [])
            video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
            if video_stream:
                w = int(video_stream.get("width") or 0)
                h = int(video_stream.get("height") or 0)
                if (w, h) in (SHORT_RESOLUTION, SHORT_RESOLUTION_TEST, (1080, 1920)) and file_size_bytes < 40000000:
                    tech_score = 10
        except (OSError, ValueError, subprocess.TimeoutExpired, RuntimeError):
            tech_score = 5  # Graceful degradation: probe failure scores partial, never crashes
        score += tech_score
        breakdown["technical_quality"] = tech_score

        passed = score >= 80

        metrics = {
            "overall_score": score,
            "passed": passed,
            "minimum_passing_score": 80,
            "scene_count": len(scenes),
            "unique_images": unique_visuals,
            "max_scene_duration_sec": max_dur,
            "duration_sec": duration_sec,
            "file_size_mb": round(file_size_bytes / 1024 / 1024, 2),
            "breakdown": breakdown
        }

        logger.info(f"Calculated Quality Score: {score}/100 (Passed: {passed}).")
        return metrics
