import tempfile
from unittest.mock import MagicMock
import pytest

from src.analytics.pruner import (
    classify_video_failure,
    mark_underperforming_candidates,
    purge_marked_videos,
)
from src.core.repository.migrations import connect, migrate_database


def test_classify_video_failure_empty_or_artifact():
    assert classify_video_failure("test", "horror", 0, 0, 50.0, 0.0) == "EMPTY_TITLE_ARTIFACT"
    assert classify_video_failure("video", "drama", 10, 0, 72.0, 5.0) == "EMPTY_TITLE_ARTIFACT"
    assert classify_video_failure("", "horror", 0, 0, 10.0, 0.0) == "EMPTY_TITLE_ARTIFACT"
    assert classify_video_failure("Untitled", "drama", 0, 0, 24.0, 0.0) == "EMPTY_TITLE_ARTIFACT"


def test_classify_video_failure_cross_contamination():
    # Drama title on horror channel
    horror_contaminated = "[RELATO DE TERROR] ¿Soy el malo por no prestar dinero a mi hermano? | Moku"
    assert classify_video_failure(horror_contaminated, "horror", 15, 0, 48.0, 10.0) == "CROSS_CONTAMINATED_TITLE"

    # Horror title on drama channel
    drama_contaminated = "SCP-173: La escultura viviente"
    assert classify_video_failure(drama_contaminated, "drama", 20, 0, 48.0, 15.0) == "CROSS_CONTAMINATED_TITLE"


def test_classify_video_failure_zero_engagement_stale():
    title = "[RELATO DE TERROR] La llamada de medianoche | Moku"
    # age >= 48h, views < 50, likes == 0
    assert classify_video_failure(title, "horror", 12, 0, 72.0, 8.5) == "ZERO_ENGAGEMENT_STALE"
    assert classify_video_failure(title, "horror", 0, 0, 50.0, 0.0) == "ZERO_ENGAGEMENT_STALE"


def test_classify_video_failure_underperforming_score():
    title = "[RELATO DE TERROR] El bosque de las sombras | Moku"
    # age >= 24h, views >= 50 (e.g. 100), likes = 2, score < 40.0 (e.g. 28.0)
    assert classify_video_failure(title, "horror", 120, 2, 36.0, 28.0) == "UNDERPERFORMING_SCORE"


def test_mark_and_purge_flow():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = tmp.name
        migrate_database(db_path)

        with connect(db_path) as conn:
            # Insert run
            conn.execute(
                "INSERT INTO runs (run_id, channel, mode, status, owner, started_at, heartbeat_at) "
                "VALUES ('run-01', 'horror', 'short', 'COMPLETED', 'test-owner', '2026-09-20T00:00:00Z', '2026-09-20T00:00:00Z')"
            )
            # Insert story
            conn.execute(
                "INSERT INTO stories (story_id, channel, title, content, url, status) "
                "VALUES ('story-01', 'horror', 'test', 'content', 'https://reddit.com/r/test', 'PUBLISHED')"
            )
            # Insert publication
            conn.execute(
                "INSERT INTO publications (run_id, story_id, provider, video_id, url, channel, visibility, title, description, thumbnail_confirmed, verified_at, actual_success_score, view_count, like_count) "
                "VALUES ('run-01', 'story-01', 'YOUTUBE', 'vid-test-01', 'https://youtu.be/vid-test-01', 'horror', 'public', 'test', 'desc', 1, '2026-09-20T00:00:00Z', 0.0, 0, 0)"
            )
            conn.commit()

        # Step 1: Mark for purge
        marked = mark_underperforming_candidates(channel="horror", db_path=db_path, min_score=40.0, grace_hours=24.0)
        assert len(marked) == 1
        assert marked[0]["video_id"] == "vid-test-01"
        assert marked[0]["failure_code"] == "EMPTY_TITLE_ARTIFACT"

        # Verify DB status is MARKED_FOR_PURGE
        with connect(db_path, read_only=True) as conn:
            row = conn.execute("SELECT status, failure_code FROM stories WHERE story_id = 'story-01'").fetchone()
            assert row["status"] == "MARKED_FOR_PURGE"
            assert row["failure_code"] == "EMPTY_TITLE_ARTIFACT"

        # Step 2: Purge marked videos
        mock_service = MagicMock()
        mock_delete = MagicMock()
        mock_service.videos.return_value.delete.return_value = mock_delete

        purge_res = purge_marked_videos(channel="horror", db_path=db_path, youtube_service=mock_service)
        assert purge_res["purged_count"] == 1
        assert purge_res["failed_count"] == 0
        mock_service.videos.return_value.delete.assert_called_once_with(id="vid-test-01")
        mock_delete.execute.assert_called_once()

        # Verify DB status is PURGED
        with connect(db_path, read_only=True) as conn:
            row = conn.execute("SELECT status FROM stories WHERE story_id = 'story-01'").fetchone()
            assert row["status"] == "PURGED"
