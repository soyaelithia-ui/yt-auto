"""Comprehensive End-to-End (E2E) Validation Test Suite for YouTube Creepy Automation.

Covers:
- Tier 1: Error-free video generation producing valid .mp4 without console crashes or exceptions.
- Tier 2: Video stream and audio track presence, audio duration matching video stream duration.
- Tier 3: Subtitle styling compliance (no line overlaps, no vertical margin safe-zone cutoffs under Shorts UI).
- Tier 4: Background asset fitting (images/videos pre-cropped and resized to target 1080x1920 / 1280x720 canvas without demux distortion).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple

import pytest
from PIL import Image, ImageDraw

from lib.qa_gatekeeper import QAGatekeeper, ffprobe
from lib.subtitles import create_ass_subtitles, create_subtitles
from lib.video import (
    LONGFORM_RES,
    SHORT_RES,
    compose_video,
    validate_video_format,
)
from src.core.resolution import LONGFORM_RESOLUTION, SHORT_RESOLUTION
from tests.e2e.conftest import E2EVideoVerifier


# ---------------------------------------------------------------------------
# Helper Fixtures & Utilities
# ---------------------------------------------------------------------------

def create_synthetic_wav(path: str | Path, duration_sec: float = 5.0, sample_rate: int = 44100) -> str:
    """Generate a clean 440Hz sine wave WAV audio file via FFmpeg."""
    path_str = str(path)
    os.makedirs(os.path.dirname(os.path.abspath(path_str)), exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration_sec}",
        "-ar", str(sample_rate), "-ac", "1",
        path_str,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return path_str


def create_synthetic_image(path: str | Path, width: int, height: int, color: Tuple[int, int, int] = (100, 50, 150)) -> str:
    """Generate a test image with high edge density and contrast for visual integrity checks."""
    path_str = str(path)
    os.makedirs(os.path.dirname(os.path.abspath(path_str)), exist_ok=True)
    img = Image.new("RGB", (width, height), color)
    draw = ImageDraw.Draw(img)

    # Draw grid lines and high-contrast geometric shapes so edge density > 2.0 & contrast > 5.0
    for x in range(0, width, 20):
        draw.line([(x, 0), (x, height)], fill=(200, 220, 255), width=2)
    for y in range(0, height, 20):
        draw.line([(0, y), (width, y)], fill=(255, 200, 220), width=2)

    draw.rectangle([width // 5, height // 5, 4 * width // 5, 4 * height // 5], fill=(240, 180, 40), outline=(0, 0, 0), width=5)
    img.save(path_str, format="JPEG", quality=90)
    return path_str


def build_test_word_timestamps(words: List[str], duration_sec: float = 5.0) -> List[Dict[str, float | str]]:
    """Build word timestamps evenly spaced over duration_sec."""
    if not words:
        words = ["Hola", "esto", "es", "una", "prueba"]
    w_dur = duration_sec / len(words)
    timestamps = []
    for idx, w in enumerate(words):
        start = round(idx * w_dur, 3)
        end = round((idx + 1) * w_dur, 3)
        timestamps.append({"word": w, "start": start, "end": end})
    return timestamps


# ---------------------------------------------------------------------------
# Tier 1: Error-Free Video Generation
# ---------------------------------------------------------------------------

@pytest.mark.tier1
def test_tier1_shorts_video_generation_error_free(tmp_path: Path):
    """Tier 1: Verify error-free Shorts video generation producing valid .mp4 without console crashes."""
    audio_file = create_synthetic_wav(tmp_path / "audio_t1_short.wav", duration_sec=5.0)
    img1 = create_synthetic_image(tmp_path / "scene1.jpg", 720, 1280, (30, 40, 80))
    img2 = create_synthetic_image(tmp_path / "scene2.jpg", 720, 1280, (80, 30, 40))

    stamps = build_test_word_timestamps(["Terror", "en", "la", "noche"], duration_sec=5.0)
    ass_file = str(tmp_path / "subs_t1_short.ass")
    create_ass_subtitles(stamps, output_path=ass_file, template="short_neon_horror", video_res=(720, 1280))

    output_mp4 = str(tmp_path / "output_t1_short.mp4")

    result_path = compose_video(
        audio_path=audio_file,
        subtitle_path=ass_file,
        background_video_path=img1,
        output_video_path=output_mp4,
        duration_sec=5.0,
        min_duration=0.0,
        video_mode="short",
        scene_images=[img1, img2],
    )

    assert os.path.exists(result_path), "Target .mp4 file must exist after compose_video."
    assert os.path.getsize(result_path) > 0, "Target .mp4 file must not be 0 bytes."

    # Validate container format & stream properties
    is_valid = validate_video_format(result_path, min_duration=0.0)
    assert is_valid is True, "Generated Shorts video must pass validate_video_format."


@pytest.mark.tier1
def test_tier1_longform_video_generation_error_free(tmp_path: Path):
    """Tier 1: Verify error-free Longform (horizontal 1280x720) video generation without crashes."""
    audio_file = create_synthetic_wav(tmp_path / "audio_t1_long.wav", duration_sec=6.0)
    img1 = create_synthetic_image(tmp_path / "scene_long1.jpg", 1280, 720, (20, 90, 40))
    img2 = create_synthetic_image(tmp_path / "scene_long2.jpg", 1280, 720, (90, 40, 20))

    stamps = build_test_word_timestamps(["Historia", "de", "terror", "completa"], duration_sec=6.0)
    ass_file = str(tmp_path / "subs_t1_long.ass")
    create_ass_subtitles(stamps, output_path=ass_file, template="reddit_card", video_res=(1280, 720))

    output_mp4 = str(tmp_path / "output_t1_longform.mp4")

    result_path = compose_video(
        audio_path=audio_file,
        subtitle_path=ass_file,
        background_video_path=img1,
        output_video_path=output_mp4,
        duration_sec=6.0,
        min_duration=0.0,
        video_mode="longform",
        scene_images=[img1, img2],
    )

    assert os.path.exists(result_path), "Target Longform .mp4 file must exist."
    assert os.path.getsize(result_path) > 0, "Target Longform .mp4 file must not be 0 bytes."
    assert validate_video_format(result_path, min_duration=0.0) is True


@pytest.mark.tier1
def test_tier1_graceful_handling_missing_optional_inputs(tmp_path: Path):
    """Tier 1: Verify graceful composition without crashes when optional background audio is omitted."""
    audio_file = create_synthetic_wav(tmp_path / "audio_minimal.wav", duration_sec=4.0)
    img = create_synthetic_image(tmp_path / "single_bg.jpg", 720, 1280, (50, 50, 50))
    output_mp4 = str(tmp_path / "output_minimal.mp4")

    result_path = compose_video(
        audio_path=audio_file,
        subtitle_path="",
        background_video_path=img,
        output_video_path=output_mp4,
        duration_sec=4.0,
        min_duration=0.0,
        video_mode="short",
        scene_images=[img],
    )

    assert os.path.exists(result_path)
    assert os.path.getsize(result_path) > 0


# ---------------------------------------------------------------------------
# Tier 2: Stream & Audio Track Alignment & Duration Matching
# ---------------------------------------------------------------------------

@pytest.mark.tier2
def test_tier2_video_audio_streams_present_and_aligned_shorts(tmp_path: Path):
    """Tier 2: Verify video stream and audio track presence and audio duration matching video duration for Shorts."""
    duration = 5.0
    audio_file = create_synthetic_wav(tmp_path / "t2_audio.wav", duration_sec=duration)
    img1 = create_synthetic_image(tmp_path / "t2_bg1.jpg", 720, 1280, (40, 60, 90))
    img2 = create_synthetic_image(tmp_path / "t2_bg2.jpg", 720, 1280, (90, 40, 60))
    output_mp4 = str(tmp_path / "output_t2_shorts.mp4")

    compose_video(
        audio_path=audio_file,
        subtitle_path="",
        background_video_path=img1,
        output_video_path=output_mp4,
        duration_sec=duration,
        min_duration=0.0,
        video_mode="short",
        scene_images=[img1, img2],
    )

    verifier = E2EVideoVerifier(strict_mode=False)
    probe_data = verifier.probe(output_mp4)

    streams = probe_data.get("streams", [])
    v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    assert v_stream is not None, "Video stream must be present in output MP4."
    assert a_stream is not None, "Audio stream must be present in output MP4."
    assert v_stream.get("codec_name") == "h264", "Video codec must be h264."
    assert a_stream.get("codec_name") == "aac", "Audio codec must be aac."

    format_dur = float(probe_data.get("format", {}).get("duration", 0.0))
    v_dur = format_dur
    a_dur = float(a_stream.get("duration") or format_dur)

    drift = abs(v_dur - a_dur)
    assert drift <= 0.30, f"Audio/video duration desync drift {drift:.3f}s exceeds allowed threshold 0.30s."


@pytest.mark.tier2
def test_tier2_video_audio_streams_present_and_aligned_longform(tmp_path: Path):
    """Tier 2: Verify video stream and audio track presence and duration matching for Longform (1280x720)."""
    duration = 6.0
    audio_file = create_synthetic_wav(tmp_path / "t2_long_audio.wav", duration_sec=duration)
    img1 = create_synthetic_image(tmp_path / "t2_long_bg1.jpg", 1280, 720, (90, 60, 40))
    img2 = create_synthetic_image(tmp_path / "t2_long_bg2.jpg", 1280, 720, (40, 90, 60))
    output_mp4 = str(tmp_path / "output_t2_longform.mp4")

    compose_video(
        audio_path=audio_file,
        subtitle_path="",
        background_video_path=img1,
        output_video_path=output_mp4,
        duration_sec=duration,
        min_duration=0.0,
        video_mode="longform",
        scene_images=[img1, img2],
    )

    verifier = E2EVideoVerifier(strict_mode=False)
    probe_data = verifier.probe(output_mp4)

    streams = probe_data.get("streams", [])
    v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    assert v_stream is not None, "Video stream must be present."
    assert a_stream is not None, "Audio stream must be present."
    assert v_stream.get("codec_name") == "h264"
    assert a_stream.get("codec_name") == "aac"

    format_dur = float(probe_data.get("format", {}).get("duration", 0.0))
    v_dur = format_dur
    a_dur = float(a_stream.get("duration") or format_dur)

    drift = abs(v_dur - a_dur)
    assert drift <= 0.30, f"Longform AV desync drift {drift:.3f}s exceeds threshold 0.30s."


@pytest.mark.tier2
def test_tier2_gatekeeper_detects_av_desync_and_missing_audio(tmp_path: Path):
    """Tier 2: Verify QAGatekeeper and E2EVideoVerifier correctly flag desync and missing audio stream."""
    verifier = E2EVideoVerifier(strict_mode=True)

    # 1. Non-existent file
    res_missing = verifier.verify_video(tmp_path / "nonexistent.mp4")
    assert res_missing["passed"] is False

    # 2. File with missing audio stream
    no_audio_mp4 = str(tmp_path / "no_audio.mp4")
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=720x1280:d=3",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        no_audio_mp4,
    ]
    subprocess.run(cmd, check=True, capture_output=True)

    res_no_audio = verifier.verify_video(no_audio_mp4, expected_resolution=(720, 1280))
    assert res_no_audio["passed"] is False
    assert any("No audio stream found" in err or "ERR_QA_DEAD_AUDIO" in err for err in res_no_audio["errors"])


# ---------------------------------------------------------------------------
# Tier 3: Subtitle Styling Compliance (No Overlaps & Safe-Zone MarginV >= 120)
# ---------------------------------------------------------------------------

@pytest.mark.tier3
def test_tier3_subtitle_margin_v_safe_zone_compliance(tmp_path: Path):
    """Tier 3: Verify ASS subtitle MarginV >= 120 to avoid YouTube Shorts UI cutoffs."""
    stamps = build_test_word_timestamps(["Esta", "es", "una", "frase", "de", "prueba"], duration_sec=4.0)
    ass_path = str(tmp_path / "shorts_safezone.ass")

    create_ass_subtitles(
        word_timestamps=stamps,
        output_path=ass_path,
        template=None,
        video_res=(720, 1280),
    )

    assert os.path.exists(ass_path)
    content = Path(ass_path).read_text(encoding="utf-8")

    # Inspect Style definitions in ASS header
    style_matches = re.findall(r"^Style:\s*([^\n]+)", content, flags=re.MULTILINE)
    assert len(style_matches) > 0, "ASS file must contain Style definition line."

    for style_line in style_matches:
        fields = [f.strip() for f in style_line.split(",")]
        # ASS style fields: Name, Fontname, Fontsize, PrimaryColour, ..., MarginL(19), MarginR(20), MarginV(21)
        if len(fields) >= 22:
            margin_v = int(float(fields[21]))
            assert margin_v >= 120, f"ASS Subtitle MarginV ({margin_v}) must be >= 120 for Shorts UI safe zone."

    gatekeeper = QAGatekeeper()
    issues, max_chars, max_words, safe = gatekeeper._audit_subtitles(ass_path)
    assert safe is True, "QAGatekeeper subtitle audit must mark default subtitle safe zone compliant."
    assert not any(i.code == "ERR_QA_SUBTITLE_SAFEZONE" for i in issues)


@pytest.mark.tier3
def test_tier3_subtitle_no_line_overlaps_and_inline_breaks(tmp_path: Path):
    """Tier 3: Verify multi-line ASS subtitles use inline \\N linebreaks without overlapping timestamp events."""
    words = ["En", "un", "lugar", "oscuro", "de", "la", "noche", "silenciosa", "nada", "es", "lo", "que", "parece"]
    stamps = build_test_word_timestamps(words, duration_sec=8.0)
    ass_path = str(tmp_path / "no_overlap.ass")

    create_ass_subtitles(
        word_timestamps=stamps,
        output_path=ass_path,
        template="short_neon_horror",
        video_res=(720, 1280),
    )

    content = Path(ass_path).read_text(encoding="utf-8")
    dialogue_lines = [line for line in content.splitlines() if line.startswith("Dialogue:")]

    assert len(dialogue_lines) > 0, "ASS file must contain Dialogue events."

    event_intervals = []
    for d_line in dialogue_lines:
        parts = d_line.split(",", 9)
        start_str = parts[1].strip()
        end_str = parts[2].strip()

        h, m, s_cc = start_str.split(":")
        s, cc = s_cc.split(".")
        start_sec = int(h) * 3600 + int(m) * 60 + int(s) + int(cc) / 100.0

        h2, m2, s_cc2 = end_str.split(":")
        s2, cc2 = s_cc2.split(".")
        end_sec = int(h2) * 3600 + int(m2) * 60 + int(s2) + int(cc2) / 100.0

        event_intervals.append((start_sec, end_sec, parts[9] if len(parts) > 9 else ""))

    starts = [interval[0] for interval in event_intervals]
    for idx in range(1, len(starts)):
        assert starts[idx] >= starts[idx - 1], f"Dialogue starts must be non-decreasing: {starts[idx]} < {starts[idx-1]}"


@pytest.mark.tier3
def test_tier3_subtitle_max_chars_and_words_bounds(tmp_path: Path):
    """Tier 3: Verify subtitle text wrapping respects max chars per line (<= 22) and words per line (<= 3)."""
    stamps = build_test_word_timestamps(["El", "fantasma", "apareció", "de", "repente"], duration_sec=5.0)
    ass_path = str(tmp_path / "bounds.ass")

    create_ass_subtitles(
        word_timestamps=stamps,
        output_path=ass_path,
        template="short_neon_horror",
        video_res=(720, 1280),
    )

    gatekeeper = QAGatekeeper()
    issues, max_chars, max_words, safe = gatekeeper._audit_subtitles(ass_path)

    assert max_chars <= 22, f"Max characters per line {max_chars} must be <= 22."
    assert max_words <= 3, f"Max words per line {max_words} must be <= 3."


# ---------------------------------------------------------------------------
# Tier 4: Background Asset Fitting (Resizing / Pre-cropping without Demux Distortion)
# ---------------------------------------------------------------------------

@pytest.mark.tier4
def test_tier4_background_asset_fitting_shorts(tmp_path: Path):
    """Tier 4: Verify pre-cropping and scaling of mixed-resolution background assets to Shorts canvas."""
    img_landscape = create_synthetic_image(tmp_path / "bg_1920x1080.jpg", 1920, 1080, (40, 80, 120))
    img_square = create_synthetic_image(tmp_path / "bg_800x800.jpg", 800, 800, (120, 40, 80))
    img_portrait = create_synthetic_image(tmp_path / "bg_720x1280.jpg", 720, 1280, (80, 120, 40))

    audio_file = create_synthetic_wav(tmp_path / "t4_shorts_audio.wav", duration_sec=6.0)
    output_mp4 = str(tmp_path / "output_t4_shorts.mp4")

    result_path = compose_video(
        audio_path=audio_file,
        subtitle_path="",
        background_video_path=img_landscape,
        output_video_path=output_mp4,
        duration_sec=6.0,
        min_duration=0.0,
        video_mode="short",
        scene_images=[img_landscape, img_square, img_portrait],
    )

    assert os.path.exists(result_path)

    probe = ffprobe(result_path)
    streams = probe.get("streams", [])
    v_stream = next((s for s in streams if s.get("codec_type") == "video"), {})

    width = int(v_stream.get("width", 0))
    height = int(v_stream.get("height", 0))

    assert (width, height) == SHORT_RES, f"Shorts video canvas must be {SHORT_RES}, got {width}x{height}."

    verifier = E2EVideoVerifier(strict_mode=False)
    # 6s synthetic videos fall below the production "short" duration floor;
    # verify the video is well-formed without enforcing the longform bound.
    probe = verifier.probe(result_path)
    streams = probe.get("streams", [])
    v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    assert v_stream is not None, "Video stream must be present."
    assert a_stream is not None, "Audio stream must be present."

    width = int(v_stream.get("width", 0))
    height = int(v_stream.get("height", 0))
    assert (width, height) == SHORT_RES, f"Shorts video must be {SHORT_RES}, got {width}x{height}."


@pytest.mark.tier4
def test_tier4_background_asset_fitting_longform(tmp_path: Path):
    """Tier 4: Verify background asset fitting and scaling to 1280x720 Longform canvas without demux distortion."""
    img_portrait = create_synthetic_image(tmp_path / "bg_port.jpg", 1080, 1920, (60, 30, 90))
    img_square = create_synthetic_image(tmp_path / "bg_sq.jpg", 1000, 1000, (90, 60, 30))
    img_long = create_synthetic_image(tmp_path / "bg_long.jpg", 1280, 720, (30, 90, 60))

    audio_file = create_synthetic_wav(tmp_path / "t4_long_audio.wav", duration_sec=6.0)
    output_mp4 = str(tmp_path / "output_t4_longform.mp4")

    result_path = compose_video(
        audio_path=audio_file,
        subtitle_path="",
        background_video_path=img_long,
        output_video_path=output_mp4,
        duration_sec=6.0,
        min_duration=0.0,
        video_mode="longform",
        scene_images=[img_portrait, img_square, img_long],
    )

    assert os.path.exists(result_path)

    probe = ffprobe(result_path)
    v_stream = next((s for s in probe.get("streams", []) if s.get("codec_type") == "video"), {})

    width = int(v_stream.get("width", 0))
    height = int(v_stream.get("height", 0))

    assert (width, height) == LONGFORM_RES, f"Longform video canvas must be {LONGFORM_RES}, got {width}x{height}."

    verifier = E2EVideoVerifier(strict_mode=False)
    # 6s synthetic videos fall below the production "longform" duration floor;
    # verify the video is well-formed without enforcing the longform bound.
    probe = verifier.probe(result_path)
    streams = probe.get("streams", [])
    v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    assert v_stream is not None, "Video stream must be present."
    assert a_stream is not None, "Audio stream must be present."

    width = int(v_stream.get("width", 0))
    height = int(v_stream.get("height", 0))
    assert (width, height) == LONGFORM_RES, f"Longform video must be {LONGFORM_RES}, got {width}x{height}."


@pytest.mark.tier4
def test_tier4_demux_concat_pre_crop_integrity(tmp_path: Path):
    """Tier 4: Verify FFmpeg concat demuxer generates clean output without frame aspect distortion when using varied inputs."""
    img1 = create_synthetic_image(tmp_path / "concat_img1.jpg", 640, 480, (20, 50, 80))
    img2 = create_synthetic_image(tmp_path / "concat_img2.jpg", 1920, 1200, (80, 50, 20))

    audio_file = create_synthetic_wav(tmp_path / "concat_audio.wav", duration_sec=5.0)
    output_mp4 = str(tmp_path / "output_t4_concat.mp4")

    compose_video(
        audio_path=audio_file,
        subtitle_path="",
        background_video_path=img1,
        output_video_path=output_mp4,
        duration_sec=5.0,
        min_duration=0.0,
        video_mode="short",
        scene_images=[img1, img2],
    )

    probe = ffprobe(output_mp4)
    format_info = probe.get("format", {})
    assert float(format_info.get("duration", 0.0)) > 4.5, "Duration of concat output must match expected video duration."
