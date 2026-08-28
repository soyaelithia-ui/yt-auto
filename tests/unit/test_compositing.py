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
