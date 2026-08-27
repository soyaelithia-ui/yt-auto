"""Unit tests for the deterministic code-based video review verdict.

Covers:
  1. evaluate_video passes on a healthy media-integrity + gatekeeper report.
  2. evaluate_video fails when MediaIntegrityVerifier reports CRITICAL.
  3. ReviewJobManager.code_approve transitions PENDING_REVIEW -> APPROVED,
     persists metadata.code_verdict, and never calls bot.send_video_review.
  4. The pipeline code-review path is bypassed when CODE_REVIEW_ENABLED=0
     (legacy submit_video_for_review is invoked).
  5. The auto-publish sweep skips jobs whose metadata.code_verdict is set.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.core.verdict import (
    CodeReviewVerdict,
    GateResultLite,
    evaluate_video,
    is_code_review_enabled,
    update_verdict_payload,
)
from review import ReviewJobManager, ReviewStatus
from review.db import ReviewStateStore
from review.domain import ReviewJob


def _make_passed_integrity_report() -> dict:
    return {
        "file_path": "/tmp/fake.mp4",
        "filename": "fake.mp4",
        "size_bytes": 1024,
        "sha256_hash": "0" * 64,
        "passed": True,
        "decode_command": "ffmpeg -v error -xerror -i /tmp/fake.mp4 ...",
        "decode_exit_code": 0,
        "errors": [],
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "duration_sec": 30.0,
        "video_stream": {
            "codec": "h264",
            "width": 1080,
            "height": 1920,
            "pix_fmt": "yuv420p",
            "fps": 30.0,
            "duration_sec": 30.0,
            "decoded_frames": 900,
            "expected_frames": 900,
        },
        "audio_stream": {
            "codec": "aac",
            "sample_rate": 48000,
            "channels": 2,
            "duration_sec": 30.0,
        },
        "faststart_optimized": True,
    }


def _make_failed_integrity_report() -> dict:
    rep = _make_passed_integrity_report()
    rep["passed"] = False
    rep["errors"] = ["FFmpeg full decode failed with exit code 1: corrupt macroblock"]
    rep["decode_exit_code"] = 1
    return rep


class _StubVerifier:
    """Stand-in for src.integrity.MediaIntegrityVerifier that returns canned reports."""

    def __init__(self, report: dict) -> None:
        self._report = report

    def verify_file(self, file_path, work_dir=None):
        return dict(self._report)


class _StubGatekeeper:
    """Stand-in for lib.qa_gatekeeper.QAGatekeeper that returns a passed report."""

    class _Issue:
        def __init__(self, code: str, message: str, severity: str) -> None:
            self.code = code
            self.message = message
            self.severity = severity

    class _Facts:
        faststart_enabled = True
        video_codec = "h264"
        pixel_format = "yuv420p"
        audio_codec = "aac"
        duration_seconds = 30.0
        av_sync_drift_sec = 0.0
        width = 1080
        height = 1920

    class _Report:
        def __init__(self, issues, passed=True) -> None:
            self.issues = issues
            self.passed = passed
            self.facts = _StubGatekeeper._Facts()

    def __init__(self, *, passed: bool = True, issues=None) -> None:
        self._passed = passed
        self._issues = issues or []

    def audit_video(self, *args, **kwargs):
        return self._Report(self._issues, passed=self._passed)


class TestEvaluateVideo(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.work_dir = self.tmp.name
        self.video_path = os.path.join(self.work_dir, "fake.mp4")
        with open(self.video_path, "wb") as f:
            f.write(b"RIFFfake" * 128)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    @patch("src.core.verdict._roi_gate")
    @patch("src.core.verdict._qa_gatekeeper_gate")
    @patch("src.core.verdict._integrity_gate")
    def test_evaluate_video_passes_on_healthy_inputs(
        self, mock_integrity, mock_qa, mock_roi
    ) -> None:
        mock_integrity.return_value = GateResultLite(
            gate_id="media_integrity", passed=True, severity="INFO",
            code="OK_INTEGRITY", message="passed",
        )
        mock_qa.return_value = GateResultLite(
            gate_id="qa_gatekeeper", passed=True, severity="INFO",
            code="OK_GATEKEEPER", message="QAGatekeeper passed (strict mode)",
        )
        mock_roi.return_value = GateResultLite(
            gate_id="visual_integrity_roi", passed=True, severity="INFO",
            code="OK_ROI", message="ROI pass",
        )
        verdict = evaluate_video(
            self.video_path,
            work_dir=self.work_dir,
            story_id="story-1",
            run_id="run-1",
            channel="moku",
            video_mode="short",
        )
        self.assertTrue(verdict.passed)
        self.assertEqual(set(verdict.gates.keys()), {"media_integrity", "qa_gatekeeper", "visual_integrity_roi"})
        self.assertEqual(verdict.reasons, [])
        self.assertIsNotNone(verdict.report_path)
        self.assertTrue(Path(verdict.report_path).is_file())
        payload = json.loads(Path(verdict.report_path).read_text())
        self.assertTrue(payload["passed"])
        self.assertEqual(payload["story_id"], "story-1")

    @patch("src.core.verdict._roi_gate")
    @patch("src.core.verdict._qa_gatekeeper_gate")
    @patch("src.core.verdict._integrity_gate")
    def test_evaluate_video_fails_when_integrity_critical(
        self, mock_integrity, mock_qa, mock_roi
    ) -> None:
        mock_integrity.return_value = GateResultLite(
            gate_id="media_integrity", passed=False, severity="CRITICAL",
            code="ERR_QA_INTEGRITY", message="corrupt macroblock detected",
        )
        verdict = evaluate_video(
            self.video_path,
            work_dir=self.work_dir,
            story_id="story-2",
            run_id="run-2",
            channel="moku",
            video_mode="short",
        )
        self.assertFalse(verdict.passed)
        self.assertIn("media_integrity", verdict.gates)
        self.assertTrue(any("ERR_QA_INTEGRITY" in r for r in verdict.reasons))
        # QA + ROI should be skipped because integrity is fail-closed upstream.
        mock_qa.assert_not_called()
        mock_roi.assert_not_called()

    def test_evaluate_video_persists_report(self) -> None:
        with patch("src.core.verdict._integrity_gate") as mock_integrity, \
             patch("src.core.verdict._qa_gatekeeper_gate") as mock_qa, \
             patch("src.core.verdict._roi_gate") as mock_roi, \
             patch("src.core.verdict._safe_thumbnail_dimensions") as mock_thumb:
            mock_integrity.return_value = GateResultLite(
                gate_id="media_integrity", passed=True, severity="INFO",
                code="OK_INTEGRITY", message="passed",
            )
            mock_qa.return_value = GateResultLite(
                gate_id="qa_gatekeeper", passed=True, severity="INFO",
                code="OK_GATEKEEPER", message="ok",
            )
            mock_roi.return_value = GateResultLite(
                gate_id="visual_integrity_roi", passed=True, severity="INFO",
                code="OK_ROI", message="ok",
            )
            mock_thumb.return_value = None
            verdict = evaluate_video(
                self.video_path, work_dir=self.work_dir,
                story_id="story-3", channel="moku", video_mode="short",
            )
            self.assertTrue(verdict.passed)
            self.assertTrue(Path(verdict.report_path).is_file())


class TestReviewJobManagerCodeApprove(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "review.db")
        # Force the store to use the temp DB.
        os.environ["VIDEO_REVIEW_DB_PATH"] = self.db_path
        self.store = ReviewStateStore(self.db_path)
        self.manager = ReviewJobManager(store=self.store, bot=MagicMock())

    def tearDown(self) -> None:
        self.tmp.cleanup()
        os.environ.pop("VIDEO_REVIEW_DB_PATH", None)

    def test_submit_for_code_review_does_not_call_bot(self) -> None:
        bot = MagicMock()
        manager = ReviewJobManager(store=self.store, bot=bot)
        job = manager.submit_for_code_review(
            job_id="story-A", channel="moku", content_type="short",
            original_video_path="/tmp/fake.mp4", title="t", description="d",
            script="hola", work_dir="/tmp", drive_url=None,
        )
        self.assertEqual(job.status, ReviewStatus.PENDING_REVIEW.value)
        # Telegram bot must NEVER be called by the code-review path.
        bot.send_video_review.assert_not_called()
        # The job should be persisted with metadata flag.
        refreshed = self.store.get_job(job.job_id, job.version)
        self.assertIsNotNone(refreshed)
        self.assertEqual(refreshed.metadata.get("code_review_path"), "deterministic")
        self.assertIn("code_review_submitted_at", refreshed.metadata)

    def test_code_approve_transitions_and_persists_verdict(self) -> None:
        bot = MagicMock()
        manager = ReviewJobManager(store=self.store, bot=bot)
        job = manager.submit_for_code_review(
            job_id="story-B", channel="moku", content_type="short",
            original_video_path="/tmp/fake.mp4", title="t", description="d",
        )
        verdict_payload = {
            "passed": True,
            "gates": {"media_integrity": {"passed": True, "code": "OK"}},
            "reasons": [],
        }
        approved = manager.code_approve("story-B", job.version, verdict_payload, user_id=0)
        self.assertEqual(approved.status, ReviewStatus.APPROVED.value)
        self.assertIn("code_verdict", approved.metadata)
        self.assertEqual(approved.metadata["code_verdict"]["passed"], True)
        self.assertIn("code_reviewed_at", approved.metadata)
        self.assertEqual(approved.metadata["code_reviewer_user_id"], 0)
        # Bot still must not be called.
        bot.send_video_review.assert_not_called()

    def test_has_code_verdict_helper(self) -> None:
        bot = MagicMock()
        manager = ReviewJobManager(store=self.store, bot=bot)
        job = manager.submit_for_code_review(
            job_id="story-C", channel="moku", content_type="short",
            original_video_path="/tmp/fake.mp4",
        )
        self.assertFalse(manager.has_code_verdict(job))
        manager.code_approve("story-C", job.version, {"passed": True, "gates": {}, "reasons": []})
        refreshed = self.store.get_job("story-C", job.version)
        self.assertTrue(manager.has_code_verdict(refreshed))


class TestUpdateVerdictPayload(unittest.TestCase):
    def test_update_merges_into_existing(self) -> None:
        existing = {"foo": "bar", "code_verdict": {"old": True}}
        verdict = CodeReviewVerdict(
            passed=False,
            reasons=["x"],
            story_id="s",
        )
        merged = update_verdict_payload(existing, verdict, user_id=42)
        self.assertEqual(merged["foo"], "bar")
        self.assertEqual(merged["code_verdict"]["passed"], False)
        self.assertEqual(merged["code_verdict"]["reasons"], ["x"])
        self.assertEqual(merged["code_reviewer_user_id"], 42)
        self.assertIn("code_reviewed_at", merged)


class TestCodeReviewEnabledFlag(unittest.TestCase):
    def test_default_is_enabled(self) -> None:
        os.environ.pop("CODE_REVIEW_ENABLED", None)
        self.assertTrue(is_code_review_enabled())

    def test_zero_disables(self) -> None:
        os.environ["CODE_REVIEW_ENABLED"] = "0"
        try:
            self.assertFalse(is_code_review_enabled())
        finally:
            os.environ.pop("CODE_REVIEW_ENABLED", None)

    def test_false_string_disables(self) -> None:
        os.environ["CODE_REVIEW_ENABLED"] = "false"
        try:
            self.assertFalse(is_code_review_enabled())
        finally:
            os.environ.pop("CODE_REVIEW_ENABLED", None)


class TestAutoPublishSweepSkipsCodeVerdict(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "review.db")
        os.environ["VIDEO_REVIEW_DB_PATH"] = self.db_path
        self.store = ReviewStateStore(self.db_path)
        # Create a PENDING_REVIEW job with a code verdict (old enough to be "stale").
        long_ago = (datetime.now(timezone.utc).replace(microsecond=0)
                    ).fromtimestamp(0, tz=timezone.utc).isoformat()
        with_review = ReviewJob(
            job_id="story-verdict", channel="moku", title="t",
            original_video_path="/tmp/fake.mp4", status="PENDING_REVIEW",
            created_at=long_ago, metadata={"code_verdict": {"passed": True, "gates": {}, "reasons": []}},
        )
        without_review = ReviewJob(
            job_id="story-legacy", channel="moku", title="t",
            original_video_path="/tmp/fake.mp4", status="PENDING_REVIEW",
            created_at=long_ago, metadata={},
        )
        self.store.create_job(with_review)
        self.store.create_job(without_review)

    def tearDown(self) -> None:
        self.tmp.cleanup()
        os.environ.pop("VIDEO_REVIEW_DB_PATH", None)

    def test_sweep_skips_rows_with_code_verdict(self) -> None:
        from src.telegram.approval import get_expired_pending_videos

        results = get_expired_pending_videos()
        ids = sorted(r["job_id"] for r in results)
        # The job with a code verdict must be filtered out, only the legacy one remains.
        self.assertEqual(ids, ["story-legacy"])


if __name__ == "__main__":
    unittest.main()
