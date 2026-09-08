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

from src.media.interface import BaseVideoCompositor, CompositorError
from src.log import get_logger
from src.media.subtitles import CodeSubtitleDrawer, SubtitleCue, SubtitleTheme
from src.media.subtitles_ass import libass_filter_clause
from src.scene_manifest import (
    CameraMotionConfig,
    HybridAIConfig,
    LayerConfig,
    LightingConfig,
    ParticleConfig,
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
)

logger = get_logger("hybrid_video_engine")

__all__ = [
    "HybridVideoEngine",
    "HybridVideoError",
    "cubic_bezier_ease",
    "force_pillow_hybrid_frames_enabled",
    "force_pillow_particles_enabled",
    "build_ken_burns_zoompan_filter",
    "canonical_ken_burns_params",
    "plan_ken_burns_still_segments",
    "KEN_BURNS_MIN_DURATION_SEC",
    "KEN_BURNS_ZOOM_START",
    "KEN_BURNS_ZOOM_END",
    "KEN_BURNS_FPS",
    "KEN_BURNS_SEGMENT_MAX_SEC",
    "KEN_BURNS_SPLIT_THRESHOLD_SEC",
    "ATMOSPHERIC_OVERLAY_OPACITY",
    "clamp_atmospheric_overlay_opacity",
    "resolve_hybrid_overlay_asset",
]


class HybridVideoError(CompositorError):
    """Base exception for HybridVideoEngine operations."""
    pass


def cubic_bezier_ease(t: float, p1: float = 0.25, p2: float = 0.1, p3: float = 0.25, p4: float = 1.0) -> float:
    """Computes cubic-bezier(0.25, 0.1, 0.25, 1.0) easing approximation for smooth cinematic camera easing."""
    t = max(0.0, min(1.0, float(t)))
    # 3-term cubic hermite / bezier blend
    return t * t * (3.0 - 2.0 * t)


def force_pillow_hybrid_frames_enabled(extra: Optional[Dict[str, Any]] = None) -> bool:
    """Opt-in only: legacy Pillow rawvideo frame loop for hybrid camera/FX.

    Default path uses FFmpeg zoompan/crop (+ FFmpeg/asset overlays) to avoid
    per-frame Python crop/resize/ImageDraw work. Enable the old path with
    FORCE_PILLOW_HYBRID_FRAMES=1 or force_pillow_hybrid_frames=True in kwargs.
    """
    env = os.environ.get("FORCE_PILLOW_HYBRID_FRAMES", "").strip().lower()
    if env in ("1", "true", "yes", "on"):
        return True
    if extra and bool(extra.get("force_pillow_hybrid_frames")):
        return True
    return False


def force_pillow_particles_enabled(extra: Optional[Dict[str, Any]] = None) -> bool:
    """Opt-in Pillow ImageDraw for particle/god-ray overlay generation.

    Default FFmpeg camera path uses asset PNGs and/or lavfi noise/geq overlays
    instead of Pillow. Enable Pillow overlay generation with
    FORCE_PILLOW_PARTICLES=1 / force_pillow_particles=True, or via the full
    FORCE_PILLOW_HYBRID_FRAMES legacy frame loop.
    """
    if force_pillow_hybrid_frames_enabled(extra):
        return True
    env = os.environ.get("FORCE_PILLOW_PARTICLES", "").strip().lower()
    if env in ("1", "true", "yes", "on"):
        return True
    if extra and bool(extra.get("force_pillow_particles")):
        return True
    return False


def _hybrid_overlay_search_roots(kind_norm: str) -> List[Path]:
    """CWD + repo assets/overlays, plus visual_bank overlays (and GIFs for tv_static)."""
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
            if kind_norm in ("tv_static", "tv-static", "static"):
                roots.append(chan / "ambient_gifs")
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
    """Return a pre-made overlay PNG/GIF (never a principal-plane background).

    Conventions:
    - particles: ``assets/overlays/particles_<type>.png`` then ``particles.png``
    - god_rays: ``assets/overlays/god_rays.png``
    - film_grain / vignette / tv_static: ``assets/overlays`` then
      ``assets/visual_bank/*/overlays`` (tv_static may be a GIF under ambient_gifs)
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
            candidates.extend(
                [
                    root / "tv_static.png",
                    root / "tv_static.gif",
                ]
            )
        else:
            return None
    for cand in candidates:
        try:
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
        lighting = cfg.lighting or LightingConfig()
        particles = cfg.particles or ParticleConfig()
        tension = max(1, min(5, scene.tension_level))

        bg_image = self._resolve_background_image(cfg.background_image_path, width, height)

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
        from src.media.subtitles_ass import (
            force_pillow_subtitles_enabled,
            write_ass_from_cues_or_words,
        )
        use_pillow_bridge = bool(subtitle_cues) and force_pillow_subtitles_enabled(extra_kwargs)
        use_pillow_frames = force_pillow_hybrid_frames_enabled(extra_kwargs) or use_pillow_bridge

        if use_pillow_frames:
            self._render_scene_pillow_rawvideo(
                scene=scene,
                bg_image=bg_image,
                width=width,
                height=height,
                fps=fps,
                total_frames=total_frames,
                zoom_start=zoom_start,
                zoom_end=zoom_end,
                pan_dir=pan_dir,
                lighting=lighting,
                particles=particles,
                tension=tension,
                out_path=out_path,
                crf=crf,
                preset=preset,
                threads_val=threads_val,
                subtitle_cues=subtitle_cues if use_pillow_bridge else None,
                scene_start_sec=scene_start_sec,
                subtitle_theme=subtitle_theme,
                use_pillow_bridge=use_pillow_bridge,
            )
        else:
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
                lighting=lighting,
                particles=particles,
                tension=tension,
                out_path=out_path,
                crf=crf,
                preset=preset,
                threads_val=threads_val,
                extra_kwargs=extra_kwargs,
            )

        if subtitle_cues and not use_pillow_bridge:
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
        lighting: LightingConfig,
        particles: ParticleConfig,
        tension: int,
        out_path: Path,
        crf: int,
        preset: str,
        threads_val: str,
        extra_kwargs: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Ken Burns + FX via FFmpeg filter_complex (no Python rawvideo frame loop).

        Still backgrounds longer than 20s are split into 12–15s zoompan subclips
        with distinct pans and concat-demuxer hard cuts. Catalog loops are not
        Ken-Burned (assembled on the loop/director path).
        """
        use_pillow_overlays = force_pillow_particles_enabled(extra_kwargs)
        segments = plan_ken_burns_still_segments(duration, fps=fps, pan_direction=str(pan_dir))
        with tempfile.TemporaryDirectory(prefix="hybrid_ff_") as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)
            bg_path = tmp_dir / "bg.png"
            bg_image.save(bg_path, format="PNG")

            if len(segments) <= 1:
                seg_dur, seg_frames, seg_pan = (
                    segments[0] if segments else (duration, total_frames, pan_dir)
                )
                self._encode_still_ken_burns_clip(
                    scene=scene,
                    bg_path=bg_path,
                    tmp_dir=tmp_dir,
                    width=width,
                    height=height,
                    fps=fps,
                    duration=seg_dur,
                    total_frames=seg_frames,
                    zoom_start=zoom_start,
                    zoom_end=zoom_end,
                    pan_dir=seg_pan,
                    lighting=lighting,
                    particles=particles,
                    tension=tension,
                    out_path=out_path,
                    crf=crf,
                    preset=preset,
                    threads_val=threads_val,
                    use_pillow_overlays=use_pillow_overlays,
                )
                return

            clips: List[Path] = []
            for i, (seg_dur, seg_frames, seg_pan) in enumerate(segments):
                clip = tmp_dir / f"kb_seg_{i:03d}.mp4"
                self._encode_still_ken_burns_clip(
                    scene=scene,
                    bg_path=bg_path,
                    tmp_dir=tmp_dir,
                    width=width,
                    height=height,
                    fps=fps,
                    duration=seg_dur,
                    total_frames=seg_frames,
                    zoom_start=float(KEN_BURNS_ZOOM_START),
                    zoom_end=float(KEN_BURNS_ZOOM_END),
                    pan_dir=seg_pan,
                    lighting=lighting,
                    particles=particles,
                    tension=tension,
                    out_path=clip,
                    crf=crf,
                    preset=preset,
                    threads_val=threads_val,
                    use_pillow_overlays=use_pillow_overlays,
                )
                clips.append(clip)
            self._concat_hard_cut_clips(
                clips=clips,
                out_path=out_path,
                tmp_dir=tmp_dir,
                crf=crf,
                preset=preset,
                threads_val=threads_val,
            )

    def _encode_still_ken_burns_clip(
        self,
        *,
        scene: SceneConfig,
        bg_path: Path,
        tmp_dir: Path,
        width: int,
        height: int,
        fps: int,
        duration: float,
        total_frames: int,
        zoom_start: float,
        zoom_end: float,
        pan_dir: str,
        lighting: LightingConfig,
        particles: ParticleConfig,
        tension: int,
        out_path: Path,
        crf: int,
        preset: str,
        threads_val: str,
        use_pillow_overlays: bool,
    ) -> None:
        """One zoompan encode (duration already capped to ≤20s by the planner)."""
        inputs: List[str] = ["-loop", "1", "-i", str(bg_path)]
        filter_parts: List[str] = []
        overlay_idx = 1

        zoompan = build_ken_burns_zoompan_filter(
            width=width,
            height=height,
            fps=fps,
            total_frames=total_frames,
            zoom_start=zoom_start,
            zoom_end=zoom_end,
            pan_direction=str(pan_dir),
        )
        # Keep RGBA until overlays finish so alpha composites stay correct.
        filter_parts.append(f"[0:v]{zoompan},format=rgba[base]")
        current = "base"

        if lighting.volumetric_rays:
            current, overlay_idx = self._attach_god_rays_overlay(
                inputs=inputs,
                filter_parts=filter_parts,
                current=current,
                overlay_idx=overlay_idx,
                tmp_dir=tmp_dir,
                width=width,
                height=height,
                duration=duration,
                lighting=lighting,
                use_pillow_overlays=use_pillow_overlays,
            )

        if particles.type != "none":
            current, overlay_idx = self._attach_particle_overlay(
                inputs=inputs,
                filter_parts=filter_parts,
                current=current,
                overlay_idx=overlay_idx,
                tmp_dir=tmp_dir,
                width=width,
                height=height,
                duration=duration,
                particles=particles,
                tension=tension,
                use_pillow_overlays=use_pillow_overlays,
            )

        current, overlay_idx = self._attach_atmospheric_overlays(
            inputs=inputs,
            filter_parts=filter_parts,
            current=current,
            overlay_idx=overlay_idx,
            width=width,
            height=height,
            tension=tension,
            lighting=lighting,
        )

        if lighting.flicker_frequency > 0.0:
            freq = float(lighting.flicker_frequency)
            # Approximate the dual-sine Pillow brightness flicker in FFmpeg eq space.
            bright = (
                f"0.08*sin(2*PI*{freq:.4f}*t/{duration:.6f})"
                f"+0.04*sin(2*PI*{freq:.4f}*2.3*t/{duration:.6f})"
            )
            # Escape commas for filtergraph.
            bright_esc = bright.replace(",", "\\,")
            filter_parts.append(f"[{current}]eq=brightness='{bright_esc}'[vflick]")
            current = "vflick"

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
            "-b:v", "4500k",
            "-maxrate", "6000k",
            "-bufsize", "8000k",
            "-threads", threads_val,
            "-an",
            "-movflags", "+faststart",
            str(out_path),
        ]
        logger.info(
            "Hybrid FFmpeg camera path scene=%s frames=%d filter_len=%d pan=%s",
            scene.scene_id,
            total_frames,
            len(filter_complex),
            pan_dir,
        )
        run_ffmpeg(ffmpeg_cmd)

    def _concat_hard_cut_clips(
        self,
        *,
        clips: List[Path],
        out_path: Path,
        tmp_dir: Path,
        crf: int,
        preset: str,
        threads_val: str,
    ) -> None:
        """Hard-cut concat demuxer; re-encode if ``-c copy`` fails."""
        if not clips:
            raise HybridVideoError("Ken Burns split produced no clips to concat")
        if len(clips) == 1:
            shutil.copy2(clips[0], out_path)
            return
        concat_list = tmp_dir / "kb_concat.txt"
        with open(concat_list, "w", encoding="utf-8") as fh:
            for clip in clips:
                fh.write(f"file '{clip.resolve()}'\n")
        copy_cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c", "copy",
            "-movflags", "+faststart",
            str(out_path),
        ]
        try:
            run_ffmpeg(copy_cmd)
            return
        except FFmpegError as exc:
            logger.warning("Ken Burns concat copy failed (%s); re-encoding", exc)
        reenc_cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_list),
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

    def _render_scene_pillow_rawvideo(
        self,
        *,
        scene: SceneConfig,
        bg_image: Image.Image,
        width: int,
        height: int,
        fps: int,
        total_frames: int,
        zoom_start: float,
        zoom_end: float,
        pan_dir: str,
        lighting: LightingConfig,
        particles: ParticleConfig,
        tension: int,
        out_path: Path,
        crf: int,
        preset: str,
        threads_val: str,
        subtitle_cues: Optional[List[SubtitleCue]],
        scene_start_sec: float,
        subtitle_theme: Optional[SubtitleTheme],
        use_pillow_bridge: bool,
    ) -> None:
        """Legacy per-frame Pillow crop/resize/FX piped as rawvideo to FFmpeg."""
        particle_system = self._init_particle_system(particles, width, height, tension)
        ffmpeg_cmd = [
            "ffmpeg", "-y",
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
            "-crf", str(crf),
            "-preset", preset,
            "-b:v", "4500k",
            "-maxrate", "6000k",
            "-bufsize", "8000k",
            "-threads", threads_val,
            "-movflags", "+faststart",
            str(out_path),
        ]

        process = subprocess.Popen(
            ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )

        stderr_bytes = b""
        try:
            god_rays_overlay = None
            if lighting.volumetric_rays:
                god_rays_overlay = self._create_god_rays_overlay(width, height, lighting)

            bg_w, bg_h = bg_image.size
            for frame_idx in range(total_frames):
                t_norm = frame_idx / max(1, total_frames - 1)
                ease_t = cubic_bezier_ease(t_norm)

                curr_zoom = zoom_start + (zoom_end - zoom_start) * ease_t
                crop_w = int(bg_w / curr_zoom)
                crop_h = int(bg_h / curr_zoom)

                if pan_dir == "center_to_top":
                    crop_x = (bg_w - crop_w) // 2
                    crop_y = int((bg_h - crop_h) * (1.0 - ease_t * 0.5))
                elif pan_dir == "center_to_bottom":
                    crop_x = (bg_w - crop_w) // 2
                    crop_y = int((bg_h - crop_h) * (ease_t * 0.5))
                elif pan_dir == "left_to_right":
                    crop_x = int((bg_w - crop_w) * ease_t)
                    crop_y = (bg_h - crop_h) // 2
                elif pan_dir == "right_to_left":
                    crop_x = int((bg_w - crop_w) * (1.0 - ease_t))
                    crop_y = (bg_h - crop_h) // 2
                else:
                    crop_x = (bg_w - crop_w) // 2
                    crop_y = (bg_h - crop_h) // 2

                crop_x = max(0, min(bg_w - crop_w, crop_x))
                crop_y = max(0, min(bg_h - crop_h, crop_y))

                frame = bg_image.crop((crop_x, crop_y, crop_x + crop_w, crop_y + crop_h))
                frame = frame.resize((width, height), Image.Resampling.BILINEAR)

                if lighting.flicker_frequency > 0.0:
                    freq = lighting.flicker_frequency
                    flicker = (
                        1.0
                        + 0.08 * math.sin(2.0 * math.pi * freq * t_norm)
                        + 0.04 * math.sin(2.0 * math.pi * freq * 2.3 * t_norm)
                    )
                    frame = ImageEnhance.Brightness(frame).enhance(flicker)

                if god_rays_overlay:
                    frame = Image.alpha_composite(frame.convert("RGBA"), god_rays_overlay).convert("RGB")

                if particles.type != "none" and particle_system:
                    frame = self._render_particles(frame, particle_system, t_norm, width, height)

                if subtitle_cues and use_pillow_bridge:
                    curr_time = scene_start_sec + (frame_idx / float(fps))
                    frame = self.subtitle_drawer.draw_on_frame(
                        frame,
                        current_time_sec=curr_time,
                        cues=subtitle_cues,
                        theme_override=subtitle_theme,
                    )

                process.stdin.write(frame.tobytes())
        finally:
            if process.stdin:
                try:
                    process.stdin.flush()
                except Exception:
                    pass
                try:
                    process.stdin.close()
                except Exception:
                    pass
            try:
                if process.stderr:
                    stderr_bytes = process.stderr.read()
            except Exception:
                pass
            retcode = process.wait()

        if retcode != 0:
            err_msg = stderr_bytes.decode("utf-8", errors="replace")
            raise FFmpegExecutionError(
                f"FFmpeg failed while rendering scene {scene.scene_id}: {err_msg}",
                returncode=retcode,
                stderr=err_msg,
                command=ffmpeg_cmd,
            )

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
        if suffix in {".gif", ".webp", ".mp4", ".webm", ".mov"}:
            inputs.extend(["-stream_loop", "-1", "-i", str(overlay_path)])
        else:
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
        lighting: LightingConfig,
    ) -> Tuple[str, int]:
        """film_grain / vignette / tv_static as 15–35% overlays, never plane-0."""
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
        use_static = float(getattr(lighting, "flicker_frequency", 0.0) or 0.0) > 0.0 or int(tension) >= 4
        if use_static:
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
        return current, overlay_idx

    def _attach_lavfi_overlay_input(
        self,
        *,
        inputs: List[str],
        filter_parts: List[str],
        current: str,
        overlay_idx: int,
        lavfi: str,
        label: str,
    ) -> Tuple[str, int]:
        """Attach a lavfi-generated RGBA stream as the next overlay input."""
        inputs.extend(["-f", "lavfi", "-i", lavfi])
        filter_parts.append(f"[{overlay_idx}:v]format=rgba[{label}]")
        out = f"v{label}"
        filter_parts.append(
            f"[{current}][{label}]overlay=0:0:format=auto:shortest=1[{out}]"
        )
        return out, overlay_idx + 1

    def _build_ffmpeg_god_rays_lavfi(
        self, width: int, height: int, duration: float, lighting: LightingConfig
    ) -> str:
        """Soft volumetric rays via geq (no Pillow ImageDraw)."""
        sx = int(width * (lighting.light_source_pos[0] if lighting.light_source_pos else 0.8))
        sy = int(height * (lighting.light_source_pos[1] if lighting.light_source_pos else 0.2))
        radius = max(width, height) * 0.9
        strength = max(20.0, min(120.0, 255.0 * float(lighting.intensity) * 0.35))
        a_expr = (
            f"min(100,floor({strength:.2f}*(1-hypot(X-{sx},Y-{sy})/{radius:.1f})"
            f"*max(0,0.55+0.45*sin(atan2(Y-{sy},X-{sx})*6))))"
        ).replace(",", r"\,")
        return (
            f"color=c=black@0.0:s={int(width)}x{int(height)}:d={max(0.2, float(duration)):.3f},"
            f"format=rgba,geq=r=200:g=240:b=255:a='{a_expr}'"
        )

    def _build_ffmpeg_particle_lavfi(
        self,
        width: int,
        height: int,
        duration: float,
        particles: ParticleConfig,
        tension: int,
    ) -> str:
        """Sparse atmospheric grain via noise (no Pillow ImageDraw)."""
        dens = max(1, min(500, int(particles.density)))
        dens = int(dens * (1.0 + 0.2 * (max(1, min(5, tension)) - 1)))
        alls = max(6, min(36, dens // 6))
        opacity = max(0.08, min(0.55, float(particles.opacity) * 0.7))
        ptype = (particles.type or "dust_motes").strip().lower()
        # Bias noise colorchannelmixer RGB gains by particle family.
        if ptype == "ember_sparks":
            mix = f"rr=1.2:gg=0.55:bb=0.2:aa={opacity:.3f}"
        elif ptype == "spores":
            mix = f"rr=0.15:gg=1.1:bb=0.85:aa={opacity:.3f}"
        elif ptype == "fog_mist":
            mix = f"rr=0.7:gg=0.85:bb=0.95:aa={min(0.4, opacity):.3f}"
        elif ptype == "rain_streaks":
            mix = f"rr=0.55:gg=0.65:bb=0.9:aa={opacity:.3f}"
        else:
            mix = f"rr=0.85:gg=0.95:bb=1.05:aa={opacity:.3f}"
        return (
            f"color=c=black@0.0:s={int(width)}x{int(height)}:d={max(0.2, float(duration)):.3f},"
            f"format=rgba,noise=alls={alls}:allf=t+u,format=rgba,colorchannelmixer={mix}"
        )

    def _attach_god_rays_overlay(
        self,
        *,
        inputs: List[str],
        filter_parts: List[str],
        current: str,
        overlay_idx: int,
        tmp_dir: Path,
        width: int,
        height: int,
        duration: float,
        lighting: LightingConfig,
        use_pillow_overlays: bool,
    ) -> Tuple[str, int]:
        """Attach god rays: Pillow (opt-in) → asset PNG → FFmpeg geq → skip."""
        if use_pillow_overlays:
            god = self._create_god_rays_overlay(width, height, lighting)
            god_path = tmp_dir / "god_rays.png"
            god.save(god_path, format="PNG")
            return self._attach_static_overlay_input(
                inputs=inputs,
                filter_parts=filter_parts,
                current=current,
                overlay_idx=overlay_idx,
                overlay_path=god_path,
                label="god",
            )

        asset = resolve_hybrid_overlay_asset("god_rays")
        if asset is not None:
            logger.info("Hybrid god rays: reusing asset %s", asset)
            return self._attach_static_overlay_input(
                inputs=inputs,
                filter_parts=filter_parts,
                current=current,
                overlay_idx=overlay_idx,
                overlay_path=asset,
                label="god",
            )

        lavfi = self._build_ffmpeg_god_rays_lavfi(width, height, duration, lighting)
        logger.info("Hybrid god rays: FFmpeg geq lavfi overlay")
        return self._attach_lavfi_overlay_input(
            inputs=inputs,
            filter_parts=filter_parts,
            current=current,
            overlay_idx=overlay_idx,
            lavfi=lavfi,
            label="god",
        )

    def _attach_particle_overlay(
        self,
        *,
        inputs: List[str],
        filter_parts: List[str],
        current: str,
        overlay_idx: int,
        tmp_dir: Path,
        width: int,
        height: int,
        duration: float,
        particles: ParticleConfig,
        tension: int,
        use_pillow_overlays: bool,
    ) -> Tuple[str, int]:
        """Attach particles: Pillow (opt-in) → asset PNG → FFmpeg noise → skip."""
        if use_pillow_overlays:
            particle_system = self._init_particle_system(particles, width, height, tension)
            if not particle_system:
                return current, overlay_idx
            particle_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            particle_img = self._render_particles(
                particle_img, particle_system, t_norm=0.35, width=width, height=height
            )
            if particle_img.mode != "RGBA":
                particle_img = particle_img.convert("RGBA")
            part_path = tmp_dir / "particles.png"
            particle_img.save(part_path, format="PNG")
            return self._attach_static_overlay_input(
                inputs=inputs,
                filter_parts=filter_parts,
                current=current,
                overlay_idx=overlay_idx,
                overlay_path=part_path,
                label="parts",
            )

        asset = resolve_hybrid_overlay_asset("particles", particles.type)
        if asset is not None:
            logger.info("Hybrid particles: reusing asset %s", asset)
            return self._attach_static_overlay_input(
                inputs=inputs,
                filter_parts=filter_parts,
                current=current,
                overlay_idx=overlay_idx,
                overlay_path=asset,
                label="parts",
            )

        lavfi = self._build_ffmpeg_particle_lavfi(
            width, height, duration, particles, tension
        )
        logger.info(
            "Hybrid particles: FFmpeg noise lavfi overlay type=%s", particles.type
        )
        return self._attach_lavfi_overlay_input(
            inputs=inputs,
            filter_parts=filter_parts,
            current=current,
            overlay_idx=overlay_idx,
            lavfi=lavfi,
            label="parts",
        )

    def _create_god_rays_overlay(self, w: int, h: int, lighting: LightingConfig) -> Image.Image:
        """Precomputes volumetric god rays mask overlay."""
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        src_x = int(w * (lighting.light_source_pos[0] if lighting.light_source_pos else 0.8))
        src_y = int(h * (lighting.light_source_pos[1] if lighting.light_source_pos else 0.2))

        ray_count = 6
        ray_intensity = int(255 * lighting.intensity * 0.35)
        for r_idx in range(ray_count):
            angle = (r_idx / ray_count) * (math.pi / 3.0) + (math.pi / 4.0)
            length = max(w, h) * 1.4
            p1_x = src_x + length * math.cos(angle - 0.08)
            p1_y = src_y + length * math.sin(angle - 0.08)
            p2_x = src_x + length * math.cos(angle + 0.08)
            p2_y = src_y + length * math.sin(angle + 0.08)

            draw.polygon([(src_x, src_y), (p1_x, p1_y), (p2_x, p2_y)], fill=(200, 240, 255, ray_intensity // (r_idx + 1)))

        return overlay.filter(ImageFilter.GaussianBlur(radius=15))

    def _resolve_background_image(self, bg_path: Optional[str], target_w: int, target_h: int) -> Image.Image:
        """Loads and prepares high-resolution base background image."""
        if bg_path and Path(bg_path).is_file():
            try:
                img = Image.open(bg_path).convert("RGB")
                # Ensure it covers target dimensions with margin for zoompan
                oversample_w = int(target_w * 1.2)
                oversample_h = int(target_h * 1.2)
                return img.resize((oversample_w, oversample_h), Image.Resampling.LANCZOS)
            except Exception as e:
                logger.warning("Failed to open bg_path %s: %s. Falling back to procedural matte.", bg_path, e)

        # Fallback: Procedural dark atmospheric matte
        oversample_w = int(target_w * 1.2)
        oversample_h = int(target_h * 1.2)
        arr = np.zeros((oversample_h, oversample_w, 3), dtype=np.uint8)
        
        # Deep cinematic dark gradient (abyssal indigo to dark charcoal)
        for y in range(oversample_h):
            fac = y / oversample_h
            arr[y, :, 0] = int(4 + fac * 8)
            arr[y, :, 1] = int(6 + fac * 12)
            arr[y, :, 2] = int(12 + fac * 18)

        img = Image.fromarray(arr, "RGB")
        return img

    def _apply_lighting(
        self, img: Image.Image, lighting: LightingConfig, t_norm: float, tension: int
    ) -> Image.Image:
        """Applies volumetric lighting, god rays, and ambient flicker."""
        # Ambient flicker
        if lighting.flicker_frequency > 0.0:
            freq = lighting.flicker_frequency
            flicker = 1.0 + 0.08 * math.sin(2.0 * math.pi * freq * t_norm) + 0.04 * math.sin(2.0 * math.pi * freq * 2.3 * t_norm)
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(flicker)

        # Volumetric god rays simulation
        if lighting.volumetric_rays:
            w, h = img.size
            overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            
            src_x = int(w * (lighting.light_source_pos[0] if lighting.light_source_pos else 0.8))
            src_y = int(h * (lighting.light_source_pos[1] if lighting.light_source_pos else 0.2))
            
            ray_count = 6
            ray_intensity = int(255 * lighting.intensity * 0.35)
            for r_idx in range(ray_count):
                angle = (r_idx / ray_count) * (math.pi / 3.0) + (math.pi / 4.0)
                length = max(w, h) * 1.4
                p1_x = src_x + length * math.cos(angle - 0.08)
                p1_y = src_y + length * math.sin(angle - 0.08)
                p2_x = src_x + length * math.cos(angle + 0.08)
                p2_y = src_y + length * math.sin(angle + 0.08)
                
                draw.polygon([(src_x, src_y), (p1_x, p1_y), (p2_x, p2_y)], fill=(200, 240, 255, ray_intensity // (r_idx + 1)))

            overlay = overlay.filter(ImageFilter.GaussianBlur(radius=15))
            img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

        return img

    def _init_particle_system(
        self, particles: ParticleConfig, width: int, height: int, tension: int
    ) -> List[Dict[str, Any]]:
        """Initializes deterministic particle state."""
        count = min(300, int(particles.density * (1.0 + 0.2 * (tension - 1))))
        np.random.seed(42 + tension)
        
        system = []
        for i in range(count):
            p = {
                "x_base": float(np.random.uniform(-50, width + 50)),
                "y_base": float(np.random.uniform(-50, height + 50)),
                "radius": float(np.random.uniform(1.0, 3.5)),
                "alpha": float(np.random.uniform(40, 160) * particles.opacity),
                "speed": float(np.random.uniform(0.5, 2.0) * particles.velocity),
                "cycle": int(np.random.choice([1, 2, 3])),
                "type": particles.type,
            }
            system.append(p)
        return system

    def _render_particles(
        self,
        img: Image.Image,
        particles: List[Dict[str, Any]],
        t_norm: float,
        width: int,
        height: int,
    ) -> Image.Image:
        """Renders atmospheric particles directly on image buffer for maximum speed."""
        draw = ImageDraw.Draw(img)

        for p in particles:
            p_type = p["type"]
            cycle_t = (t_norm * p["cycle"]) % 1.0
            
            if p_type == "dust_motes":
                # Brownian floating drift
                px = (p["x_base"] + math.sin(2 * math.pi * cycle_t) * 25.0) % width
                py = (p["y_base"] - cycle_t * 60.0 * p["speed"]) % height
                r = p["radius"]
                draw.ellipse([px - r, py - r, px + r, py + r], fill=(190, 220, 240))
                
            elif p_type == "ember_sparks":
                # Rising glowing embers
                px = (p["x_base"] + math.sin(4 * math.pi * cycle_t) * 15.0) % width
                py = (p["y_base"] - cycle_t * 140.0 * p["speed"]) % height
                r = max(0.8, p["radius"] * (1.0 - cycle_t * 0.5))
                draw.ellipse([px - r, py - r, px + r, py + r], fill=(255, 140, 40))
                draw.ellipse([px - r * 0.5, py - r * 0.5, px + r * 0.5, py + r * 0.5], fill=(255, 240, 180))

            elif p_type == "spores":
                # Bioluminescent pulsing spores
                px = (p["x_base"] + math.sin(2 * math.pi * cycle_t) * 35.0) % width
                py = (p["y_base"] + math.cos(2 * math.pi * cycle_t) * 25.0) % height
                r = p["radius"] * 1.2
                draw.ellipse([px - r, py - r, px + r, py + r], fill=(0, 255, 200))

            elif p_type == "fog_mist":
                # Volumetric horizontal mist band
                px = (p["x_base"] + cycle_t * 80.0 * p["speed"]) % (width + 100) - 50
                py = p["y_base"]
                rw = p["radius"] * 30.0
                rh = p["radius"] * 6.0
                draw.ellipse([px - rw, py - rh, px + rw, py + rh], fill=(150, 190, 200))

        return img
