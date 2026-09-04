"""Unit tests for live FFmpeg hot-path smoke evidence (copy vs veryfast/CRF21)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.media.ffmpeg_hot_path_smoke import parse_ffmpeg_evidence, read_evidence_file


def test_empty_capture_fails_without_argv():
    verdict = parse_ffmpeg_evidence("")
    assert verdict.argv_recovered is False
    assert verdict.copy_observed is False
    assert verdict.reencode_observed is False
    assert verdict.passed is False


def test_documentation_like_paths_are_read_as_text_not_executed(tmp_path: Path, monkeypatch):
    import os
    import subprocess

    def _boom(*_args, **_kwargs):
        raise AssertionError("evidence path must not be executed")

    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(os, "system", _boom)

    payload = (
        "Executing Stream-Copy LoopVideoEngine command: "
        "ffmpeg -y -f concat -safe 0 -i list.txt -c:v copy -c:a aac out.mp4\n"
    )
    readme = tmp_path / "README.sh"
    reqs = tmp_path / "requirements.txt"
    readme.write_text(payload, encoding="utf-8")
    reqs.write_text(payload, encoding="utf-8")

    for path in (readme, reqs):
        text = read_evidence_file(path)
        verdict = parse_ffmpeg_evidence(text)
        assert verdict.argv_recovered is True
        assert verdict.copy_observed is True
        assert verdict.passed is True


def test_beats_stream_copy_argv_passes_without_director():
    text = (
        "Executing Stream-Copy LoopVideoEngine command: "
        "ffmpeg -y -f concat -safe 0 -i /tmp/concat.txt -i /tmp/a.wav "
        "-c:v copy -c:a aac -b:a 192k out.mp4\n"
    )
    verdict = parse_ffmpeg_evidence(text)
    assert verdict.argv_recovered is True
    assert verdict.copy_observed is True
    assert verdict.reencode_observed is False
    assert verdict.note == "no re-encode observed"
    assert verdict.passed is True


def test_libx264_veryfast_crf21_passes():
    text = (
        "Executing LoopVideoEngine composition command: "
        "ffmpeg -y -i loop.mp4 -c:v libx264 -preset veryfast -crf 21 -c:a aac out.mp4\n"
    )
    verdict = parse_ffmpeg_evidence(text)
    assert verdict.argv_recovered is True
    assert verdict.reencode_observed is True
    assert verdict.reencode_preset == "veryfast"
    assert verdict.reencode_crf == 21
    assert verdict.passed is True


@pytest.mark.parametrize(
    "argv",
    [
        "ffmpeg -i in.mp4 -c:v libx264 -preset slow -crf 21 out.mp4",
        "ffmpeg -i in.mp4 -c:v libx264 -preset ultrafast -crf 21 out.mp4",
        "ffmpeg -i in.mp4 -c:v libx264 -preset veryfast -crf 18 out.mp4",
    ],
)
def test_libx264_wrong_preset_or_crf_fails(argv: str):
    verdict = parse_ffmpeg_evidence(f"Executing command: {argv}\n")
    assert verdict.argv_recovered is True
    assert verdict.reencode_observed is True
    assert verdict.passed is False


def test_missing_file_does_not_recover_argv(tmp_path: Path):
    missing = tmp_path / "no-such-ffmpeg.log"
    text = read_evidence_file(missing)
    verdict = parse_ffmpeg_evidence(text)
    assert text == ""
    assert verdict.argv_recovered is False
    assert verdict.passed is False
