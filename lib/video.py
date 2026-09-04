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

SHORT_RES = SHORT_RESOLUTION
LONGFORM_RES = LONGFORM_RESOLUTION
MAX_SCENE_SECONDS = 15.0
MIN_SCENE_SECONDS = 8.0
SHORT_MIN_SCENE_SECONDS = 3.0
SHORT_MAX_SCENE_SECONDS = 4.5

# Render performance knobs (env-overridable). Lower fps encodes fewer frames;
# a thread cap keeps ffmpeg from saturating every core and starving the host.
VIDEO_FPS = max(15, int(os.environ.get("VIDEO_FPS", "30")))
# Quality & performance knobs (env-overridable). Defaults: CRF 24, veryfast preset.
RENDER_CRF = max(0, min(51, int(os.environ.get("RENDER_CRF", "24"))))
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


def _is_chunked_xfade_enabled() -> bool:
    """Rollback flag: FFMPEG_CHUNKED_XFADE=0 disables chunked xfade, reverts to plain concat."""
    return os.getenv("FFMPEG_CHUNKED_XFADE", "1") == "1"


def _is_visual_overlays_enabled() -> bool:
    """Rollback flag: VISUAL_OVERLAYS=0 skips the per-channel Pillow overlay bake."""
    return os.getenv("VISUAL_OVERLAYS", "1") == "1"


def _is_visual_grade_enabled() -> bool:
    """Rollback flag: VISUAL_GRADE=0 skips the subtle ImageEnhance grade pass."""
    return os.getenv("VISUAL_GRADE", "1") == "1"


def _is_eased_pan_enabled() -> bool:
    """Rollback flag: EASED_PAN=0 restores the literal linear pan expressions."""
    return os.getenv("EASED_PAN", "1") == "1"


def _repo_root() -> Path:
    """Repo root inferred from this file's location (lib/ -> parents[1])."""
    return Path(__file__).resolve().parents[1]


VENDORED_FONT_NAME = "Montserrat-Black.ttf"

# Per-channel bake stack (2c). Files resolve under
# assets/visual_bank/<channel>/overlays/; missing entries are silently skipped.
CHANNEL_OVERLAYS: dict[str, tuple[str, ...]] = {
    "moku": ("dark_vignette.png", "film_grain.png"),
    "aelithia": ("soft_vignette.png", "drama_shadow.png"),
}

# Subtle grade (2c+grade): ImageEnhance factors per channel. Deltas stay within
# the visual_integrity QA floors (avg_lum >= 22, dark_ratio <= 0.45,
# contrast >= 5, edges >= 2).
CHANNEL_GRADE: dict[str, dict[str, float]] = {
    "moku": {"contrast": 1.05, "color": 0.96, "brightness": 0.98},
    "aelithia": {"contrast": 1.03, "color": 1.04},
}


def channel_overlay_paths(channel: str | None) -> list[Path]:
    """Existing RGBA overlay paths for a channel, in bake order."""
    if not channel:
        return []
    names = CHANNEL_OVERLAYS.get(str(channel or "").strip().lower(), ())
    base = _repo_root() / "assets" / "visual_bank" / str(channel) / "overlays"
    out: list[Path] = []
    for name in names:
        p = base / name
        try:
            if p.is_file() and p.stat().st_size > 0:
                out.append(p)
        except OSError:
            continue
    return out


def channel_grade_factors(channel: str | None) -> dict[str, float]:
    """ImageEnhance factors for a channel ({} when none/unknown)."""
    if not channel:
        return {}
    return dict(CHANNEL_GRADE.get(str(channel or "").strip().lower(), {}))


def _apply_channel_overlays(img, channel: str | None):
    """Composite the channel overlay stack onto ``img`` at its current size.

    Pure helper (no I/O beyond opening the resolved overlay files); returns the
    input image unchanged when Pillow is missing, overlays are disabled via
    VISUAL_OVERLAYS=0, the channel has no resolvable layers, or compositing
    fails for any reason.
    """
    if img is None or not _is_visual_overlays_enabled():
        return img
    if not _HAS_PIL:
        return img
    from PIL import Image

    layers = channel_overlay_paths(channel)
    if not layers:
        return img
    try:
        rgba = img.convert("RGBA")
        w, h = rgba.size
        for layer_path in layers:
            try:
                with Image.open(layer_path) as ov:
                    layer = ov.convert("RGBA").resize((w, h), Image.Resampling.BILINEAR)
                rgba = Image.alpha_composite(rgba, layer)
            except Exception as exc:  # missing/corrupt layer: skip that layer
                logger.debug("Overlay layer skipped (%s): %s", layer_path, exc)
        return rgba.convert("RGB")
    except Exception as exc:
        logger.debug("Channel overlay bake failed for %s: %s", channel, exc)
        return img


def _apply_channel_grade(img, channel: str | None):
    """Apply the subtle per-channel grade; returns ``img`` unchanged on any skip."""
    if img is None or not _is_visual_grade_enabled():
        return img
    factors = channel_grade_factors(channel)
    if not factors or not _HAS_PIL:
        return img
    from PIL import ImageEnhance

    try:
        out = img
        contrast = float(factors.get("contrast") or 1.0)
        color = float(factors.get("color") or 1.0)
        brightness = float(factors.get("brightness") or 1.0)
        if contrast != 1.0:
            out = ImageEnhance.Contrast(out).enhance(contrast)
        if color != 1.0:
            out = ImageEnhance.Color(out).enhance(color)
        if brightness != 1.0:
            out = ImageEnhance.Brightness(out).enhance(brightness)
        return out
    except Exception as exc:
        logger.debug("Channel grade failed for %s: %s", channel, exc)
        return img


def _is_mastering_folded() -> bool:
    """Rollback flag: YT_FOLD_MASTERING=0 keeps the separate master_voice_audio pass."""
    return os.getenv("YT_FOLD_MASTERING", "1") == "1"


# EQ cut + loudnorm applied inline on the narration branch when mastering is
# folded into the mux (identical chain to lib.tts.master_voice_audio).
_MASTERING_PREFIX = "equalizer=f=120:t=q:w=1:g=-2,loudnorm=I=-14:TP=-1.5:LRA=11,"


def _compute_T_trans(img_durations: list[float]) -> float:
    """Transition duration: min(0.5, max(0.1, min_dur/3))."""
    if not img_durations:
        return 0.5
    try:
        min_dur = min(float(d) for d in img_durations if d is not None)
    except Exception:
        return 0.5
    return min(0.5, max(0.1, min_dur / 3.0))


def _build_chunked_blocks(n: int) -> list[tuple[int, int]]:
    """Overlapping blocks of max 15 with overlap 1: block k is k*14 : k*14+15."""
    if n <= 15:
        return [(0, n)]
    blocks = math.ceil((n - 1) / 14)
    return [(k * 14, min(k * 14 + 15, n)) for k in range(int(blocks))]


def _filter_complex_exceeds_limit(filter_str: str, limit: int = 32768) -> bool:
    return len(filter_str) > limit

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
        if profile and profile != "main":
            raise ValueError(f"Invalid video profile: {video.get('profile')} (expected Main)")
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


def resolve_font_path() -> str:
    """First usable TrueType font path.

    Priority: explicit SHORTS_FONT_PATH override, then the vendored brand font
    (assets/fonts/Montserrat-Black.ttf, SIL OFL), then system fallbacks.
    """
    candidates = [
        os.environ.get("SHORTS_FONT_PATH", ""),
        str(_repo_root() / "assets" / "fonts" / VENDORED_FONT_NAME),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return ""


def extract_hook_title(title: str) -> str:
    """3-6 word punchy uppercase hook extracted from a title."""
    if not title or not str(title).strip():
        return "HISTORIA IMPACTANTE"
    words = str(title).split()
    cut = min(6, len(words))
    for idx, word in enumerate(words[:6]):
        base = word.rstrip(".,;!?").lower()
        if base == "por":
            cut = min(cut, idx)
            break
    text = " ".join(words[:cut]).upper()
    raw = str(title).rstrip()
    if raw.endswith(("?", "!")) and not text.endswith(("?", "!")):
        text += raw[-1]
    return text


# ---------------------------------------------------------------------------
# Scene planning / cadence
# ---------------------------------------------------------------------------

def _split_duration_to_cadence(duration: float, min_sec: float = 8.0, max_sec: float = 15.0) -> list[float]:
    """Split a duration into chunks within [min_sec, max_sec] that sum exactly.

    Single pieces are clamped up to min_sec when the target is too short to
    reach the minimum cadence.
    """
    pieces: list[float] = []
    remaining = float(duration)
    if remaining <= 0:
        return pieces
    import math
    if remaining <= max_sec:
        pieces.append(round(max(remaining, min_sec), 3))
        return pieces
    n = max(1, math.ceil(remaining / max_sec))
    if remaining / n < min_sec:
        n = max(1, int(remaining // min_sec))
    base = remaining / n
    for _ in range(n):
        pieces.append(round(base, 3))
    drift = round(remaining - sum(pieces), 3)
    if abs(drift) >= 0.001:
        pieces[-1] = round(pieces[-1] + drift, 3)
    return pieces


def expand_durations_to_cadence(durations, min_seconds: float = 1.0, max_seconds: float = 15.0) -> list[float]:
    """Flatten per-shot durations into 8-15s cadence chunks."""
    out: list[float] = []
    for d in durations:
        out.extend(_split_duration_to_cadence(float(d), min_sec=min_seconds, max_sec=max_seconds))
    return out


def build_visual_scene_plan(
    total_duration_sec: float,
    source_images: list[str] | None = None,
    min_seconds: float | None = None,
    max_seconds: float | None = None,
    custom_durations: list[float] | None = None,
    shot_durations: list[float] | None = None,
    video_mode: str = "longform",
    **kwargs,
) -> list[dict]:
    """Build a scene plan; each entry: {'duration', 'variant', 'source'}."""
    if min_seconds is None:
        min_seconds = SHORT_MIN_SCENE_SECONDS if video_mode == "short" else MIN_SCENE_SECONDS
    if max_seconds is None:
        max_seconds = SHORT_MAX_SCENE_SECONDS if video_mode == "short" else MAX_SCENE_SECONDS
    if custom_durations is not None:
        durations = custom_durations
    elif shot_durations is not None:
        durations = shot_durations
    else:
        durations = None
    if durations is None:
        pieces = _split_duration_to_cadence(
            float(total_duration_sec), min_sec=min_seconds, max_sec=max_seconds
        )
    else:
        pieces = expand_durations_to_cadence(
            durations, min_seconds=min_seconds, max_seconds=max_seconds
        )
    if not pieces:
        pieces = [round(float(total_duration_sec), 3)]
    sources = list(source_images or []) if source_images else []
    plan = []
    for i, duration in enumerate(pieces):
        plan.append({
            "duration": round(float(duration), 3),
            "variant": i % 4,
            "source": sources[i % len(sources)] if sources else None,
        })
    return plan


# ---------------------------------------------------------------------------
# Scene image resolution is owned by src.media.scene_image_provider.
# ---------------------------------------------------------------------------

def _resolve_local_scene_images(
    scene_prompts: list[str] | None,
    channel: str,
) -> list[str]:
    """Return only thematically matched bank assets; never synthesize images."""
    if not scene_prompts:
        return []
    try:
        from src.media.assets import check_local_templates

        images: list[str] = []
        for i, prompt in enumerate(scene_prompts):
            asset = check_local_templates(channel, prompt, match_only=True, scene_index=i)
            if asset and os.path.exists(asset):
                images.append(asset)
        return images
    except Exception as exc:
        logger.warning("Scene image resolution failed: %s", exc, exc_info=True)
        return []


# ---------------------------------------------------------------------------
# FFmpeg filter graphs
# ---------------------------------------------------------------------------

def build_audio_chain(
    ambient_volume: float = 0.04,
    music_volume: float = 0.04,
    lowpass_freq: int = 14000,
    audio_idx: int = 1,
    **kwargs,
) -> str:
    """Filter graph for narration + music/ambient with sidechain ducking.

    Con YT_FOLD_MASTERING=1 (default) la narración se masteriza en línea
    (EQ 120 Hz + loudnorm -14 LUFS), eliminando la pasada separada de
    lib.tts.master_voice_audio.
    """
    has_music = bool(kwargs.get("music_path"))
    has_ambient = bool(kwargs.get("ambient_path"))
    a1 = audio_idx
    a2 = audio_idx + 1
    a3 = audio_idx + 2
    narration_head = (
        f"[{a1}:a]{_MASTERING_PREFIX}aresample=48000,"
        if _is_mastering_folded()
        else f"[{a1}:a]aresample=48000,"
    )
    if has_music and has_ambient:
        return (
            f"{narration_head}asplit=3[speech_sc1][speech_sc2][speech_mix];"
            f"[{a2}:a]lowpass=f={lowpass_freq},volume={music_volume:.3f}[music_in];"
            "[music_in][speech_sc1]sidechaincompress=threshold=0.05:ratio=8:attack=20:release=300[music_ducked];"
            f"[{a3}:a]lowpass=f={lowpass_freq},volume={ambient_volume:.3f}[ambient_in];"
            "[ambient_in][speech_sc2]sidechaincompress=threshold=0.08:ratio=4:attack=40:release=400[ambient_ducked];"
            "[speech_mix][music_ducked][ambient_ducked]amix=inputs=3:duration=first:normalize=0[amixed];"
            "[amixed]aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[aout]"
        )
    if has_music or has_ambient:
        vol = music_volume if has_music else ambient_volume
        return (
            f"{narration_head}asplit=2[speech_sc][speech_mix];"
            f"[{a2}:a]lowpass=f={lowpass_freq},volume={vol:.3f}[bg_in];"
            "[bg_in][speech_sc]sidechaincompress=threshold=0.05:ratio=8:attack=20:release=300[bg_ducked];"
            "[speech_mix][bg_ducked]amix=inputs=2:duration=first:normalize=0[speech_bg];"
            "[speech_bg]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[aout]"
        )
    return (
        f"{narration_head}aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[aout]"
    )


def _default_audio_chain() -> str:
    return build_audio_chain()


class FFmpegFilterBuilder:
    """Builds sanitized ffmpeg filter graphs for narration + music/ambient mixes."""

    def __init__(self):
        self.inputs: list[str] = []

    def build_audio_chain(self, has_ambient=False, has_music=False, **kwargs):
        music_path = "music.wav" if has_music else None
        ambient_path = "ambient.wav" if has_ambient else None
        return shared_build_audio_chain(
            music_path=music_path, ambient_path=ambient_path,
            music_volume=kwargs.get("music_volume", 0.012),
            ambient_volume=kwargs.get("ambient_volume", 0.15),
            lowpass_freq=kwargs.get("lowpass_freq", 3000),
        )

    def build_video_chain(self, *args, **kwargs):  # noqa: ARG002
        return ""

    def build_subtitle_filter(self, *args, **kwargs):  # noqa: ARG002
        return ""


shared_build_audio_chain = build_audio_chain


# ---------------------------------------------------------------------------
# Thumbnails
# ---------------------------------------------------------------------------

def _cover_resize(img, size: tuple[int, int]):
    target_w, target_h = size
    img.thumbnail((target_w * 2, target_h * 2))
    ratio = max(target_w / img.width, target_h / img.height)
    new = img.resize((int(img.width * ratio), int(img.height * ratio)))
    left = (new.width - target_w) // 2
    top = (new.height - target_h) // 2
    return new.crop((left, top, left + target_w, top + target_h))


def _wrap_text(text, font, max_width):
    words = text.split()
    lines = []
    current = ""
    for w in words:
        test = f"{current} {w}".strip()
        if font.getlength(test) <= max_width or not current:
            current = test
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines or [text]


def generate_pil_thumbnail(
    title: str,
    output_path: str,
    bg_image_path: str | None = None,
    width: int = 1920,
    height: int = 1080,
    style: str | None = None,
    template: str | None = None,
    style_preset: Any | None = None,
    **kwargs,
) -> str:
    """Render a YouTube thumbnail with Pillow (pure local)."""
    if not _HAS_PIL:
        raise RuntimeError("Pillow is required to render thumbnails")
    from PIL import Image, ImageDraw, ImageFont, ImageEnhance

    thumb_style = style_preset
    if thumb_style is None and template:
        try:
            from src.templates.template_manager import get_template as get_tpl
            tpl = get_tpl(template)
            thumb_style = getattr(tpl, "thumbnail", None)
        except Exception:
            thumb_style = None

    def font(size: int):
        path = resolve_font_path()
        if path:
            try:
                return ImageFont.truetype(path, size=size)
            except (OSError, ValueError) as exc:
                logger.debug("Font load failed (%s): %s", path, exc)
        return ImageFont.load_default()

    if bg_image_path and os.path.exists(bg_image_path):
        img = _cover_resize(Image.open(bg_image_path).convert("RGB"), (width, height))
    else:
        base = Image.new("RGB", (width, height), (14, 12, 18))
        draw = ImageDraw.Draw(base)
        for i in range(0, height, 4):
            t = i / height
            shade = int(14 + (40 - 14) * t)
            draw.line([0, i, width, i], fill=(shade, shade - 2, shade + 6))
        img = base

    if thumb_style:
        c_boost = getattr(thumb_style, "contrast_boost", 1.0)
        if c_boost and c_boost != 1.0:
            img = ImageEnhance.Contrast(img).enhance(c_boost)
        clr_boost = getattr(thumb_style, "color_boost", 1.0)
        if clr_boost and clr_boost != 1.0:
            img = ImageEnhance.Color(img).enhance(clr_boost)

    draw = ImageDraw.Draw(img)
    title_upper = extract_hook_title(title or "HISTORIA IMPACTANTE")
    layout = getattr(thumb_style, "layout_type", "neon_horror") if thumb_style else "neon_horror"

    accent1 = getattr(thumb_style, "accent_color_1", "#FFE600") if thumb_style else "#FFE600"
    accent2 = getattr(thumb_style, "accent_color_2", "#FF003B") if thumb_style else "#FF003B"
    card_border = getattr(thumb_style, "card_border_color", "#FF4500") if thumb_style else "#FF4500"
    card_bg = getattr(thumb_style, "card_bg_color", "#0F0F16") if thumb_style else "#0F0F16"

    font_sz = getattr(thumb_style, "primary_font_size", None) if thumb_style else None
    if not font_sz:
        font_sz = max(56, int(height * 0.09))
    else:
        scale = height / 1080.0
        font_sz = max(40, int(font_sz * scale))

    fnt = font(font_sz)

    if layout == "reddit_card":
        card_w = int(width * 0.90)
        card_h = int(height * 0.35)
        card_x = (width - card_w) // 2
        card_y = int(height * 0.60)
        draw.rectangle([card_x, card_y, card_x + card_w, card_y + card_h], fill=card_bg, outline=card_border, width=4)
        lines = _wrap_text(title_upper, fnt, int(card_w * 0.92))
        y = card_y + max(10, (card_h - (len(lines) * (font_sz + 8))) // 2)
        for s in lines:
            bbox = draw.textbbox((0, 0), s, font=fnt)
            x = (width - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), s, font=fnt, fill="#FFFFFF", stroke_width=3, stroke_fill="#000000")
            y += (bbox[3] - bbox[1]) + 8

    elif layout == "cyberpunk":
        draw.rectangle([10, 10, width - 10, height - 10], outline=accent1, width=5)
        draw.line([20, 20, width - 20, 20], fill=accent2, width=3)
        draw.line([20, height - 20, width - 20, height - 20], fill=accent2, width=3)
        lines = _wrap_text(title_upper, fnt, int(width * 0.86))
        y = int(height * 0.65)
        for idx, s in enumerate(lines):
            bbox = draw.textbbox((0, 0), s, font=fnt)
            x = (width - (bbox[2] - bbox[0])) // 2
            fill_clr = accent1 if idx % 2 == 0 else accent2
            draw.text((x, y), s, font=fnt, fill=fill_clr, stroke_width=max(3, width // 100), stroke_fill="#000000")
            y += (bbox[3] - bbox[1]) + 10

    elif layout == "documentary":
        bar_h = int(height * 0.10)
        draw.rectangle([0, 0, width, bar_h], fill="#000000")
        draw.rectangle([0, height - bar_h, width, height], fill="#000000")
        lines = _wrap_text(title_upper, fnt, int(width * 0.86))
        y = int(height * 0.68)
        for s in lines:
            bbox = draw.textbbox((0, 0), s, font=fnt)
            x = (width - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), s, font=fnt, fill=accent1, stroke_width=3, stroke_fill="#000000")
            y += (bbox[3] - bbox[1]) + 8

    else:  # neon_horror default
        lines = _wrap_text(title_upper, fnt, int(width * 0.86))
        y = int(height * 0.68)
        for idx, s in enumerate(lines):
            bbox = draw.textbbox((0, 0), s, font=fnt)
            x = (width - (bbox[2] - bbox[0])) // 2
            fill_clr = accent1 if idx == 0 else (accent2 if idx == 1 else "#FFFFFF")
            draw.text((x, y), s, font=fnt, fill=fill_clr, stroke_width=max(4, width // 100), stroke_fill="#000000")
            y += (bbox[3] - bbox[1]) + 8

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out), format="JPEG", quality=90)
    return str(out)


def _overlay_hook_text(img, title: str):
    """Draw the uppercase hook title at ~76% height; returns the image."""
    from PIL import ImageDraw, ImageFont

    draw = ImageDraw.Draw(img)
    hook = extract_hook_title(title)
    path = resolve_font_path()
    fnt = None
    if path:
        try:
            fnt = ImageFont.truetype(path, size=max(48, int(img.width * 0.07)))
        except (OSError, ValueError) as exc:
            logger.debug("Hook text font load failed (%s): %s", path, exc)
            fnt = None
    if fnt is None:
        fnt = ImageFont.load_default()
    y = int(img.height * 0.76)
    for s in _wrap_text(hook, fnt, int(img.width * 0.82)):
        bbox = draw.textbbox((0, 0), s, font=fnt)
        x = (img.width - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), s, font=fnt, fill=(255, 255, 255),
                  stroke_width=4, stroke_fill=(0, 0, 0))
        y += (bbox[3] - bbox[1]) + 10
    return img


def _default_cover_prompt(title: str) -> str:
    return f"{title} cinematic storytelling cover, dramatic lighting, rich textures, 4k, No text, no watermark"


def _download_url(url: str) -> str | None:
    """Download a remote image to the local workset."""
    import hashlib

    try:
        import httpx
        resp = httpx.get(url, timeout=45, follow_redirects=True)
        if resp.status_code != 200:
            return None
        content = resp.content
    except ImportError:
        import requests
        resp = requests.get(url, timeout=45)
        if resp.status_code != 200:
            return None
        content = resp.content
    except Exception:
        return None
    cache_dir = Path(work_worksets_cache())
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / f"cover_{hashlib.sha256(url.encode()).hexdigest()[:16]}.jpg"
    dest.write_bytes(content)
    return str(dest) if dest.stat().st_size > 1000 else None


def work_worksets_cache() -> str:
    from src.config import SETTINGS

    return str(Path(SETTINGS.work_root) / "worksets" / "canonical")


def create_video_thumbnail(
    title: str,
    style: str,
    output_path: str,
    cover_prompt: str | None = None,
    strict_official_sdk: bool = False,
    **kwargs,
) -> str:
    """Create a high-CTR video thumbnail using ThumbnailEngine (extracting climax frame & chiaroscuro grading)."""
    v_mode = kwargs.get(
        "video_mode",
        "short" if style == "short" or kwargs.get("video_mode") == "short" else "longform",
    )
    target_w, target_h = SHORT_RES if v_mode == "short" else LONGFORM_RES

    bg_image_path = (
        kwargs.get("bg_image_path")
        or kwargs.get("background_image_path")
        or kwargs.get("background_path")
    )
    video_path = kwargs.get("video_path")
    manifest_path = kwargs.get("manifest_path") or kwargs.get("scene_manifest_path")
    channel_id = kwargs.get("channel_id") or kwargs.get("channel_name") or style or "moku"

    if is_test_environment() and not (video_path or manifest_path or bg_image_path):
        return generate_pil_thumbnail(
            title=title,
            output_path=output_path,
            bg_image_path=bg_image_path,
            width=target_w,
            height=target_h,
            style=style,
            **kwargs,
        )

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
            blur_radius=float(kwargs["blur_radius"]) if "blur_radius" in kwargs else 3.5,
            contrast_boost=float(kwargs["contrast_boost"]) if "contrast_boost" in kwargs else 1.35,
            primary_color=kwargs.get("primary_color"),
            accent_color=kwargs.get("accent_color"),
            archetype=kwargs.get("archetype") or kwargs.get("template") or kwargs.get("category"),
            template=kwargs.get("template"),
            metadata=meta,
        )
        res = engine.generate(
            config=cfg,
            video_path=video_path,
            manifest_path=manifest_path,
            base_image_path=bg_image_path,
        )
        return str(res)
    except Exception as e:
        logger.warning("ThumbnailEngine failed (%s), falling back to PIL basic: %s", e, output_path)
        return generate_pil_thumbnail(
            title=title,
            output_path=output_path,
            bg_image_path=bg_image_path,
            width=target_w,
            height=target_h,
            style=style,
            template=kwargs.get("template"),
            style_preset=kwargs.get("style_preset"),
        )


# ---------------------------------------------------------------------------
# compose_video — main FFmpeg composition
# ---------------------------------------------------------------------------

def _escape_filter_path(path: str) -> str:
    """Escape a filesystem path for an ffmpeg filter option value."""
    return str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def _ass_fontsdir_option() -> str:
    """``fontsdir=`` option pointing at the vendored font dir (empty when absent).

    libass resolves the "Montserrat Black"/"Montserrat" families declared by the
    ASS styles through this directory instead of falling back to a system font.
    """
    fonts_dir = _repo_root() / "assets" / "fonts"
    try:
        if not fonts_dir.is_dir():
            return ""
    except OSError:
        return ""
    return f":fontsdir='{_escape_filter_path(str(fonts_dir))}'"


def _pan_crop_expressions(w: int, h: int, dur_i: float, index: int) -> tuple[str, str]:
    """(x, y) crop expressions for scene ``index``.

    EASED_PAN=1 (default): cosine ease-in/out — slow at the extremes, fastest in
    the middle. EASED_PAN=0 restores the literal linear ramp. Both are crop-only
    (no zoompan, no rescales).
    """
    if _is_eased_pan_enabled():
        if index % 2 == 0:
            # Escenas pares: paneo horizontal suave con easing coseno
            x = f"(in_w-out_w)*(0.5-0.5*cos(PI*t/{dur_i:.4f}))"
            y = "(in_h-out_h)/2"
        else:
            # Escenas impares: paneo vertical suave con easing coseno
            x = "(in_w-out_w)/2"
            y = f"(in_h-out_h)*(0.5-0.5*cos(PI*t/{dur_i:.4f}))"
        return x, y
    if index % 2 == 0:
        # Escenas pares: Paneo horizontal suave de izquierda a derecha
        return f"(in_w-out_w)*(t/{dur_i:.4f})", "(in_h-out_h)/2"
    # Escenas impares: Paneo vertical o diagonal sutil
    return "(in_w-out_w)/2", f"(in_h-out_h)*(t/{dur_i:.4f})"


def _asset_manager_instance():
    """Load the asset manager defensively (None when unavailable)."""
    try:
        from src.asset_manager import get_asset_manager
        return get_asset_manager()
    except Exception:
        return None


_asset_manager = _asset_manager_instance


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
    """Compose a vertical/horizontal video from narration, subtitles and visuals."""
    test_env = _get_video_attr("is_test_environment", is_test_environment)()
    if min_duration is not None:
        effective_min = float(min_duration)
    elif test_env:
        effective_min = 10.0
    else:
        effective_min = float(DEFAULT_MIN_DURATION)

    if float(duration_sec or 0) < effective_min:
        raise ValueError(
            f"Video duration {duration_sec} must exceed minimum duration "
            f"{effective_min} seconds"
        )

    out_dir = os.path.dirname(os.path.abspath(output_video_path)) or "."
    os.makedirs(out_dir, exist_ok=True)

    short = video_mode == "short"
    res = SHORT_RES if short else LONGFORM_RES
    min_s = SHORT_MIN_SCENE_SECONDS if short else MIN_SCENE_SECONDS
    max_s = SHORT_MAX_SCENE_SECONDS if short else MAX_SCENE_SECONDS

    # ---- visual planning ---------------------------------------------------
    if shot_durations:
        plan = build_visual_scene_plan(
            float(duration_sec), shot_durations=shot_durations,
            min_seconds=min_s, max_seconds=max_s, video_mode=video_mode,
        )
    elif scene_images:
        plan = build_visual_scene_plan(
            float(duration_sec), source_images=scene_images,
            min_seconds=min_s, max_seconds=max_s, video_mode=video_mode,
        )
    elif scene_prompts:
        plan = build_visual_scene_plan(
            float(duration_sec), min_seconds=min_s, max_seconds=max_s, video_mode=video_mode,
        )
    else:
        plan = build_visual_scene_plan(
            float(duration_sec),
            source_images=[background_video_path] if background_video_path else None,
            min_seconds=min_s, max_seconds=max_s, video_mode=video_mode,
        )

    materialized: list[str] = []
    if scene_images:
        materialized = list(scene_images)
    elif scene_prompts:
        materialized = _resolve_local_scene_images(scene_prompts, channel)
    else:
        manager = _asset_manager()
        if manager is not None:
            try:
                seq = manager.get_background_sequence(count=len(plan)) or []
                materialized = [str(p) for p in seq if p]
            except Exception:
                materialized = []
            if not materialized:
                try:
                    bg = manager.get_background() or ""
                except Exception:
                    bg = ""
                if bg and os.path.exists(bg):
                    materialized = [str(bg)]
        if not materialized and background_video_path and os.path.exists(background_video_path):
            materialized = [background_video_path]

    valid_sources = [p for p in materialized if p and os.path.exists(p)]
    inputs: list[str] = []

    # ---- visual chain ------------------------------------------------------
    concat_txt_path: Path | None = None
    processed_sources: list[Any] = []
    overlays_applied: list[str] = []
    try:
        if valid_sources:
            n_src = len(valid_sources)
            w, h = res
            scale_w = int(round(w * 1.08))
            scale_h = int(round(h * 1.08))
            if _HAS_PIL:
                from PIL import Image, ImageOps
                for idx, img_p in enumerate(valid_sources):
                    p_obj = Path(img_p)
                    if p_obj.is_file() and p_obj.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                        try:
                            prescaled_p = Path(out_dir) / f"prescaled_{idx:03d}.jpg"
                            # ---- 2c: per-channel overlay + grade bake -----------
                            # Runs before/independently of the overscale size check so
                            # bank assets already inside the 1.08x box still get the
                            # look. VISUAL_OVERLAYS=0 / VISUAL_GRADE=0 restore exact
                            # current bytes (no re-encode at all).
                            bake_active = False
                            layers: list[Path] = []
                            if (
                                _is_visual_overlays_enabled()
                                or _is_visual_grade_enabled()
                            ):
                                layers = channel_overlay_paths(channel)
                                grade_factors = channel_grade_factors(channel)
                                bake_active = bool(layers or grade_factors)
                                if (
                                    bake_active
                                    and not prescaled_p.is_file()
                                    and p_obj.resolve() != prescaled_p.resolve()
                                ):
                                    with Image.open(p_obj) as im_src:
                                        im_fit = ImageOps.fit(
                                            im_src.convert("RGB"),
                                            (scale_w, scale_h),
                                            method=Image.Resampling.BICUBIC,
                                        )
                                    im_fit = _apply_channel_overlays(im_fit, channel)
                                    im_fit = _apply_channel_grade(im_fit, channel)
                                    im_fit.save(prescaled_p, format="JPEG", quality=92)
                                    for layer in layers:
                                        name = Path(layer).name
                                        if name not in overlays_applied:
                                            overlays_applied.append(name)
                            with Image.open(p_obj) as im:
                                if (
                                    im.width <= scale_w
                                    and im.height <= scale_h
                                    and not bake_active
                                ):
                                    # Ya ≤ objetivo: reescalar la AMPLIFICARÍA (+16% px)
                                    # y encarecería el decode de cada frame looped.
                                    processed_sources.append(img_p)
                                    continue
                                if not prescaled_p.is_file() or prescaled_p.stat().st_size == 0:
                                    if im.format == "JPEG":
                                        im.draft("RGB", (scale_w, scale_h))
                                    im_rgb = im.convert("RGB")
                                    im_fit = ImageOps.fit(im_rgb, (scale_w, scale_h), method=Image.Resampling.BICUBIC)
                                    im_fit.save(prescaled_p, format="JPEG", quality=92)
                                processed_sources.append(prescaled_p)
                                continue
                        except Exception:
                            pass
                    processed_sources.append(img_p)
            else:
                processed_sources = list(valid_sources)

            if shot_durations and len(shot_durations) == n_src:
                img_durations = [float(d) for d in shot_durations]
            else:
                img_durations = [float(duration_sec or 1.0) / n_src] * n_src
            rem = float(duration_sec or 1.0) - sum(img_durations)
            if img_durations:
                img_durations[-1] += rem

            enable_zoompan = kwargs.get("zoompan", True) and kwargs.get("motion", True)
            enable_transitions = kwargs.get("transitions", True)

            # Calculate transition duration T_trans
            T_trans = 0.5
            if img_durations:
                min_dur = min(img_durations)
                T_trans = min(0.5, max(0.1, min_dur / 3.0))

            if n_src > 1 and enable_transitions:
                total_trans_time = (n_src - 1) * T_trans
                pad_per_img = total_trans_time / n_src
                padded_durations = [d + pad_per_img for d in img_durations]
            else:
                padded_durations = list(img_durations)

            for i in range(n_src):
                img_p = processed_sources[i]
                dur_i = padded_durations[i]
                p_str = str(img_p)
                if p_str.lower().endswith((".mp4", ".mov", ".mkv", ".webm", ".avi")):
                    inputs += ["-stream_loop", "-1", "-t", f"{dur_i:.4f}", "-i", p_str]
                elif p_str.lower().endswith(".gif"):
                    inputs += ["-ignore_loop", "0", "-t", f"{dur_i:.4f}", "-i", p_str]
                else:
                    inputs += ["-loop", "1", "-t", f"{dur_i:.4f}", "-i", p_str]

            v_stream_filters = []
            for i in range(n_src):
                dur_i = max(0.1, padded_durations[i])
                if enable_zoompan:
                    # Zero-cost motion: crop-only pan. EASED_PAN=1 (default) eases
                    # the ramp with cos(); EASED_PAN=0 restores the linear ramp.
                    pan_x, pan_y = _pan_crop_expressions(w, h, dur_i, i)
                    crop_filter = f"crop=w={w}:h={h}:x={pan_x}:y={pan_y}"
                    v_stream_filters.append(
                        f"[{i}:v]scale={scale_w}:{scale_h}:force_original_aspect_ratio=increase,"
                        f"crop={scale_w}:{scale_h},{crop_filter},"
                        f"fps={VIDEO_FPS},setsar=1,format=yuv420p[v{i}]"
                    )
                else:
                    v_stream_filters.append(
                        f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
                        f"crop={w}:{h},fps={VIDEO_FPS},setsar=1,format=yuv420p[v{i}]"
                    )

            # --- chunked xfade: lift n<=15 ceiling ---
            # Use helper for T_trans consistency (same formula as above)
            T_trans = _compute_T_trans(img_durations)
            tot_dur = float(duration_sec or 1.0)
            fade_out_st = max(0.0, tot_dur - 0.3)

            xfade_filters: list[str] = []
            use_chunked = enable_transitions and n_src > 15 and _is_chunked_xfade_enabled()

            if use_chunked:
                blocks = _build_chunked_blocks(n_src)
                # split overlapping sources so same [v idx] can be used in two adjacent blocks
                split_filters: list[str] = []
                overlap_indices = [blocks[k][0] for k in range(1, len(blocks))]
                for idx in overlap_indices:
                    split_filters.append(f"[v{idx}]split=2[v{idx}_a][v{idx}_b]")

                block_output_tags: list[str] = []
                for block_idx, (s, e) in enumerate(blocks):
                    block_len = e - s
                    # resolve source tags for this block respecting splits
                    src_tags: list[str] = []
                    for pos in range(block_len):
                        g_idx = s + pos
                        if g_idx in overlap_indices:
                            if pos == 0 and block_idx != 0:
                                src_tags.append(f"[v{g_idx}_b]")
                            elif pos == block_len - 1 and block_idx != len(blocks) - 1:
                                src_tags.append(f"[v{g_idx}_a]")
                            else:
                                # interior overlap cannot happen except at boundaries
                                src_tags.append(f"[v{g_idx}]")
                        else:
                            src_tags.append(f"[v{g_idx}]")
                    if block_len == 1:
                        blk_tag = f"[blk{block_idx}]"
                        xfade_filters.append(f"{src_tags[0]}null{blk_tag}")
                        block_output_tags.append(blk_tag)
                    else:
                        block_cum = padded_durations[s]
                        current_tag = src_tags[0]
                        for local_k in range(block_len - 1):
                            next_tag = src_tags[local_k + 1]
                            if local_k == block_len - 2:
                                out_tag = f"[blk{block_idx}]"
                            else:
                                out_tag = f"[blk{block_idx}_vx{local_k+1}]"
                            offset_k = max(0.0, block_cum - T_trans)
                            block_cum += padded_durations[s + local_k + 1] - T_trans
                            xfade_filters.append(
                                f"{current_tag}{next_tag}xfade=transition=fade:duration={T_trans:.3f}:offset={offset_k:.3f}{out_tag}"
                            )
                            current_tag = out_tag
                        block_output_tags.append(f"[blk{block_idx}]")

                # prepend split filters so they are resolved before use
                if split_filters:
                    xfade_filters = split_filters + xfade_filters

                if len(block_output_tags) == 1:
                    chained_tag = block_output_tags[0]
                else:
                    concat_inputs = "".join(block_output_tags)
                    concat_filter = f"{concat_inputs}concat=n={len(block_output_tags)}:v=1:a=0[vchained]"
                    xfade_filters.append(concat_filter)
                    chained_tag = "[vchained]"

                # Tentative full filter to check 32k overflow
                tentative = ";".join(v_stream_filters + xfade_filters + [f"{chained_tag}fade=t=in:st=0:d=0.3,fade=t=out:st={fade_out_st:.3f}:d=0.3[vconcat]"])
                if _filter_complex_exceeds_limit(tentative):
                    # Fallback to temp-file style plain concat (no xfade) — preserve rollback path
                    try:
                        concat_txt_path = Path(out_dir) / "chunked_fallback_concat.txt"
                        with open(concat_txt_path, "w") as _cf:
                            for i in range(n_src):
                                _cf.write(f"file '{processed_sources[i]}'\n")
                    except Exception:
                        pass
                    concat_inputs = "".join(f"[v{i}]" for i in range(n_src))
                    fallback = f"{concat_inputs}concat=n={n_src}:v=1:a=0[vchained]"
                    xfade_filters = [fallback]
                    chained_tag = "[vchained]"

            elif 1 < n_src <= 15 and enable_transitions:
                cum_dur = padded_durations[0]
                current_tag = "[v0]"
                for k in range(n_src - 1):
                    next_tag = f"[v{k+1}]"
                    out_tag = f"[vx{k+1}]"
                    offset_k = max(0.0, cum_dur - T_trans)
                    cum_dur += padded_durations[k+1] - T_trans
                    xfade_filters.append(
                        f"{current_tag}{next_tag}xfade=transition=fade:duration={T_trans:.3f}:offset={offset_k:.3f}{out_tag}"
                    )
                    current_tag = out_tag
                chained_tag = current_tag
            elif n_src > 1:
                concat_inputs = "".join(f"[v{i}]" for i in range(n_src))
                concat_filter = f"{concat_inputs}concat=n={n_src}:v=1:a=0[vchained]"
                xfade_filters.append(concat_filter)
                chained_tag = "[vchained]"
            else:
                chained_tag = "[v0]"

            ambient_fade_str = f"{chained_tag}fade=t=in:st=0:d=0.3,fade=t=out:st={fade_out_st:.3f}:d=0.3[vconcat]"
            vchain = ";".join(v_stream_filters + xfade_filters + [ambient_fade_str])
        else:
            inputs += ["-f", "lavfi", "-i", f"color=c=black:s={res[0]}x{res[1]}:r={VIDEO_FPS}"]
            vchain = (
                f"[0:v]scale={res[0]}:{res[1]}:force_original_aspect_ratio=increase,"
                f"crop={res[0]}:{res[1]}[vconcat]"
            )

        if subtitle_path and os.path.exists(subtitle_path):
            sub_escaped = _escape_filter_path(str(subtitle_path))
            if subtitle_path.lower().endswith(".ass"):
                # fontsdir lets libass resolve the vendored brand font for the
                # "Montserrat Black"/"Montserrat" style families; omitted when
                # the directory does not exist (filtergraph stays byte-identical
                # to the pre-2d shape in that case).
                vchain += f";[vconcat]ass=filename='{sub_escaped}'{_ass_fontsdir_option()}[vsubbed]"
            else:
                vchain += f";[vconcat]subtitles=filename='{sub_escaped}'[vsubbed]"
            # Cada rama por escena ya emite yuv420p; solo afirmamos el formato
            # (sin el rescale out_range=tv redundante a resolución completa).
            vchain += ";[vsubbed]format=yuv420p[vout]"
        else:
            vchain += ";[vconcat]format=yuv420p[vout]"

        # ---- audio inputs ------------------------------------------------------
        audio_start_idx = n_src if valid_sources else 1
        inputs += ["-i", audio_path]

        bgm = kwargs.get("bgm_path") or kwargs.get("bg_music_path") or bgm_path or ""
        ambient = kwargs.get("ambient_path") or kwargs.get("bg_ambient_path") or bg_ambient_path or ""
        manager = _asset_manager()
        if not bgm and manager is not None:
            try:
                candidate = manager.get_music() or ""
            except Exception:
                candidate = ""
            if candidate and os.path.exists(candidate):
                bgm = str(candidate)
        if not ambient and manager is not None:
            try:
                candidate = manager.get_ambient() or ""
            except Exception:
                candidate = ""
            if candidate and os.path.exists(candidate):
                ambient = str(candidate)

        has_music = bool(bgm and os.path.exists(bgm))
        has_ambient = bool(ambient and os.path.exists(ambient))
        if has_music:
            inputs += ["-stream_loop", "-1", "-i", bgm]
        if has_ambient:
            inputs += ["-stream_loop", "-1", "-i", ambient]

        if has_music and has_ambient:
            achain = build_audio_chain(music_path=bgm, ambient_path=ambient, audio_idx=audio_start_idx)
        elif has_music or has_ambient:
            achain = build_audio_chain(
                music_path=bgm if has_music else None,
                ambient_path=ambient if has_ambient else None,
                audio_idx=audio_start_idx,
            )
        else:
            achain = build_audio_chain(audio_idx=audio_start_idx)

        args = ["ffmpeg", "-y", "-hide_banner"]
        args += inputs
        args += ["-filter_complex", f"{vchain};{achain}"]
        args += ["-map", "[vout]", "-map", "[aout]"]
        args += ["-c:v", "libx264", "-preset", RENDER_PRESET, "-crf", str(RENDER_CRF)]
        args += ["-threads", str(FFMPEG_THREADS)]
        args += ["-filter_threads", str(min(FFMPEG_THREADS, 2))]
        if _ENABLE_X264_AQ:
            args += ["-x264-params", "aq-mode=3:aq-strength=1.0"]
        args += ["-pix_fmt", "yuv420p", "-color_range", "tv", "-profile:v", "main"]
        args += ["-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2"]
        args += ["-movflags", "+faststart", "-t", f"{float(duration_sec):.2f}"]
        args += [output_video_path]

        # R5: stream the (huge) ffmpeg progress log to disk instead of buffering
        # the whole stderr in RAM. Off by default so hermetic tests that patch
        # ``subprocess.run`` keep working; production enables it via compose env.
        if os.environ.get("YT_COMPOSE_STREAM_STDERR", "0") == "1":
            try:
                log_path = Path(out_dir) / "ffmpeg_compose.log"
                res = run_ffmpeg(
                    args, timeout=3600.0, check=False, stderr_file=str(log_path)
                )
                if res.returncode != 0:
                    raise RuntimeError(
                        f"FFmpeg composition failed: {res.stderr[-1200:]}"
                    )
            except RuntimeError:
                raise
            except Exception as exc:
                raise RuntimeError(f"FFmpeg composition failed: {exc}") from exc
        else:
            _subprocess = _get_video_attr("subprocess", subprocess)
            if _subprocess is not None and hasattr(_subprocess, "run"):
                result = _subprocess.run(args, capture_output=True, text=True, timeout=3600)
                if result.returncode != 0:
                    raise RuntimeError(f"FFmpeg composition failed: {result.stderr[-1200:]}")
            else:
                try:
                    run_ffmpeg(args, timeout=3600.0, check=True)
                except Exception as exc:
                    raise RuntimeError(f"FFmpeg composition failed: {exc}") from exc

        validator = _get_video_attr("validate_video_format", validate_video_format)
        if not validator(output_video_path, min_duration=effective_min):
            raise RuntimeError(f"Composed video failed validation: {output_video_path}")

        vplan = {
            "scene_count": len(plan),
            "covered_seconds": round(float(sum(p["duration"] for p in plan)), 3),
            "black_fallbacks": 0,
            "overlays_applied": overlays_applied,
            "scenes": [
                {
                    "duration": p["duration"],
                    "source": materialized[i % len(materialized)] if materialized else "",
                }
                for i, p in enumerate(plan)
            ],
        }
        Path(os.path.join(out_dir, "visual_plan.json")).write_text(
            json.dumps(vplan, indent=2), encoding="utf-8"
        )

        return output_video_path
    finally:
        if concat_txt_path and concat_txt_path.exists():
            try:
                concat_txt_path.unlink()
            except OSError:
                pass
        for proc_p in processed_sources:
            if isinstance(proc_p, Path) and proc_p.name.startswith("prescaled_") and proc_p.exists():
                try:
                    proc_p.unlink()
                except OSError:
                    pass
        try:
            for extra_p in Path(out_dir).glob("prescaled_*.jpg"):
                try:
                    extra_p.unlink()
                except OSError:
                    pass
        except Exception:
            pass


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
# Back-compat aliases
# ---------------------------------------------------------------------------

def _compose_video_effect(
    audio_path, subtitle_file, background_path, output_video,
    duration_sec, min_duration, channel, template, strict_visuals,
    scene_prompts, shot_durations, video_mode, scene_images, bg_music_path, bg_ambient_path,
):
    return compose_video(
        audio_path=audio_path, subtitle_path=subtitle_file,
        background_video_path=background_path, output_video_path=output_video,
        duration_sec=duration_sec, min_duration=min_duration, channel=channel,
        template=template, strict_visuals=strict_visuals, scene_prompts=scene_prompts,
        shot_durations=shot_durations, video_mode=video_mode, scene_images=scene_images,
        bgm_path=bg_music_path, bg_ambient_path=bg_ambient_path,
    )


compose_media = _compose_video_effect
create_motion_fragment = _compose_video_effect
_compositor_compose_video = _compose_video_effect


# ---------------------------------------------------------------------------
# Container helpers
# ---------------------------------------------------------------------------

def has_faststart(path: str) -> bool:
    """True when the moov atom precedes mdat (or file too small to decide)."""
    return ffmpeg_has_faststart(path)


def daemon_video_test() -> bool:
    return True
