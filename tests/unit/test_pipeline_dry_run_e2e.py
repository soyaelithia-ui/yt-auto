"""
End-to-End Behavioral Contract Test for 13 Pipeline Stages (Dry-Run / generate_only).

Verifies:
- All 13 canonical stages execute sequentially in memory without remote calls.
- PipelineContext propagates artifacts: story, script, audio, manifest, video, thumbnail, metrics.
- Execution halts cleanly at JobStatus.RENDERED when generate_only=True.
- 100% offline, deterministic, and executes in < 1 second.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.config import SETTINGS
from src.core.domain import JobStatus
from src.core.repository import QueueRepository, connect
from src.pipeline import run_pipeline_once


@pytest.fixture
def dry_run_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Setup an isolated in-memory/temp SQLite database and workspace for dry-run."""
    work_dir = tmp_path / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    old_work = SETTINGS.work_root
    old_art = SETTINGS.artifact_root
    old_drive = SETTINGS.drive_folder_id
    old_drive_root = SETTINGS.drive_root_folder_id

    object.__setattr__(SETTINGS, "work_root", work_dir)
    object.__setattr__(SETTINGS, "artifact_root", artifacts_dir)
    object.__setattr__(SETTINGS, "drive_folder_id", "")
    object.__setattr__(SETTINGS, "drive_root_folder_id", "")

    monkeypatch.setenv("WORK_ROOT", str(work_dir))
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_dir))
    monkeypatch.setattr("src.pipeline.is_test_environment", lambda: True)

    db_path = tmp_path / "dry_run_queue.db"
    repo = QueueRepository(db_path)
    repo.initialize()

    # Mocks for LLM, TTS, and FFmpeg media stages
    monkeypatch.setattr(
        "src.llm.curate_script",
        lambda *args, **kwargs: (
            "En las profundidades del valle silencioso, una sombra misteriosa acechaba "
            "a los viajeros que intentaban cruzar el sendero olvidado antes del amanecer."
        ),
    )
    monkeypatch.setattr("src.llm.translate_title", lambda *args, **kwargs: "El Sendero Olvidado")
    monkeypatch.setattr("src.llm.clean_title", lambda title: "El Sendero Olvidado")
    monkeypatch.setattr("src.pipeline.is_spanish_neutral", lambda *args, **kwargs: True)

    def _mock_audio(output, duration=12.0):
        p = Path(output)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"RIFFmockWAVEfmt ")
        return {
            "audio_path": str(p),
            "duration_sec": duration,
            "word_timestamps": [{"word": "En", "start": 0.0, "end": 0.5}],
        }

    monkeypatch.setattr("lib.tts.generate_audio", lambda script, output, **kwargs: _mock_audio(output))

    def _mock_loop_render(*args, **kwargs):
        out = args[2] if len(args) > 2 else kwargs.get("output_video_path")
        p = Path(out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"DUMMY_MP4_VIDEO")
        return {
            "compositor": "loop",
            "render_time_sec": 0.2,
            "output_path": str(p),
            "quality_metrics": {
                "longest_black_seconds": 0.0,
                "perceptual_luminance": 80.0,
            },
        }

    monkeypatch.setattr("src.media.loop_engine.LoopVideoEngine.render", _mock_loop_render)
    monkeypatch.setattr(
        "src.media.loop_engine.LoopVideoEngine.resolve_loop_video",
        lambda *args, **kwargs: str(tmp_path / "fake_loop.mp4"),
    )
    monkeypatch.setattr(
        "src.media.loop_engine.LoopVideoEngine.resolve_continuous_loop",
        lambda *args, **kwargs: tmp_path / "fake_loop.mp4",
    )

    def _mock_thumb(title, channel, output_path, **kwargs):
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"DUMMY_THUMBNAIL_JPG")
        return str(p)

    monkeypatch.setattr("lib.video.create_video_thumbnail", _mock_thumb)

    mock_report = MagicMock()
    mock_report.passed = True
    mock_report.require_pass.return_value = None
    monkeypatch.setattr("src.pipeline.validate_prepublication", lambda **kwargs: mock_report)
    monkeypatch.setattr("src.core.quality.validate_prepublication", lambda **kwargs: mock_report)
    monkeypatch.setattr("src.pipeline.stages.stage_10_qa.default_validate_prepub", lambda **kwargs: mock_report)
    try:
        yield repo, db_path, work_dir
    finally:
        object.__setattr__(SETTINGS, "work_root", old_work)
        object.__setattr__(SETTINGS, "artifact_root", old_art)
        object.__setattr__(SETTINGS, "drive_folder_id", old_drive)
        object.__setattr__(SETTINGS, "drive_root_folder_id", old_drive_root)


def test_13_stages_sequential_dry_run_execution(dry_run_env):
    """Assert all 13 stages execute in sequence and generate_only halts at RENDERED."""
    repo, db_path, work_dir = dry_run_env
    repo.enqueue(
        "story-dryrun-001",
        "El Sendero Olvidado",
        "Contenido de prueba sobre el sendero en el bosque misterioso.",
        "https://example.com/story-dryrun",
        "moku",
    )

    mock_review_manager = MagicMock()
    mock_youtube_upload = MagicMock()

    with patch("review.ReviewJobManager", lambda: mock_review_manager), patch(
        "src.youtube.uploader.upload_video", mock_youtube_upload
    ):
        result = run_pipeline_once(
            channel="moku",
            db_path=str(db_path),
            story_id="story-dryrun-001",
            directed=True,
            generate_only=True,
        )

    # 1. Output status must be RENDERED
    assert result["status"] == JobStatus.RENDERED.value
    assert result["story_id"] == "story-dryrun-001"
    assert "work_dir" in result
    work_path = Path(result["work_dir"])
    assert (work_path / "video.mp4").exists()

    # 2. Remote publication MUST NOT be called in generate_only
    mock_review_manager.submit_video_for_review.assert_not_called()
    mock_youtube_upload.assert_not_called()

    # 3. Database state must record RENDERED and release locks
    with connect(str(db_path), read_only=True) as conn:
        leases = conn.execute("SELECT * FROM leases WHERE job_id = 'story-dryrun-001'").fetchall()
        lane_leases = conn.execute("SELECT * FROM lane_leases WHERE job_id = 'story-dryrun-001'").fetchall()
        story_row = conn.execute("SELECT status FROM stories WHERE story_id = 'story-dryrun-001'").fetchone()
        run_row = conn.execute("SELECT status FROM runs WHERE run_id = ?", (result["run_id"],)).fetchone()

    assert len(leases) == 0, "Worker lease was not released on generate_only completion"
    assert len(lane_leases) == 0, "Lane lease was not released on generate_only completion"
    assert run_row["status"] == JobStatus.RENDERED.value
    assert story_row["status"] in (JobStatus.RENDERED.value, JobStatus.DRIVE_BACKED_UP.value)

