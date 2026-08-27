"""
Adversarial Edge-Case Stress Tests for Milestone M4 Iteration 3:
- Audio Mastering & Normalization (src/audio.py & src/scp/audio_processor.py)
- Automated QA Gatekeeper (src/qa_gatekeeper.py)
- SCP Quality Verifier (src/scp/quality_verifier.py)
"""

import json
import os
import shutil
import subprocess
import pytest
from pathlib import Path

from src.audio import (
    normalize_narration_lufs,
    apply_sidechain_ducking,
    master_audio_track,
)
from src.audio_processor import AudioProcessor
from lib.qa_gatekeeper import (
    QAGatekeeper,
    QualityReportDTO,
    QualityReportFacts,
    QualityReportIssue,
    _safe_float,
    _safe_int,
)
from src.verification.quality import QualityVerifier, QualityCheckError


class TestAudioMasteringAdversarial:
    """Adversarial stress tests for EBU R128 audio mastering and processor functions."""

    def test_safe_helpers_extreme_inputs(self):
        """Test _safe_float and _safe_int against malformed, NaN, None, and complex structures."""
        assert _safe_float(None, 42.0) == 42.0
        assert _safe_float("N/A", -1.0) == -1.0
        assert _safe_float("", 0.0) == 0.0
        assert _safe_float("invalid_number", 5.5) == 5.5
        assert _safe_float([1, 2, 3], 9.9) == 9.9
        assert _safe_float({"a": 1}, 8.8) == 8.8
        assert _safe_float(" -14.5 ", 0.0) == -14.5
        assert _safe_float("1e-3", 0.0) == 0.001

        assert _safe_int(None, 100) == 100
        assert _safe_int("N/A", -1) == -1
        assert _safe_int("", 0) == 0
        assert _safe_int("abc", 7) == 7
        assert _safe_int(12.34, 0) == 12
        assert _safe_int("44100", 0) == 44100

    def test_normalize_narration_missing_or_empty_input(self, tmp_path):
        """Missing or 0-byte audio input should return input_path gracefully without crashing."""
        missing_file = str(tmp_path / "non_existent.wav")
        out_file = str(tmp_path / "output.wav")
        res = normalize_narration_lufs(missing_file, out_file)
        assert res == missing_file

        empty_file = tmp_path / "empty.wav"
        empty_file.write_bytes(b"")
        res_empty = normalize_narration_lufs(str(empty_file), out_file)
        assert res_empty == str(empty_file)

    def test_normalize_narration_extreme_lufs_and_freq(self, tmp_path):
        """Normalize audio with non-standard target LUFS and custom lowpass frequencies."""
        raw_audio = tmp_path / "raw.wav"
        out_audio = tmp_path / "norm.wav"

        # Generate 2-second sine wave
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "1",
            str(raw_audio)
        ], capture_output=True, check=True)

        res = normalize_narration_lufs(
            input_path=str(raw_audio),
            output_path=str(out_audio),
            target_lufs=-18.0,
            max_tp=-2.0,
            apply_lowpass=True,
            lowpass_freq=8000,
        )
        assert res == str(out_audio)
        assert os.path.exists(out_audio)
        assert os.path.getsize(out_audio) > 1000

    def test_sidechain_ducking_missing_or_invalid_music(self, tmp_path):
        """Ducking with missing music or empty narration should fall back safely."""
        speech = tmp_path / "speech.wav"
        out_wav = tmp_path / "ducked.wav"

        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "sine=frequency=300:duration=2",
            "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2",
            str(speech)
        ], capture_output=True, check=True)

        # None music path -> returns speech
        res1 = apply_sidechain_ducking(str(speech), None, str(out_wav))
        assert res1 == str(speech)

        # Nonexistent music path -> returns speech
        res2 = apply_sidechain_ducking(str(speech), str(tmp_path / "no_music.wav"), str(out_wav))
        assert res2 == str(speech)

        # 0-byte music path -> returns speech
        empty_music = tmp_path / "empty_music.wav"
        empty_music.write_bytes(b"")
        res3 = apply_sidechain_ducking(str(speech), str(empty_music), str(out_wav))
        assert res3 == str(speech)

    def test_concat_crossfade_audio_edge_cases(self, tmp_path):
        """Crossfade concatenation with 0 clips, 1 clip, short clips, and malformed paths."""
        proc = AudioProcessor()
        out_wav = str(tmp_path / "concat_out.mp3")

        # 1. Zero clips
        res_path, durs = proc.concat_crossfade_audio([], out_wav)
        assert res_path == out_wav
        assert durs == []

        # 2. Clips with nonexistent paths filtered out
        res_path, durs = proc.concat_crossfade_audio(["/nonexistent/file.mp3"], out_wav)
        assert res_path == out_wav
        assert durs == []

        # Generate two short audio clips (0.3s each)
        clip1 = tmp_path / "clip1.wav"
        clip2 = tmp_path / "clip2.wav"
        clip3 = tmp_path / "clip3.wav"

        for p in (clip1, clip2, clip3):
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "sine=frequency=500:duration=1.0",
                "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2",
                str(p)
            ], capture_output=True, check=True)

        # Single clip
        res_path1, durs1 = proc.concat_crossfade_audio([str(clip1)], out_wav)
        assert os.path.exists(res_path1)
        assert len(durs1) == 1

        # 3 clips crossfade
        res_path3, durs3 = proc.concat_crossfade_audio([str(clip1), str(clip2), str(clip3)], out_wav, crossfade_sec=0.1)
        assert os.path.exists(res_path3)
        assert len(durs3) == 3
        # Check scene durations calculation logic
        assert all(d > 0 for d in durs3)


class TestQAGatekeeperAdversarial:
    """Adversarial stress tests for QA Gatekeeper gates QA-1 to QA-7."""

    def test_qa_gatekeeper_corrupted_video_file(self, tmp_path):
        """QA Gatekeeper handling of corrupted/truncated video file (ffprobe failure)."""
        bad_video = tmp_path / "corrupt.mp4"
        bad_video.write_bytes(b"NOT_A_VALID_MP4_HEADER_RANDOM_GARBAGE_BYTES_1234567890")

        gk = QAGatekeeper(strict_mode=True)
        report = gk.audit_video(str(bad_video))

        assert report.passed is False
        codes = [i.code for i in report.issues]
        assert "ERR_QA_FFPROBE_FAILED" in codes

    def test_qa1_volume_boundary_conditions(self, monkeypatch, tmp_path):
        """QA-1 boundary testing: mean volume = -30.0 dBFS (pass) vs -30.1 dBFS (fail)."""
        video_p = tmp_path / "vol_test.mp4"
        video_p.write_bytes(b"dummy video")

        def mock_base_probe(p):
            return {
                "format": {"duration": "10.0"},
                "streams": [
                    {"codec_type": "video", "codec_name": "h264", "profile": "Main", "pix_fmt": "yuv420p", "width": 384, "height": 680, "duration": "10.0"},
                    {"codec_type": "audio", "codec_name": "aac", "sample_rate": "44100", "channels": "2", "duration": "10.0"},
                ]
            }

        monkeypatch.setattr("lib.qa_gatekeeper.ffprobe", mock_base_probe)
        monkeypatch.setattr("lib.qa_gatekeeper.ffprobe", mock_base_probe)
        monkeypatch.setattr("lib.qa_gatekeeper.has_faststart", lambda p: True)
        monkeypatch.setattr("lib.qa_gatekeeper.QAGatekeeper._audit_freeze_and_black_frames", lambda self, p: (0.0, 0.0))
        monkeypatch.setattr("lib.qa_gatekeeper.QAGatekeeper._audit_ebu_r128_loudness", lambda self, p: (-14.0, -1.5, 8.0))

        # Mean volume = -29.9 dBFS (Pass QA-1)
        monkeypatch.setattr("lib.qa_gatekeeper.QAGatekeeper._audit_audio_silence_and_volume", lambda self, p: (0.0, -29.9, -1.5))
        gk = QAGatekeeper()
        rep_pass = gk.audit_video(str(video_p))
        codes_pass = [i.code for i in rep_pass.issues]
        assert "ERR_QA_DEAD_AUDIO" not in codes_pass

        # Mean volume = -30.1 dBFS (Fail QA-1)
        monkeypatch.setattr("lib.qa_gatekeeper.QAGatekeeper._audit_audio_silence_and_volume", lambda self, p: (0.0, -30.1, -1.5))
        rep_fail = gk.audit_video(str(video_p))
        codes_fail = [i.code for i in rep_fail.issues]
        assert "ERR_QA_DEAD_AUDIO" in codes_fail

    def test_qa5_ass_subtitle_syntax_and_margin_boundaries(self, tmp_path):
        """QA-5: Test ASS subtitle parsing with edge-case MarginV and Karaoke syntax bug demonstration."""
        gk = QAGatekeeper()

        # Demonstration of the regex inversion bug in src/qa_gatekeeper.py line 557:
        # Valid Spanish ASS karaoke line (punctuation OUTSIDE tag):
        sub_valid = tmp_path / "valid_span.ass"
        sub_valid.write_text("""[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Montserrat,42,&H0000FFFF,&H00FFFFFF,&H00000000,&H90000000,1,0,0,0,100,100,0,0,1,4,2,2,40,40,120,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,{\\kf20}¿Hola {\\kf30}amigo
""", encoding="utf-8")

        issues_valid, _, _, _ = gk._audit_subtitles(str(sub_valid))
        codes_valid = [i.code for i in issues_valid]
        # Verified fix: valid subtitle correctly formatted as {\kf20}¿Hola does not trigger ERR_QA_SUBTITLE_SYNTAX
        assert "ERR_QA_SUBTITLE_SYNTAX" not in codes_valid, "Valid Spanish karaoke punctuation should not trigger syntax error"

        # Invalid Spanish ASS karaoke line (punctuation INSIDE tag):
        sub_invalid = tmp_path / "invalid_span.ass"
        sub_invalid.write_text("""[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Montserrat,42,&H0000FFFF,&H00FFFFFF,&H00000000,&H90000000,1,0,0,0,100,100,0,0,1,4,2,2,40,40,120,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,{\\kf20¿}Hola
""", encoding="utf-8")

        issues_invalid, _, _, _ = gk._audit_subtitles(str(sub_invalid))
        codes_invalid = [i.code for i in issues_invalid]
        # Verified fix: invalid subtitle with punctuation inside tag {\kf20¿} triggers ERR_QA_SUBTITLE_SYNTAX
        assert "ERR_QA_SUBTITLE_SYNTAX" in codes_invalid, "Invalid Spanish karaoke punctuation inside tag must trigger syntax error"


class TestSCPQualityVerifierAdversarial:
    """Adversarial stress tests for QualityVerifier."""

    def test_verify_scp_video_missing_media_asset(self, monkeypatch, tmp_path):
        """Quality verifier should raise QualityCheckError if media asset is missing."""
        video_p = tmp_path / "valid.mp4"

        # Create synthetic valid video
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=size=64x64:rate=10:duration=1",
            "-f", "lavfi", "-i", "sine=frequency=1000:duration=1",
            "-c:v", "libx264", "-preset", "ultrafast", "-profile:v", "main", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
            "-movflags", "+faststart",
            str(video_p)
        ], capture_output=True, check=True)

        verifier = QualityVerifier()
        research_data = {"entity_id": "SCP-096"}
        script_data = {"full_script": "SCP-096 es un humanoide peligroso.", "attribution": "CC BY-SA 3.0"}

        # Missing media asset file
        bad_assets = [{"local_path": str(tmp_path / "missing_img.png")}]

        with pytest.raises(QualityCheckError, match="Media asset #1 is missing or corrupted"):
            verifier.verify_video(
                video_path=str(video_p),
                research_data=research_data,
                script_data=script_data,
                media_assets=bad_assets
            )

    def test_verify_scp_video_missing_canonical_fact(self, tmp_path):
        """Quality verifier should raise error if scp_id is not mentioned in full_script or title."""
        video_p = tmp_path / "valid.mp4"

        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=size=64x64:rate=10:duration=1",
            "-f", "lavfi", "-i", "sine=frequency=1000:duration=1",
            "-c:v", "libx264", "-preset", "ultrafast", "-profile:v", "main", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
            "-movflags", "+faststart",
            str(video_p)
        ], capture_output=True, check=True)

        verifier = QualityVerifier()
        research_data = {"entity_id": "SCP-999"}
        # Script mentions SCP-049 instead of SCP-999 or 999
        script_data = {"full_script": "SCP-049 es la peste.", "title": "La Peste", "attribution": "CC BY-SA 3.0"}

        with pytest.raises(QualityCheckError, match="Script missing canonical entity reference: SCP-999"):
            verifier.verify_video(
                video_path=str(video_p),
                research_data=research_data,
                script_data=script_data,
                media_assets=[]
            )

    def test_verify_scp_video_missing_license_attribution(self, tmp_path):
        """Quality verifier should raise error if CC BY-SA 3.0 attribution is missing."""
        video_p = tmp_path / "valid.mp4"

        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=size=64x64:rate=10:duration=1",
            "-f", "lavfi", "-i", "sine=frequency=1000:duration=1",
            "-c:v", "libx264", "-preset", "ultrafast", "-profile:v", "main", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
            "-movflags", "+faststart",
            str(video_p)
        ], capture_output=True, check=True)

        verifier = QualityVerifier()
        research_data = {"entity_id": "SCP-173"}
        script_data = {"full_script": "SCP-173 es una estatua.", "title": "SCP-173", "attribution": "Public Domain"}

        with pytest.raises(QualityCheckError, match="Missing required license attribution"):
            verifier.verify_video(
                video_path=str(video_p),
                research_data=research_data,
                script_data=script_data,
                media_assets=[]
            )
