"""
tests/unit/test_compositing.py - Unit tests for ASS Subtitles Generator and Direct Stream Compositor.
"""
from pathlib import Path
import pytest

from src.compositing.subtitles import TerminalKaraokeSubtitleGenerator, format_ass_timestamp
from src.compositing.stream_renderer import DirectStreamCompositor
from src.narrative.engine import CosmicNarrativeEngine
from src.narrative.schema import NarrativeArchetype, VideoFormat
from src.rendering.renderer import resolve_chrome_path


def test_format_ass_timestamp() -> None:
    assert format_ass_timestamp(0.0) == "0:00:00.00"
    assert format_ass_timestamp(65.45) == "0:01:05.45"
    assert format_ass_timestamp(3661.12) == "1:01:01.12"


def test_terminal_karaoke_subtitle_generator(tmp_path: Path) -> None:
    generator = TerminalKaraokeSubtitleGenerator()
    words = [
        {"word": "Registro", "start": 0.0, "end": 0.5},
        {"word": "de", "start": 0.5, "end": 0.7},
        {"word": "telemetría", "start": 0.7, "end": 1.4},
        {"word": "anómala", "start": 1.4, "end": 2.1},
        {"word": "detectada", "start": 2.1, "end": 2.8},
    ]

    ass_path = tmp_path / "test_subtitles.ass"
    generator.generate_ass(
        word_timestamps=words,
        output_ass_path=ass_path,
        width=1080,
        height=1920,
        words_per_cue=3,
    )

    assert ass_path.is_file()
    content = ass_path.read_text(encoding="utf-8")
    assert "[Script Info]" in content
    assert "TerminalKaraoke" in content
    assert "{\\k" in content
    assert "Registro" in content
    assert "detectada" in content


def test_direct_stream_compositor_fast_render(tmp_path: Path) -> None:
    chrome_path = resolve_chrome_path()
    if not chrome_path:
        pytest.skip("No Chrome/Chromium executable available")

    engine = CosmicNarrativeEngine()
    script = engine.generate_script(
        archetype=NarrativeArchetype.HYDROACOUSTIC_TELEMETRY,
        video_format=VideoFormat.SHORT_VERTICAL,
        duration_sec=1.0,
    )

    compositor = DirectStreamCompositor(chrome_exec_path=chrome_path)
    output_mp4 = tmp_path / "test_stream_render.mp4"

    res = compositor.render_and_mux(
        script_contract=script,
        output_mp4_path=output_mp4,
        duration_sec=1.0,
        width=360,
        height=640,
        fps=15,
    )

    assert res.is_file()
    assert res.stat().st_size > 1000


def test_direct_stream_compositor_dynamic_duration_linked_to_audio(tmp_path: Path) -> None:
    """Verifies render duration and frame count are derived dynamically from master audio."""
    import math
    import subprocess
    from lib.ffmpeg import probe_media

    chrome_path = resolve_chrome_path()
    if not chrome_path:
        pytest.skip("No Chrome/Chromium executable available")

    # Generate synthetic master audio of 1.8s
    audio_path = tmp_path / "master_test_audio.wav"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=1.8",
        "-c:a", "pcm_s16le", str(audio_path),
    ], check=True)

    audio_probe = probe_media(audio_path)
    audio_dur = audio_probe.duration
    assert audio_dur == pytest.approx(1.8, abs=0.1)

    fps = 15
    expected_frames = math.ceil((audio_dur + 0.5) * fps)
    expected_duration = expected_frames / fps

    engine = CosmicNarrativeEngine()
    script = engine.generate_script(
        archetype=NarrativeArchetype.HYDROACOUSTIC_TELEMETRY,
        video_format=VideoFormat.SHORT_VERTICAL,
        duration_sec=1.0,  # Intentional nominal duration to verify override by audio
    )

    compositor = DirectStreamCompositor(chrome_exec_path=chrome_path)
    output_mp4 = tmp_path / "dynamic_duration_mux.mp4"

    res = compositor.render_and_mux(
        script_contract=script,
        output_mp4_path=output_mp4,
        master_audio_path=audio_path,
        width=360,
        height=640,
        fps=fps,
    )

    assert res.is_file()
    video_probe = probe_media(res)
    assert video_probe.has_video is True
    assert video_probe.has_audio is True
    assert video_probe.duration == pytest.approx(expected_duration, abs=0.2)


def test_direct_stream_compositor_backpressure_drain() -> None:
    """Verifies _write_frame_with_backpressure handles pipe flow control and closed pipes."""
    import subprocess
    import sys

    compositor = DirectStreamCompositor()
    
    # Spawn a child process reading from stdin
    proc = subprocess.Popen(
        [sys.executable, "-c", "import sys, time; data = sys.stdin.buffer.read(50); time.sleep(0.01)"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Valid write with backpressure check
    sample_bytes = b"X" * 50
    ok = compositor._write_frame_with_backpressure(proc, sample_bytes, timeout=1.0)
    assert ok is True

    # Close stdin and wait for process to finish
    if proc.stdin:
        proc.stdin.close()
    proc.wait(timeout=2.0)

    # After process finishes / pipe closes, write returns False cleanly
    closed_ok = compositor._write_frame_with_backpressure(proc, sample_bytes, timeout=0.1)
    assert closed_ok is False


