"""
Unit tests for Milestone M4:
- EBU R128 Audio Mastering (src/audio.py & src/scp/audio_processor.py)
- Automated QA Gatekeeper QA-1 to QA-7 (src/qa_gatekeeper.py)
"""

import json
import os
import subprocess
import pytest
from pathlib import Path

from src.audio import normalize_narration_lufs, apply_sidechain_ducking, master_audio_track
from src.audio_processor import AudioProcessor
from lib.qa_gatekeeper import QAGatekeeper, QualityReportDTO, QualityReportFacts


def test_audio_normalization_ebu_r128(tmp_path):
    raw_audio = tmp_path / "raw_speech.wav"
    norm_audio = tmp_path / "norm_speech.wav"

    # Generate synthetic 800Hz sine wave audio track
    gen_cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=800:duration=4",
        "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2",
        str(raw_audio)
    ]
    subprocess.run(gen_cmd, capture_output=True, text=True, check=True)

    result = normalize_narration_lufs(
        input_path=str(raw_audio),
        output_path=str(norm_audio),
        target_lufs=-14.0,
        max_tp=-1.5,
        apply_lowpass=True,
        lowpass_freq=12000,
    )

    assert result == str(norm_audio)
    assert os.path.exists(norm_audio)
    assert os.path.getsize(norm_audio) > 1000

    # Audit normalized audio with QAGatekeeper EBU R128 loudness check
    gk = QAGatekeeper()
    lufs, tp, lra = gk._audit_ebu_r128_loudness(str(norm_audio))

    # Numerical assertions checking integrated LUFS and True Peak ceiling
    assert -15.5 <= lufs <= -12.5, f"Integrated loudness {lufs} LUFS outside target range [-15.5, -12.5]"
    assert tp <= -1.5, f"True peak {tp} dBTP exceeds maximum ceiling -1.5 dBTP"


def test_sidechain_ducking_and_mastering(tmp_path):
    speech = tmp_path / "speech.wav"
    music = tmp_path / "music.wav"
    mastered = tmp_path / "mastered.wav"

    # Generate synthetic speech and music
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=500:duration=3",
        "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2",
        str(speech)
    ], capture_output=True, check=True)

    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=200:duration=3",
        "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2",
        str(music)
    ], capture_output=True, check=True)

    res_duck = apply_sidechain_ducking(
        narration_path=str(speech),
        music_path=str(music),
        output_path=str(mastered),
        ducking_db=-18.0,
    )
    assert res_duck == str(mastered)
    assert os.path.exists(mastered)

    # Verify custom ducking_db execution
    mastered_6db = tmp_path / "mastered_6db.wav"
    res_duck_6db = apply_sidechain_ducking(
        narration_path=str(speech),
        music_path=str(music),
        output_path=str(mastered_6db),
        ducking_db=-6.0,
    )
    assert res_duck_6db == str(mastered_6db)
    assert os.path.exists(mastered_6db)

    # Test master_audio_track wrapper
    final_out = tmp_path / "final_track.wav"
    res_master = master_audio_track(
        narration_path=str(speech),
        music_path=str(music),
        output_path=str(final_out),
        target_lufs=-14.0,
        ducking_db=-18.0,
        lowpass_freq=12000,
    )
    assert res_master == str(final_out)
    assert os.path.exists(final_out)


def test_scp_audio_processor_integration(tmp_path):
    proc = AudioProcessor()
    raw = tmp_path / "raw.mp3"
    norm = tmp_path / "norm.mp3"

    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=600:duration=3",
        "-c:a", "libmp3lame", "-b:a", "192k",
        str(raw)
    ], capture_output=True, check=True)

    res = proc.normalize_loudness(str(raw), str(norm), target_lufs=-14.0)
    assert res == str(norm)
    assert os.path.exists(norm)

    # Verify mix_background_ambient with custom ambient_volume argument
    ambient_out = tmp_path / "ambient_out.mp3"
    res_amb = proc.mix_background_ambient(str(norm), str(ambient_out), ambient_volume=0.25)
    assert res_amb == str(ambient_out)
    assert os.path.exists(ambient_out)


def test_qa_gatekeeper_validation(tmp_path):
    video_p = tmp_path / "test_video.mp4"
    ass_p = tmp_path / "test_sub.ass"
    report_p = tmp_path / "quality_report.json"

    # Create a synthetic MP4 video file with H.264 Main / AAC / faststart
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=size=384x680:rate=30:duration=3",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=3",
        "-c:v", "libx264", "-profile:v", "main", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart",
        str(video_p)
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)

    # Create a valid ASS subtitle file
    ass_content = """[Script Info]
ScriptType: v4.00+
PlayResX: 768
PlayResY: 1360
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Montserrat,42,&H0000FFFF,&H00FFFFFF,&H00000000,&H90000000,1,0,0,0,100,100,0,0,1,4,2,2,40,40,120,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,{\\kf20}Hola {\\kf30}mundo
"""
    ass_p.write_text(ass_content, encoding="utf-8")

    gk = QAGatekeeper(strict_mode=True)
    report = gk.audit_video(
        video_path=str(video_p),
        run_id="test_run_123",
        channel="moku",
        subtitle_path=str(ass_p),
        script_text="El sujeto SCP ha sido asegurado y contenido en las instalaciones principales.",
        output_report_path=str(report_p),
        video_mode="short",
    )

    assert isinstance(report, QualityReportDTO)
    assert report.run_id == "test_run_123"
    assert report.channel == "moku"
    assert report.facts.faststart_enabled is True
    assert report.facts.video_codec == "h264"
    assert report.facts.pixel_format == "yuv420p"
    assert report.facts.audio_codec == "aac"
    assert os.path.exists(report_p)

    # Read back generated JSON
    data = json.loads(report_p.read_text(encoding="utf-8"))
    assert data["run_id"] == "test_run_123"
    assert "issues" in data
    assert "facts" in data


# ---------------------------------------------------------------------------
# Unit tests for QA Gatekeeper failure branches (ERR_QA_* codes)
# ---------------------------------------------------------------------------

def test_qa_gatekeeper_na_duration_handling(monkeypatch, tmp_path):
    video_p = tmp_path / "na_video.mp4"
    video_p.write_bytes(b"fake mp4 video bytes")

    def mock_ffprobe(path):
        return {
            "format": {"duration": "N/A"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "profile": "Main", "pix_fmt": "yuv420p", "width": 384, "height": 680, "duration": "N/A"},
                {"codec_type": "audio", "codec_name": "aac", "sample_rate": "44100", "channels": "2", "duration": "N/A"},
            ]
        }

    monkeypatch.setattr("lib.qa_gatekeeper.ffprobe", mock_ffprobe)
    monkeypatch.setattr("lib.qa_gatekeeper.has_faststart", lambda p: True)
    monkeypatch.setattr("lib.qa_gatekeeper.QAGatekeeper._audit_audio_silence_and_volume", lambda self, p: (0.0, -20.0, -1.5))
    monkeypatch.setattr("lib.qa_gatekeeper.QAGatekeeper._audit_freeze_and_black_frames", lambda self, p: (0.0, 0.0))
    monkeypatch.setattr("lib.qa_gatekeeper.QAGatekeeper._audit_ebu_r128_loudness", lambda self, p: (-14.0, -1.5, 8.0))

    gk = QAGatekeeper(strict_mode=True)
    report = gk.audit_video(str(video_p))
    assert report.facts.duration_seconds == 0.0
    assert report.facts.av_sync_drift_sec == 0.0


def test_qa1_dead_audio_and_extreme_silence_failures(monkeypatch, tmp_path):
    video_p = tmp_path / "qa1_test.mp4"
    video_p.write_bytes(b"dummy video content")

    def mock_base_probe():
        return {
            "format": {"duration": "10.0"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "profile": "Main", "pix_fmt": "yuv420p", "width": 384, "height": 680, "duration": "10.0"},
                {"codec_type": "audio", "codec_name": "aac", "sample_rate": "44100", "channels": "2", "duration": "10.0"},
            ]
        }

    monkeypatch.setattr("lib.qa_gatekeeper.ffprobe", lambda p: mock_base_probe())
    monkeypatch.setattr("lib.qa_gatekeeper.has_faststart", lambda p: True)
    monkeypatch.setattr("lib.qa_gatekeeper.QAGatekeeper._audit_freeze_and_black_frames", lambda self, p: (0.0, 0.0))
    monkeypatch.setattr("lib.qa_gatekeeper.QAGatekeeper._audit_ebu_r128_loudness", lambda self, p: (-14.0, -1.5, 8.0))

    # Scenario 1A: Muted audio (mean volume -35 dBFS < -30 dBFS)
    monkeypatch.setattr("lib.qa_gatekeeper.QAGatekeeper._audit_audio_silence_and_volume", lambda self, p: (0.0, -35.0, -10.0))
    gk = QAGatekeeper()
    rep1 = gk.audit_video(str(video_p))
    codes1 = [issue.code for issue in rep1.issues]
    assert "ERR_QA_DEAD_AUDIO" in codes1
    assert rep1.passed is False

    # Scenario 1B: Extreme mid-video silence (1.5s > 1.0s)
    monkeypatch.setattr("lib.qa_gatekeeper.QAGatekeeper._audit_audio_silence_and_volume", lambda self, p: (1.5, -20.0, -1.5))
    rep2 = gk.audit_video(str(video_p))
    codes2 = [issue.code for issue in rep2.issues]
    assert "ERR_QA_EXTREME_SILENCE" in codes2

    # Scenario 1C: Missing audio stream entirely
    def mock_no_audio_probe(p):
        d = mock_base_probe()
        d["streams"] = [d["streams"][0]]
        return d
    monkeypatch.setattr("lib.qa_gatekeeper.ffprobe", mock_no_audio_probe)
    rep3 = gk.audit_video(str(video_p))
    codes3 = [issue.code for issue in rep3.issues]
    assert "ERR_QA_DEAD_AUDIO" in codes3


def test_qa2_container_failures(monkeypatch, tmp_path):
    video_p = tmp_path / "qa2_test.mp4"
    video_p.write_bytes(b"dummy container video")

    monkeypatch.setattr("lib.qa_gatekeeper.has_faststart", lambda p: False)
    monkeypatch.setattr("lib.qa_gatekeeper.QAGatekeeper._audit_audio_silence_and_volume", lambda self, p: (0.0, -20.0, -1.5))
    monkeypatch.setattr("lib.qa_gatekeeper.QAGatekeeper._audit_freeze_and_black_frames", lambda self, p: (0.0, 0.0))
    monkeypatch.setattr("lib.qa_gatekeeper.QAGatekeeper._audit_ebu_r128_loudness", lambda self, p: (-14.0, -1.5, 8.0))

    # Bad codec (hevc), non-main profile (High), bad pix_fmt (yuv444p), bad audio codec (mp3)
    def mock_invalid_container_probe(p):
        return {
            "format": {"duration": "10.0"},
            "streams": [
                {"codec_type": "video", "codec_name": "hevc", "profile": "High", "pix_fmt": "yuv444p", "width": 384, "height": 680, "duration": "10.0"},
                {"codec_type": "audio", "codec_name": "mp3", "sample_rate": "44100", "channels": "2", "duration": "10.0"},
            ]
        }

    monkeypatch.setattr("lib.qa_gatekeeper.ffprobe", mock_invalid_container_probe)

    gk = QAGatekeeper()
    rep = gk.audit_video(str(video_p))
    codes = [issue.code for issue in rep.issues]

    assert "ERR_QA_CONTAINER_INVALID" in codes
    assert "ERR_QA_PIXFMT_INVALID" in codes
    assert "ERR_QA_AUDIOCODEC_INVALID" in codes
    assert "ERR_QA_FASTSTART_MISSING" in codes
    assert rep.passed is False


def test_qa3_visual_freeze_and_black_frames_failures(monkeypatch, tmp_path):
    video_p = tmp_path / "qa3_test.mp4"
    video_p.write_bytes(b"dummy freeze video")

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
    monkeypatch.setattr("lib.qa_gatekeeper.QAGatekeeper._audit_ebu_r128_loudness", lambda self, p: (-14.0, -1.5, 8.0))

    # Freeze = 3.0s (>= 2.5s), Black frames = 3.5s (>= 3.0s)
    monkeypatch.setattr("lib.qa_gatekeeper.QAGatekeeper._audit_freeze_and_black_frames", lambda self, p: (3.0, 3.5))

    gk = QAGatekeeper()
    rep = gk.audit_video(str(video_p))
    codes = [issue.code for issue in rep.issues]

    assert "ERR_QA_VISUAL_FREEZE" in codes
    assert "ERR_QA_BLACK_FRAME" in codes
    assert rep.passed is False


def test_qa4_av_desync_failure(monkeypatch, tmp_path):
    video_p = tmp_path / "qa4_test.mp4"
    video_p.write_bytes(b"dummy desync video")

    # Video duration = 10.0s, Audio duration = 10.5s -> drift = 0.5s > 0.30s
    def mock_desync_probe(p):
        return {
            "format": {"duration": "10.0"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "profile": "Main", "pix_fmt": "yuv420p", "width": 384, "height": 680, "duration": "10.0"},
                {"codec_type": "audio", "codec_name": "aac", "sample_rate": "44100", "channels": "2", "duration": "10.5"},
            ]
        }

    monkeypatch.setattr("lib.qa_gatekeeper.ffprobe", mock_desync_probe)
    monkeypatch.setattr("lib.qa_gatekeeper.has_faststart", lambda p: True)
    monkeypatch.setattr("lib.qa_gatekeeper.QAGatekeeper._audit_audio_silence_and_volume", lambda self, p: (0.0, -20.0, -1.5))
    monkeypatch.setattr("lib.qa_gatekeeper.QAGatekeeper._audit_freeze_and_black_frames", lambda self, p: (0.0, 0.0))
    monkeypatch.setattr("lib.qa_gatekeeper.QAGatekeeper._audit_ebu_r128_loudness", lambda self, p: (-14.0, -1.5, 8.0))

    gk = QAGatekeeper()
    rep = gk.audit_video(str(video_p))
    codes = [issue.code for issue in rep.issues]

    assert "ERR_QA_AV_DESYNC" in codes
    assert rep.facts.av_sync_drift_sec == 0.5
    assert rep.passed is False


def test_qa5_subtitle_failures(tmp_path):
    ass_p = tmp_path / "invalid_sub.ass"

    # Invalid ASS file: MarginV = 80 (< 120 safe zone), character length > 22, words > 3, karaoke syntax error
    ass_content = """[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Montserrat,42,&H0000FFFF,&H00FFFFFF,&H00000000,&H90000000,1,0,0,0,100,100,0,0,1,4,2,2,40,40,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,{\\kf20¿}Esta linea es demasiado larga para una sola pantalla de video short
"""
    ass_p.write_text(ass_content, encoding="utf-8")

    gk = QAGatekeeper()
    issues, max_c, max_w, safe_comp = gk._audit_subtitles(str(ass_p))
    codes = [i.code for i in issues]

    assert "ERR_QA_SUBTITLE_SAFEZONE" in codes
    assert "ERR_QA_SUBTITLE_OVERFLOW" in codes
    assert "ERR_QA_SUBTITLE_SYNTAX" in codes
    assert safe_comp is False


def test_qa5_spanish_inverted_punctuation_valid_syntax(tmp_path):
    """Verifies that valid Spanish karaoke subtitles with inverted punctuation (¿ and ¡) pass QA-5."""
    ass_p = tmp_path / "valid_spanish_sub.ass"

    ass_content = """[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Montserrat,42,&H0000FFFF,&H00FFFFFF,&H00000000,&H90000000,1,0,0,0,100,100,0,0,1,4,2,2,40,40,200,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,{\\kf20}¿Hola {\\kf30}amigo?
Dialogue: 0,0:00:02.00,0:00:04.00,Default,,0,0,0,,{\\kf25}¡Genial!
"""
    ass_p.write_text(ass_content, encoding="utf-8")

    gk = QAGatekeeper()
    issues, max_c, max_w, safe_comp = gk._audit_subtitles(str(ass_p))
    codes = [i.code for i in issues]

    assert "ERR_QA_SUBTITLE_SYNTAX" not in codes
    assert safe_comp is True
    assert len(issues) == 0




def test_qa6_lufs_and_clipping_failures(monkeypatch, tmp_path):
    video_p = tmp_path / "qa6_test.mp4"
    video_p.write_bytes(b"dummy audio test video")

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

    # Integrated LUFS = -18.0 (< -15.5) and True Peak = -0.5 (> -1.5)
    monkeypatch.setattr("lib.qa_gatekeeper.QAGatekeeper._audit_ebu_r128_loudness", lambda self, p: (-18.0, -0.5, 8.0))

    gk = QAGatekeeper()
    rep = gk.audit_video(str(video_p))
    codes = [issue.code for issue in rep.issues]

    assert "ERR_QA_LUFS_OUT_OF_BOUNDS" in codes
    assert "ERR_QA_AUDIO_CLIPPING" in codes
    assert rep.passed is False


def test_qa7_resolution_and_duration_failures(monkeypatch, tmp_path):
    video_p = tmp_path / "qa7_test.mp4"
    video_p.write_bytes(b"dummy res/dur video")

    # Resolution 1920x1080 (horizontal landscape), duration 0.2s (too short in test env)
    def mock_bad_res_dur_probe(p):
        return {
            "format": {"duration": "0.2"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "profile": "Main", "pix_fmt": "yuv420p", "width": 1920, "height": 1080, "duration": "0.2"},
                {"codec_type": "audio", "codec_name": "aac", "sample_rate": "44100", "channels": "2", "duration": "0.2"},
            ]
        }

    monkeypatch.setattr("lib.qa_gatekeeper.ffprobe", mock_bad_res_dur_probe)
    monkeypatch.setattr("lib.qa_gatekeeper.has_faststart", lambda p: True)
    monkeypatch.setattr("lib.qa_gatekeeper.QAGatekeeper._audit_audio_silence_and_volume", lambda self, p: (0.0, -20.0, -1.5))
    monkeypatch.setattr("lib.qa_gatekeeper.QAGatekeeper._audit_freeze_and_black_frames", lambda self, p: (0.0, 0.0))
    monkeypatch.setattr("lib.qa_gatekeeper.QAGatekeeper._audit_ebu_r128_loudness", lambda self, p: (-14.0, -1.5, 8.0))

    gk = QAGatekeeper()
    rep = gk.audit_video(str(video_p))
    codes = [issue.code for issue in rep.issues]

    assert "ERR_QA_RESOLUTION_INVALID" in codes
    assert "ERR_QA_DURATION_OUT_OF_BOUNDS" in codes
    assert rep.passed is False


def test_qa_file_missing_and_text_checks(monkeypatch, tmp_path):
    video_p = tmp_path / "existing_video.mp4"
    video_p.write_bytes(b"dummy content")

    # Test missing file error code
    gk = QAGatekeeper()
    missing_rep = gk.audit_video(str(tmp_path / "non_existent.mp4"))
    assert missing_rep.passed is False
    assert missing_rep.issues[0].code == "ERR_QA_FILE_MISSING"

    # Test text checks: non-neutral Spanish & forbidden alias
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

    bad_script = "En este video del canal soy_el_malo vamos a platicar sobre la neta del SCP."
    rep = gk.audit_video(video_path=str(video_p), script_text=bad_script)
    codes = [issue.code for issue in rep.issues]

    assert "ERR_QA_NON_NEUTRAL_SPANISH" in codes
    assert "ERR_QA_ALIAS_LEAK" in codes
    assert rep.passed is False
