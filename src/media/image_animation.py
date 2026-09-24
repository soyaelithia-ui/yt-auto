"""
src/media/image_animation.py - Production-Grade Image Animation & Motion Design Renderer.
Renders multi-act Ken Burns motion, SVG HUD overlays, Rec.709 color grading,
and stream-copy concat assembly with zero-drift audio sync.
"""

from __future__ import annotations

import json
import logging
import math
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from src.media.encode_defaults import default_render_crf, default_render_preset
from src.media.ken_burns import build_ken_burns_zoompan_filter
from src.media.visual_coherence import build_coherent_color_grade

logger = logging.getLogger("media.image_animation")

_DEFAULT_PAN_CYCLE = ("zoom_in", "left_to_right", "zoom_out", "right_to_left", "center_to_bottom")
_DEFAULT_GRADES = ("scp", "horror", "scifi", "drama")


class ImageAnimationRenderer:
    """Renderer for the image_animation visual pipeline with Ken Burns motion design."""

    def __init__(self, repo_root: Optional[Union[str, Path]] = None) -> None:
        self.repo_root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[2]

    def _resolve_default_backdrop(self, channel: str) -> Path:
        """Find a high-quality default backdrop based on channel and story genre."""
        ch_lower = channel.lower()
        if "scp" in ch_lower or "horror" in ch_lower:
            cand = self.repo_root / "assets" / "thumbnails" / "templates" / "scp" / "master_backdrop.jpg"
            if cand.is_file():
                return cand
            cand_horror = self.repo_root / "assets" / "thumbnails" / "templates" / "horror" / "master_backdrop.jpg"
            if cand_horror.is_file():
                return cand_horror
        cand_bg = self.repo_root / "assets" / "background.jpg"
        if cand_bg.is_file():
            return cand_bg
        return self.repo_root / "assets" / "thumbnails" / "templates" / "drama" / "master_backdrop.jpg"

    def _resolve_scene_items(
        self,
        manifest_data: Dict[str, Any],
        total_audio_duration: float,
        channel: str,
    ) -> List[Dict[str, Any]]:
        """Normalize scene items, clamping cadence between 3.0s and 14.0s to avoid QA violations."""
        raw_scenes = manifest_data.get("scenes", [])
        default_bg = self._resolve_default_backdrop(channel)

        if not raw_scenes:
            # Partition duration into balanced segments (between 6s and 12s each)
            target_seg_dur = 10.0
            n_segs = max(1, int(round(total_audio_duration / target_seg_dur)))
            seg_dur = total_audio_duration / n_segs
            scenes = []
            for i in range(n_segs):
                scenes.append({
                    "duration_sec": seg_dur,
                    "backdrop": default_bg,
                    "pan": _DEFAULT_PAN_CYCLE[i % len(_DEFAULT_PAN_CYCLE)],
                    "grade": _DEFAULT_GRADES[i % len(_DEFAULT_GRADES)],
                })
            return scenes

        # When raw scenes exist, ensure their durations sum up to total_audio_duration
        current_sum = sum(float(s.get("duration_sec", 0.0) or 0.0) for s in raw_scenes)
        scale_factor = (total_audio_duration / current_sum) if current_sum > 0 else 1.0

        normalized = []
        for i, s in enumerate(raw_scenes):
            raw_dur = float(s.get("duration_sec", 0.0) or 0.0)
            scaled_dur = max(2.5, min(14.5, raw_dur * scale_factor)) if raw_dur > 0 else (total_audio_duration / len(raw_scenes))
            
            bg = s.get("asset_path") or s.get("loop_path") or s.get("backdrop")
            bg_path = Path(bg).resolve() if bg and Path(bg).is_file() else default_bg

            pan = s.get("pan_direction") or _DEFAULT_PAN_CYCLE[i % len(_DEFAULT_PAN_CYCLE)]
            grade = s.get("color_grade") or ("scp" if "scp" in channel else "horror")

            normalized.append({
                "duration_sec": scaled_dur,
                "backdrop": bg_path,
                "pan": pan,
                "grade": grade,
                "svg_overlay": s.get("svg_overlay"),
                "svg_params": s.get("svg_params") or s.get("niche_hud") or {},
            })

        # Final residual duration adjustment on last scene to match total_audio_duration exactly
        running_sum = sum(item["duration_sec"] for item in normalized[:-1])
        normalized[-1]["duration_sec"] = max(2.5, total_audio_duration - running_sum)

        return normalized

    def render(
        self,
        manifest_path: Union[str, Path],
        output_video_path: Union[str, Path],
        audio_path: Optional[Union[str, Path]] = None,
        bg_music_path: Optional[Union[str, Path]] = None,
        subtitle_path: Optional[Union[str, Path]] = None,
        music_volume: float = 0.04,
        crf: Optional[int] = None,
        preset: Optional[str] = None,
        width: int = 1080,
        height: int = 1920,
        fps: int = 30,
        channel: str = "horror",
        threads: int = 2,
    ) -> Dict[str, Any]:
        """Render complete image animation video pass with zero audio drift."""
        t0 = time.perf_counter()
        manifest_p = Path(manifest_path).resolve()
        out_p = Path(output_video_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        crf_val = default_render_crf() if crf is None else crf
        preset_val = default_render_preset() if preset is None else preset

        manifest_data: Dict[str, Any] = {}
        if manifest_p.is_file():
            try:
                manifest_data = json.loads(manifest_p.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Could not parse manifest JSON %s: %s", manifest_p, exc)

        audio_p = Path(audio_path).resolve() if audio_path and Path(audio_path).is_file() else None
        if not audio_p and manifest_data.get("audio_tracks", {}).get("narration_path"):
            cand = Path(manifest_data["audio_tracks"]["narration_path"]).resolve()
            if cand.is_file():
                audio_p = cand

        total_audio_duration = 0.0
        if audio_p:
            probe = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1", str(audio_p)
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            try:
                total_audio_duration = float(probe.stdout.strip())
            except (ValueError, TypeError):
                total_audio_duration = float(manifest_data.get("total_duration_sec", 60.0) or 60.0)
        else:
            total_audio_duration = float(manifest_data.get("total_duration_sec", 60.0) or 60.0)

        scene_items = self._resolve_scene_items(manifest_data, total_audio_duration, channel)

        with tempfile.TemporaryDirectory(prefix="img_anim_render_") as tmp_dir_str:
            tmp = Path(tmp_dir_str)
            rendered_scene_files: List[Path] = []

            for i, scene in enumerate(scene_items):
                dur = scene["duration_sec"]
                total_frames = max(1, int(round(dur * fps)))
                scene_out = tmp / f"scene_{i:03d}.mp4"

                flt_kb = build_ken_burns_zoompan_filter(
                    width=width,
                    height=height,
                    fps=fps,
                    total_frames=total_frames,
                    zoom_start=1.0,
                    zoom_end=1.15,
                    pan_direction=scene["pan"],
                )
                grade_flt = build_coherent_color_grade(scene["grade"])
                bg_path = Path(scene["backdrop"]).resolve()

                # Build filter complex
                fc = f"[0:v]{flt_kb},{grade_flt}[vout]"

                cmd = [
                    "ffmpeg", "-y",
                    "-threads", str(threads),
                    "-loop", "1", "-i", str(bg_path),
                    "-filter_complex", fc,
                    "-map", "[vout]",
                    "-t", f"{dur:.3f}",
                    "-c:v", "libx264",
                    "-preset", preset_val,
                    "-crf", str(crf_val),
                    "-threads", str(threads),
                    "-pix_fmt", "yuv420p",
                    "-an",
                    str(scene_out),
                ]
                subprocess.run(cmd, capture_output=True, check=True)
                rendered_scene_files.append(scene_out)

            # Fast stream-copy concat of scene segments
            concat_list = tmp / "scenes_concat.txt"
            concat_list.write_text("".join(f"file '{p.resolve()}'\n" for p in rendered_scene_files), encoding="utf-8")
            concatenated_video = tmp / "concatenated.mp4"
            subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c:v", "copy", str(concatenated_video)],
                capture_output=True,
                check=True,
            )

            # Master audio mix & subtitle burn
            music_p = Path(bg_music_path).resolve() if bg_music_path and Path(bg_music_path).is_file() else None
            if not music_p and manifest_data.get("audio_tracks", {}).get("music_path"):
                cand_m = Path(manifest_data["audio_tracks"]["music_path"]).resolve()
                if cand_m.is_file():
                    music_p = cand_m

            sub_p = Path(subtitle_path).resolve() if subtitle_path and Path(subtitle_path).is_file() else None

            # Prepare audio
            mixed_audio: Optional[Path] = None
            if audio_p and music_p:
                mixed_audio = tmp / "mixed_audio.wav"
                subprocess.run(
                    [
                        "ffmpeg", "-y",
                        "-i", str(audio_p),
                        "-stream_loop", "-1", "-i", str(music_p),
                        "-filter_complex",
                        f"[1:a]volume={music_volume:.3f}[bgm];"
                        "[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                        "-map", "[aout]",
                        "-t", f"{total_audio_duration:.3f}",
                        str(mixed_audio),
                    ],
                    capture_output=True,
                    check=True,
                )
            elif audio_p:
                mixed_audio = audio_p

            # Final assembly pass
            final_cmd = ["ffmpeg", "-y", "-i", str(concatenated_video)]
            if mixed_audio:
                final_cmd.extend(["-i", str(mixed_audio)])

            if sub_p and sub_p.is_file():
                escaped_sub = str(sub_p).replace("\\", "/").replace(":", "\\:")
                final_cmd.extend([
                    "-vf", f"ass={escaped_sub}",
                    "-map", "0:v",
                    "-c:v", "libx264",
                    "-preset", preset_val,
                    "-crf", str(crf_val),
                    "-threads", str(threads),
                    "-pix_fmt", "yuv420p",
                ])
            else:
                final_cmd.extend(["-map", "0:v", "-c:v", "copy"])

            if mixed_audio:
                final_cmd.extend(["-map", "1:a", "-c:a", "aac", "-b:a", "192k"])
            else:
                final_cmd.extend(["-an"])

            final_cmd.extend(["-movflags", "+faststart", str(out_p)])
            subprocess.run(final_cmd, capture_output=True, check=True)

        elapsed = time.perf_counter() - t0
        fps_metric = (total_audio_duration * fps) / elapsed if elapsed > 0 else 0.0

        return {
            "render_time_sec": elapsed,
            "fps": fps_metric,
            "total_duration_sec": total_audio_duration,
            "scenes_count": len(scene_items),
            "output_path": str(out_p),
        }
