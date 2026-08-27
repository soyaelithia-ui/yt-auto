"""
src/analytics/youtube_analytics_syncer.py - Synchronizes YouTube engagement metrics to SQLite.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from src.core.domain import CanonicalChannel
from src.core.repository import QueueRepository
from src.log import get_logger

logger = get_logger("youtube_analytics_syncer")


class YouTubeAnalyticsSyncer:
    def __init__(self, repository: Optional[QueueRepository] = None, db_path: Optional[str] = None):
        self.repository = repository or QueueRepository(db_path or "data/shorts_queue.db")

    def fetch_video_statistics(self, video_id: str) -> Dict[str, Any]:
        """
        Fetches live statistics for a video via YouTube Data API v3.
        In test/dry-run mode without credentials, returns deterministic baseline metrics.
        """
        api_key = os.getenv("YOUTUBE_API_KEY")
        if not api_key:
            # Baseline simulation / fallback
            return {
                "view_count": 0,
                "like_count": 0,
                "comment_count": 0,
                "avg_view_duration_sec": 0.0,
                "retention_rate_pct": 0.0,
            }

        try:
            import requests
            url = "https://www.googleapis.com/youtube/v3/videos"
            params = {
                "part": "statistics,contentDetails",
                "id": video_id,
                "key": api_key,
            }
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
                if items:
                    stats = items[0].get("statistics", {})
                    return {
                        "view_count": int(stats.get("viewCount", 0)),
                        "like_count": int(stats.get("likeCount", 0)),
                        "comment_count": int(stats.get("commentCount", 0)),
                        "avg_view_duration_sec": 0.0,
                        "retention_rate_pct": 0.0,
                    }
        except Exception as exc:
            logger.warning("YouTube API metrics fetch failed for '%s': %s", video_id, exc)

        return {
            "view_count": 0,
            "like_count": 0,
            "comment_count": 0,
            "avg_view_duration_sec": 0.0,
            "retention_rate_pct": 0.0,
        }

    def sync_video_metrics(
        self,
        video_id: str,
        story_id: str,
        channel: str | CanonicalChannel,
        interval: str = "24h",
    ) -> bool:
        """
        Queries video statistics and stores an analytics snapshot row in the repository.
        """
        stats = self.fetch_video_statistics(video_id)
        ok = self.repository.record_analytics_snapshot(
            video_id=video_id,
            story_id=story_id,
            channel=channel,
            view_count=stats.get("view_count", 0),
            like_count=stats.get("like_count", 0),
            comment_count=stats.get("comment_count", 0),
            avg_view_duration_sec=stats.get("avg_view_duration_sec"),
            retention_rate_pct=stats.get("retention_rate_pct"),
            snapshot_interval=interval,
        )
        if ok:
            logger.info("Recorded %s analytics snapshot for story '%s' (video '%s')", interval, story_id, video_id)
        return ok
