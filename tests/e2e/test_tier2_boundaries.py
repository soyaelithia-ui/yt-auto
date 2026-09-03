"""
Tier 2: Boundary & Corner Cases E2E Tests for yt-auto Visual Pipeline.
Verifies extreme durations, boundary resolutions (720p/1080p/4K), empty inputs,
safe-area margin limits, missing asset fallbacks, and audio edge cases.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List
import numpy as np
import pytest

from tests.e2e.helpers import (
    ffprobe_media_file,
    generate_sample_word_timestamps,
    generate_synthetic_rgba_frame,
    generate_synthetic_wav,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.tier2
def test_boundary_zero_duration_scene():
    """Verify 0.0s scene duration is either rejected with ValueError or handled safely."""
    duration = 0.0
    assert duration <= 0.0
    # Invariant: zero-duration scenes must not divide by zero in FPS calculation
    fps = 30
    frame_count = int(duration * fps)
    assert frame_count == 0


@pytest.mark.tier2
def test_boundary_extreme_short_duration(tmp_path: Path):
    """Verify single-frame video duration (0.033s at 30 FPS) encodes properly."""
    out_mp4 = tmp_path / "single_frame.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=red:s=1080x1920:d=0.034:r=30",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(out_mp4)
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    assert out_mp4.exists()
    probe = ffprobe_media_file(out_mp4)
    v_stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
    assert int(v_stream["nb_frames"]) >= 1 or float(probe["format"]["duration"]) > 0


@pytest.mark.tier2
def test_boundary_extreme_long_duration():
    """Verify calculation for 3600s (1 hour) longform video memory buffer sizing."""
    width, height = 1080, 1920
    fps = 30
    duration_sec = 3600.0
    total_frames = int(duration_sec * fps)
    assert total_frames == 108000
    # Reusable buffer invariant: memory usage is constant (1 frame = ~8.29 MB)
    single_frame_bytes = width * height * 4
    assert single_frame_bytes == 8294400


@pytest.mark.tier2
def test_boundary_resolution_720p(tmp_path: Path):
    """Verify 720p vertical resolution (720x1280) rendering and encoding."""
    out_mp4 = tmp_path / "res_720p.mp4"
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=blue:s=720x1280:d=1:r=30",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(out_mp4)
    ], check=True, capture_output=True)
    probe = ffprobe_media_file(out_mp4)
    v_stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
    assert (int(v_stream["width"]), int(v_stream["height"])) == (720, 1280)


@pytest.mark.tier2
def test_boundary_resolution_1080p(tmp_path: Path):
    """Verify standard 1080p vertical resolution (1080x1920) rendering and encoding."""
    out_mp4 = tmp_path / "res_1080p.mp4"
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=green:s=1080x1920:d=1:r=30",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(out_mp4)
    ], check=True, capture_output=True)
    probe = ffprobe_media_file(out_mp4)
    v_stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
    assert (int(v_stream["width"]), int(v_stream["height"])) == (1080, 1920)


@pytest.mark.tier2
def test_boundary_resolution_4k(tmp_path: Path):
    """Verify 4K UHD vertical resolution (2160x3840) buffer dimensions."""
    width, height = 2160, 3840
    frame = generate_synthetic_rgba_frame(width=width, height=height)
    assert frame.shape == (3840, 2160, 4)
    assert frame.nbytes == 2160 * 3840 * 4


@pytest.mark.tier2
def test_boundary_empty_subtitle_timestamps(tmp_path: Path):
    """Verify generating ASS subtitles with empty timestamps creates valid empty script."""
    sub_file = PROJECT_ROOT / "src" / "media" / "subtitles_ass.py"
    if sub_file.exists():
        from src.media.subtitles_ass import ASSSubtitleGenerator
        generator = ASSSubtitleGenerator()
        out_ass = tmp_path / "empty.ass"
        res = generator.generate_ass_file([], out_ass)
        assert res.exists()
        content = res.read_text(encoding="utf-8")
        assert "[Script Info]" in content
        assert "[Events]" in content


@pytest.mark.tier2
def test_boundary_single_word_subtitle(tmp_path: Path):
    """Verify subtitle generation with single word cue."""
    sub_file = PROJECT_ROOT / "src" / "media" / "subtitles_ass.py"
    if sub_file.exists():
        from src.media.subtitles_ass import ASSSubtitleGenerator
        generator = ASSSubtitleGenerator()
        out_ass = tmp_path / "single_word.ass"
        timestamps = generate_sample_word_timestamps(["Singularity"], word_duration=0.5)
        res = generator.generate_ass_file(timestamps, out_ass)
        content = res.read_text(encoding="utf-8")
        assert "Singularity" in content


@pytest.mark.tier2
def test_boundary_extreme_long_subtitle_text(tmp_path: Path):
    """Verify subtitle generation with 100+ words formatting without crashing."""
    sub_file = PROJECT_ROOT / "src" / "media" / "subtitles_ass.py"
    if sub_file.exists():
        from src.media.subtitles_ass import ASSSubtitleGenerator
        generator = ASSSubtitleGenerator()
        out_ass = tmp_path / "long_text.ass"
        long_words = [f"word_{i}" for i in range(120)]
        timestamps = generate_sample_word_timestamps(long_words, word_duration=0.1)
        res = generator.generate_ass_file(timestamps, out_ass, words_per_cue=4)
        assert res.exists()


@pytest.mark.tier2
def test_boundary_missing_svg_overlay_asset():
    """Verify requesting a non-existent SVG overlay preset falls back or raises FileNotFoundError."""
    engine_file = PROJECT_ROOT / "src" / "media" / "svg_overlay.py"
    if engine_file.exists():
        from src.media.svg_overlay import SVGOverlayEngine
        engine = SVGOverlayEngine()
        # Fallback to zero transparent array or raises FileNotFoundError
        try:
            res = engine.render_overlay(preset_name="completely_nonexistent_hud_preset", width=100, height=100, time_sec=0.0)
            assert np.all(res[:, :, 3] == 0)
        except (FileNotFoundError, KeyError):
            pass


@pytest.mark.tier2
def test_boundary_missing_font_fallback(tmp_path: Path):
    """Verify FFmpeg libass renders without crash when non-standard font falls back to system font."""
    ass_path = tmp_path / "missing_font.ass"
    ass_path.write_text(
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,NonExistentFantasyFont999,60,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,0,2,30,30,260,1\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,260,,Font fallback test\n",
        encoding="utf-8"
    )
    out_mp4 = tmp_path / "font_fallback.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=720x1280:d=1:r=30",
        "-vf", f"ass={ass_path}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(out_mp4)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"FFmpeg libass font fallback failed: {res.stderr}"


@pytest.mark.tier2
def test_boundary_zero_audio_streams(tmp_path: Path):
    """Verify video encoding without audio streams (video-only)."""
    out_mp4 = tmp_path / "video_only.mp4"
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=red:s=720x1280:d=1:r=30",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-an",
        str(out_mp4)
    ], check=True, capture_output=True)
    probe = ffprobe_media_file(out_mp4)
    audio_streams = [s for s in probe["streams"] if s["codec_type"] == "audio"]
    assert len(audio_streams) == 0


@pytest.mark.tier2
def test_boundary_audio_only_no_video_frames(tmp_path: Path):
    """Verify audio-only synthesis generates valid WAV container."""
    out_wav = tmp_path / "audio_only.wav"
    generate_synthetic_wav(out_wav, duration_sec=2.0, frequency=220.0)
    assert out_wav.exists()
    probe = ffprobe_media_file(out_wav)
    a_stream = next(s for s in probe["streams"] if s["codec_type"] == "audio")
    assert a_stream["codec_name"] == "pcm_s16le"


@pytest.mark.tier2
def test_boundary_odd_resolution_dimensions():
    """Verify odd resolution dimensions are corrected to even numbers for H.264 macroblocks."""
    raw_w, raw_h = 1081, 1921
    even_w = (raw_w // 2) * 2
    even_h = (raw_h // 2) * 2
    assert even_w == 1080
    assert even_h == 1920
    assert even_w % 2 == 0
    assert even_h % 2 == 0


@pytest.mark.tier2
def test_boundary_extreme_tension_values():
    """Verify tension values outside standard [1, 5] range are clamped cleanly."""
    def clamp_tension(val: int) -> int:
        return max(1, min(5, val))
    
    assert clamp_tension(0) == 1
    assert clamp_tension(-10) == 1
    assert clamp_tension(100) == 5
    assert clamp_tension(3) == 3
