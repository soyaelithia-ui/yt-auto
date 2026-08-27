"""
Unit tests for Quality Audit Engine (lib/qa/).
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from lib.ffmpeg import (
    AudioStreamInfo,
    FFmpegCommandResult,
    MediaProbeResult,
    VideoStreamInfo,
)
from lib.qa.engine import QualityAuditEngine, audit_media
from lib.qa.gates import (
    AudioGate,
    AudioQualityGate,
    AuditContext,
    ContainerGate,
    ScriptGate,
    SizeGate,
    SizeQuotaGate,
    SubtitleGate,
    VisualGate,
    VisualQualityGate,
)
from lib.qa.models import (
    GateResult,
    GateStatus,
    MediaProbeFacts,
    QualityAuditReport,
    RuleProfile,
    Severity,
)


class TestQualityAuditModelsAndPresets(unittest.TestCase):
    def test_gate_result_properties(self):
        gr_pass = GateResult(gate_id="g1", name="Gate 1", status=GateStatus.PASS, score=1.0)
        self.assertTrue(gr_pass.is_passed)

        gr_fail = GateResult(gate_id="g2", name="Gate 2", status=GateStatus.FAIL, score=0.0, errors=["Error"])
        self.assertFalse(gr_fail.is_passed)

        gr_warn = GateResult(gate_id="g3", name="Gate 3", status=GateStatus.WARNING, score=0.8, warnings=["Warn"])
        self.assertTrue(gr_warn.is_passed)

    def test_rule_profile_presets(self):
        p_short = RuleProfile.get_preset("short")
        self.assertEqual(p_short.name, "short")
        self.assertEqual(p_short.max_file_size_mb, 50.0)

        p_long = RuleProfile.get_preset("longform")
        self.assertEqual(p_long.name, "longform")
        self.assertEqual(p_long.max_file_size_mb, 2048.0)

        p_tel = RuleProfile.get_preset("telegram")
        self.assertEqual(p_tel.name, "telegram_canary")
        self.assertEqual(p_tel.max_file_size_mb, 45.0)

        p_strict = RuleProfile.get_preset("strict")
        self.assertEqual(p_strict.name, "strict_master")
        self.assertTrue(p_strict.require_full_decode)

    def test_report_serialization(self):
        gr = GateResult(gate_id="c1", name="Container", status=GateStatus.PASS, score=1.0)
        rep = QualityAuditReport(
            file_path="/tmp/video.mp4",
            passed=True,
            overall_score=1.0,
            duration=12.5,
            gates={"container": gr},
            summary_reasons=[],
        )
        d = rep.to_dict()
        self.assertEqual(d["file_path"], "/tmp/video.mp4")
        self.assertTrue(d["passed"])
        self.assertEqual(d["overall_score"], 1.0)

        is_ok, reason, all_reasons = rep.to_legacy_gatekeeper_tuple()
        self.assertTrue(is_ok)
        self.assertEqual(reason, "PASS")

        dto = rep.to_legacy_dto()
        self.assertTrue(dto.passed)

        integ = rep.to_integrity_dict()
        self.assertTrue(integ["passed"])


class TestGateValidators(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.profile = RuleProfile.get_preset("short")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_size_quota_gate_pass_and_fail(self):
        test_file = os.path.join(self.temp_dir.name, "test_size.mp4")
        # 1MB file
        with open(test_file, "wb") as f:
            f.write(b"0" * 1024 * 1024)

        res = SizeQuotaGate.evaluate(test_file, self.profile)
        self.assertTrue(res.is_passed)
        self.assertEqual(res.status, GateStatus.PASS)

        # Profile with tiny 0.5MB limit
        tiny_prof = RuleProfile(name="tiny", max_file_size_mb=0.5)
        res_fail = SizeQuotaGate.evaluate(test_file, tiny_prof)
        self.assertFalse(res_fail.is_passed)
        self.assertEqual(res_fail.status, GateStatus.FAIL)

    @patch("lib.qa.gates.has_faststart", return_value=True)
    def test_container_gate_valid_media(self, mock_faststart):
        v_stream = VideoStreamInfo(
            codec_name="h264",
            width=1080,
            height=1920,
            fps=30.0,
            pix_fmt="yuv420p",
            duration=30.0,
        )
        a_stream = AudioStreamInfo(
            codec_name="aac",
            sample_rate=48000,
            channels=2,
            duration=30.0,
        )
        probe = MediaProbeResult(
            format_name="mov,mp4,m4a,3gp,3g2,mj2",
            duration=30.0,
            size_bytes=10000,
            video_streams=[v_stream],
            audio_streams=[a_stream],
            file_path="video.mp4",
        )
        ctx = AuditContext(file_path="video.mp4", profile=self.profile, probe=probe)
        gate = ContainerGate()
        res = gate.audit(ctx)
        self.assertTrue(all(r.passed for r in res))

    @patch("lib.qa.gates.has_faststart", return_value=False)
    def test_container_gate_missing_faststart(self, mock_faststart):
        v_stream = VideoStreamInfo(
            codec_name="h264",
            width=1080,
            height=1920,
            fps=30.0,
            pix_fmt="yuv420p",
            duration=30.0,
        )
        probe = MediaProbeResult(
            format_name="mp4",
            duration=30.0,
            size_bytes=10000,
            video_streams=[v_stream],
            audio_streams=[],
            file_path="video.mp4",
        )
        ctx = AuditContext(file_path="video.mp4", profile=self.profile, probe=probe)
        gate = ContainerGate()
        res = gate.audit(ctx)
        self.assertTrue(any("faststart" in r.message.lower() for r in res))

    @patch("lib.qa.gates.run_ffmpeg")
    def test_audio_gate_failures(self, mock_ffmpeg):
        # Extreme silence failure
        mock_ffmpeg.return_value = FFmpegCommandResult(
            returncode=0,
            stdout="",
            stderr="silence_duration: 3.5\nI: -14.0 LUFS\nTrue peak: -2.0 dBTP",
            command=["ffmpeg"],
            duration_sec=0.1,
        )
        ctx = AuditContext(file_path="test.mp4", profile=self.profile)
        gate = AudioQualityGate()
        res = gate.audit(ctx)
        self.assertTrue(any("silence" in r.message.lower() for r in res))

    @patch("lib.qa.gates.run_ffmpeg")
    def test_visual_gate_black_and_freeze(self, mock_ffmpeg):
        mock_ffmpeg.return_value = FFmpegCommandResult(
            returncode=0,
            stdout="",
            stderr="freeze_start: 0.0\nfreeze_end: 4.0\nblack_duration: 3.5",
            command=["ffmpeg"],
            duration_sec=0.1,
        )
        ctx = AuditContext(file_path="test.mp4", profile=self.profile)
        gate = VisualQualityGate()
        res = gate.audit(ctx)
        codes = [r.code for r in res]
        self.assertIn("ERR_QA_VISUAL_FREEZE", codes)
        self.assertIn("ERR_QA_BLACK_FRAME", codes)

    def test_subtitle_gate_safezone(self):
        sub_file = Path(self.temp_dir.name) / "test.ass"
        sub_file.write_text(
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,10,10,50,1\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\\k50¿HOLA?} Texto largo\n",
            encoding="utf-8"
        )
        ctx = AuditContext(file_path="dummy.mp4", profile=self.profile, subtitle_path=str(sub_file))
        gate = SubtitleGate()
        res = gate.audit(ctx)
        codes = [r.code for r in res]
        self.assertIn("ERR_QA_SUBTITLE_SYNTAX", codes)
        self.assertIn("ERR_QA_SUBTITLE_SAFEZONE", codes)

    def test_script_gate(self):
        ctx = AuditContext(file_path="", profile=self.profile, script_text="Historia de terror y moku_terror")
        gate = ScriptGate()
        res = gate.audit(ctx)
        codes = [r.code for r in res]
        self.assertIn("ERR_QA_ALIAS_LEAK", codes)


class TestQualityAuditEngineIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_video = os.path.join(self.temp_dir.name, "test.mp4")
        with open(self.test_video, "wb") as f:
            f.write(b"0" * 1024 * 50)
        self.engine = QualityAuditEngine()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_file_not_found(self):
        rep = self.engine.audit_media("/nonexistent/video.mp4")
        self.assertFalse(rep.passed)
        self.assertTrue(any("missing" in s.lower() or "not found" in s.lower() for s in rep.summary_reasons))

    @patch("lib.qa.engine.probe_media")
    @patch("lib.qa.gates.has_faststart", return_value=True)
    @patch("lib.qa.gates.run_ffmpeg")
    def test_audit_media_success(self, mock_ffmpeg, mock_faststart, mock_probe):
        v_stream = VideoStreamInfo(
            codec_name="h264",
            width=1080,
            height=1920,
            fps=30.0,
            pix_fmt="yuv420p",
            duration=25.0,
        )
        a_stream = AudioStreamInfo(
            codec_name="aac",
            sample_rate=48000,
            channels=2,
            duration=25.0,
        )
        mock_probe.return_value = MediaProbeResult(
            format_name="mp4",
            duration=25.0,
            size_bytes=os.path.getsize(self.test_video),
            video_streams=[v_stream],
            audio_streams=[a_stream],
            file_path=self.test_video,
        )
        mock_ffmpeg.return_value = FFmpegCommandResult(
            returncode=0,
            stdout="",
            stderr="Integrated loudness:\n I: -14.0 LUFS\nTrue peak:\n Peak: -2.0 dBFS",
            command=["ffmpeg"],
            duration_sec=0.1,
        )
        rep = self.engine.audit_media(self.test_video, work_dir=self.temp_dir.name)
        self.assertTrue(rep.passed)
        self.assertGreaterEqual(rep.overall_score, 0.9)
        report_file = Path(self.temp_dir.name) / "quality_audit_report.json"
        self.assertTrue(report_file.exists())


if __name__ == "__main__":
    unittest.main()
