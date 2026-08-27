import json
import os
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

from src import retention
from src.cleaner import clean_system_cache


def _run(tmp_path, *, active=False, run_id="run-1"):
    work = tmp_path / "work"
    run_dir = work / run_id
    run_dir.mkdir(parents=True)
    video = run_dir / "video.mp4"
    video.write_bytes(b"video")
    marker = run_dir / ".run.json"
    marker.write_text(
        json.dumps({"run_id": run_id, "active": active, "updated_at": 123}),
        encoding="utf-8",
    )
    return work, run_dir, video, marker


def test_valid_marker_is_marked_and_timestamp_is_preserved(tmp_path, monkeypatch):
    work, _, video, marker = _run(tmp_path)
    monkeypatch.setattr(retention, "SETTINGS", SimpleNamespace(work_root=work))
    assert retention.mark_run_retention_satisfied(
        video, published_id="yt-1", published_url="https://youtu.be/yt-1"
    )
    metadata = json.loads(marker.read_text(encoding="utf-8"))
    assert metadata["run_id"] == "run-1"
    assert metadata["active"] is False
    assert metadata["updated_at"] == 123
    assert metadata["retention_satisfied"] is True
    assert metadata["published_id"] == "yt-1"


def test_paths_outside_work_are_rejected(tmp_path, monkeypatch):
    work, _, _, _ = _run(tmp_path)
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"outside")
    monkeypatch.setattr(retention, "SETTINGS", SimpleNamespace(work_root=work))
    assert not retention.mark_run_retention_satisfied(outside)


def test_active_or_mismatched_marker_is_preserved(tmp_path, monkeypatch):
    work, _, video, marker = _run(tmp_path, active=True)
    monkeypatch.setattr(retention, "SETTINGS", SimpleNamespace(work_root=work))
    original = marker.read_text(encoding="utf-8")
    assert not retention.mark_run_retention_satisfied(video)
    assert marker.read_text(encoding="utf-8") == original
    marker.write_text(
        json.dumps({"run_id": "other", "active": False, "updated_at": 123}),
        encoding="utf-8",
    )
    original = marker.read_text(encoding="utf-8")
    assert not retention.mark_run_retention_satisfied(video)
    assert marker.read_text(encoding="utf-8") == original


def test_cleaner_waits_for_local_retention_seconds(tmp_path, monkeypatch):
    work, run_dir, _, marker = _run(tmp_path)
    marker.write_text(
        json.dumps({"run_id": run_dir.name, "active": False, "retention_satisfied": True}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "src.cleaner.SETTINGS",
        SimpleNamespace(work_root=work, artifact_root=tmp_path / "artifacts"),
    )
    monkeypatch.setenv("LOCAL_RETENTION_SECONDS", "60")
    os.utime(marker, (time.time(), time.time()))
    assert clean_system_cache()["deleted_dirs_count"] == 0
    assert run_dir.exists()
    old = time.time() - 61
    os.utime(marker, (old, old))
    assert clean_system_cache()["deleted_dirs_count"] == 1
    assert not run_dir.exists()


def test_adapter_marks_only_verified_youtube_result(monkeypatch, tmp_path):
    from src import review_publication_adapter as adapter

    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    monkeypatch.setattr(adapter, "_verify_core_claim", lambda *args: None)
    monkeypatch.setattr(adapter, "_backup_drive", lambda **kwargs: {"status": "verified"})
    mark = MagicMock(return_value=True)
    monkeypatch.setattr(adapter, "mark_run_retention_satisfied", mark)
    monkeypatch.setattr(
        adapter,
        "upload_video",
        lambda *args, **kwargs: {"status": "PUBLISHED", "verified": False, "video_id": "yt-1"},
    )
    published = adapter.publish(
        {"job_id": "job-1", "version": 1, "original_video_path": str(video)}
    )
    assert published["retention_satisfied"] is False
    mark.assert_not_called()

    monkeypatch.setattr(
        adapter,
        "upload_video",
        lambda *args, **kwargs: {
            "status": "PUBLISHED",
            "verified": True,
            "video_id": "yt-1",
            "url": "https://youtu.be/yt-1",
        },
    )
    published = adapter.publish(
        {"job_id": "job-1", "version": 1, "original_video_path": str(video)}
    )
    assert published["retention_satisfied"] is True
    mark.assert_called_once_with(
        str(video), published_id="yt-1", published_url="https://youtu.be/yt-1"
    )
