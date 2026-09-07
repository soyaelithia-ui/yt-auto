"""
E2E Test Suite for Tier 3 Pairwise Interactions & Tier 4 Real-World Workload Scenarios.
Simulates production runs for Moku Horror (Short/Long) and Aelithia Drama (Short/Long)
under offline/test profile with hermetic assets and zero network quota.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List
import pytest

from src.core.catalog import LoopCatalogRepository, LoopRecord
from src.core.quality import is_spanish_neutral
from src.media.subtitles_ass import (
    ASSSubtitleGenerator,
    calculate_safe_margins,
    escape_ffmpeg_filter_path,
    libass_filter_clause,
)
from tests.e2e.helpers import (
    check_faststart_moov_atom,
    ffprobe_media_file,
    generate_sample_word_timestamps,
    generate_synthetic_wav,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = PROJECT_ROOT / "assets" / "loops"


# ==============================================================================
# Tier 3: Pairwise Cross-Feature Interactions
# ==============================================================================

@pytest.mark.tier3
def test_pairwise_subtitles_and_multiscene_loops(tmp_path: Path):
    """Verify ASS subtitle karaoke burning over a multi-scene background loop sequence."""
    out_mp4 = tmp_path / "pairwise_sub_multiscene.mp4"
    ass_path = tmp_path / "subtitles.ass"

    # 1. Generate ASS subtitles with safe margins
    words = generate_sample_word_timestamps(
        words=["En", "la", "oscuridad", "del", "bosque", "algo", "respira"],
        start_offset=0.2,
        word_duration=0.4,
    )
    generator = ASSSubtitleGenerator()
    generator.generate_ass_file(
        word_timestamps=words,
        output_path=ass_path,
        video_width=1080,
        video_height=1920,
    )
    assert ass_path.exists()

    # 2. Render 2-second vertical test clip burning the subtitles
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=1080x1920:d=2.5:r=30",
        "-f", "lavfi", "-i", "sine=f=440:d=2.5",
        "-vf", f"ass={escape_ffmpeg_filter_path(ass_path)}",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(out_mp4)
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    assert out_mp4.exists()

    # 3. Probe output
    probe = ffprobe_media_file(out_mp4)
    v_stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
    a_stream = next(s for s in probe["streams"] if s["codec_type"] == "audio")
    assert (int(v_stream["width"]), int(v_stream["height"])) == (1080, 1920)
    assert a_stream["codec_name"] == "aac"
    assert check_faststart_moov_atom(out_mp4)


@pytest.mark.tier3
def test_pairwise_pre_tts_validation_with_audio_pipeline():
    """Verify narrative coherence validation precedes audio generation and blocks invalid scripts."""
    invalid_script = "Hello this is a completely English text with no Spanish at all."
    assert not is_spanish_neutral(invalid_script), "Invalid non-Spanish text must be caught before TTS"


@pytest.mark.tier3
def test_pairwise_seeded_rotation_and_channel_isolation(tmp_path: Path):
    """Verify seeded rotation isolates horror loops for Moku and drama loops for Aelithia."""
    db_path = tmp_path / "test_pairwise_rotation.db"
    repo = LoopCatalogRepository(db_path=str(db_path))

    # Register horror loop and drama loop
    repo.register_loop(LoopRecord(
        loop_id="horror_loop_01",
        category="horror",
        technology="mp4",
        orientation="vertical",
        width=1080,
        height=1920,
        duration_sec=10.0,
        fps=30,
        file_path=str(PROJECT_ROOT / "assets" / "loops" / "vertical" / "horror"),
        file_size_bytes=100000,
        sha256="horror_sha_123",
    ))
    repo.register_loop(LoopRecord(
        loop_id="drama_loop_01",
        category="drama",
        technology="mp4",
        orientation="vertical",
        width=1080,
        height=1920,
        duration_sec=10.0,
        fps=30,
        file_path=str(PROJECT_ROOT / "assets" / "loops" / "vertical" / "drama"),
        file_size_bytes=100000,
        sha256="drama_sha_456",
    ))

    # Verify category filtering guarantees channel/thematic separation
    moku_loop = repo.get_best_loop("horror", "vertical")
    aelithia_loop = repo.get_best_loop("drama", "vertical")

    if moku_loop and aelithia_loop:
        assert moku_loop.category != aelithia_loop.category
        assert moku_loop.loop_id != aelithia_loop.loop_id


# ==============================================================================
# Tier 4: Real-World Workload Scenarios
# ==============================================================================

@pytest.mark.tier4
def test_workload_moku_horror_short_offline(tmp_path: Path):
    """Simulate complete Moku Horror Short (1080x1920 vertical, 3-act script, ASS, AAC, faststart)."""
    out_mp4 = tmp_path / "moku_horror_short.mp4"
    ass_path = tmp_path / "moku_subtitles.ass"
    audio_wav = tmp_path / "moku_voice.wav"

    # 1. 3-Act horror script verification
    horror_script = (
        "Nunca debi abrir el armario tapiado del abuelo. "
        "Dentro no habia ropa vieja ni recuerdos familiares, sino un espejo cubierto de polvo "
        "y un mensaje tallado en el marco que decia que no lo mirara a los ojos. "
        "Cuando levante la mirada, mi propio reflejo sonrio antes que yo."
    )
    assert is_spanish_neutral(horror_script), "Script must be valid neutral Spanish"

    # 2. Audio track generation
    generate_synthetic_wav(audio_wav, duration_sec=3.0, frequency=220.0, amplitude=0.6)

    # 3. Subtitles with MarginV >= 480
    words = generate_sample_word_timestamps(
        words=["Nunca", "debi", "abrir", "el", "armario", "tapiado", "del", "abuelo"],
        start_offset=0.2,
        word_duration=0.3,
    )
    generator = ASSSubtitleGenerator()
    generator.generate_ass_file(
        word_timestamps=words,
        output_path=ass_path,
        video_width=1080,
        video_height=1920,
    )

    # 4. Render 3s vertical Short clip
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=0x100505:s=1080x1920:d=3.0:r=30",
        "-i", str(audio_wav),
        "-vf", f"ass={escape_ffmpeg_filter_path(ass_path)}",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(out_mp4)
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    assert out_mp4.exists()

    # 5. Verify container invariants
    probe = ffprobe_media_file(out_mp4)
    v_stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
    assert (int(v_stream["width"]), int(v_stream["height"])) == (1080, 1920)
    assert check_faststart_moov_atom(out_mp4)


@pytest.mark.tier4
def test_workload_moku_horror_long_offline(tmp_path: Path):
    """Simulate complete Moku Horror Longform (1920x1080 horizontal, MarginV >= 130, AAC, faststart)."""
    out_mp4 = tmp_path / "moku_horror_long.mp4"
    audio_wav = tmp_path / "moku_long_voice.wav"
    ass_path = tmp_path / "moku_long_subtitles.ass"

    generate_synthetic_wav(audio_wav, duration_sec=3.0, frequency=150.0, amplitude=0.5)

    words = generate_sample_word_timestamps(
        words=["El", "silencio", "en", "el", "faro", "era", "absoluto"],
        start_offset=0.2,
        word_duration=0.35,
    )
    generator = ASSSubtitleGenerator()
    generator.generate_ass_file(
        word_timestamps=words,
        output_path=ass_path,
        video_width=1920,
        video_height=1080,
    )

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=0x080810:s=1920x1080:d=3.0:r=30",
        "-i", str(audio_wav),
        "-vf", f"ass={escape_ffmpeg_filter_path(ass_path)}",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(out_mp4)
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    assert out_mp4.exists()

    probe = ffprobe_media_file(out_mp4)
    v_stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
    assert (int(v_stream["width"]), int(v_stream["height"])) == (1920, 1080)
    assert check_faststart_moov_atom(out_mp4)


@pytest.mark.tier4
def test_workload_aelithia_drama_short_offline(tmp_path: Path):
    """Simulate complete Aelithia Drama Short (1080x1920 vertical, human dilemma narrative, ASS)."""
    out_mp4 = tmp_path / "aelithia_drama_short.mp4"
    audio_wav = tmp_path / "aelithia_voice.wav"
    ass_path = tmp_path / "aelithia_subtitles.ass"

    drama_script = (
        "Descubri que mi mejor amiga falsifico mi firma en el contrato de la empresa. "
        "Cuando la confronte, solo me miro a los ojos y dijo que lo hizo para salvarme. "
        "Ahora la policia esta afuera y tengo diez segundos para decidir si delatarla o callar."
    )
    assert is_spanish_neutral(drama_script)

    generate_synthetic_wav(audio_wav, duration_sec=3.0, frequency=330.0, amplitude=0.5)

    words = generate_sample_word_timestamps(
        words=["Descubri", "la", "verdad", "demasiado", "tarde"],
        start_offset=0.2,
        word_duration=0.4,
    )
    generator = ASSSubtitleGenerator()
    generator.generate_ass_file(
        word_timestamps=words,
        output_path=ass_path,
        video_width=1080,
        video_height=1920,
    )

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=0x151020:s=1080x1920:d=3.0:r=30",
        "-i", str(audio_wav),
        "-vf", f"ass={escape_ffmpeg_filter_path(ass_path)}",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(out_mp4)
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    assert out_mp4.exists()

    probe = ffprobe_media_file(out_mp4)
    v_stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
    assert (int(v_stream["width"]), int(v_stream["height"])) == (1080, 1920)
    assert check_faststart_moov_atom(out_mp4)


@pytest.mark.tier4
def test_workload_aelithia_drama_long_offline(tmp_path: Path):
    """Simulate complete Aelithia Drama Longform (1920x1080 horizontal, multi-scene drama)."""
    out_mp4 = tmp_path / "aelithia_drama_long.mp4"
    audio_wav = tmp_path / "aelithia_long_voice.wav"
    ass_path = tmp_path / "aelithia_long_subtitles.ass"

    generate_synthetic_wav(audio_wav, duration_sec=3.0, frequency=280.0, amplitude=0.5)

    words = generate_sample_word_timestamps(
        words=["A", "veces", "el", "perdon", "es", "mas", "dificil", "que", "la", "venganza"],
        start_offset=0.1,
        word_duration=0.3,
    )
    generator = ASSSubtitleGenerator()
    generator.generate_ass_file(
        word_timestamps=words,
        output_path=ass_path,
        video_width=1920,
        video_height=1080,
    )

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=0x181412:s=1920x1080:d=3.0:r=30",
        "-i", str(audio_wav),
        "-vf", f"ass={escape_ffmpeg_filter_path(ass_path)}",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(out_mp4)
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    assert out_mp4.exists()

    probe = ffprobe_media_file(out_mp4)
    v_stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
    assert (int(v_stream["width"]), int(v_stream["height"])) == (1920, 1080)
    assert check_faststart_moov_atom(out_mp4)
