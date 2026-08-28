"""
tests/integration/test_cosmic_pipeline_e2e.py - End-to-End Integration Tests for Cosmic Video Pipeline.
"""
import json
import subprocess
from pathlib import Path
import pytest

from src.export.pipeline import CosmicVideoPipeline
from src.narrative.schema import NarrativeArchetype, VideoFormat
from src.rendering.renderer import resolve_chrome_path


def probe_file(file_path: Path) -> dict:
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        str(file_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(res.stdout)


def test_cosmic_pipeline_short_vertical_e2e(tmp_path: Path) -> None:
    if not resolve_chrome_path():
        pytest.skip("No Chrome/Chromium executable available")

    pipeline = CosmicVideoPipeline(work_dir=tmp_path / "work")
    out_mp4 = tmp_path / "test_short_vertical.mp4"

    res = pipeline.generate_video(
        topic="Anomalía Fosa de las Marianas // Bloop-7",
        archetype=NarrativeArchetype.HYDROACOUSTIC_TELEMETRY,
        video_format=VideoFormat.SHORT_VERTICAL,
        duration_sec=2.0,
        output_mp4=out_mp4,
        width=360,
        height=640,
        fps=15,
    )

    assert Path(res["video_path"]).is_file()
    assert Path(res["master_audio_path"]).is_file()
    assert Path(res["subtitles_path"]).is_file()

    info = probe_file(Path(res["video_path"]))
    streams = info.get("streams", [])
    video_streams = [s for s in streams if s["codec_type"] == "video"]
    audio_streams = [s for s in streams if s["codec_type"] == "audio"]

    assert len(video_streams) == 1
    assert video_streams[0]["width"] == 360
    assert video_streams[0]["height"] == 640
    assert len(audio_streams) == 1
    assert audio_streams[0]["codec_name"] == "aac"


def test_cosmic_pipeline_long_horizontal_e2e(tmp_path: Path) -> None:
    if not resolve_chrome_path():
        pytest.skip("No Chrome/Chromium executable available")

    pipeline = CosmicVideoPipeline(work_dir=tmp_path / "work")
    out_mp4 = tmp_path / "test_long_horizontal.mp4"

    res = pipeline.generate_video(
        topic="Protocolo SCP-3000 // Anamnesis Profunda",
        archetype=NarrativeArchetype.PROCEDURAL_INSTITUTIONAL_MANUAL,
        video_format=VideoFormat.LONG_HORIZONTAL,
        duration_sec=2.0,
        output_mp4=out_mp4,
        width=640,
        height=360,
        fps=15,
    )

    assert Path(res["video_path"]).is_file()
    info = probe_file(Path(res["video_path"]))
    streams = info.get("streams", [])
    video_streams = [s for s in streams if s["codec_type"] == "video"]

    assert len(video_streams) == 1
    assert video_streams[0]["width"] == 640
    assert video_streams[0]["height"] == 360
