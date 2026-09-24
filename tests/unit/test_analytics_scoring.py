"""Unit tests for Empirical Scoring & Music Attribution (src/analytics/scoring.py)."""
import tempfile
import pytest

from src.analytics.scoring import (
    calculate_empirical_score,
    classify_comment_level,
    get_top_performing_music_tracks,
    get_video_by_sha256,
    sync_and_score_channel_publications,
)
from src.core.inventory import record_published_inventory


def test_calculate_empirical_score_high_engagement():
    # 5,000 views, 300 likes, 40 comments, 85% retention, 48 hours age
    score = calculate_empirical_score(
        views=5000,
        likes=300,
        comments=40,
        retention_rate_pct=85.0,
        age_hours=48.0,
    )
    assert 70.0 <= score <= 100.0


def test_calculate_empirical_score_zero_division_resilience():
    score = calculate_empirical_score(
        views=0,
        likes=0,
        comments=0,
        retention_rate_pct=0.0,
        age_hours=0.0,
    )
    assert score == 0.0


def test_calculate_empirical_score_moderate_engagement():
    score = calculate_empirical_score(
        views=500,
        likes=15,
        comments=2,
        retention_rate_pct=60.0,
        age_hours=24.0,
    )
    assert 25.0 <= score <= 60.0


def test_music_track_attribution_and_leaderboard():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = tmp.name

        # Record 3 videos with the same music track
        record_published_inventory(
            db_path=db_path,
            run_id="run-1",
            story_id="story-1",
            video_id="vid-1",
            url="https://youtube.com/watch?v=vid-1",
            channel="moku",
            title="Video 1",
            description="Desc 1",
            actual_success_score=60.0,
            used_resources={"music": "assets/audio/music/dark_ambient_01.mp3"},
        )
        record_published_inventory(
            db_path=db_path,
            run_id="run-2",
            story_id="story-2",
            video_id="vid-2",
            url="https://youtube.com/watch?v=vid-2",
            channel="moku",
            title="Video 2",
            description="Desc 2",
            actual_success_score=80.0,
            used_resources={"music": "assets/audio/music/dark_ambient_01.mp3"},
        )
        record_published_inventory(
            db_path=db_path,
            run_id="run-3",
            story_id="story-3",
            video_id="vid-3",
            url="https://youtube.com/watch?v=vid-3",
            channel="moku",
            title="Video 3",
            description="Desc 3",
            actual_success_score=70.0,
            used_resources={"music": "assets/audio/music/dark_ambient_01.mp3"},
        )
        # Record another video with a different music track
        record_published_inventory(
            db_path=db_path,
            run_id="run-4",
            story_id="story-4",
            video_id="vid-4",
            url="https://youtube.com/watch?v=vid-4",
            channel="moku",
            title="Video 4",
            description="Desc 4",
            actual_success_score=40.0,
            used_resources={"music": "assets/audio/music/upbeat_02.mp3"},
        )

        leaderboard = get_top_performing_music_tracks(channel="moku", db_path=db_path)
        assert len(leaderboard) == 2
        # First entry should be dark_ambient_01 with avg score 70.0
        assert leaderboard[0]["music_track"] == "assets/audio/music/dark_ambient_01.mp3"
        assert leaderboard[0]["usage_count"] == 3
        assert leaderboard[0]["avg_score"] == 70.0

        # Second entry
        assert leaderboard[1]["music_track"] == "assets/audio/music/upbeat_02.mp3"
        assert leaderboard[1]["usage_count"] == 1
        assert leaderboard[1]["avg_score"] == 40.0


def test_get_video_by_sha256():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = tmp.name
        sha = "a" * 64
        record_published_inventory(
            db_path=db_path,
            run_id="run-sha",
            story_id="story-sha",
            video_id="vid-sha",
            url="https://youtube.com/watch?v=vid-sha",
            channel="moku",
            title="SHA Video",
            description="SHA Desc",
            video_sha256=sha,
            actual_success_score=95.0,
        )

        found = get_video_by_sha256(video_sha256=sha, db_path=db_path)
        assert found is not None
        assert found.video_id == "vid-sha"
        assert found.actual_success_score == 95.0

        missing = get_video_by_sha256(video_sha256="b" * 64, db_path=db_path)
        assert missing is None


def test_sync_and_score_channel_publications_live_no_database_lock():
    from unittest.mock import patch, MagicMock
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = tmp.name
        record_published_inventory(
            db_path=db_path,
            run_id="run-lock-test",
            story_id="story-lock-test",
            video_id="vid-lock-test",
            url="https://youtube.com/watch?v=vid-lock-test",
            channel="moku",
            title="Lock Test Video",
            description="Testing concurrency",
            actual_success_score=10.0,
        )

        with patch("src.analytics.scoring.YouTubeAnalyticsSyncer.fetch_video_statistics") as mock_stats:
            mock_stats.return_value = {
                "view_count": 2500,
                "like_count": 150,
                "comment_count": 20,
                "retention_rate_pct": 75.0,
            }
            res = sync_and_score_channel_publications(
                channel="moku",
                db_path=db_path,
                dry_run=False,
            )

            assert res["updated_count"] == 1
            assert len(res["items"]) == 1
            assert res["items"][0]["video_id"] == "vid-lock-test"
            assert res["items"][0]["score"] > 50.0


def test_classify_comment_level():
    # 0 comments -> "none"
    assert classify_comment_level(0, 1000) == "none"
    assert classify_comment_level(0, 0) == "none"

    # low comments (< 6 and ratio < 3%)
    assert classify_comment_level(2, 1000) == "low"
    assert classify_comment_level(5, 500) == "low"

    # moderate comments (6-30 comments, >= 0.5% ratio)
    assert classify_comment_level(10, 1000) == "moderate"  # 1% ratio
    assert classify_comment_level(6, 0) == "moderate"

    # viral comments (> 30 comments or > 3% ratio)
    assert classify_comment_level(35, 2000) == "viral"
    assert classify_comment_level(5, 100) == "viral"  # 5% ratio > 3%

