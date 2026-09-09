"""
src/media/hybrid_video_engine.py - Cinematic AI Hybrid Video Rendering Engine.

Combines high-resolution 2K/4K background mattes with monocular depth estimation,
2.5D multi-plane parallax, 3D Ken Burns camera trajectories (Cubic Bezier easing),
volumetric lighting shaders (god rays, chiaroscuro, ambient flicker), and atmospheric
particle simulations (dust motes, embers, spores, mist).
Conforms to BaseVideoCompositor interface.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance

from src.media.interface import BaseVideoCompositor, CompositorError, CatalogAssetNotFoundError
from src.log import get_logger
from src.media.subtitles import CodeSubtitleDrawer, SubtitleCue, SubtitleTheme
from src.media.subtitles_ass import libass_filter_clause
from src.scene_manifest import (
    CameraMotionConfig,
    HybridAIConfig,
    LayerConfig,
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
from src.media.encode_defaults import (
    default_ffmpeg_threads,
    default_render_crf,
    default_render_preset,
    loop_matches_target_geometry,
)

logger = get_logger("hybrid_video_engine")

__all__ = [
    "HybridVideoEngine",
    "HybridVideoError",
    "build_ken_burns_zoompan_filter",
    "canonical_ken_burns_params",
    "plan_ken_burns_still_segments",
    "max_reencoded_shots",
    "is_motion_loop_path",
    "resolve_hybrid_motion_loop",
    "KEN_BURNS_MIN_DURATION_SEC",
    "KEN_BURNS_ZOOM_START",
    "KEN_BURNS_ZOOM_END",
    "KEN_BURNS_FPS",
    "KEN_BURNS_SEGMENT_MAX_SEC",
    "KEN_BURNS_SPLIT_THRESHOLD_SEC",
    "MAX_REENCODE_SHOTS_PER_MIN",
    "ATMOSPHERIC_OVERLAY_OPACITY",
    "clamp_atmospheric_overlay_opacity",
    "resolve_hybrid_overlay_asset",
]


class HybridVideoError(CompositorError):
    """Base exception for HybridVideoEngine operations."""
    pass


MOTION_LOOP_SUFFIXES = {".mp4", ".webm", ".mov", ".mkv"}
ANIMATED_OVERLAY_SUFFIXES = {".gif", ".webp", ".mp4", ".webm", ".mov"}
MAX_REENCODE_SHOTS_PER_MIN = 4


def _hybrid_overlay_search_roots(kind_norm: str) -> List[Path]:
    """CWD + repo assets/overlays, plus visual_bank overlays (PNG only)."""
    from src.config import BASE_DIR

    roots: List[Path] = [Path("assets/overlays")]
    repo_overlays = BASE_DIR / "assets" / "overlays"
    if repo_overlays not in roots:
        roots.append(repo_overlays)
    vb = BASE_DIR / "assets" / "visual_bank"
    if vb.is_dir():
        try:
            channels = sorted(p for p in vb.iterdir() if p.is_dir() and not p.name.startswith("_"))
        except OSError:
            channels = []
        for chan in channels:
            roots.append(chan / "overlays")
            # Never scan ambient_gifs: full-frame GIF decode is banned on the hot path.
    seen: set[str] = set()
    out: List[Path] = []
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        out.append(root)
    return out


def resolve_hybrid_overlay_asset(
    kind: str,
    particle_type: Optional[str] = None,
) -> Optional[Path]:
    """Return a pre-made static overlay PNG (never a principal-plane background).

    Conventions:
    - particles: ``assets/overlays/particles_<type>.png`` then ``particles.png``
    - god_rays: ``assets/overlays/god_rays.png``
    - film_grain / vignette / tv_static: ``assets/overlays`` then
      ``assets/visual_bank/*/overlays`` (PNG only; GIFs are skipped)
    """
    kind_norm = (kind or "").strip().lower()
    candidates: List[Path] = []
    for root in _hybrid_overlay_search_roots(kind_norm):
        if kind_norm == "particles":
            ptype = (particle_type or "none").strip().lower()
            if ptype and ptype != "none":
                candidates.append(root / f"particles_{ptype}.png")
            candidates.append(root / "particles.png")
        elif kind_norm in ("god_rays", "god-rays", "rays"):
            candidates.append(root / "god_rays.png")
        elif kind_norm in ("film_grain", "grain"):
            candidates.append(root / "film_grain.png")
        elif kind_norm in ("vignette", "dark_vignette"):
            candidates.extend(
                [
                    root / "dark_vignette.png",
                    root / "vignette.png",
                    root / "soft_vignette.png",
                ]
            )
        elif kind_norm in ("tv_static", "tv-static", "static"):
            candidates.append(root / "tv_static.png")
        else:
            return None
    for cand in candidates:
        try:
            if cand.suffix.lower() in ANIMATED_OVERLAY_SUFFIXES:
                continue
            if cand.is_file() and cand.stat().st_size > 0:
                return cand.resolve()
        except OSError:
            continue
    return None


def build_ken_burns_zoompan_filter(
    width: int,
    height: int,
    fps: int,
    total_frames: int,
    zoom_start: float,
    zoom_end: float,
    pan_direction: str,
) -> str:
    """Build an FFmpeg zoompan expression matching HybridVideoEngine camera easing.

    Uses the same smoothstep easing as ``cubic_bezier_ease`` (t^2*(3-2t)).
    """
    denom = max(1, int(total_frames) - 1)
    e = f"(on/{denom})*(on/{denom})*(3-2*(on/{denom}))"
    z0 = float(zoom_start)
    z1 = float(zoom_end)
    z = f"({z0:.6f}+({z1:.6f}-{z0:.6f})*{e})"
    pan = (pan_direction or "static").strip().lower()
    if pan == "left_to_right":
        x = f"(iw-iw/zoom)*{e}"
        y = "(ih-ih/zoom)/2"
    elif pan == "right_to_left":
        x = f"(iw-iw/zoom)*(1-{e})"
        y = "(ih-ih/zoom)/2"
    elif pan == "center_to_top":
        x = "(iw-iw/zoom)/2"
        y = f"(ih-ih/zoom)*(1-0.5*{e})"
    elif pan == "center_to_bottom":
        x = "(iw-iw/zoom)/2"
        y = f"(ih-ih/zoom)*(0.5*{e})"
    else:
        x = "(iw-iw/zoom)/2"
        y = "(ih-ih/zoom)/2"
    return (
        f"zoompan=z='{z}':x='{x}':y='{y}':"
        f"d={int(total_frames)}:s={int(width)}x{int(height)}:fps={int(fps)}"
    )


# Canonical Ken Burns for still backgrounds (not applied to motion loops).
# Acceptance: zoom 1.00→1.10, duration ≥12 s, 30 fps when using defaults / still path.
# A single zoompan must not span >20s; stills longer than that hard-cut at 12–15s.
KEN_BURNS_ZOOM_START = 1.00
KEN_BURNS_ZOOM_END = 1.10
KEN_BURNS_MIN_DURATION_SEC = 12.0
KEN_BURNS_FPS = 30
KEN_BURNS_SEGMENT_TARGET_SEC = 13.0
KEN_BURNS_SEGMENT_MAX_SEC = 15.0
KEN_BURNS_SPLIT_THRESHOLD_SEC = 20.0
KEN_BURNS_PAN_CYCLE: Tuple[str, ...] = (
    "center_to_top",
    "left_to_right",
    "center_to_bottom",
    "right_to_left",
)
ATMOSPHERIC_OVERLAY_OPACITY_MIN = 0.15
ATMOSPHERIC_OVERLAY_OPACITY_MAX = 0.35
ATMOSPHERIC_OVERLAY_OPACITY = 0.25


def canonical_ken_burns_params(
    *,
    duration_sec: float | None = None,
    fps: int | None = None,
    zoom_start: float | None = None,
    zoom_end: float | None = None,
    enforce_min_duration: bool = False,
) -> tuple[float, int, int, float, float]:
    """Return (duration, fps, total_frames, zoom_start, zoom_end) for still Ken Burns.

    Defaults match acceptance (1.00→1.10 @ 30 fps, ≥12 s). Scene renders keep the
    caller duration unless ``enforce_min_duration`` is set (acceptance / smoke).
    """
    base_dur = float(duration_sec) if duration_sec is not None else float(KEN_BURNS_MIN_DURATION_SEC)
    if enforce_min_duration:
        dur = max(float(KEN_BURNS_MIN_DURATION_SEC), base_dur)
    else:
        dur = max(0.5, base_dur)
    use_fps = int(fps) if fps and int(fps) > 0 else int(KEN_BURNS_FPS)
    z0 = float(KEN_BURNS_ZOOM_START if zoom_start is None else zoom_start)
    z1 = float(KEN_BURNS_ZOOM_END if zoom_end is None else zoom_end)
    if z0 <= 0:
        z0 = float(KEN_BURNS_ZOOM_START)
    if z1 <= z0:
        z1 = float(KEN_BURNS_ZOOM_END)
    total_frames = max(1, int(round(dur * use_fps)))
    return dur, use_fps, total_frames, z0, z1


def plan_ken_burns_still_segments(
    duration_sec: float,
    fps: int | None = None,
    pan_direction: str = "center_to_top",
) -> List[Tuple[float, int, str]]:
    """Split a still Ken Burns scene into 12–15s zoompan segments (never >20s).

    Catalog motion loops are not Ken-Burned; this planner is still-path only.
    Returns (duration_sec, frame_count, pan_direction) tuples whose durations
    sum to ``duration_sec``.
    """
    dur = max(0.5, float(duration_sec))
    use_fps = int(fps) if fps and int(fps) > 0 else int(KEN_BURNS_FPS)
    pan0 = (pan_direction or "center_to_top").strip().lower()
    if pan0 not in KEN_BURNS_PAN_CYCLE:
        pan0 = "center_to_top"

    if dur <= KEN_BURNS_SPLIT_THRESHOLD_SEC:
        frames = max(1, int(round(dur * use_fps)))
        return [(dur, frames, pan0)]

    n = max(2, int(round(dur / KEN_BURNS_SEGMENT_TARGET_SEC)))
    while dur / n > KEN_BURNS_SEGMENT_MAX_SEC:
        n += 1
    while dur / n < KEN_BURNS_MIN_DURATION_SEC and n > 2:
        n -= 1
    while dur / n > KEN_BURNS_SPLIT_THRESHOLD_SEC:
        n += 1
    cap = max_reencoded_shots(dur)
    if n > cap:
        n = cap
        while dur / n > KEN_BURNS_SPLIT_THRESHOLD_SEC:
            n += 1

    base = round(dur / n, 3)
    durs = [base] * (n - 1)
    durs.append(round(dur - sum(durs), 3))
    start_idx = KEN_BURNS_PAN_CYCLE.index(pan0)
    segs: List[Tuple[float, int, str]] = []
    for i, seg_dur in enumerate(durs):
        pan = KEN_BURNS_PAN_CYCLE[(start_idx + i) % len(KEN_BURNS_PAN_CYCLE)]
        frames = max(1, int(round(float(seg_dur) * use_fps)))
        segs.append((float(seg_dur), frames, pan))
    return segs


def clamp_atmospheric_overlay_opacity(opacity: float | None = None) -> float:
    """Keep film_grain / vignette / tv_static in the 15–35% overlay band."""
    val = ATMOSPHERIC_OVERLAY_OPACITY if opacity is None else float(opacity)
    return max(ATMOSPHERIC_OVERLAY_OPACITY_MIN, min(ATMOSPHERIC_OVERLAY_OPACITY_MAX, val))


def max_reencoded_shots(
    duration_sec: float,
    per_minute: int = MAX_REENCODE_SHOTS_PER_MIN,
) -> int:
    """Cap libx264 Ken Burns encodes per minute of output (still path only)."""
    dur = max(0.0, float(duration_sec))
    minutes = 1 if dur <= 0 else int(math.ceil(dur / 60.0))
    return max(1, int(per_minute) * minutes)


def is_motion_loop_path(path: Union[Path, str, None]) -> bool:
    """True when ``path`` is a non-empty motion video (never a still)."""
    if not path:
        return False
    p = Path(path)
    try:
        return (
            p.is_file()
            and p.suffix.lower() in MOTION_LOOP_SUFFIXES
            and p.stat().st_size > 0
        )
    except OSError:
        return False


def resolve_hybrid_motion_loop(
    scene: SceneConfig,
    extra: Optional[Dict[str, Any]] = None,
) -> Optional[Path]:
    """Pick a catalog/scenery motion loop for stream-copy planes (skip grey/overlays)."""
    extra = extra or {}
    cfg = scene.hybrid_ai_config or HybridAIConfig()
    candidates: List[Any] = [
        extra.get("video_loop_path"),
        extra.get("loop_path"),
        extra.get("background_video_path"),
        cfg.background_image_path,
        scene.image_path,
        scene.asset_path,
    ]
    extra_loops = extra.get("loop_paths")
    if isinstance(extra_loops, (list, tuple)):
        candidates.extend(extra_loops)
    seen: set[str] = set()
    for raw in candidates:
        if not raw:
            continue
        p = Path(str(raw))
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        if not is_motion_loop_path(p):
            continue
        try:
            from src.media.loop_engine import is_grey_procedural_plane, is_overlay_not_plane0

            if is_overlay_not_plane0(p) or is_grey_procedural_plane(path=p):
                continue
        except Exception:
            pass
        return p.resolve()
    return None


class HybridVideoEngine(BaseVideoCompositor):
    """
    Renders cinematic scene segments using layered 2.5D parallax,
    volumetric lighting, atmospheric particle systems, and high-bitrate FFmpeg encoding.
    """

    def __init__(self, output_dir: Optional[Union[str, Path]] = None) -> None:
        self.output_dir = Path(output_dir or "work/hybrid_renders").resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.subtitle_drawer = CodeSubtitleDrawer()

    def render(
        self,
        manifest_path: Union[Path, str],
        output_video_path: Union[Path, str],
        **extra_kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Renders a validated scene manifest or individual scene configuration.
        """
        manifest = parse_scene_manifest_model(manifest_path)
        out_p = Path(output_video_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        width = manifest.resolution[0]
        height = manifest.resolution[1]
        fps = manifest.fps

        logger.info(
            "Starting Hybrid Video Engine render: story=%s, scenes=%d, res=%dx%d @ %dfps",
            manifest.story_id,
            len(manifest.scenes),
            width,
            height,
            fps,
        )

        t0 = time.time()
        rendered_scene_paths: List[Path] = []

        with tempfile.TemporaryDirectory(prefix="hybrid_render_") as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)

            for idx, scene in enumerate(manifest.scenes):
                scene_out = tmp_dir / f"scene_{idx:03d}_{scene.scene_id}.mp4"
                self.render_scene_segment(
                    scene=scene,
                    width=width,
                    height=height,
                    fps=fps,
                    output_mp4=scene_out,
                )
                rendered_scene_paths.append(scene_out)

            # If single scene, copy or rename directly
            if len(rendered_scene_paths) == 1:
                shutil.copy2(rendered_scene_paths[0], out_p)
            else:
                # Concatenate scene segments with stream copy
                concat_list_file = tmp_dir / "concat_scenes.txt"
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
            "Hybrid Video Engine finished render in %.2fs. Output: %s (%d bytes)",
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
            "engine": "hybrid_cinematic_ai",
        }

    def render_scene_segment(
        self,
        scene: SceneConfig,
        width: int,
        height: int,
        fps: int,
        output_mp4: Union[Path, str],
        crf: int | None = None,
        subtitle_cues: Optional[List[SubtitleCue]] = None,
        scene_start_sec: float = 0.0,
        subtitle_theme: Optional[SubtitleTheme] = None,
        **extra_kwargs: Any,
    ) -> Path:
        """
        Renders a single scene segment using 3D camera pan, volumetric lighting, and particle simulation.

        Default path: FFmpeg ``zoompan`` for Ken Burns (no per-frame Pillow crop/resize
        rawvideo pipe). Particles / god rays use a pre-made ``assets/overlays`` PNG when
        present, otherwise lightweight FFmpeg lavfi ``noise``/``geq`` overlays — never
        Pillow ``ImageDraw`` on the default path. Ambient flicker uses FFmpeg ``eq``.

        Opt-in fallbacks:
        - ``FORCE_PILLOW_HYBRID_FRAMES=1`` restores the legacy Pillow frame loop.
        - ``FORCE_PILLOW_PARTICLES=1`` restores Pillow-drawn particle/god-ray PNGs on the
          FFmpeg camera path (without the full rawvideo loop).
        Pillow subtitle burn remains opt-in via ``FORCE_PILLOW_SUBTITLES``.
        """
        out_path = Path(output_mp4).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        cfg = scene.hybrid_ai_config or HybridAIConfig()
        camera = cfg.camera_motion or CameraMotionConfig()
        tension = max(1, min(5, scene.tension_level))

        # Still background path uses Ken Burns (loops are assembled elsewhere — do not KB loops).
        # Canonical defaults: zoom 1.00→1.10; keep scene duration for narration sync.
        zoom_start = float(camera.start_zoom)
        zoom_end = float(camera.end_zoom) + (0.02 * (tension - 1))
        if zoom_start <= 0:
            zoom_start = float(KEN_BURNS_ZOOM_START)
        if zoom_end <= zoom_start:
            zoom_end = float(KEN_BURNS_ZOOM_END)
        duration = max(0.5, float(scene.duration_sec))
        total_frames = int(round(duration * fps))
        pan_dir = camera.pan_direction

        if crf is None:
            crf = default_render_crf()
        preset = str(extra_kwargs.get("preset") or default_render_preset())
        threads_val = str(extra_kwargs.get("threads") or default_ffmpeg_threads())
        from src.media.subtitles_ass import write_ass_from_cues_or_words

        motion_loop = resolve_hybrid_motion_loop(scene, extra_kwargs)
        still_bg = getattr(cfg, "still_bg", None) or getattr(cfg, "background_image_path", None) or getattr(scene, "image_path", None) or getattr(scene, "asset_path", None)

        if motion_loop is not None:
            self._render_scene_loop_hard_cuts(
                loop_path=motion_loop,
                duration=duration,
                fps=fps,
                width=width,
                height=height,
                out_path=out_path,
                crf=crf,
                preset=preset,
                threads_val=threads_val,
            )
        else:
            bg_image = self._resolve_background_image(still_bg, width, height)
            self._render_scene_ffmpeg_camera(
                scene=scene,
                bg_image=bg_image,
                width=width,
                height=height,
                fps=fps,
                duration=duration,
                total_frames=total_frames,
                zoom_start=zoom_start,
                zoom_end=zoom_end,
                pan_dir=pan_dir,
                tension=tension,
                out_path=out_path,
                crf=crf,
                preset=preset,
                threads_val=threads_val,
                extra_kwargs=extra_kwargs,
            )

        if subtitle_cues:
            self._burn_libass_subtitles(
                out_path=out_path,
                subtitle_cues=subtitle_cues,
                width=width,
                height=height,
                scene_start_sec=scene_start_sec,
                crf=crf,
                preset=preset,
                threads_val=threads_val,
                write_ass_from_cues_or_words=write_ass_from_cues_or_words,
            )

        return out_path

    def _burn_libass_subtitles(
        self,
        *,
        out_path: Path,
        subtitle_cues: List[SubtitleCue],
        width: int,
        height: int,
        scene_start_sec: float,
        crf: int,
        preset: str,
        threads_val: str,
        write_ass_from_cues_or_words: Any,
    ) -> None:
        """Native libass burn-in post-pass (avoids Pillow GIL frame bridge)."""
        burned = out_path.with_name(out_path.stem + "_libass" + out_path.suffix)
        with tempfile.TemporaryDirectory(prefix="hybrid_ass_") as _ass_dir:
            ass_path = Path(_ass_dir) / "scene_subs.ass"
            write_ass_from_cues_or_words(
                output_path=ass_path,
                cues=subtitle_cues,
                video_width=width,
                video_height=height,
                time_offset_sec=float(scene_start_sec or 0.0),
            )
            fonts_dir = Path("assets/fonts").resolve()
            sub_clause = libass_filter_clause(
                ass_path,
                fonts_dir if fonts_dir.is_dir() else None,
            )
            vf = f"{sub_clause},format=yuv420p"
            burn_cmd = [
                "ffmpeg", "-y",
                "-i", str(out_path),
                "-vf", vf,
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-colorspace", "bt709",
                "-color_primaries", "bt709",
                "-color_trc", "bt709",
                "-crf", str(crf),
                "-preset", preset,
                "-threads", threads_val,
                "-an",
                "-movflags", "+faststart",
                str(burned),
            ]
            run_ffmpeg(burn_cmd)
        burned.replace(out_path)

    def _render_scene_ffmpeg_camera(
        self,
        *,
        scene: SceneConfig,
        bg_image: Image.Image,
        width: int,
        height: int,
        fps: int,
        duration: float,
        total_frames: int,
        zoom_start: float,
        zoom_end: float,
        pan_dir: str,
        tension: int,
        out_path: Path,
        crf: int,
        preset: str,
        threads_val: str,
        extra_kwargs: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Ken Burns + FX via one FFmpeg filter_complex (no Python rawvideo frame loop).

        Still backgrounds longer than 20s are split into 12–15s zoompan segments
        with distinct pans, concatenated in a single graph. Catalog loops are not
        Ken-Burned (stream-copy hard cuts on the loop path).
        """
        segments = plan_ken_burns_still_segments(duration, fps=fps, pan_direction=str(pan_dir))
        if not segments:
            segments = [(duration, total_frames, pan_dir)]
        with tempfile.TemporaryDirectory(prefix="hybrid_ff_") as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)
            bg_path = tmp_dir / "bg.png"
            bg_image.save(bg_path, format="PNG")
            self._encode_still_ken_burns_clip(
                scene=scene,
                bg_path=bg_path,
                tmp_dir=tmp_dir,
                width=width,
                height=height,
                fps=fps,
                segments=segments,
                zoom_start=zoom_start,
                zoom_end=zoom_end,
                tension=tension,
                out_path=out_path,
                crf=crf,
                preset=preset,
                threads_val=threads_val,
            )

    def _render_scene_loop_hard_cuts(
        self,
        *,
        loop_path: Path,
        duration: float,
        fps: int,
        width: int,
        height: int,
        out_path: Path,
        crf: int,
        preset: str,
        threads_val: str,
    ) -> None:
        """Hard-cut/trim catalog loops with stream-copy when geometry matches."""
        segments = plan_ken_burns_still_segments(duration, fps=fps)
        if loop_matches_target_geometry(loop_path, width, height):
            with tempfile.TemporaryDirectory(prefix="hybrid_loop_") as tmp_dir_str:
                tmp_dir = Path(tmp_dir_str)
                concat_list = tmp_dir / "loop_planes.txt"
                loop_abs = str(loop_path.resolve()).replace("'", r"'\''")
                with open(concat_list, "w", encoding="utf-8") as fh:
                    for _seg_dur, _frames, _pan in segments:
                        fh.write(f"file '{loop_abs}'\n")
                cmd = [
                    "ffmpeg", "-y",
                    "-f", "concat", "-safe", "0",
                    "-i", str(concat_list),
                    "-t", f"{float(duration):.3f}",
                    "-c:v", "copy",
                    "-an",
                    "-movflags", "+faststart",
                    str(out_path),
                ]
                run_ffmpeg(cmd)
                return

        logger.info(
            "Hybrid loop transcode trim loop=%s dur=%.3f planes=%d",
            loop_path.name,
            duration,
            len(segments),
        )
        reenc_cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1",
            "-i", str(loop_path.resolve()),
            "-t", f"{float(duration):.3f}",
            "-vf", f"scale={int(width)}:{int(height)},format=yuv420p",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-colorspace", "bt709",
            "-color_primaries", "bt709",
            "-color_trc", "bt709",
            "-crf", str(crf),
            "-preset", preset,
            "-threads", threads_val,
            "-an",
            "-movflags", "+faststart",
            str(out_path),
        ]
        run_ffmpeg(reenc_cmd)

    def _encode_still_ken_burns_clip(
        self,
        *,
        scene: SceneConfig,
        bg_path: Path,
        tmp_dir: Path,
        width: int,
        height: int,
        fps: int,
        segments: List[Tuple[float, int, str]],
        zoom_start: float,
        zoom_end: float,
        tension: int,
        out_path: Path,
        crf: int,
        preset: str,
        threads_val: str,
    ) -> None:
        """One zoompan (or split+concat zoompans) encode; overlays after concat."""
        if not segments:
            raise HybridVideoError("Ken Burns still encode produced no segments")
        duration = sum(float(s[0]) for s in segments)
        total_frames = sum(int(s[1]) for s in segments)
        inputs: List[str] = ["-loop", "1", "-i", str(bg_path)]
        filter_parts: List[str] = []
        overlay_idx = 1

        if len(segments) == 1:
            _seg_dur, seg_frames, seg_pan = segments[0]
            zoompan = build_ken_burns_zoompan_filter(
                width=width,
                height=height,
                fps=fps,
                total_frames=seg_frames,
                zoom_start=zoom_start,
                zoom_end=zoom_end,
                pan_direction=str(seg_pan),
            )
            filter_parts.append(f"[0:v]{zoompan},format=rgba[base]")
        else:
            n = len(segments)
            split_labs = "".join(f"[i{i}]" for i in range(n))
            filter_parts.append(f"[0:v]split={n}{split_labs}")
            concat_in = ""
            for i, (_seg_dur, seg_frames, seg_pan) in enumerate(segments):
                zoompan = build_ken_burns_zoompan_filter(
                    width=width,
                    height=height,
                    fps=fps,
                    total_frames=seg_frames,
                    zoom_start=float(KEN_BURNS_ZOOM_START),
                    zoom_end=float(KEN_BURNS_ZOOM_END),
                    pan_direction=str(seg_pan),
                )
                filter_parts.append(f"[i{i}]{zoompan},format=rgba[s{i}]")
                concat_in += f"[s{i}]"
            filter_parts.append(f"{concat_in}concat=n={n}:v=1:a=0[base]")
        current = "base"

        # Pre-rendered asset overlays only
        god_rays_asset = resolve_hybrid_overlay_asset("god_rays")
        if god_rays_asset is not None:
            current, overlay_idx = self._attach_static_overlay_input(
                inputs=inputs,
                filter_parts=filter_parts,
                current=current,
                overlay_idx=overlay_idx,
                overlay_path=god_rays_asset,
                label="god",
            )

        particle_asset = resolve_hybrid_overlay_asset("particles")
        if particle_asset is not None:
            current, overlay_idx = self._attach_static_overlay_input(
                inputs=inputs,
                filter_parts=filter_parts,
                current=current,
                overlay_idx=overlay_idx,
                overlay_path=particle_asset,
                label="parts",
            )

        current, overlay_idx = self._attach_atmospheric_overlays(
            inputs=inputs,
            filter_parts=filter_parts,
            current=current,
            overlay_idx=overlay_idx,
            width=width,
            height=height,
            tension=tension,
            duration=duration,
        )

        filter_parts.append(f"[{current}]format=yuv420p[vout]")
        filter_complex = ";".join(filter_parts)

        ffmpeg_cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-frames:v", str(total_frames),
            "-r", str(fps),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-colorspace", "bt709",
            "-color_primaries", "bt709",
            "-color_trc", "bt709",
            "-crf", str(crf),
            "-preset", preset,
            "-threads", threads_val,
            "-an",
            "-movflags", "+faststart",
            str(out_path),
        ]
        run_ffmpeg(ffmpeg_cmd)

    def _attach_static_overlay_input(
        self,
        *,
        inputs: List[str],
        filter_parts: List[str],
        current: str,
        overlay_idx: int,
        overlay_path: Path,
        label: str,
        opacity: Optional[float] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> Tuple[str, int]:
        """Attach a static RGBA PNG (or looping GIF) as the next overlay input."""
        suffix = overlay_path.suffix.lower()
        if suffix in ANIMATED_OVERLAY_SUFFIXES:
            return current, overlay_idx
        inputs.extend(["-loop", "1", "-i", str(overlay_path)])
        prep = f"[{overlay_idx}:v]format=rgba"
        if width and height:
            prep += f",scale={int(width)}:{int(height)}"
        if opacity is not None:
            aa = clamp_atmospheric_overlay_opacity(opacity)
            prep += f",colorchannelmixer=aa={aa:.3f}"
        filter_parts.append(f"{prep}[{label}]")
        out = f"v{label}"
        filter_parts.append(f"[{current}][{label}]overlay=0:0:format=auto[{out}]")
        return out, overlay_idx + 1

    def _attach_atmospheric_overlays(
        self,
        *,
        inputs: List[str],
        filter_parts: List[str],
        current: str,
        overlay_idx: int,
        width: int,
        height: int,
        tension: int,
        duration: float = 1.0,
    ) -> Tuple[str, int]:
        """film_grain / vignette / tv_static as 15–35% overlays, never plane-0. Asset-only."""
        opacity = clamp_atmospheric_overlay_opacity()
        grain = resolve_hybrid_overlay_asset("film_grain")
        if grain is not None:
            current, overlay_idx = self._attach_static_overlay_input(
                inputs=inputs,
                filter_parts=filter_parts,
                current=current,
                overlay_idx=overlay_idx,
                overlay_path=grain,
                label="grain",
                opacity=opacity,
                width=width,
                height=height,
            )
        vig = resolve_hybrid_overlay_asset("vignette")
        if vig is not None:
            current, overlay_idx = self._attach_static_overlay_input(
                inputs=inputs,
                filter_parts=filter_parts,
                current=current,
                overlay_idx=overlay_idx,
                overlay_path=vig,
                label="vig",
                opacity=opacity,
                width=width,
                height=height,
            )
        if int(tension) >= 4:
            static = resolve_hybrid_overlay_asset("tv_static")
            if static is not None:
                current, overlay_idx = self._attach_static_overlay_input(
                    inputs=inputs,
                    filter_parts=filter_parts,
                    current=current,
                    overlay_idx=overlay_idx,
                    overlay_path=static,
                    label="static",
                    opacity=opacity,
                    width=width,
                    height=height,
                )
            else:
                logger.warning("tv_static overlay asset not found; skipping synthetic fallback")
        return current, overlay_idx

    def _resolve_background_image(self, bg_path: Optional[str], target_w: int, target_h: int) -> Image.Image:
        """Loads and prepares high-resolution base background image. Fails closed if missing."""
        if bg_path and Path(bg_path).is_file() and Path(bg_path).suffix.lower() not in MOTION_LOOP_SUFFIXES:
            try:
                img = Image.open(bg_path).convert("RGB")
                oversample_w = int(target_w * 1.2)
                oversample_h = int(target_h * 1.2)
                return img.resize((oversample_w, oversample_h), Image.Resampling.LANCZOS)
            except Exception as e:
                raise CatalogAssetNotFoundError(f"Failed to load background image {bg_path}: {e}") from e

        raise CatalogAssetNotFoundError(f"Background image not found on disk: {bg_path}")
