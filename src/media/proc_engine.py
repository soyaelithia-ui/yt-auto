"""
src/media/procedural_video_engine.py - Pure Procedural WebGL/Three.js/Canvas2D Rendering Engine.

Renders deterministic, mathematical procedural scene segments with virtual time stepping,
strict Rec.709 color matrices, and zero API costs.
Conforms to BaseVideoCompositor interface.
"""
from __future__ import annotations

import contextlib
import json
import math
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from src.media.interface import BaseVideoCompositor, CompositorError
from src.core.catalog import LoopCatalogRepository, LoopRecord
from src.core.lifecycle import cleanup_subprocesses, register_process
from src.log import get_logger
from src.scene_manifest import (
    ProceduralConfig,
    SceneConfig,
    SceneManifestV2,
    parse_scene_manifest_model,
)
from lib.ffmpeg import (
    FFmpegError,
    FFmpegExecutionError,
    probe_media,
    run_ffmpeg,
)

logger = get_logger("procedural_video_engine")

__all__ = [
    "ProceduralVideoEngine",
    "ProceduralVideoError",
]


class ProceduralVideoError(CompositorError):
    """Base exception for ProceduralVideoEngine operations."""
    pass


class ProceduralVideoEngine(BaseVideoCompositor):
    """
    Renders pure procedural WebGL, Three.js, and HTML5 Canvas video segments.
    """

    def __init__(
        self,
        renderer: Optional[Any] = None,
        catalog: Optional[LoopCatalogRepository] = None,
    ) -> None:
        self.renderer = renderer
        self.catalog = catalog or LoopCatalogRepository()

    def render(
        self,
        manifest_path: Union[Path, str],
        output_video_path: Union[Path, str],
        **extra_kwargs: Any,
    ) -> Dict[str, Any]:
        """Renders procedural scenes from a scene manifest."""
        manifest = parse_scene_manifest_model(manifest_path)
        out_p = Path(output_video_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        width = manifest.resolution[0]
        height = manifest.resolution[1]
        fps = manifest.fps

        logger.info(
            "Starting Procedural Video Engine render: story=%s, scenes=%d, res=%dx%d @ %dfps",
            manifest.story_id,
            len(manifest.scenes),
            width,
            height,
            fps,
        )

        t0 = time.time()
        rendered_scene_paths: List[Path] = []

        with tempfile.TemporaryDirectory(prefix="procedural_render_") as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)

            for idx, scene in enumerate(manifest.scenes):
                scene_out = tmp_dir / f"scene_{idx:03d}_{scene.scene_id}.mp4"
                self.render_scene_segment(
                    scene=scene,
                    width=width,
                    height=height,
                    fps=fps,
                    lane_id=manifest.lane_id,
                    output_mp4=scene_out,
                )
                rendered_scene_paths.append(scene_out)

            if len(rendered_scene_paths) == 1:
                shutil.copy2(rendered_scene_paths[0], out_p)
            else:
                concat_list_file = tmp_dir / "concat_procedural_scenes.txt"
                with open(concat_list_file, "w") as f:
                    for sc_path in rendered_scene_paths:
                        f.write(f"file '{sc_path.resolve()}'\n")

                concat_cmd = [
                    "ffmpeg", "-y",
                    "-f", "concat", "-safe", "0", "-i", str(concat_list_file),
                    "-c", "copy",
                    "-movflags", "+faststart",
                    str(out_p),
                ]
                run_ffmpeg(concat_cmd)

        elapsed = time.time() - t0
        file_size = out_p.stat().st_size if out_p.exists() else 0
        logger.info(
            "Procedural Video Engine finished render in %.2fs. Output: %s (%d bytes)",
            elapsed,
            out_p,
            file_size,
        )

        return {
            "status": "success",
            "output_path": str(out_p),
            "file_size_bytes": file_size,
            "render_time_sec": elapsed,
            "scenes_count": len(manifest.scenes),
            "engine": "pure_procedural_webgl",
        }

    def render_scene_segment(
        self,
        scene: SceneConfig,
        width: int,
        height: int,
        fps: int,
        lane_id: str,
        output_mp4: Union[Path, str],
        crf: int = 18,
        subtitle_cues: Optional[List[Any]] = None,
        scene_start_sec: float = 0.0,
        subtitle_theme: Optional[Any] = None,
        **extra_kwargs: Any,
    ) -> Path:
        """
        Renders an individual procedural scene segment by repeating/looping a deterministic micro-loop
        or rendering on demand, with optional code-level subtitle overlays.
        """
        out_path = Path(output_mp4).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        duration = max(0.5, float(scene.duration_sec))

        cfg = scene.procedural_config or ProceduralConfig()
        orientation = "vertical" if height > width else "horizontal"

        # 1. Resolve matching category or template
        category = self._resolve_category(scene.environment_name, cfg.template_name, lane_id)

        # 2. Check catalog for pre-rendered loop only if template_name is not an explicit archetype
        is_archetype_template = bool(cfg.template_name and "archetype_" in cfg.template_name)
        matching_loop = None if is_archetype_template else self.catalog.get_best_loop(category=category, orientation=orientation)
        
        loop_file: Optional[Path] = None
        if matching_loop and Path(matching_loop.file_path).is_file():
            loop_file = Path(matching_loop.file_path).resolve()
        else:
            # Synthesize micro-loop on demand (6s)
            synth_dir = Path("assets/loops/web_procedural") / category
            synth_dir.mkdir(parents=True, exist_ok=True)
            synth_mp4 = synth_dir / f"proc_{category}_{orientation}_{width}x{height}_s{cfg.seed}_6s.mp4"

            palette_obj = getattr(cfg, "palette", None) or getattr(scene, "palette", None)
            pal_primary = getattr(palette_obj, "primary", "#00ff66")
            pal_secondary = getattr(palette_obj, "secondary", getattr(palette_obj, "mid_tone", "#052b12"))
            pal_accent = getattr(palette_obj, "accent", "#00ff66")
            pal_shadow = getattr(palette_obj, "shadow", getattr(palette_obj, "base_dark", "#020604"))
            pal_highlight = getattr(palette_obj, "highlight", "#ffffff")

            render_params = {
                "seed": cfg.seed,
                "tension": scene.tension_level,
                "u_tension": float(scene.tension_level) / 5.0,
                "u_resolution": [width, height],
                "u_palette_primary": pal_primary,
                "u_palette_secondary": pal_secondary,
                "u_palette_accent": pal_accent,
                "u_palette_shadow": pal_shadow,
                "u_palette_highlight": pal_highlight,
                "accentColor": pal_accent,
                "secondaryColor": pal_secondary,
                "shadowDark": pal_shadow,
                **(cfg.uniforms if hasattr(cfg, "uniforms") and isinstance(cfg.uniforms, dict) else {}),
            }

            if self.renderer is not None and hasattr(self.renderer, "render_loop"):
                try:
                    loop_rec = self.renderer.render_loop(
                        template_name=cfg.template_name,
                        category=category,
                        orientation=orientation,
                        width=width,
                        height=height,
                        duration_sec=6.0,
                        fps=fps,
                        output_path=synth_mp4,
                        params=render_params,
                    )
                    loop_file = Path(getattr(loop_rec, "file_path", loop_rec))
                except Exception as e:
                    logger.warning("Procedural on-demand rendering failed (%s). Using fallback generator.", e)
                    loop_file = self._generate_fallback_loop(category, width, height, fps, 6.0, synth_mp4)
            else:
                loop_file = self._generate_fallback_loop(category, width, height, fps, 6.0, synth_mp4)

        # 3. Stream-loop or concatenate to reach exact scene duration
        loop_duration = 6.0
        try:
            probe = probe_media(loop_file)
            if probe.primary_video and probe.primary_video.duration:
                loop_duration = probe.primary_video.duration
            elif probe.duration:
                loop_duration = probe.duration
        except Exception:
            pass

        loop_count = int(math.ceil(duration / max(0.1, loop_duration))) + 1
        with tempfile.TemporaryDirectory(prefix=f"proc_concat_{scene.scene_id}_") as concat_dir_str:
            concat_txt = Path(concat_dir_str) / "concat.txt"
            with open(concat_txt, "w") as f:
                for _ in range(loop_count):
                    f.write(f"file '{loop_file.resolve()}'\n")

            threads_val = str(extra_kwargs.get("threads") or max(1, (os.cpu_count() or 4) // 4))

            if subtitle_cues:
                from PIL import Image
                from src.media.subtitles import CodeSubtitleDrawer
                drawer = CodeSubtitleDrawer(theme=subtitle_theme)

                read_cmd = [
                    "ffmpeg", "-y",
                    "-f", "concat", "-safe", "0", "-i", str(concat_txt),
                    "-t", f"{duration:.3f}",
                    "-vf", f"scale={width}:{height}",
                    "-f", "rawvideo", "-pix_fmt", "rgb24",
                    "-r", str(fps),
                    "-",
                ]
                write_cmd = [
                    "ffmpeg", "-y",
                    "-loglevel", "error",
                    "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps),
                    "-i", "-",
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    "-colorspace", "bt709",
                    "-color_primaries", "bt709",
                    "-color_trc", "bt709",
                    "-crf", str(crf),
                    "-preset", "faster",
                    "-b:v", "4500k",
                    "-maxrate", "6000k",
                    "-bufsize", "8000k",
                    "-threads", threads_val,
                    "-movflags", "+faststart",
                    str(out_path),
                ]
                frame_size = width * height * 3
                proc_in = subprocess.Popen(read_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                proc_out = subprocess.Popen(write_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                register_process(proc_in)
                register_process(proc_out)

                stderr_out = b""
                ret_out = 0
                try:
                    frame_idx = 0
                    while True:
                        raw_bytes = proc_in.stdout.read(frame_size) if proc_in.stdout else b""
                        if not raw_bytes or len(raw_bytes) < frame_size:
                            break
                        img = Image.frombytes("RGB", (width, height), raw_bytes)
                        t_sec = scene_start_sec + (frame_idx / float(fps))
                        img = drawer.draw_on_frame(img, t_sec, subtitle_cues, theme_override=subtitle_theme)
                        if proc_out.stdin:
                            proc_out.stdin.write(img.tobytes())
                        frame_idx += 1
                    if proc_in.stdout:
                        with contextlib.suppress(Exception):
                            proc_in.stdout.close()
                    proc_in.wait()

                    if proc_out.stdin:
                        with contextlib.suppress(Exception):
                            proc_out.stdin.flush()
                            proc_out.stdin.close()
                    if proc_out.stderr:
                        with contextlib.suppress(Exception):
                            stderr_out = proc_out.stderr.read()
                    ret_out = proc_out.wait()
                finally:
                    cleanup_subprocesses(proc_in, proc_out)

                if ret_out != 0:
                    err_msg = stderr_out.decode("utf-8", errors="replace")
                    raise FFmpegExecutionError(
                        f"FFmpeg subtitle pipeline failed (returncode {ret_out}): {err_msg}",
                        returncode=ret_out,
                        stderr=err_msg,
                        command=write_cmd,
                    )
            else:
                ffmpeg_cmd = [
                    "ffmpeg", "-y",
                    "-f", "concat", "-safe", "0", "-i", str(concat_txt),
                    "-t", f"{duration:.3f}",
                    "-c:v", "libx264",
                    "-crf", str(crf),
                    "-preset", "faster",
                    "-b:v", "4500k",
                    "-maxrate", "6000k",
                    "-bufsize", "8000k",
                    "-threads", threads_val,
                    "-pix_fmt", "yuv420p",
                    "-colorspace", "bt709",
                    "-color_primaries", "bt709",
                    "-color_trc", "bt709",
                    "-movflags", "+faststart",
                    str(out_path),
                ]
                run_ffmpeg(ffmpeg_cmd)

        return out_path

    def _resolve_category(self, env_name: Optional[str], template_name: Optional[str], lane_id: str) -> str:
        """Resolves thematic procedural category or universal archetype."""
        if template_name:
            t_norm = template_name.lower().replace(".html", "").replace("archetype_", "")
            for arch in [
                "classified_terminal", "atmospheric_landscape", "tactical_chamber",
                "synaptic_network", "anomaly_silhouette", "cosmic_singularity",
                "drama_waves_canvas", "cosmic_horror_three", "space_abyss_three"
            ]:
                if arch in t_norm:
                    return arch
        if env_name:
            norm = env_name.lower().replace(" ", "_").replace("-", "_")
            for cat in [
                "classified_terminal", "atmospheric_landscape", "tactical_chamber",
                "synaptic_network", "anomaly_silhouette", "cosmic_singularity",
                "cosmic_horror", "dark_forest", "monsters", "space_abyss", "scp", "dark_ambient", "drama_aita"
            ]:
                if cat in norm or norm in cat:
                    return cat
        if template_name and "three" in template_name.lower():
            return "cosmic_singularity"
        if "scp" in lane_id.lower():
            return "classified_terminal"
        if "aita" in lane_id.lower() or "drama" in lane_id.lower():
            return "drama_aita"
        return "atmospheric_landscape"

    def _generate_fallback_loop(
        self, category: str, width: int, height: int, fps: int, duration_sec: float, out_path: Path
    ) -> Path:
        """Generates deterministic mathematical fallback loop video."""
        from PIL import Image, ImageDraw
        import numpy as np

        total_frames = int(fps * duration_sec)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            "ffmpeg", "-y",
            "-loglevel", "error",
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-s", f"{width}x{height}",
            "-r", str(fps),
            "-i", "-",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-colorspace", "bt709",
            "-color_primaries", "bt709",
            "-color_trc", "bt709",
            "-crf", "18",
            "-preset", "fast",
            "-movflags", "+faststart",
            str(out_path),
        ]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        register_process(proc)

        stderr_bytes = b""
        retcode = 0
        try:
            for i in range(total_frames):
                t_norm = i / float(total_frames)
                # Create atmospheric procedural frame
                arr = np.zeros((height, width, 3), dtype=np.uint8)
                for y in range(0, height, 4):
                    fac = y / height
                    val = int(5 + fac * 25 + 10 * math.sin(2 * math.pi * t_norm + fac * 3))
                    arr[y:y+4, :, 0] = max(0, min(255, val // 2))
                    arr[y:y+4, :, 1] = max(0, min(255, val // 3))
                    arr[y:y+4, :, 2] = max(0, min(255, val))

                if proc.stdin:
                    proc.stdin.write(arr.tobytes())

            if proc.stdin:
                with contextlib.suppress(Exception):
                    proc.stdin.flush()
                    proc.stdin.close()
            if proc.stderr:
                with contextlib.suppress(Exception):
                    stderr_bytes = proc.stderr.read()
            retcode = proc.wait()
        finally:
            cleanup_subprocesses(proc)

        if retcode != 0:
            err_msg = stderr_bytes.decode("utf-8", errors="replace")
            raise FFmpegExecutionError(
                f"FFmpeg fallback loop generation failed (returncode {retcode}): {err_msg}",
                returncode=retcode,
                stderr=err_msg,
                command=cmd,
            )
        return out_path
