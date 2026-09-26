import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.config import SETTINGS
from src.core.repository import QueueRepository
from src.pipeline import run_pipeline_once


def _render_fixture(monkeypatch, tmp_path):
    repository = QueueRepository(tmp_path / "queue.db")
    repository.initialize()
    repository.enqueue("review-job", "SCP-173: La Escultura", "Contenido de prueba", "https://example.invalid", "horror")
    object.__setattr__(SETTINGS, "work_root", tmp_path / "work")
    object.__setattr__(SETTINGS, "drive_folder_id", "test_drive_fld")
    monkeypatch.setattr("src.llm.curate_script", lambda *args, **kwargs: "Historia de prueba")
    monkeypatch.setattr("src.llm.translate_title", lambda *args, **kwargs: "Titulo")
    monkeypatch.setattr("src.pipeline.is_spanish_neutral", lambda *args, **kwargs: True)
    monkeypatch.setattr("lib.tts.generate_audio", lambda script, output, **kwargs: _audio(output))
    monkeypatch.setattr("lib.subtitles.create_subtitles", lambda timestamps, output, **kwargs: _text(output))
    def _mock_loop_render(*args, **kwargs):
        # Bound method: args = (self, manifest_path, output_video_path, ...)
        out = args[2] if len(args) > 2 else kwargs.get("output_video_path")
        return _video(out)

    monkeypatch.setattr("src.media.loop_engine.LoopVideoEngine.render", _mock_loop_render)
    monkeypatch.setattr("src.media.loop_engine.LoopVideoEngine.resolve_loop_video", lambda *args, **kwargs: str(tmp_path / "fake_loop.mp4"))
    monkeypatch.setattr("src.media.loop_engine.LoopVideoEngine.resolve_continuous_loop", lambda *args, **kwargs: tmp_path / "fake_loop.mp4")
    monkeypatch.setattr("lib.video.create_video_thumbnail", lambda *args, **kwargs: _image(args[2]))
    manager = MagicMock()
    monkeypatch.setattr("src.asset_manager.get_asset_manager", lambda: _assets(tmp_path))
    monkeypatch.setattr("src.pipeline.validate_prepublication", lambda **kwargs: _report())
    monkeypatch.setattr("src.agents.video_qa.enforce_multimodal_qa_gate", lambda *args, **kwargs: {"overall_pass": True})
    return repository, manager


def _audio(output):
    Path(output).write_bytes(b"wav")
    return {"duration_sec": 2.0, "word_timestamps": [{"word": "hola", "start": 0.0, "end": 2.0}]}


def _text(output):
    Path(output).write_text("subtitles", encoding="utf-8")


def _video(output):
    Path(output).write_bytes(b"mp4")


def _image(output):
    Path(output).write_bytes(b"jpg")


def _assets(tmp_path):
    img = tmp_path / "bg.jpg"
    if not img.exists():
        img.write_bytes(b"image")
    return SimpleNamespace(
        get_background=lambda **kwargs: str(img),
        get_background_sequence=lambda count, **kwargs: [str(img)] * count,
        get_music=lambda **kwargs: "",
        get_ambient=lambda **kwargs: "",
        resolve_or_create_background_audio=lambda **kwargs: "",
    )


def _report():
    report = MagicMock()
    report.require_pass.return_value = None
    return report


def test_pending_review_never_calls_drive_or_youtube(monkeypatch, tmp_path):
    repository, manager = _render_fixture(monkeypatch, tmp_path)
    monkeypatch.setenv("TEST_MODE", "0")
    monkeypatch.setenv("AUTO_APPROVE", "0")
    monkeypatch.setattr("src.pipeline.is_test_environment", lambda: False)
    manager.submit_video_for_review.return_value = SimpleNamespace(
        status="PENDING_REVIEW", version=1, delivery_error=None
    )
    monkeypatch.setattr("review.ReviewJobManager", lambda: manager)
    drive_proof = SimpleNamespace(
        file_id="drive-123", name="vid.mp4", size_bytes=100, folder_id="fld", exists=True
    )
    drive = MagicMock(return_value=drive_proof)
    youtube = MagicMock()
    monkeypatch.setattr("src.drive.upload_to_drive_verified", drive)
    monkeypatch.setattr("src.youtube.uploader.upload_video", youtube)

    result = run_pipeline_once(
        channel="horror", db_path=str(repository.db_path), story_id="review-job"
    )

    assert result["status"] == "PENDING_REVIEW", result
    # Drive was called to store the video and pass the link to Telegram review
    drive.assert_called_once()
    assert result.get("drive_url") == "https://drive.google.com/file/d/drive-123/view"
    # YouTube publish was not called because human review is pending
    youtube.assert_not_called()


def test_auto_approve_delivers_to_telegram_and_publishes(monkeypatch, tmp_path):
    repository, manager = _render_fixture(monkeypatch, tmp_path)
    monkeypatch.setenv("TEST_MODE", "0")
    monkeypatch.setenv("AUTO_APPROVE", "1")
    monkeypatch.setattr("src.pipeline.is_test_environment", lambda: False)

    job_mock = SimpleNamespace(status="PENDING_REVIEW", version=1, delivery_error=None)
    approved_mock = SimpleNamespace(status="APPROVED", version=1, delivery_error=None)
    manager.submit_video_for_review.return_value = job_mock
    manager.code_approve.return_value = approved_mock
    monkeypatch.setattr("review.ReviewJobManager", lambda: manager)

    drive_proof = SimpleNamespace(
        file_id="drive-123", name="vid.mp4", size_bytes=100, folder_id="fld", exists=True
    )
    drive = MagicMock(return_value=drive_proof)
    def mock_upload(*args, **kwargs):
        vid = "yt-test-id"
        return {
            "status": "PUBLISHED",
            "video_id": vid,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "method": "api",
            "channel": "horror",
            "visibility": "public",
            "thumbnail_confirmed": True,
            "verified": True,
            "title": args[1] if len(args) > 1 else kwargs.get("title", "Titulo"),
            "description": args[2] if len(args) > 2 else kwargs.get("description", "Descripcion"),
        }
    upload_mock = MagicMock(side_effect=mock_upload)
    monkeypatch.setattr("src.drive.upload_to_drive_verified", drive)
    monkeypatch.setattr("src.youtube.uploader.upload_video", upload_mock)

    result = run_pipeline_once(
        channel="horror", db_path=str(repository.db_path), story_id="review-job"
    )

    # 1. Video MUST be delivered to Telegram
    manager.submit_video_for_review.assert_called_once()
    # 2. Video MUST be approved
    manager.code_approve.assert_called_once()
    # 3. Video MUST be published to YouTube
    upload_mock.assert_called_once()
    assert result["status"] == "PUBLISHED"


def test_generate_only_stops_at_rendered_without_remote_calls(monkeypatch, tmp_path):
    repository, manager = _render_fixture(monkeypatch, tmp_path)
    submit = MagicMock()
    drive_proof = SimpleNamespace(
        file_id="drive-123", name="vid.mp4", size_bytes=100, folder_id="fld", exists=True
    )
    drive = MagicMock(return_value=drive_proof)
    youtube = MagicMock()
    monkeypatch.setattr("review.ReviewJobManager.submit_video_for_review", submit)
    monkeypatch.setattr("src.drive.upload_to_drive_verified", drive)
    monkeypatch.setattr("src.youtube.uploader.upload_video", youtube)

    result = run_pipeline_once(
        channel="horror", db_path=str(repository.db_path),
        generate_only=True, story_id="review-job"
    )

    assert result["status"] == "RENDERED"
    submit.assert_not_called()
    youtube.assert_not_called()


def test_adapter_rejects_missing_job_identity(monkeypatch, tmp_path):
    from src import review_publication_adapter as adapter

    with pytest.raises(ValueError, match="job_id, version and original_video_path"):
        adapter.publish({"original_video_path": str(tmp_path / "video.mp4")})


def test_adapter_orders_drive_before_youtube_and_passes_claim(monkeypatch, tmp_path):
    from src import review_publication_adapter as adapter

    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    thumbnail = tmp_path / "thumbnail.jpg"
    thumbnail.write_bytes(b"cover")
    events = []
    monkeypatch.setattr(adapter, "_verify_core_claim", lambda *args: events.append("gate"))
    monkeypatch.setattr(adapter, "SETTINGS", SimpleNamespace(
        drive_folder_id="video-folder", drive_key_path=tmp_path / "drive-key.json",
        drive_approved_video_folder_id="video-folder",
        drive_approved_cover_folder_id="cover-folder",
        drive_metadata_folder_id="metadata-folder",
    ))
    def upload_drive(path, **kwargs):
        if kwargs["folder_id"] == "metadata-folder":
            manifest = json.loads(Path(path).read_text(encoding="utf-8"))
            assert manifest["job_id"] == "job-1"
            assert manifest["version"] == 2
            assert manifest["project"] == "YTShort"
            assert manifest["original_path_basename"] == "video.mp4"
            assert manifest["upload_timestamp"]
            assert "token" not in json.dumps(manifest).lower()
        events.append(("drive", kwargs["folder_id"], kwargs["idempotency_key"]))
        return SimpleNamespace(file_id="drive-id", name="uploaded", size_bytes=5, folder_id=kwargs["folder_id"], exists=True)

    monkeypatch.setattr(adapter, "upload_to_drive_verified", upload_drive)
    monkeypatch.setattr(
        adapter,
        "upload_video",
        lambda *args, **kwargs: events.append(("youtube", kwargs["job_id"], kwargs["version"])) or
        {"status": "PUBLISHED", "verified": True, "video_id": "yt-id", "url": "https://youtu.be/id"},
    )

    result = adapter.publish({
        "job_id": "job-1", "version": 2, "original_video_path": str(video),
        "thumbnail_path": str(thumbnail),
        "channel": "horror", "title": "Titulo", "description": "Descripcion",
    })

    assert events == [
        "gate",
        ("drive", "video-folder", "YTShort:horror:job-1"),
        ("drive", "cover-folder", "YTShort:horror:job-1:cover"),
        ("drive", "metadata-folder", "YTShort:horror:job-1:metadata"),
        ("youtube", "job-1", 2),
    ]
    assert result["youtube_result"]["video_id"] == "yt-id"
    assert result["drive_backup"]["status"] == "verified"
    assert set(result["drive_backup"]) == {"status", "video", "cover", "metadata"}


def test_uploader_rejects_pending_claim(monkeypatch, tmp_path):
    from src import youtube_uploader

    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    monkeypatch.delenv("SKIP_PUBLICATION_GATE_FOR_TESTS", raising=False)
    monkeypatch.setattr(youtube_uploader, "is_test_environment", lambda: False)

    class PendingStore:
        def get_job(self, job_id, version):
            return SimpleNamespace(
                status="PENDING_REVIEW", original_video_path=str(video)
            )

    monkeypatch.setattr("review.ReviewStateStore", lambda *args, **kwargs: PendingStore())
    with pytest.raises(RuntimeError, match="not approved"):
        youtube_uploader.upload_video(
            str(video), "Titulo", "Descripcion", job_id="job-1", version=1
        )
