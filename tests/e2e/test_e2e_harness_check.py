"""Initial placeholder test to verify E2E harness and fixtures."""
from __future__ import annotations

import subprocess
from pathlib import Path
import pytest


@pytest.mark.tier4
def test_e2e_harness_check(temp_e2e_workspace: Path, e2e_workset: dict, e2e_video_verifier):
    """Verify that E2E workspace, workset loader, and video verifier fixtures function properly."""
    # 1. Verify workspace directory
    assert temp_e2e_workspace.exists()
    assert temp_e2e_workspace.is_dir()

    # 2. Verify workset loader fixture
    assert isinstance(e2e_workset, dict)
    assert "id" in e2e_workset
    assert "title" in e2e_workset
    assert "content" in e2e_workset
    assert e2e_workset["id"] == "MOKU-STORY-001"

    # 3. Verify video verifier probing with synthetic MP4 video (1080x1920)
    synthetic_mp4 = temp_e2e_workspace / "synthetic_test.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=blue:s=1080x1920:d=1",
        "-f", "lavfi", "-i", "sine=f=440:d=1",
        "-c:v", "libx264", "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        str(synthetic_mp4),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"FFmpeg synthetic video creation failed: {res.stderr}"
    assert synthetic_mp4.exists()

    # Probe synthetic video via verifier
    probe_res = e2e_video_verifier.probe(synthetic_mp4)
    assert "streams" in probe_res
    assert len(probe_res["streams"]) >= 2

    # Perform full verification check
    result = e2e_video_verifier.verify_video(synthetic_mp4, expected_resolution=(1080, 1920))
    assert result["dimensions"] == (1080, 1920)
    assert result["audio_codec"] == "aac"
    assert "ffprobe" in result
    assert "qa_report" in result
    # visual_report removed: per-scene visual integrity verifier has been
    # retired alongside the per-scene image generation. The loop-level
    # visual gate is validate_prepublication in src.core.quality.


@pytest.mark.tier4
def test_e2e_video_verifier_invalid_attributes(temp_e2e_workspace: Path, e2e_video_verifier):
    """Verify e2e_video_verifier properly detects and reports invalid MP4 attributes."""
    # 1. Non-existent file
    missing_res = e2e_video_verifier.verify_video(temp_e2e_workspace / "non_existent.mp4")
    assert missing_res["passed"] is False
    assert any("File does not exist" in err for err in missing_res["errors"])

    # 2. Corrupted file probing
    corrupt_mp4 = temp_e2e_workspace / "corrupt.mp4"
    corrupt_mp4.write_bytes(b"INVALID_HEADER_DATA_NOT_A_REAL_MP4")
    with pytest.raises(RuntimeError, match="FFprobe binary crashed"):
        e2e_video_verifier.probe(corrupt_mp4)

    # 3. Missing audio stream
    no_audio_mp4 = temp_e2e_workspace / "no_audio.mp4"
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=blue:s=1080x1920:d=1",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(no_audio_mp4)
    ], check=True, capture_output=True)
    no_audio_res = e2e_video_verifier.verify_video(no_audio_mp4, expected_resolution=(1080, 1920))
    assert no_audio_res["passed"] is False
    assert "No audio stream found" in no_audio_res["errors"]

    # 4. Audio codec mismatch (mp3 instead of aac)
    bad_codec_mp4 = temp_e2e_workspace / "bad_codec.mp4"
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=blue:s=1080x1920:d=1",
        "-f", "lavfi", "-i", "sine=f=440:d=1",
        "-c:v", "libx264", "-c:a", "libmp3lame", "-pix_fmt", "yuv420p",
        str(bad_codec_mp4)
    ], check=True, capture_output=True)
    bad_codec_res = e2e_video_verifier.verify_video(bad_codec_mp4, expected_resolution=(1080, 1920))
    assert bad_codec_res["passed"] is False
    assert any("Audio codec mismatch" in err for err in bad_codec_res["errors"])

    # 5. Dimension mismatch (1280x720 when 1080x1920 expected)
    bad_dim_mp4 = temp_e2e_workspace / "bad_dim.mp4"
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=blue:s=1280x720:d=1",
        "-f", "lavfi", "-i", "sine=f=440:d=1",
        "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p",
        str(bad_dim_mp4)
    ], check=True, capture_output=True)
    bad_dim_res = e2e_video_verifier.verify_video(bad_dim_mp4, expected_resolution=(1080, 1920))
    assert bad_dim_res["passed"] is False
    assert any("Dimension mismatch" in err for err in bad_dim_res["errors"])

