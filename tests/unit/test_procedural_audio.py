"""
tests/unit/test_procedural_audio.py - Unit tests for ProceduralAudioEngine.
"""
import os
import wave
from pathlib import Path
import pytest

from src.media.procedural_audio import ProceduralAudioEngine, get_procedural_audio_engine


def test_procedural_audio_engine_singleton():
    engine1 = get_procedural_audio_engine()
    engine2 = get_procedural_audio_engine()
    assert engine1 is engine2
    assert isinstance(engine1, ProceduralAudioEngine)


@pytest.mark.parametrize("theme", ["horror", "cosmic_horror", "drama", "aita", "scp", "tactical", "default"])
def test_generate_ambient_track_themes(tmp_path: Path, theme: str):
    engine = ProceduralAudioEngine()
    out_wav = tmp_path / f"ambient_{theme}.wav"
    res = engine.generate_ambient_track(
        output_path=out_wav,
        theme=theme,
        duration_sec=3.0,
        volume=0.25,
        seed=12345,
    )
    assert res == out_wav
    assert out_wav.is_file()
    assert out_wav.stat().st_size > 0

    with wave.open(str(out_wav), "rb") as wf:
        assert wf.getnchannels() == 2
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 48000
        n_frames = wf.getnframes()
        dur = n_frames / float(wf.getframerate())
        assert abs(dur - 3.0) < 0.05


def test_procedural_audio_seed_determinism(tmp_path: Path):
    engine = ProceduralAudioEngine()
    pcm1 = engine.synthesize_ambient_pcm(theme="horror", duration_sec=2.0, seed=42)
    pcm2 = engine.synthesize_ambient_pcm(theme="horror", duration_sec=2.0, seed=42)
    pcm3 = engine.synthesize_ambient_pcm(theme="horror", duration_sec=2.0, seed=999)

    assert pcm1 == pcm2
    assert pcm1 != pcm3
