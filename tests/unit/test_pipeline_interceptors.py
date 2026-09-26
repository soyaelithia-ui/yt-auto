"""Unit tests for Phase 2 operational interceptors and lifecycle telemetry."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from review.db import ReviewStateStore
from review.domain import ReviewJob, ReviewStatus
from src.audio.tts_router import TTSRouter, TTSResponse
from src.core.db_reconciler import DBReconciler
from src.core.domain import YouTubeQuotaExceededError, YouTubeUploadLimitError
from src.core.repository import QueueRepository, backup_database, connect
from src.observability import clear_run_context, set_run_context


@pytest.fixture(autouse=True)
def _clean_context():
    clear_run_context()
    yield
    clear_run_context()


@pytest.fixture
def repo(tmp_path: Path) -> QueueRepository:
    db_path = tmp_path / "test_interceptors.db"
    r = QueueRepository(db_path)
    r.initialize()
    return r


def test_database_backup_telemetry(repo: QueueRepository, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Assert backup_database emits database_backup_completed with size and duration."""
    monkeypatch.setenv("DEFAULT_DB_PATH", str(repo.db_path))

    backup_dest = tmp_path / "backup_dest.db"
    out_path = backup_database(repo.db_path, backup_dest)
    assert out_path.is_file()

    with connect(repo.db_path, read_only=True) as conn:
        events = conn.execute(
            "SELECT * FROM system_events WHERE event_type = 'database_backup_completed'"
        ).fetchall()
        assert len(events) >= 1
        ev = events[0]
        assert ev["level"] == "INFO"
        details = json.loads(ev["details_json"])
        assert "size_bytes" in details
        assert details["size_bytes"] > 0
        assert "duration_ms" in details


def test_tts_router_token_burn_recording(repo: QueueRepository, monkeypatch: pytest.MonkeyPatch) -> None:
    """Assert TTSRouter._record_tts_burn persists token_burn_events for voice synthesis."""
    monkeypatch.setenv("DEFAULT_DB_PATH", str(repo.db_path))
    set_run_context(channel="horror", story_id="story-tts-1", run_id="run-tts-1", stage="stage_4_audio")

    resp = TTSResponse(
        audio_path="/tmp/fake.mp3",
        duration_sec=12.5,
        word_timestamps=[],
        provider="edge-tts",
        voice="es-ES-AlvaroNeural",
    )
    script_text = "Esta es una narración corta de prueba para medir tokens de voz."

    TTSRouter._record_tts_burn(resp, script_text, duration_sec=1.2, channel="horror")

    with connect(repo.db_path, read_only=True) as conn:
        records = conn.execute(
            "SELECT * FROM token_burn_events WHERE channel = 'horror' AND provider = 'edge-tts'"
        ).fetchall()
        assert len(records) == 1
        row = records[0]
        assert row["total_tokens"] == len(script_text)
        assert row["model"] == "es-ES-AlvaroNeural"
        assert row["status"] == "success"


def test_editorial_rejection_event_emission(repo: QueueRepository, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Assert transitioning review job to REJECTED emits asset_rejection with defect_category 'editorial'."""
    monkeypatch.setenv("DEFAULT_DB_PATH", str(repo.db_path))
    review_db_path = tmp_path / "review.db"
    rdb = ReviewStateStore(review_db_path)

    job = ReviewJob(
        job_id="story-rej-1",
        version=1,
        channel="moku",
        title="Test Story",
        status=ReviewStatus.PENDING_REVIEW.value,
        original_video_path="/tmp/v.mp4",
    )
    rdb.create_job(job)

    rdb.reject_job(job.job_id, job.version)

    with connect(repo.db_path, read_only=True) as conn:
        events = conn.execute(
            "SELECT * FROM system_events WHERE event_type = 'asset_rejection'"
        ).fetchall()
        assert len(events) >= 1
        ev = events[0]
        assert ev["level"] == "WARNING"
        details = json.loads(ev["details_json"])
        assert details["defect_category"] == "editorial"
        assert details["job_id"] == "story-rej-1"


def test_youtube_quota_limit_telemetry(repo: QueueRepository, monkeypatch: pytest.MonkeyPatch) -> None:
    """Assert YouTube quota exceptions emit youtube_quota_limit with reason and estimated units."""
    monkeypatch.setenv("DEFAULT_DB_PATH", str(repo.db_path))

    from src.observability.events import emit_event

    # 1. Quota Exceeded
    emit_event(
        "youtube_quota_limit",
        level="WARNING",
        message="Daily YouTube API quota exhausted",
        details={
            "reason": "quota_exceeded",
            "estimated_units": 1600,
            "channel": "moku",
            "story_id": "story-yt-quota-1",
        },
        channel="moku",
        story_id="story-yt-quota-1",
    )

    # 2. Upload Limit Exceeded
    emit_event(
        "youtube_quota_limit",
        level="WARNING",
        message="Channel daily upload limit reached",
        details={
            "reason": "upload_limit_exceeded",
            "estimated_units": 0,
            "channel": "scifi",
            "story_id": "story-yt-limit-1",
        },
        channel="scifi",
        story_id="story-yt-limit-1",
    )

    with connect(repo.db_path, read_only=True) as conn:
        events = conn.execute(
            "SELECT * FROM system_events WHERE event_type = 'youtube_quota_limit' ORDER BY event_id ASC"
        ).fetchall()
        assert len(events) == 2
        assert json.loads(events[0]["details_json"])["reason"] == "quota_exceeded"
        assert json.loads(events[0]["details_json"])["estimated_units"] == 1600
        assert json.loads(events[1]["details_json"])["reason"] == "upload_limit_exceeded"


def test_technical_qa_rejection_telemetry(repo: QueueRepository, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Assert TechnicalQAAuditor emits asset_rejection events with classified defect categories."""
    monkeypatch.setenv("DEFAULT_DB_PATH", str(repo.db_path))
    set_run_context(channel="horror", story_id="story-tqa-1", run_id="run-tqa-1", stage="stage_12_qa")

    fake_video = tmp_path / "test_video.mp4"
    fake_video.touch()

    from src.verification.technical_qa import TechnicalQAAuditor

    auditor = TechnicalQAAuditor()
    # Mock probe and ffmpeg check to trigger luminance and sync defects
    mock_probe = MagicMock()
    mock_probe.streams = []
    mock_probe.format = {"format_name": "mp4"}
    mock_probe.video = MagicMock(codec_name="h264", width=1080, height=1920, pix_fmt="yuv420p", duration=60.0)
    mock_probe.audio = MagicMock(codec_name="aac", duration=55.0)  # Drift > 1.5s
    mock_probe.audio_streams = [mock_probe.audio]
    mock_probe.primary_audio = mock_probe.audio
    mock_probe.duration = 60.0

    with patch("src.verification.technical_qa.probe_media", return_value=mock_probe), \
         patch("src.verification.technical_qa.has_faststart", return_value=True), \
         patch("subprocess.run") as mock_subproc:
        mock_subproc.return_value = MagicMock(returncode=0, stdout="", stderr="YAVG: 10.5\n")
        report = auditor.audit_video(fake_video, run_id="run-tqa-1")

    assert not report["overall_pass"]

    with connect(repo.db_path, read_only=True) as conn:
        events = conn.execute(
            "SELECT * FROM system_events WHERE event_type = 'asset_rejection' AND channel = 'horror'"
        ).fetchall()
        assert len(events) >= 1
        categories = {json.loads(e["details_json"])["defect_category"] for e in events}
        assert "luminance" in categories or "sync" in categories

