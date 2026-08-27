"""
Empirical Stress Test Harness for Milestone M4 Iteration 3
(EBU R128 Audio Mastering, AudioProcessor, QA Gatekeeper, QualityVerifier)
"""

import json
import os
import shutil
import subprocess
import pytest
from pathlib import Path

from src.audio import normalize_narration_lufs, apply_sidechain_ducking, master_audio_track
from src.audio_processor import AudioProcessor
from lib.qa_gatekeeper import QAGatekeeper, QualityReportDTO, _safe_float, _safe_int
from src.verification.quality import QualityVerifier, QualityCheckError


# ============================================================================
# 1. Defect Re-verification: QualityVerifier with duration="N/A"
# ============================================================================

def test_reverify_scp_quality_verifier_na_duration(monkeypatch, tmp_path):
    """
    Re-verify previous defect:
    Test QualityVerifier.verify_video() with probe dict containing
    "duration": "N/A" in format_info to confirm it handles it cleanly without crashing.
    """
    video_path = tmp_path / "test_na_duration.mp4"
    video_path.write_bytes(b"dummy mp4 data for probe test")

    def mock_ffprobe_na_duration(path):
        return {
            "format": {
                "duration": "N/A",
                "size": "1000",
            },
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "profile": "Main",
                    "pix_fmt": "yuv420p",
                    "width": 384,
                    "height": 680,
                    "duration": "N/A",
                },
                {
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "sample_rate": "44100",
                    "channels": "2",
                    "duration": "N/A",
                },
            ]
        }

    # Patch dependencies in quality_verifier and qa_gatekeeper
    monkeypatch.setattr("src.verification.quality.ffprobe", mock_ffprobe_na_duration)
    monkeypatch.setattr("lib.qa_gatekeeper.ffprobe", mock_ffprobe_na_duration)
    monkeypatch.setattr("lib.qa_gatekeeper.has_faststart", lambda p: True)
    monkeypatch.setattr("lib.qa_gatekeeper.QAGatekeeper._audit_audio_silence_and_volume", lambda self, p: (0.0, -20.0, -1.5))
    monkeypatch.setattr("lib.qa_gatekeeper.QAGatekeeper._audit_freeze_and_black_frames", lambda self, p: (0.0, 0.0))
    monkeypatch.setattr("lib.qa_gatekeeper.QAGatekeeper._audit_ebu_r128_loudness", lambda self, p: (-14.0, -1.5, 8.0))

    verifier = QualityVerifier()
    research_data = {"entity_id": "SCP-173"}
    script_data = {
        "full_script": "SCP-173 es una estatua de hormigón que se mueve a gran velocidad.",
        "title": "El misterio de SCP-173",
        "attribution": "Contenido bajo licencia Creative Commons CC BY-SA 3.0.",
    }
    media_asset_file = tmp_path / "asset1.png"
    media_asset_file.write_bytes(b"dummy image content")
    media_assets = [{"local_path": str(media_asset_file)}]

    # With duration="N/A", _safe_float returns 0.0.
    # verify_scp_video should catch 0.0 < min_dur and raise QualityCheckError cleanly (no float/ValueError crash).
    with pytest.raises(QualityCheckError) as exc_info:
        verifier.verify_video(
            video_path=str(video_path),
            research_data=research_data,
            script_data=script_data,
            media_assets=media_assets,
            min_duration_sec=15.0,
            max_duration_sec=300.0,
        )

    assert "outside target threshold" in str(exc_info.value)
    assert "0.0s" in str(exc_info.value)


# ============================================================================
# 2. Stress-testing Audio Processing (src/audio.py & src/scp/audio_processor.py)
# ============================================================================

def test_audio_normalization_missing_and_empty_file(tmp_path):
    missing = tmp_path / "non_existent.wav"
    out = tmp_path / "out.wav"
    res = normalize_narration_lufs(str(missing), str(out))
    assert res == str(missing)

    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    res_empty = normalize_narration_lufs(str(empty), str(out))
    assert res_empty == str(empty)


def test_audio_normalization_special_characters_in_path(tmp_path):
    special_dir = tmp_path / "dir with spaces & (special) #chars"
    special_dir.mkdir(parents=True, exist_ok=True)
    raw_audio = special_dir / "raw #1 (test).wav"
    norm_audio = special_dir / "norm #1 (test).wav"

    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2",
        str(raw_audio)
    ], capture_output=True, text=True, check=True)

    result = normalize_narration_lufs(
        input_path=str(raw_audio),
        output_path=str(norm_audio),
        target_lufs=-14.0,
        max_tp=-1.5,
    )
    assert result == str(norm_audio)
    assert os.path.exists(norm_audio)


def test_sidechain_ducking_missing_inputs(tmp_path):
    narr = tmp_path / "narr.wav"
    music = tmp_path / "music.wav"
    out = tmp_path / "out.wav"

    # Missing narration
    res1 = apply_sidechain_ducking(str(narr), str(music), str(out))
    assert res1 == str(narr)

    # Valid narration, missing music
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2",
        str(narr)
    ], capture_output=True, text=True, check=True)

    res2 = apply_sidechain_ducking(str(narr), str(music), str(out))
    assert res2 == str(narr)


def test_concat_crossfade_audio_edge_cases(tmp_path):
    proc = AudioProcessor()
    out_path = tmp_path / "concat_out.mp3"

    # Edge case A: Empty clip list
    path, durs = proc.concat_crossfade_audio([], str(out_path))
    assert path == str(out_path)
    assert durs == []

    # Edge case B: Non-existent clips
    path, durs = proc.concat_crossfade_audio(["/tmp/fake1.wav", "/tmp/fake2.wav"], str(out_path))
    assert path == str(out_path)
    assert durs == []

    # Edge case C: Single clip
    c1 = tmp_path / "c1.wav"
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=300:duration=2",
        "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2",
        str(c1)
    ], capture_output=True, check=True)

    path, durs = proc.concat_crossfade_audio([str(c1)], str(out_path))
    assert path == str(out_path)
    assert len(durs) == 1
    assert durs[0] > 0

    # Edge case D: 3 short clips with crossfade recalculation
    c2 = tmp_path / "c2.wav"
    c3 = tmp_path / "c3.wav"
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=400:duration=2",
        "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2",
        str(c2)
    ], capture_output=True, check=True)
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=500:duration=2",
        "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2",
        str(c3)
    ], capture_output=True, check=True)

    path, durs = proc.concat_crossfade_audio([str(c1), str(c2), str(c3)], str(out_path), crossfade_sec=0.2)
    assert path == str(out_path)
    assert len(durs) == 3
    assert os.path.exists(out_path)


# ============================================================================
# 3. QA Gatekeeper (src/qa_gatekeeper.py) Boundary & Edge Case Stress Testing
# ============================================================================

def test_safe_converters_edge_cases():
    assert _safe_float(None, 5.0) == 5.0
    assert _safe_float("", 5.0) == 5.0
    assert _safe_float("N/A", 5.0) == 5.0
    assert _safe_float("invalid", 5.0) == 5.0
    assert _safe_float("12.34", 5.0) == 12.34
    assert _safe_float(15, 5.0) == 15.0

    assert _safe_int(None, 10) == 10
    assert _safe_int("", 10) == 10
    assert _safe_int("N/A", 10) == 10
    assert _safe_int("abc", 10) == 10
    assert _safe_int("42", 10) == 42
    assert _safe_int(7, 10) == 7


def test_qa_gatekeeper_corrupted_ffprobe(monkeypatch, tmp_path):
    video_p = tmp_path / "corrupt.mp4"
    video_p.write_bytes(b"not an mp4 file")

    def mock_ffprobe_throws(p):
        raise RuntimeError("FFprobe binary crashed on corrupted file")

    monkeypatch.setattr("lib.qa_gatekeeper.ffprobe", mock_ffprobe_throws)

    gk = QAGatekeeper(strict_mode=True)
    report = gk.audit_video(str(video_p))
    assert report.passed is False
    codes = [i.code for i in report.issues]
    assert "ERR_QA_FFPROBE_FAILED" in codes


def test_qa_gatekeeper_filesize_limit(monkeypatch, tmp_path):
    video_p = tmp_path / "huge_video.mp4"
    video_p.write_bytes(b"0" * 100)  # placeholder

    def mock_valid_probe(p):
        return {
            "format": {"duration": "10.0"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "profile": "Main", "pix_fmt": "yuv420p", "width": 384, "height": 680, "duration": "10.0"},
                {"codec_type": "audio", "codec_name": "aac", "sample_rate": "44100", "channels": "2", "duration": "10.0"},
            ]
        }

    monkeypatch.setattr("lib.qa_gatekeeper.ffprobe", mock_valid_probe)
    monkeypatch.setattr("lib.qa_gatekeeper.has_faststart", lambda p: True)
    monkeypatch.setattr("lib.qa_gatekeeper.QAGatekeeper._audit_audio_silence_and_volume", lambda self, p: (0.0, -20.0, -1.5))
    monkeypatch.setattr("lib.qa_gatekeeper.QAGatekeeper._audit_freeze_and_black_frames", lambda self, p: (0.0, 0.0))
    monkeypatch.setattr("lib.qa_gatekeeper.QAGatekeeper._audit_ebu_r128_loudness", lambda self, p: (-14.0, -1.5, 8.0))

    gk = QAGatekeeper()
    # Mock stat().st_size to return 55MB (exceeding 50MB limit)
    original_stat = Path.stat

    def mock_stat(self, *args, **kwargs):
        st = original_stat(self, *args, **kwargs)
        if "huge_video.mp4" in str(self):
            class MockStatResult:
                st_size = 55 * 1024 * 1024
                def __getattr__(self, name):
                    return getattr(st, name)
            return MockStatResult()
        return st

    monkeypatch.setattr(Path, "stat", mock_stat)

    report = gk.audit_video(str(video_p))
    codes = [i.code for i in report.issues]
    assert "ERR_QA_FILESIZE_EXCEEDED" in codes
    assert report.passed is False


def test_qa_gatekeeper_ass_subtitle_safe_margin_edge_cases(tmp_path):
    # Test ASS file with non-standard layout or missing style definition
    ass_p = tmp_path / "no_styles.ass"
    ass_content = """[Script Info]
ScriptType: v4.00+

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,{\\kf20}Hola mundo
"""
    ass_p.write_text(ass_content, encoding="utf-8")

    gk = QAGatekeeper()
    issues, max_c, max_w, safe_comp = gk._audit_subtitles(str(ass_p))
    assert safe_comp is True
    assert max_c == 10
    assert max_w == 2


# ============================================================================
# 4. SCP Quality Verifier (src/scp/quality_verifier.py) Comprehensive Checks
# ============================================================================

def test_scp_quality_verifier_missing_attribution(monkeypatch, tmp_path):
    video_p = tmp_path / "valid_video.mp4"
    video_p.write_bytes(b"dummy video")

    def mock_valid_probe(p):
        return {
            "format": {"duration": "20.0"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264"},
                {"codec_type": "audio", "codec_name": "aac"},
            ]
        }

    monkeypatch.setattr("src.verification.quality.ffprobe", mock_valid_probe)

    verifier = QualityVerifier()
    research_data = {"entity_id": "SCP-096"}
    script_data = {
        "full_script": "El SCP-096 atacará a cualquiera que vea su rostro.",
        "title": "SCP-096 El Chicomalo",
        "attribution": "Sin atribucion alguna.",
    }
    media_asset = tmp_path / "image.png"
    media_asset.write_bytes(b"png")
    media_assets = [{"local_path": str(media_asset)}]

    with pytest.raises(QualityCheckError) as exc_info:
        verifier.verify_video(
            video_path=str(video_p),
            research_data=research_data,
            script_data=script_data,
            media_assets=media_assets,
        )

    assert "Missing required license attribution" in str(exc_info.value)


def test_scp_quality_verifier_missing_item_id_in_script(monkeypatch, tmp_path):
    video_p = tmp_path / "valid_video.mp4"
    video_p.write_bytes(b"dummy video")

    def mock_valid_probe(p):
        return {
            "format": {"duration": "20.0"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264"},
                {"codec_type": "audio", "codec_name": "aac"},
            ]
        }

    monkeypatch.setattr("src.verification.quality.ffprobe", mock_valid_probe)

    verifier = QualityVerifier()
    research_data = {"entity_id": "SCP-999"}
    script_data = {
        "full_script": "Esta criatura de gelatina naranja abraza a todos los investigadores.",
        "title": "Monstruo de las Cosquillas",
        "attribution": "Creative Commons CC BY-SA 3.0",
    }
    media_asset = tmp_path / "image.png"
    media_asset.write_bytes(b"png")
    media_assets = [{"local_path": str(media_asset)}]

    with pytest.raises(QualityCheckError) as exc_info:
        verifier.verify_video(
            video_path=str(video_p),
            research_data=research_data,
            script_data=script_data,
            media_assets=media_assets,
        )

    assert "Script missing canonical entity reference: SCP-999" in str(exc_info.value)
