"""FFmpeg complex filtergraph generation (Lanczos scaling, deband, safe areas, multi-shot)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.config import BASE_DIR
from src.core.resolution import SHORT_RESOLUTION
from src.log import get_logger
from src.media.encode_defaults import (
    default_ffmpeg_threads,
    default_render_crf,
    default_render_preset,
)
from src.media.subtitles_ass import (
    escape_ffmpeg_filter_path,
    has_active_subtitles,
    libass_filter_clause,
)

logger = get_logger("loop_filtergraph")


class LoopFilterGraphMixin:
    """Methods for generating video filter chains, multi-shot concat graphs, and quality metrics."""

    RESOLUTIONS: dict[str, tuple[int, int]]
    SUPPORTED_IMAGE_EXTENSIONS: tuple[str, ...]

    def parse_resolution(self, resolution_or_orientation: str | tuple[int, int] | list[int]) -> tuple[int, int]:
        """
        Parses resolution tuple or orientation identifier (e.g. 'vertical', 'horizontal', '9:16', '16:9').
        """
        if isinstance(resolution_or_orientation, (tuple, list)):
            if len(resolution_or_orientation) == 2:
                w, h = int(resolution_or_orientation[0]), int(resolution_or_orientation[1])
                if w > 0 and h > 0:
                    return (w, h)
            raise ValueError(f"Invalid resolution dimensions: {resolution_or_orientation}")

        if isinstance(resolution_or_orientation, str):
            key = resolution_or_orientation.strip().lower()
            if key in self.RESOLUTIONS:
                return self.RESOLUTIONS[key]

            m = re.match(r"^(\d+)[xX:](\d+)$", key)
            if m:
                w, h = int(m.group(1)), int(m.group(2))
                if w > 0 and h > 0:
                    return (w, h)

        raise ValueError(f"Unsupported aspect ratio or resolution: {resolution_or_orientation}")

    def build_video_filter(
        self,
        target_resolution: tuple[int, int] = SHORT_RESOLUTION,
        fps: int = 30,
        subtitle_path: str | Path | None = None,
        include_subtitles: bool = False,
        fonts_dir: str | Path | None = None,
    ) -> str:
        """
        Generates FFmpeg video filter graph for scaling, cropping to exact aspect ratio,
        and optionally burning in subtitles.
        """
        w, h = target_resolution
        base_filter = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps},setsar=1,format=yuv420p"

        if include_subtitles and subtitle_path and has_active_subtitles(subtitle_path):
            sub_p = Path(subtitle_path)
            resolved_fonts = Path(fonts_dir) if fonts_dir else (BASE_DIR / "assets" / "fonts")
            fonts_arg = resolved_fonts if resolved_fonts.exists() and resolved_fonts.is_dir() else None
            if sub_p.suffix.lower() == ".ass":
                sub_filter = libass_filter_clause(sub_p, fonts_arg)
            else:
                sub_escaped = escape_ffmpeg_filter_path(sub_p)
                fonts_clause = (
                    f":fontsdir={escape_ffmpeg_filter_path(fonts_arg)}" if fonts_arg else ""
                )
                sub_filter = f"subtitles=filename={sub_escaped}{fonts_clause}"

            return f"[0:v]{base_filter}[vbase];[vbase]{sub_filter}[vsubbed];[vsubbed]format=yuv420p[vout]"

        return f"[0:v]{base_filter}[vout]"

    def build_composition_filter_graph(
        self,
        video_path: Path,
        audio_path: Path,
        bgm_path: Path | None,
        target_resolution: tuple[int, int],
        duration_sec: float,
        include_subtitles: bool = False,
        subtitle_path: Path | None = None,
        **kwargs,
    ) -> list[str]:
        """
        Builds the complete list of FFmpeg CLI arguments for video composition.
        """
        v_path = Path(video_path)
        a_path = Path(audio_path)
        is_image = v_path.suffix.lower() in self.SUPPORTED_IMAGE_EXTENSIONS

        cmd: list[str] = ["ffmpeg", "-y"]

        if is_image:
            cmd.extend(["-loop", "1", "-i", str(v_path)])
        else:
            cmd.extend(["-stream_loop", "-1", "-i", str(v_path)])

        cmd.extend(["-i", str(a_path)])

        has_music = False
        if bgm_path:
            bg_p = Path(bgm_path)
            if bg_p.is_file() and bg_p.stat().st_size > 0:
                cmd.extend(["-stream_loop", "-1", "-i", str(bg_p)])
                has_music = True

        video_filter = self.build_video_filter(
            target_resolution=target_resolution,
            fps=kwargs.get("fps", 30),
            subtitle_path=subtitle_path,
            include_subtitles=include_subtitles,
            fonts_dir=kwargs.get("fonts_dir"),
        )
        audio_filter = getattr(self, "build_audio_filter")(
            has_music=has_music,
            music_volume=kwargs.get("music_volume", 0.04),
            ducking_threshold=kwargs.get("ducking_threshold", 0.035),
            ducking_ratio=kwargs.get("ducking_ratio", 8.0),
            ducking_attack_ms=kwargs.get("ducking_attack_ms", 20.0),
            ducking_release_ms=kwargs.get("ducking_release_ms", 350.0),
            lowpass_freq=kwargs.get("lowpass_freq", 12000),
            master_loudness=kwargs.get("master_loudness", True),
            target_lufs=kwargs.get("target_lufs", -16.0),
            max_tp=kwargs.get("max_tp", -1.5),
            lra=kwargs.get("lra", 11.0),
        )

        filter_complex = f"{video_filter};{audio_filter}"
        crf = kwargs.get("crf", default_render_crf())
        preset = kwargs.get("preset", default_render_preset())
        threads = kwargs.get("threads") or default_ffmpeg_threads()
        filter_threads = kwargs.get("filter_threads") or min(threads, 2)

        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "[aout]",
            "-t", f"{max(0.1, duration_sec):.3f}",
            "-c:v", "libx264",
            "-profile:v", "main",
            "-pix_fmt", "yuv420p",
            "-preset", preset,
            "-threads", str(threads),
            "-filter_threads", str(filter_threads),
            "-crf", str(crf),
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            "-ac", "2",
            "-movflags", "+faststart",
        ])

        return cmd

    @staticmethod
    def _shot_video_filter(idx: int, width: int, height: int, fps: int, kwargs: dict) -> str:
        from src.agents.shot_mix import SETTLED, video_filter_for_role

        roles = kwargs.get("shot_roles") or []
        role = roles[idx] if idx < len(roles) else SETTLED
        return video_filter_for_role(str(role), width, height, fps)

    def _build_multi_shot_sub_clause(
        self,
        include_subtitles: bool,
        subtitle_path: Path | None,
        fonts_dir: str | Path | None = None,
    ) -> str:
        if include_subtitles and subtitle_path and has_active_subtitles(subtitle_path):
            sub_escaped = escape_ffmpeg_filter_path(subtitle_path)
            resolved_fonts = Path(fonts_dir) if fonts_dir else (BASE_DIR / "assets" / "fonts")
            fonts_arg = resolved_fonts if resolved_fonts.exists() and resolved_fonts.is_dir() else None
            if Path(subtitle_path).suffix.lower() == ".ass":
                return f"[vbase]{libass_filter_clause(subtitle_path, fonts_arg)}[vout];"
            fonts_clause = f":fontsdir={escape_ffmpeg_filter_path(fonts_arg)}" if fonts_arg else ""
            return f"[vbase]subtitles=filename={sub_escaped}{fonts_clause}[vout];"
        return "[vbase]null[vout];"

    def build_multi_shot_filter_graph(
        self,
        scene_images: list[str | Path],
        shot_durations: list[float],
        audio_path: Path,
        bgm_path: Path | None,
        target_resolution: tuple[int, int],
        duration_sec: float,
        include_subtitles: bool = False,
        subtitle_path: Path | None = None,
        **kwargs,
    ) -> list[str]:
        """
        Builds FFmpeg command for multi-shot video composition with dynamic camera cuts across scenes.
        """
        w, h = target_resolution
        fps = kwargs.get("fps", 30)
        cmd: list[str] = ["ffmpeg", "-y"]

        filter_inputs = []
        for idx, (s_path, s_dur) in enumerate(zip(scene_images, shot_durations)):
            p = Path(s_path).resolve()
            if p.suffix.lower() in self.SUPPORTED_IMAGE_EXTENSIONS:
                cmd.extend(["-loop", "1", "-t", f"{max(0.1, float(s_dur)):.3f}", "-i", str(p)])
            else:
                cmd.extend(["-stream_loop", "-1", "-t", f"{max(0.1, float(s_dur)):.3f}", "-i", str(p)])
            filter_inputs.append(
                f"[{idx}:v]{self._shot_video_filter(idx, w, h, fps, kwargs)}[v_shot_{idx}];"
            )

        n_scenes = len(scene_images)
        concat_clause = "".join([f"[v_shot_{i}]" for i in range(n_scenes)]) + f"concat=n={n_scenes}:v=1:a=0[vbase];"

        audio_idx = n_scenes
        cmd.extend(["-i", str(Path(audio_path).resolve())])

        has_music = False
        bgm_idx = -1
        if bgm_path:
            bg_p = Path(bgm_path)
            if bg_p.is_file() and bg_p.stat().st_size > 0:
                cmd.extend(["-stream_loop", "-1", "-i", str(bg_p.resolve())])
                bgm_idx = audio_idx + 1
                has_music = True

        sub_filter = self._build_multi_shot_sub_clause(
            include_subtitles=include_subtitles,
            subtitle_path=subtitle_path,
            fonts_dir=kwargs.get("fonts_dir"),
        )

        audio_filter = getattr(self, "build_audio_filter")(
            has_music=has_music,
            music_volume=kwargs.get("music_volume", 0.04),
            ducking_threshold=kwargs.get("ducking_threshold", 0.035),
            ducking_ratio=kwargs.get("ducking_ratio", 8.0),
            ducking_attack_ms=kwargs.get("ducking_attack_ms", 20.0),
            ducking_release_ms=kwargs.get("ducking_release_ms", 350.0),
            lowpass_freq=kwargs.get("lowpass_freq", 12000),
            master_loudness=kwargs.get("master_loudness", True),
            target_lufs=kwargs.get("target_lufs", -14.0),
            max_tp=kwargs.get("max_tp", -1.5),
            lra=kwargs.get("lra", 11.0),
        )
        if has_music:
            audio_filter = audio_filter.replace("[1:a]", f"[{audio_idx}:a]").replace("[2:a]", f"[{bgm_idx}:a]")
        else:
            audio_filter = audio_filter.replace("[1:a]", f"[{audio_idx}:a]")

        filter_complex = "".join(filter_inputs) + concat_clause + sub_filter + audio_filter

        crf = kwargs.get("crf") if kwargs.get("crf") is not None else default_render_crf()
        preset = kwargs.get("preset") or default_render_preset()
        threads = kwargs.get("threads") or default_ffmpeg_threads()
        filter_threads = kwargs.get("filter_threads") or min(threads, 2)

        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "[aout]",
            "-t", f"{max(0.1, duration_sec):.3f}",
            "-c:v", "libx264",
            "-profile:v", "main",
            "-pix_fmt", "yuv420p",
            "-preset", preset,
            "-threads", str(threads),
            "-filter_threads", str(filter_threads),
            "-crf", str(crf),
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            "-ac", "2",
            "-movflags", "+faststart",
        ])
        return cmd

    def get_loop_quality_metrics(self, loop_path: str | Path | None) -> dict[str, Any]:
        """
        Retrieves precomputed quality metrics (blackdetect, perceptual luminance)
        for a loop asset, avoiding redundant full-length video re-analysis.
        """
        if not loop_path:
            return {}
        lp = Path(loop_path).resolve()
        manifest_path = (BASE_DIR / "assets" / "loops" / "bank_manifest.json").resolve()
        if manifest_path.is_file():
            try:
                manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
                for entry in manifest_data.get("master_loops", []):
                    entry_path = (BASE_DIR / entry.get("file_path", "")).resolve()
                    if lp == entry_path or lp.name == entry.get("filename"):
                        out: dict[str, Any] = {}
                        if "longest_black_seconds" in entry:
                            out["longest_black_seconds"] = float(entry["longest_black_seconds"])
                            out["black_segments"] = list(entry.get("black_segments") or [])
                        if entry.get("perceptual_luminance") is not None:
                            out["perceptual_luminance"] = entry.get("perceptual_luminance")
                        return out
            except Exception as exc:
                logger.debug("Could not read loop quality metrics from manifest: %s", exc)
        return {}
