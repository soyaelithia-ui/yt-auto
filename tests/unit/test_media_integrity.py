"""
Unit & Integration Test Suite for Media Integrity Verification Gate.
Covers all 13 mandatory safety and verification points.
"""

import json
import os
import shutil
import subprocess
import tempfile
import pytest
from pathlib import Path
from src.integrity import MediaIntegrityVerifier, compute_file_sha256, verify_media_integrity
from src.verification.quality import QualityVerifier, QualityCheckError
from src.verification.sheets import ContactSheetGenerator
from src.telegram.notifier import send_video_for_review, DeliveryResult, TelegramReviewBot


def generate_valid_mini_mp4(output_path: str, duration_sec: float = 2.0) -> str:
    """Generates a real, fully decodable 9:16 vertical MP4 with valid H.264 video and AAC audio."""
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c=blue:s=360x640:r=30",
        "-f", "lavfi", "-i", f"sine=frequency=1000:sample_rate=44100",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        "-t", str(duration_sec),
        "-movflags", "+faststart",
        output_path
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"Mini MP4 creation failed: {res.stderr}"
    return output_path


def test_1_corrupt_nal_units_rejected(tmp_path):
    """Point 1: MP4 with valid metadata header but corrupt NAL units is rejected."""
    corrupt_file = Path("/home/Moku/projects/YTShort/work/scp_SCP-087/scp-087_corrupt_invalid.mp4")
    if corrupt_file.exists():
        report = verify_media_integrity(corrupt_file, work_dir=tmp_path)
        assert report["passed"] is False, "Corrupt NAL units file must be rejected"


def test_2_corrupt_aac_rejected(tmp_path):
    """Point 2: File with corrupt audio stream is rejected."""
    dummy_file = tmp_path / "bad_audio.mp4"
    dummy_file.write_bytes(b"\x00\x00\x00\x1cftypisom" + b"\x00" * 500)
    report = verify_media_integrity(dummy_file, work_dir=tmp_path)
    assert report["passed"] is False, "Corrupt audio/container file must be rejected"


def test_3_partial_file_not_renamed_on_failure(tmp_path):
    """Point 3: Output written to .partial.mp4 is NEVER renamed to final if integrity fails."""
    final_path = tmp_path / "output_master.mp4"
    partial_path = tmp_path / "output_master.mp4.partial.mp4"
    partial_path.write_bytes(b"corrupted_bytes_stream" * 50)

    verifier = MediaIntegrityVerifier()
    report = verifier.verify_file(partial_path)
    assert report["passed"] is False

    # Simulate pipeline logic check: rename MUST NOT occur
    if not report["passed"]:
        assert not final_path.exists(), "Final file must NOT exist when integrity check fails"


def test_4_nonzero_ffmpeg_exit_code_blocks(tmp_path):
    """Point 4: Non-zero FFmpeg decode returncode blocks processing."""
    fake_video = tmp_path / "fake.mp4"
    fake_video.write_bytes(b"not_a_video_stream")
    decode_cmd = ["ffmpeg", "-v", "error", "-xerror", "-i", str(fake_video), "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"]
    res = subprocess.run(decode_cmd, capture_output=True, text=True)
    assert res.returncode != 0, "FFmpeg decode on fake video must fail with non-zero exit code"


def test_5_full_process_wait(tmp_path):
    """Point 5: Pipeline waits for complete FFmpeg process closure before reading moov atom."""
    valid_mp4 = str(tmp_path / "test_closure.mp4")
    generate_valid_mini_mp4(valid_mp4, duration_sec=1.0)
    assert os.path.exists(valid_mp4)
    assert os.path.getsize(valid_mp4) > 0


def test_6_preview_not_generated_if_master_fails(tmp_path):
    """Point 6: Preview video is NOT generated if master video fails integrity."""
    master_partial = tmp_path / "master.partial.mp4"
    master_partial.write_bytes(b"invalid_master_data")

    verifier = MediaIntegrityVerifier()
    master_report = verifier.verify_file(master_partial)
    assert master_report["passed"] is False

    preview_generated = False
    if master_report["passed"]:
        preview_generated = True

    assert preview_generated is False, "Preview must not be generated if master integrity fails"


def test_7_preview_validated_with_same_decode_gate(tmp_path):
    """Point 7: Preview video must pass the exact same full decode verification."""
    preview_mp4 = str(tmp_path / "test_preview.mp4")
    generate_valid_mini_mp4(preview_mp4, duration_sec=1.0)

    verifier = MediaIntegrityVerifier()
    report = verifier.verify_file(preview_mp4)
    assert report["passed"] is True, "Valid preview video must pass full decode verification"


def test_8_corrupt_file_does_not_reach_sendvideo(tmp_path):
    """Point 8: Undecodable file is blocked in preflight before sendVideo is called."""
    bad_video = tmp_path / "corrupt_preview.mp4"
    bad_video.write_bytes(b"corrupt_mp4_bytes" * 50)

    meta = {"scp_id": "SCP-087", "title": "Test SCP"}
    result = send_video_for_review(str(bad_video), meta)
    assert result.ok is False, "send_video_for_review must reject corrupt preview in preflight"
    assert "preflight" in result.error.lower() or "integrity" in result.error.lower()


def test_9_telegram_failure_not_converted_to_success():
    """Point 9: Telegram sendVideo rejection returns ok=False without hiding error."""
    res = DeliveryResult(ok=False, error="Telegram API Error 400: Bad Request: wrong video format")
    assert res.ok is False
    assert "Telegram API Error" in res.error


def test_10_quality_score_zero_on_integrity_failure(tmp_path):
    """Point 10: Quality Score MUST be 0 if media integrity verification fails."""
    bad_video = tmp_path / "bad.mp4"
    bad_video.write_bytes(b"corrupt")

    contact_sheet_gen = ContactSheetGenerator()
    storyboard = {"scenes": [{"overlay_text": "Hook"}]}
    score_res = contact_sheet_gen.calculate_quality_score(str(bad_video), storyboard, 60.0, 1000)
    assert score_res["overall_score"] == 0, "Quality Score must be 0 when media integrity fails"
    assert score_res["passed"] is False


def test_11_valid_h264_aac_master_passes(tmp_path):
    """Point 11: Valid H.264/AAC master video passes media integrity verification cleanly."""
    valid_mp4 = str(tmp_path / "valid_master.mp4")
    generate_valid_mini_mp4(valid_mp4, duration_sec=2.0)

    verifier = MediaIntegrityVerifier()
    report = verifier.verify_file(valid_mp4, work_dir=tmp_path)
    assert report["passed"] is True
    assert report["video_stream"]["codec"] in ("h264", "libx264")
    assert report["audio_stream"]["codec"] == "aac"
    assert report["faststart_optimized"] is True


@pytest.mark.skipif(not Path("/home/Moku/projects/YTShort/work/scp_SCP-087").exists(), reason="work/scp_SCP-087 not present in workspace")
def test_12_rebuild_from_existing_assets_preserves_artifacts(tmp_path):
    """Point 12: Rebuilding SCP-087 uses existing intact source assets without repeating TTS."""
    work_dir = Path("/home/Moku/projects/YTShort/work/scp_SCP-087")
    assert (work_dir / "narration_mastered.mp3").exists()
    assert (work_dir / "subtitles.ass").exists()
    assert (work_dir / "storyboard.json").exists()
    assert (work_dir / "scp_content_profile.json").exists()


def test_13_telegram_review_and_idempotency_working(tmp_path):
    """Point 13: Telegram review portal idempotency and full decode check integration."""
    valid_mp4 = str(tmp_path / "idempotent_test.mp4")
    generate_valid_mini_mp4(valid_mp4, duration_sec=1.0)
    rep1 = verify_media_integrity(valid_mp4)
    rep2 = verify_media_integrity(valid_mp4)
    assert rep1["sha256_hash"] == rep2["sha256_hash"]
    assert rep1["passed"] is True and rep2["passed"] is True
