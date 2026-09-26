"""
Unit tests for YouTubeAnalyticsSyncer and YouTube video metadata & ROM analytics module.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch
import pytest

from src.core.domain import CanonicalChannel
from src.core.repository import QueueRepository
from src.youtube.analytics import (
    YouTubeAnalyticsSyncer,
    calculate_engagement_rate,
    calculate_rom_score,
    estimate_retention_metrics,
    generate_mock_statistics,
    get_video_snapshot_history,
    parse_iso8601_duration,
    sync_video_metrics,
)


# ---------------------------------------------------------------------------
# Duration & Retention Unit Tests
# ---------------------------------------------------------------------------


def test_parse_iso8601_duration():
    """Verify ISO 8601 duration parsing across standard formats and edge cases."""
    assert parse_iso8601_duration("PT59S") == 59.0
    assert parse_iso8601_duration("PT1M30S") == 90.0
    assert parse_iso8601_duration("PT2M") == 120.0
    assert parse_iso8601_duration("PT1H2M3S") == 3723.0
    assert parse_iso8601_duration("P1DT2H3M4S") == 93784.0
    assert parse_iso8601_duration("PT45.5S") == 45.5

    # Edge cases
    assert parse_iso8601_duration(None) == 0.0
    assert parse_iso8601_duration("") == 0.0
    assert parse_iso8601_duration("invalid_str") == 0.0
    assert parse_iso8601_duration("   ") == 0.0


def test_estimate_retention_metrics():
    """Verify retention metric estimation for short-form and long-form video."""
    # Shorts format (<= 60s)
    avg_dur, ret_pct = estimate_retention_metrics(
        duration_sec=50.0,
        view_count=1000,
        like_count=50,
        comment_count=10,
    )
    assert 75.0 <= ret_pct <= 98.0
    assert avg_dur == round(50.0 * (ret_pct / 100.0), 2)

    # Longform format (> 60s)
    avg_dur_long, ret_pct_long = estimate_retention_metrics(
        duration_sec=300.0,
        view_count=5000,
        like_count=100,
        comment_count=20,
    )
    assert 50.0 <= ret_pct_long <= 98.0
    assert avg_dur_long == round(300.0 * (ret_pct_long / 100.0), 2)

    # Zero or negative duration
    assert estimate_retention_metrics(0.0, 100, 5, 1) == (0.0, 0.0)
    assert estimate_retention_metrics(-10.0, 100, 5, 1) == (0.0, 0.0)


# ---------------------------------------------------------------------------
# Engagement Rate & ROM Score Unit Tests
# ---------------------------------------------------------------------------


def test_calculate_engagement_rate():
    """Verify engagement rate formula: (likes + comments) / views."""
    # Standard values
    rate = calculate_engagement_rate(view_count=1000, like_count=50, comment_count=10)
    assert rate == 0.06

    # Zero views
    assert calculate_engagement_rate(view_count=0, like_count=10, comment_count=5) == 0.0
    assert calculate_engagement_rate(view_count=-50, like_count=10, comment_count=5) == 0.0

    # Negative likes or comments clamped to 0
    assert calculate_engagement_rate(view_count=100, like_count=-10, comment_count=5) == 0.05


def test_calculate_rom_score():
    """Verify Return On Media (ROM) composite score calculation."""
    # Standard baseline: 1000 views, 50 likes, 10 comments, 75% retention, cost 1.0
    # Media value = 1000*1 + 50*10 + 10*25 = 1750. Retention multiplier = 1.0 + 0.75 = 1.75
    # ROM = 1750 * 1.75 / 1.0 = 3062.5
    rom = calculate_rom_score(
        view_count=1000,
        like_count=50,
        comment_count=10,
        avg_view_duration_sec=45.0,
        retention_rate_pct=75.0,
        production_cost=1.0,
    )
    assert rom == 3062.5

    # Zero metrics -> 0.0
    assert calculate_rom_score(0, 0, 0) == 0.0
    assert calculate_rom_score(-10, -5, -2) == 0.0

    # Zero or tiny cost does not raise ZeroDivisionError
    rom_zero_cost = calculate_rom_score(
        view_count=500,
        like_count=20,
        comment_count=5,
        production_cost=0.0,
    )
    assert rom_zero_cost > 0.0


# ---------------------------------------------------------------------------
# Deterministic Mock Generator Tests
# ---------------------------------------------------------------------------


def test_generate_mock_statistics():
    """Verify deterministic mock generator output consistency and reproducibility."""
    stats_a1 = generate_mock_statistics("vid_abc_123")
    stats_a2 = generate_mock_statistics("vid_abc_123")
    stats_b = generate_mock_statistics("vid_xyz_789")

    # Identical video ID yields identical mock stats
    assert stats_a1 == stats_a2
    assert stats_a1["video_id"] == "vid_abc_123"
    assert stats_a1["view_count"] > 0
    assert stats_a1["like_count"] > 0
    assert stats_a1["comment_count"] > 0
    assert stats_a1["avg_view_duration_sec"] > 0.0
    assert stats_a1["retention_rate_pct"] > 0.0
    assert stats_a1["engagement_rate"] > 0.0
    assert stats_a1["rom_score"] > 0.0

    # Different video ID yields different mock stats
    assert stats_a1["view_count"] != stats_b["view_count"] or stats_a1["like_count"] != stats_b["like_count"]

    # Baseline only mode
    baseline = generate_mock_statistics("vid_test", baseline_only=True)
    assert baseline["view_count"] == 0
    assert baseline["like_count"] == 0
    assert baseline["comment_count"] == 0
    assert baseline["rom_score"] == 0.0


# ---------------------------------------------------------------------------
# YouTube API Response Parsing & Fallbacks
# ---------------------------------------------------------------------------


def test_fetch_video_statistics_real_api_parsing():
    """Verify parsing of real YouTube Data API v3 JSON response."""
    syncer = YouTubeAnalyticsSyncer(api_key="AIzaSyDummyTestKey")

    mock_api_response = {
        "kind": "youtube#videoListResponse",
        "items": [
            {
                "id": "test_video_123",
                "snippet": {
                    "title": "SCP-096 Documented",
                    "channelTitle": "Moku Stories",
                },
                "contentDetails": {
                    "duration": "PT52S",
                },
                "statistics": {
                    "viewCount": "8450",
                    "likeCount": "620",
                    "commentCount": "78",
                },
            }
        ],
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_api_response

    with patch("requests.get", return_value=mock_resp) as mock_get:
        stats = syncer.fetch_video_statistics("test_video_123")
        assert mock_get.called
        assert stats["video_id"] == "test_video_123"
        assert stats["view_count"] == 8450
        assert stats["like_count"] == 620
        assert stats["comment_count"] == 78
        assert stats["duration_sec"] == 52.0
        assert stats["retention_rate_pct"] >= 75.0
        assert stats["engagement_rate"] == round((620 + 78) / 8450, 6)
        assert stats["rom_score"] > 0.0


def test_fetch_video_statistics_empty_items():
    """Verify graceful handling when video is not found or private (empty items)."""
    syncer = YouTubeAnalyticsSyncer(api_key="AIzaSyDummyTestKey")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"kind": "youtube#videoListResponse", "items": []}

    with patch("requests.get", return_value=mock_resp):
        stats = syncer.fetch_video_statistics("not_found_vid")
        assert stats["view_count"] == 0
        assert stats["like_count"] == 0
        assert stats["comment_count"] == 0


def test_fetch_video_statistics_api_error_fallback():
    """Verify fallback to deterministic mock generator on non-200 HTTP status."""
    syncer = YouTubeAnalyticsSyncer(api_key="AIzaSyDummyTestKey")
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = "Quota exceeded"

    with patch("requests.get", return_value=mock_resp):
        stats = syncer.fetch_video_statistics("vid_error_fallback")
        assert stats["video_id"] == "vid_error_fallback"
        assert stats["view_count"] > 0
        assert stats["rom_score"] > 0.0


def test_fetch_video_statistics_network_exception_fallback():
    """Verify fallback to deterministic mock generator when network raises an exception."""
    syncer = YouTubeAnalyticsSyncer(api_key="AIzaSyDummyTestKey")

    with patch("requests.get", side_effect=ConnectionError("DNS lookup failure")):
        stats = syncer.fetch_video_statistics("vid_net_exc")
        assert stats["video_id"] == "vid_net_exc"
        assert stats["view_count"] > 0


def test_fetch_video_statistics_dry_run_mode():
    """Verify dry_run mode bypasses network calls and uses deterministic mock generator."""
    syncer = YouTubeAnalyticsSyncer(api_key="AIzaSyDummyTestKey", dry_run=True)

    with patch("requests.get") as mock_get:
        stats = syncer.fetch_video_statistics("vid_dry_run")
        assert not mock_get.called
        assert stats["video_id"] == "vid_dry_run"
        assert stats["view_count"] > 0


def test_fetch_video_statistics_no_api_key():
    """Verify missing API key uses deterministic mock generator without error."""
    with patch.dict(os.environ, {}, clear=True):
        syncer = YouTubeAnalyticsSyncer()
        stats = syncer.fetch_video_statistics("vid_no_key")
        assert stats["video_id"] == "vid_no_key"
        assert stats["view_count"] > 0


# ---------------------------------------------------------------------------
# Database Persistence & Snapshot History Tests
# ---------------------------------------------------------------------------


def test_sync_video_metrics_with_mock_client(tmp_path):
    """Verify end-to-end sync_video_metrics recording a snapshot in SQLite repository."""
    db_path = tmp_path / "test_queue.db"
    repo = QueueRepository(db_path)
    repo.initialize()

    story_id = "story_yt_001"
    repo.enqueue(story_id=story_id, title="YT Story", content="Content", url="https://reddit.com/r/yt1", channel="horror")

    syncer = YouTubeAnalyticsSyncer(repository=repo)

    mock_stats = {
        "view_count": 4500,
        "like_count": 320,
        "comment_count": 45,
        "avg_view_duration_sec": 48.5,
        "retention_rate_pct": 78.2,
    }

    with patch.object(syncer, "fetch_video_statistics", return_value=mock_stats):
        ok = syncer.sync_video_metrics(
            video_id="test_vid_xyz",
            story_id=story_id,
            channel="horror",
            interval="24h",
        )
        assert ok is True

    snapshots = repo.get_analytics_snapshots(story_id=story_id)
    assert len(snapshots) == 1
    assert snapshots[0]["video_id"] == "test_vid_xyz"
    assert snapshots[0]["view_count"] == 4500
    assert snapshots[0]["like_count"] == 320
    assert snapshots[0]["snapshot_interval"] == "24h"


def test_chronological_snapshots_and_history_retrieval(tmp_path):
    """Verify multiple chronological snapshot recording and history retrieval helper."""
    db_path = tmp_path / "test_queue.db"
    repo = QueueRepository(db_path)
    repo.initialize()

    story_id = "story_yt_chrono"
    repo.enqueue(story_id=story_id, title="Chrono Story", content="Content", url="https://reddit.com/r/chrono", channel="horror")

    syncer = YouTubeAnalyticsSyncer(repository=repo)

    # Record 3 chronological snapshots (1h, 24h, 7d)
    stats_1h = {"view_count": 500, "like_count": 40, "comment_count": 8, "avg_view_duration_sec": 40.0, "retention_rate_pct": 70.0}
    stats_24h = {"view_count": 3200, "like_count": 280, "comment_count": 35, "avg_view_duration_sec": 44.0, "retention_rate_pct": 75.0}
    stats_7d = {"view_count": 12500, "like_count": 980, "comment_count": 120, "avg_view_duration_sec": 46.0, "retention_rate_pct": 78.0}

    with patch.object(syncer, "fetch_video_statistics", return_value=stats_1h):
        assert syncer.sync_video_metrics("vid_c1", story_id, "horror", interval="1h", recorded_at="2026-08-20T10:00:00Z") is True

    with patch.object(syncer, "fetch_video_statistics", return_value=stats_24h):
        assert syncer.sync_video_metrics("vid_c1", story_id, "horror", interval="24h", recorded_at="2026-08-21T10:00:00Z") is True

    with patch.object(syncer, "fetch_video_statistics", return_value=stats_7d):
        assert syncer.sync_video_metrics("vid_c1", story_id, "horror", interval="7d", recorded_at="2026-08-27T10:00:00Z") is True

    # Retrieve history via syncer method
    history_method = syncer.get_video_snapshot_history(story_id)
    assert len(history_method) == 3
    assert [s["snapshot_interval"] for s in history_method] == ["1h", "24h", "7d"]
    assert [s["view_count"] for s in history_method] == [500, 3200, 12500]

    # Retrieve history via top-level function
    history_func = get_video_snapshot_history(story_id, repository=repo)
    assert len(history_func) == 3
    assert history_func[0]["recorded_at"] == "2026-08-20T10:00:00Z"
    assert history_func[2]["recorded_at"] == "2026-08-27T10:00:00Z"


def test_top_level_sync_video_metrics_convenience_function(tmp_path):
    """Verify top-level sync_video_metrics convenience function."""
    db_path = tmp_path / "test_queue.db"
    repo = QueueRepository(db_path)
    repo.initialize()

    story_id = "story_top_level"
    repo.enqueue(story_id=story_id, title="Top Story", content="Content", url="https://reddit.com/r/top", channel="drama")

    ok = sync_video_metrics(
        video_id="vid_top_level",
        story_id=story_id,
        channel="drama",
        interval="12h",
        repository=repo,
        dry_run=True,
    )
    assert ok is True

    history = get_video_snapshot_history(story_id, repository=repo)
    assert len(history) == 1
    assert history[0]["channel"] == "drama"
    assert history[0]["snapshot_interval"] == "12h"
    assert history[0]["view_count"] > 0


def test_sync_video_metrics_foreign_key_resilience(tmp_path):
    """Verify sync_video_metrics handles database errors gracefully (e.g. non-existent story)."""
    db_path = tmp_path / "test_queue.db"
    repo = QueueRepository(db_path)
    repo.initialize()

    syncer = YouTubeAnalyticsSyncer(repository=repo, dry_run=True)

    # Attempting to record snapshot for non-existent story_id violates FOREIGN KEY constraint
    ok = syncer.sync_video_metrics(
        video_id="vid_orphan",
        story_id="non_existent_story_id",
        channel="horror",
        interval="24h",
    )
    assert ok is False

