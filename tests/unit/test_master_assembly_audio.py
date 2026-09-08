"""Unit tests for MultiSceneCompositor._master_assembly audio sample rate and codec gating."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

import src.media.compositor as compositor_mod
from src.media.compositor import MultiSceneCompositor


def _run_master(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    narration_audio: Path | None,
    music_audio: Path | None = None,
) -> list[str]:
    compositor = MultiSceneCompositor()
    video_input = tmp_path / "in.mp4"
    video_input.write_bytes(b"dummy")
    output_mp4 = tmp_path / "out.mp4"
    captured: list[list[str]] = []

    def fake_run_ffmpeg(cmd, **kwargs):
        captured.append(list(cmd))
        return MagicMock(returncode=0)

    monkeypatch.setattr(compositor_mod, "run_ffmpeg", fake_run_ffmpeg)
    compositor._master_assembly(
        video_input=video_input,
        narration_audio=narration_audio,
        music_audio=music_audio,
        music_volume=0.2,
        subtitle_path=None,
        total_duration=5.0,
        width=1920,
        height=1080,
        crf=23,
        preset="veryfast",
        output_mp4=output_mp4,
    )
    assert len(captured) == 1
    return captured[0]


def test_master_assembly_video_only_omits_audio_codecs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    cmd = _run_master(monkeypatch, tmp_path, narration_audio=None)
    assert "-c:a" not in cmd
    assert "-b:a" not in cmd
    assert "-ar" not in cmd
    assert "-ac" not in cmd
    assert "[aout]" not in cmd


def test_master_assembly_with_narration_uses_aac_44100_stereo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    narration = tmp_path / "narration.wav"
    narration.write_bytes(b"RIFF")
    cmd = _run_master(monkeypatch, tmp_path, narration_audio=narration)

    assert "-map" in cmd
    assert "[aout]" in cmd
    assert cmd[cmd.index("-c:a") + 1] == "aac"
    assert cmd[cmd.index("-b:a") + 1] == "192k"
    assert cmd[cmd.index("-ar") + 1] == "44100"
    assert cmd[cmd.index("-ac") + 1] == "2"

    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "aresample=44100" in fc
    assert "sample_rates=44100" in fc
    assert "loudnorm=I=-16.0:TP=-1.5:LRA=11.0" in fc
    assert "48000" not in fc
    assert "48000" not in " ".join(cmd)
    assert "I=-14" not in fc


def test_master_assembly_with_narration_and_music_uses_44100(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    narration = tmp_path / "narration.wav"
    music = tmp_path / "music.wav"
    narration.write_bytes(b"RIFF")
    music.write_bytes(b"RIFF")
    cmd = _run_master(
        monkeypatch, tmp_path, narration_audio=narration, music_audio=music
    )

    assert cmd[cmd.index("-c:a") + 1] == "aac"
    assert cmd[cmd.index("-ar") + 1] == "44100"
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "sidechaincompress" in fc
    assert "aresample=44100" in fc
    assert "sample_rates=44100" in fc
    assert "loudnorm=I=-16.0:TP=-1.5:LRA=11.0" in fc
    assert "48000" not in fc
