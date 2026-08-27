"""Unit tests for YouTubeAnalyticsSyncer."""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from src.core.repository import QueueRepository
from src.youtube.analytics import YouTubeAnalyticsSyncer

def test_sync_video_metrics_with_mock_client(tmp_path):
    db_path = tmp_path / "test_queue.db"
    repo = QueueRepository(db_path)
    repo.initialize()

    story_id = "story_yt_001"
    repo.enqueue(story_id=story_id, title="YT Story", content="Content", url="https://reddit.com/r/yt1", channel="moku")

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
            channel="moku",
            interval="24h",
        )
        assert ok is True

    snapshots = repo.get_analytics_snapshots(story_id=story_id)
    assert len(snapshots) == 1
    assert snapshots[0]["video_id"] == "test_vid_xyz"
    assert snapshots[0]["view_count"] == 4500
    assert snapshots[0]["like_count"] == 320
    assert snapshots[0]["snapshot_interval"] == "24h"
