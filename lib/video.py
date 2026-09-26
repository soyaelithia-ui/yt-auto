"""Video composition engine: scene plans, FFmpeg filter graphs, thumbnails.

All public entry points are also reachable through the ``lib.video`` shim,
which is why internals resolve name overrides through ``vars(lib.video)`` so
that monkeypatches applied to the shim module are honored.
"""
from __future__ import annotations

import json
import logging
import math
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

from lib.ffmpeg import (
    FFmpegError,
    FFmpegExecutionError,
    TempMediaContext,
    has_faststart as ffmpeg_has_faststart,
    probe_media,
    run_ffmpeg,
)

MIN_VIDEO_DURATION_SEC = 60.0
DEFAULT_MIN_DURATION = 120.0
from src.core.resolution import LONGFORM_RESOLUTION, SHORT_RESOLUTION
from src.media.subtitles_ass import libass_filter_clause

SHORT_RES = SHORT_RESOLUTION
LONGFORM_RES = LONGFORM_RESOLUTION
MAX_SCENE_SECONDS = 15.0
MIN_SCENE_SECONDS = 8.0
SHORT_MIN_SCENE_SECONDS = 3.0
SHORT_MAX_SCENE_SECONDS = 4.5

# Render performance knobs (env-overridable). Lower fps encodes fewer frames;
# a thread cap keeps ffmpeg from saturating every core and starving the host.
VIDEO_FPS = max(15, int(os.environ.get("VIDEO_FPS", "30")))
# Quality & performance knobs (env-overridable). Defaults: CRF 21, veryfast preset
# (aligned with docker-compose RENDER_* and src.config SETTINGS.render_crf).
RENDER_CRF = max(0, min(51, int(os.environ.get("RENDER_CRF", "19"))))
RENDER_PRESET = os.environ.get("RENDER_PRESET", "veryfast").strip() or "veryfast"
_FFMPEG_THREADS_ENV = os.environ.get("FFMPEG_THREADS", "")
# R7: respect the env knob up to the CPU count (capped at the container quota
# of 4 vCPUs) instead of the old hard cap of 2.
_FFMPEG_CPU_CAP = max(1, min(os.cpu_count() or 2, 4))
FFMPEG_THREADS = (
    max(1, min(int(_FFMPEG_THREADS_ENV), _FFMPEG_CPU_CAP))
    if _FFMPEG_THREADS_ENV
    else _FFMPEG_CPU_CAP
)
# R8: aq-mode=3 (auto-variance AQ with dark-scene bias) mitigates banding on
# near-black gradients — a recurring artifact in horror content — at ~zero
# encode cost. X264_AQ_MODE=0 restores the previous plain encode.
_ENABLE_X264_AQ = os.environ.get("X264_AQ_MODE", "1") == "1"


def _repo_root() -> Path:
    """Repo root inferred from this file's location (lib/ -> parents[1])."""
    return Path(__file__).resolve().parents[1]


def _resolve(name: str, default=None):
    """Return a module member, honoring overrides planted on the lib.video shim."""
    try:
        import lib.video as _shim
    except Exception:
        return default
    return vars(_shim).get(name, default)


def _get_video_attr(name: str, default=None):
    return _resolve(name, default)


def _hard_is_test_environment() -> bool:
    return os.environ.get("TEST_MODE") == "1" or bool(os.environ.get("PYTEST_CURRENT_TEST"))


def is_test_environment() -> bool:
    """True under pytest or TEST_MODE=1 (disables AI/net side effects)."""
    shadow = _resolve("is_test_environment", None)
    if shadow is not None and shadow is not is_test_environment:
        return bool(shadow())
    return _hard_is_test_environment()


def subprocess_module():
    return subprocess


try:
    from PIL import Image  # noqa: F401
    _HAS_PIL = True
except Exception:  # pragma: no cover
    _HAS_PIL = False


def _resolve(name: str, default=None):
    """Return a module member, honoring overrides planted on the lib.video shim."""
    try:
        import lib.video as _shim  # noqa: F401
    except Exception:
        return default
    attrs = vars(_shim)
    if name in attrs:
        return attrs[name]
    return default


def _get_video_attr(name: str, default=None):
    """Resolution hook used by compose/validate paths; patchable in tests."""
    return _resolve(name, default)


def _hard_is_test_environment() -> bool:
    return os.environ.get("TEST_MODE") == "1" or bool(os.environ.get("PYTEST_CURRENT_TEST"))


def is_test_environment() -> bool:
    """True under pytest or TEST_MODE=1 (disables AI/net side effects)."""
    shadow = _resolve("is_test_environment", None)
    if shadow is not None and shadow is not is_test_environment:
        return bool(shadow())
    return _hard_is_test_environment()


def subprocess_module():
    return subprocess


# ---------------------------------------------------------------------------
# Media probing
# ---------------------------------------------------------------------------

def get_media_size(path: str) -> float:
    try:
        return os.path.getsize(path) / (1024 * 1024)
    except OSError:
        return 0.0


def get_media_duration(path: str) -> float:
    """Duration in seconds via ffprobe; 0.0 on failure."""
    if not path or not os.path.exists(path):
        return 0.0
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except Exception:
        pass
    return 0.0


def validate_video_format(
    path: str,
    min_duration: float = 0.0,
    video_mode: str | None = None,
) -> bool:
    """Validate mp4 (h264 main yuv420p + aac 44100 stereo) and duration bounds.

    Raises ValueError when a hard requirement is violated; returns True when
    the file meets all of them.
    """
    if not path or not os.path.exists(path) or os.path.getsize(path) == 0:
        raise ValueError(f"Video file missing or empty: {path}")
    if not _resolve("is_test_environment", is_test_environment)():
        size = os.path.getsize(path)
        if size < 100 * 1024:
            raise ValueError(
                f"Video file dangerously small ({size} bytes < 100KB) in production mode"
            )
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise ValueError(f"ffprobe failed for {path}")
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid ffprobe output for {path}") from exc
    fmt = data.get("format") or {}
    streams = data.get("streams") or []
    try:
        duration = float(fmt.get("duration", 0) or 0)
    except (TypeError, ValueError):
        duration = 0.0
    if video_mode == "short":
        if duration < 60.0 or duration > 180.0:
            raise ValueError(
                f"Short video duration out of range: {duration:.2f}s (allowed 60-180s)"
            )
    elif min_duration > 0 and duration < min_duration:
        raise ValueError(
            f"Video duration {duration:.2f}s below minimum {min_duration:.2f}s"
        )
    container = str(fmt.get("format_name", "") or "")
    if "mp4" not in container:
        raise ValueError(
            f"Invalid video container format: {container or 'unknown'} (mp4 required)"
        )
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
    if not video:
        raise ValueError("Video file lacks a valid video stream")
    if not audio:
        raise ValueError("Video file lacks a valid audio stream")
    if video.get("codec_name") != "h264":
        raise ValueError(
            f"Invalid video codec: {video.get('codec_name', 'unknown')} (expected h264)"
        )
    if video.get("pix_fmt") and video.get("pix_fmt") not in ("yuv420p", "yuvj420p"):
        raise ValueError(
            f"Invalid pixel format: {video.get('pix_fmt')} (expected yuv420p)"
        )
    if not _resolve("is_test_environment", is_test_environment)():
        profile = str(video.get("profile", "") or "").lower()
        if profile and profile not in ("main", "high"):
            raise ValueError(f"Invalid video profile: {video.get('profile')} (expected Main or High)")
    if audio.get("codec_name") not in ("aac", None):
        raise ValueError(f"Invalid audio codec: {audio.get('codec_name')} (expected aac)")
    try:
        channels = int(audio.get("channels", 2) or 2)
    except (TypeError, ValueError):
        channels = 2
    if channels != 2:
        raise ValueError(f"Invalid audio channels: {channels} (expected 2)")
    try:
        sample_rate = int(audio.get("sample_rate", 44100) or 44100)
    except (TypeError, ValueError):
        sample_rate = 44100
    if sample_rate != 44100:
        raise ValueError(f"Invalid audio sample rate: {sample_rate} (expected 44100)")
    if not _resolve("is_test_environment", is_test_environment)():
        fast = _resolve("has_faststart", has_faststart)
        if not bool(fast(path)):
            raise ValueError("Missing faststart moov atom (use -movflags +faststart)")
    return True


def detect_gpu_encoder():
    """Return (encoder_name, encoder_flags); strictly software libx264."""
    return "libx264", ["-c:v", "libx264"]


def create_video_thumbnail(

    title: str,
    style: str,
    output_path: str,
    cover_prompt: str | None = None,
    strict_official_sdk: bool = False,
    **kwargs,
) -> str:
    """Export a text-free thumbnail selected from the local asset bank."""
    del strict_official_sdk
    v_mode = kwargs.get(
        "video_mode",
        "short" if style == "short" or kwargs.get("video_mode") == "short" else "longform",
    )
    from src.media.thumbnails.engine import default_thumbnail_canvas

    if kwargs.get("width") and kwargs.get("height"):
        target_w, target_h = int(kwargs["width"]), int(kwargs["height"])
    else:
        full_hd = os.environ.get("YT_THUMB_FULLHD", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        target_w, target_h = default_thumbnail_canvas(
            vertical=(v_mode == "short"),
            full_hd=full_hd,
        )

    bg_image_path = (
        kwargs.get("bg_image_path")
        or kwargs.get("background_image_path")
        or kwargs.get("background_path")
    )
    kwargs.pop("video_path", None)
    kwargs.pop("manifest_path", None)
    kwargs.pop("scene_manifest_path", None)
    channel_id = kwargs.get("channel_id") or kwargs.get("channel_name") or style or "moku"

    try:
        from src.media.thumbnails.engine import ThumbnailConfig, ThumbnailEngine
        engine = ThumbnailEngine()
        meta = {
            "subreddit": kwargs.get("subreddit"),
            "upvotes": kwargs.get("upvotes"),
            "author": kwargs.get("author") or kwargs.get("user_handle"),
            "hazard_level": kwargs.get("hazard_level"),
            "site": kwargs.get("site"),
            "cam": kwargs.get("cam"),
            "tape_id": kwargs.get("tape_id"),
            "channel_tag": kwargs.get("channel_tag"),
            "category": kwargs.get("category"),
            "quote": kwargs.get("quote") or kwargs.get("callout") or kwargs.get("excerpt"),
            "date": kwargs.get("date") or kwargs.get("timestamp_label"),
        }
        if kwargs.get("story") and isinstance(kwargs.get("story"), dict):
            s_dict = kwargs["story"]
            for k in ("subreddit", "upvotes", "author", "user_handle", "hazard_level", "site", "cam", "tape_id", "channel_tag", "category", "quote", "callout", "date", "timestamp_label"):
                if s_dict.get(k) is not None and not meta.get(k):
                    meta[k] = s_dict[k]
        if kwargs.get("metadata") and isinstance(kwargs.get("metadata"), dict):
            meta.update(kwargs.get("metadata"))
        meta = {k: v for k, v in meta.items() if v is not None}

        cfg = ThumbnailConfig(
            title=title,
            channel_id=str(channel_id),
            hook_text=kwargs.get("hook_text"),
            output_path=output_path,
            width=target_w,
            height=target_h,
            tilt_angle=float(kwargs["tilt_angle"]) if "tilt_angle" in kwargs else -3.5,
            blur_radius=float(kwargs["blur_radius"]) if "blur_radius" in kwargs else 0.0,
            contrast_boost=float(kwargs["contrast_boost"]) if "contrast_boost" in kwargs else 1.35,
            primary_color=kwargs.get("primary_color"),
            accent_color=kwargs.get("accent_color"),
            archetype=kwargs.get("archetype") or kwargs.get("template") or kwargs.get("category"),
            template=kwargs.get("template"),
            metadata=meta,
            cover_prompt=cover_prompt or kwargs.get("prompt"),
            focal_subject=kwargs.get("focal_subject"),
        )
        res = engine.generate(
            config=cfg,
            video_path=None,
            manifest_path=None,
            base_image_path=bg_image_path,
        )
        return str(res)
    except Exception as exc:
        logger.error("Text-free local thumbnail generation failed: %s", exc)
        raise


# ---------------------------------------------------------------------------
# compose_video — local asset composition adapter
# ---------------------------------------------------------------------------

def _resolve_local_scene_images(scene_prompts: list[str] | None, channel: str) -> list[str]:
    """Resolve existing local videos; prompts never trigger image generation."""
    del scene_prompts
    try:
        from src.asset_manager import get_asset_manager

        manager = get_asset_manager()
        paths = manager.get_background_sequence(count=1, channel=channel) or []
        return [str(path) for path in paths if path and Path(path).is_file()]
    except Exception:
        return []


def build_visual_scene_plan(
    total_duration: float,
    source_paths: list[str] | None = None,
    *,
    source_images: list[str] | None = None,
    shot_durations: list[float] | None = None,
    min_seconds: float = MIN_SCENE_SECONDS,
    max_seconds: float = MAX_SCENE_SECONDS,
    video_mode: str | None = None,
) -> list[dict[str, Any]]:
    """Build an asset manifest plan without camera motion or frame generation."""
    del video_mode
    duration = max(0.1, float(total_duration))
    sources = [str(path) for path in (source_paths or source_images or []) if path]
    if not sources:
        # Planning is still useful before the asset resolver runs.  Keep an empty
        # source marker instead of inventing a generated image or graphics frame.
        sources = [""]
    if shot_durations:
        raw = [max(0.1, float(value)) for value in shot_durations]
        scale = duration / sum(raw) if sum(raw) > 0 else 1.0
        durations = [value * scale for value in raw]
    else:
        low = max(0.1, float(min_seconds))
        high = max(low, float(max_seconds))
        count = max(1, int(math.ceil(duration / high)))
        target = duration / count
        if target < low and count > 1:
            count = max(1, int(math.floor(duration / low)))
            target = duration / count
        durations = [target] * count
        durations[-1] = duration - sum(durations[:-1])
    return [
        {
            "scene_index": idx + 1,
            "source": sources[idx % len(sources)],
            "image_path": sources[idx % len(sources)],
            "duration": round(max(0.1, value), 3),
            "duration_sec": round(max(0.1, value), 3),
        }
        for idx, value in enumerate(durations)
    ]


def compose_video(
    audio_path: str,
    subtitle_path: str,
    background_video_path: str,
    output_video_path: str,
    duration_sec: float = 605.0,
    min_duration: float = DEFAULT_MIN_DURATION,
    channel: str = "moku",
    template: str | None = None,
    style: str | None = None,
    strict_visuals: bool = False,
    scene_prompts: list[str] | None = None,
    shot_durations: list[float] | None = None,
    video_mode: str = "short",
    scene_images: list[str] | None = None,
    bgm_path: str = "",
    bg_ambient_path: str = "",
    **kwargs,
) -> str:
    """Compose local video assets through LoopVideoEngine only."""
    del template, style, strict_visuals, scene_prompts, shot_durations, scene_images, kwargs
    if min_duration is not None and float(duration_sec or 0) < float(min_duration):
        raise ValueError(
            f"Video duration {duration_sec} must exceed minimum duration {float(min_duration)} seconds"
        )
    from src.media.loop_engine import LoopVideoEngine

    loop_path = Path(background_video_path) if background_video_path else None
    if loop_path is not None and not loop_path.is_file():
        loop_path = None
    subtitle = Path(subtitle_path) if subtitle_path and Path(subtitle_path).is_file() else None
    orientation = "vertical" if video_mode == "short" else "horizontal"
    music = bgm_path or bg_ambient_path or None
    engine = LoopVideoEngine()
    res = engine.compose(
        audio_path=audio_path,
        output_video_path=output_video_path,
        category=channel,
        orientation=orientation,
        duration_sec=float(duration_sec),
        bg_music_path=music,
        subtitle_path=subtitle,
        include_subtitles=subtitle is not None,
        video_loop_path=loop_path,
        stream_copy=True,
    )
    try:
        sources = [str(loop_path)] if loop_path else ([str(background_video_path)] if background_video_path else None)
        plan = build_visual_scene_plan(
            duration_sec,
            sources,
        )
        out_dir = Path(output_video_path).parent
        vplan = {
            "scene_count": len(plan),
            "covered_seconds": round(float(sum(p["duration"] for p in plan)), 3),
            "black_fallbacks": 0,
            "scenes": plan,
        }
        (out_dir / "visual_plan.json").write_text(json.dumps(vplan, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not write visual_plan.json in compose_video: %s", exc)
    return str(res)


# ---------------------------------------------------------------------------
# Manifest-facing helpers
# ---------------------------------------------------------------------------

def prepare_scene_plan_and_manifest(
    output_video_path: str,
    duration_sec: float,
    style: str | None = None,
    template: str | None = None,
    channel: str = "moku",
    strict_visuals: bool = False,
    scene_prompts: list[str] | None = None,
    shot_durations: list[float] | None = None,
    video_mode: str = "short",
    **kwargs,
) -> list[str]:
    """Resolve thematic bank assets; AI generation belongs to the media provider."""
    return _resolve_local_scene_images(scene_prompts, channel)


# ---------------------------------------------------------------------------
# Container helpers
# ---------------------------------------------------------------------------

def has_faststart(path: str) -> bool:
    """True when the moov atom precedes mdat (or file too small to decide)."""
    return ffmpeg_has_faststart(path)
