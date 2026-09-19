"""ensure_h264_main_profile: High re-encodes; Main is no-op."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lib.ffmpeg import MediaProbeResult, VideoStreamInfo
from src.media.loop_engine import LoopVideoEngine


def _probe(profile: str | None) -> MediaProbeResult:
    return MediaProbeResult(
        format_name="mov,mp4",
        duration=2.0,
        size_bytes=1000,
        video_streams=[
            VideoStreamInfo(
                codec_name="h264",
                width=1080,
                height=1920,
                fps=30.0,
                pix_fmt="yuv420p",
                duration=2.0,
                profile=profile,
            )
        ],
        raw_payload={
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "profile": profile or ""}
            ]
        },
    )


@pytest.fixture()
def tiny_mp4(tmp_path: Path) -> Path:
    p = tmp_path / "clip.mp4"
    p.write_bytes(b"\x00\x00\x00\x18ftypmp42")  # non-empty stub
    return p


def test_high_profile_is_noop(tiny_mp4: Path) -> None:
    eng = LoopVideoEngine()
    original = tiny_mp4.read_bytes()
    with patch("src.media.loop_engine.probe_media", return_value=_probe("High")) as pm, patch(
        "src.media.loop_engine.run_ffmpeg"
    ) as rf:
        out = eng.ensure_h264_main_profile(tiny_mp4, crf=28, preset="ultrafast", timeout=30)
        assert out == tiny_mp4
        pm.assert_called_once()
        rf.assert_not_called()
        assert tiny_mp4.read_bytes() == original


def test_unsupported_profile_reencodes(tiny_mp4: Path) -> None:
    eng = LoopVideoEngine()
    with patch("src.media.loop_engine.probe_media", return_value=_probe("High 4:2:2")) as pm, patch(
        "src.media.loop_engine.run_ffmpeg"
    ) as rf:
        def _fake_ffmpeg(cmd, **kwargs):
            # write the .main tmp that ensure expects to replace onto target
            out = Path(cmd[-1])
            out.write_bytes(b"reencoded")
            return MagicMock(returncode=0)

        rf.side_effect = _fake_ffmpeg
        out = eng.ensure_h264_main_profile(tiny_mp4, crf=28, preset="ultrafast", timeout=30)
        assert out == tiny_mp4
        pm.assert_called_once()
        rf.assert_called_once()
        cmd = rf.call_args.args[0]
        assert "-profile:v" in cmd and "main" in cmd
        assert tiny_mp4.read_bytes() == b"reencoded"


def test_main_profile_is_noop(tiny_mp4: Path) -> None:
    eng = LoopVideoEngine()
    original = tiny_mp4.read_bytes()
    with patch("src.media.loop_engine.probe_media", return_value=_probe("Main")) as pm, patch(
        "src.media.loop_engine.run_ffmpeg"
    ) as rf:
        out = eng.ensure_h264_main_profile(tiny_mp4, crf=28, preset="ultrafast", timeout=30)
        assert out == tiny_mp4
        pm.assert_called_once()
        rf.assert_not_called()
        assert tiny_mp4.read_bytes() == original


def test_baseline_profile_is_noop(tiny_mp4: Path) -> None:
    eng = LoopVideoEngine()
    with patch("src.media.loop_engine.probe_media", return_value=_probe("Constrained Baseline")), patch(
        "src.media.loop_engine.run_ffmpeg"
    ) as rf:
        eng.ensure_h264_main_profile(tiny_mp4)
        rf.assert_not_called()
