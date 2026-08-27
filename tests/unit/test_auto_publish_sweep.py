from unittest.mock import MagicMock, patch

from src.telegram.approval import (
    _cutoff_time,
    _run_sweep,
    get_expired_pending_videos,
    update_video_status,
)


class FakeReviewStore:
    """Duck-typed db_conn exposing the review store contract used by approval.py."""

    def __init__(self, videos):
        self.videos = videos

    def get_expired_pending_videos(self, cutoff_time=None):
        return list(self.videos)

    def update_video_status(self, video_id, status="auto_published"):
        self.updated = getattr(self, "updated", [])
        self.updated.append((video_id, status))


SAMPLE_VIDEO = {
    "id": "job-1",
    "job_id": "job-1",
    "title": "Historia",
    "version": 2,
    "channel": "moku",
}


def test_cutoff_time_is_in_the_past():
    cutoff = _cutoff_time(6 * 3600)
    from datetime import datetime, timezone

    assert cutoff < datetime.now(timezone.utc)
    assert cutoff.tzinfo is not None


def test_get_expired_pending_videos_uses_provided_store():
    store = FakeReviewStore([SAMPLE_VIDEO])
    videos = get_expired_pending_videos(cutoff_time=_cutoff_time(3600), db_conn=store)
    assert len(videos) == 1
    assert videos[0]["job_id"] == "job-1"
    assert videos[0]["version"] == 2


def test_get_expired_pending_videos_empty_store():
    store = FakeReviewStore([])
    videos = get_expired_pending_videos(cutoff_time=_cutoff_time(3600), db_conn=store)
    assert videos == []


def test_update_video_status_delegates_to_provided_store():
    store = FakeReviewStore([])
    # El estado ilegal 'auto_published' se normaliza a PUBLISHED.
    assert update_video_status("job-1", status="auto_published", db_conn=store) is True
    assert ("job-1", "PUBLISHED") in store.updated
    assert update_video_status("job-1", status="RETRYABLE_FAILED", db_conn=store) is True
    assert ("job-1", "RETRYABLE_FAILED") in store.updated


def test_sweep_publishes_expired_and_marks_published():
    """Auto-publication lands in the canonical PUBLISHED state, never 'auto_published'."""
    store = FakeReviewStore([SAMPLE_VIDEO])
    with patch("src.telegram.approval._trigger_youtube_upload_sync", return_value={"ok": True}) as mock_publish:
        published = _run_sweep(3600, db_conn=store)
    assert published == ["job-1"]
    mock_publish.assert_called_once()
    assert ("job-1", "PUBLISHED") in store.updated


def test_sweep_skips_failed_publishes():
    store = FakeReviewStore([SAMPLE_VIDEO])
    with patch("src.telegram.approval._trigger_youtube_upload_sync", return_value={"ok": False, "error": "quota"}):
        published = _run_sweep(3600, db_conn=store)
    assert published == []
    assert not hasattr(store, "updated")


def test_sweep_is_empty_when_nothing_expired():
    store = FakeReviewStore([])
    with patch("src.telegram.approval._trigger_youtube_upload_sync") as mock_publish:
        published = _run_sweep(3600, db_conn=store)
    assert published == []
    mock_publish.assert_not_called()


def test_sweep_continues_after_one_video_raises():
    store = FakeReviewStore([SAMPLE_VIDEO, {**SAMPLE_VIDEO, "id": "job-2", "job_id": "job-2"}])
    results = {"job-1": {"ok": True}, "job-2": {"ok": True}}

    def fake_publish(video):
        v_id = str(video.get("id") or video.get("job_id"))
        if v_id == "job-1":
            raise RuntimeError("transient")
        return results[v_id]

    with patch("src.telegram.approval._trigger_youtube_upload_sync", side_effect=fake_publish):
        published = _run_sweep(3600, db_conn=store)
    assert published == ["job-2"]
    assert ("job-2", "PUBLISHED") in store.updated
