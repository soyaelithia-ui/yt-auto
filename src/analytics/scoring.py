"""
src/analytics/scoring.py - Empirical Performance Scoring & Music Attribution Engine.

Computes normalized success scores (0.0 - 100.0) for published YouTube Shorts based on
view velocity, engagement ratio (likes, comments), and audience retention. Attributes
success scores to underlying background music tracks and provides sub-millisecond lookups.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.config import DEFAULT_DB_PATH
from src.core.domain import CanonicalChannel, canonical_channel
from src.core.inventory import PublishedVideoRecord, get_published_inventory
from src.core.repository.migrations import connect
from src.log import get_logger
from src.youtube.analytics import YouTubeAnalyticsSyncer

logger = get_logger("analytics.scoring")


@dataclass(slots=True, frozen=True)
class EmpiricalScoreResult:
    video_id: str
    channel: str
    views: int
    likes: int
    comments: int
    retention_rate_pct: float
    age_hours: float
    actual_success_score: float
    music_track: Optional[str] = None


def calculate_empirical_score(
    views: int,
    likes: int,
    comments: int,
    retention_rate_pct: float = 0.0,
    age_hours: float = 24.0,
) -> float:
    """
    Calculates a normalized empirical success score between 0.0 and 100.0.

    Weights:
    - 40% Normalized Views / Velocity (log10 scaled)
    - 35% Normalized Engagement Rate ((likes*10 + comments*25) / views)
    - 25% Audience Retention Rate (0.0 - 100.0%)
    """
    safe_views = max(0, int(views))
    safe_likes = max(0, int(likes))
    safe_comments = max(0, int(comments))
    safe_retention = max(0.0, min(100.0, float(retention_rate_pct or 0.0)))
    safe_age = max(0.1, float(age_hours or 24.0))

    if safe_views == 0 and safe_likes == 0 and safe_comments == 0:
        return 0.0

    # 1. Log-scaled view performance relative to short-form baseline (10,000 views = 100.0)
    norm_views = min(100.0, (math.log10(max(1, safe_views)) / 4.0) * 100.0)

    # 2. Weighted engagement rate: standard high-performing short has ~5-8% like+comment ratio
    eng_ratio = (safe_likes * 10.0 + safe_comments * 25.0) / max(1.0, float(safe_views))
    norm_engagement = min(100.0, eng_ratio * 100.0)

    # 3. Composite synthesis
    composite = (0.40 * norm_views) + (0.35 * norm_engagement) + (0.25 * safe_retention)
    return round(max(0.0, min(100.0, composite)), 2)


def classify_comment_level(comments: int, views: int = 0) -> str:
    """
    Classifies video audience comment engagement into discrete operational levels:
    - 'none': 0 comments
    - 'low': 1-5 comments or engagement ratio < 0.5%
    - 'moderate': 6-30 comments with engagement ratio between 0.5% and 3.0%
    - 'viral': >30 comments or engagement ratio > 3.0%
    """
    c = max(0, int(comments))
    v = max(0, int(views))
    if c == 0:
        return "none"
    ratio = (c / max(1.0, float(v))) * 100.0 if v > 0 else 0.0
    if c > 30 or ratio > 3.0:
        return "viral"
    if c >= 6 and (v == 0 or ratio >= 0.5):
        return "moderate"
    return "low"


def get_top_performing_music_tracks(
    channel: str | CanonicalChannel,
    db_path: str = DEFAULT_DB_PATH,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Returns music tracks aggregated by average empirical success score and usage count.
    """
    canon = canonical_channel(channel).value
    query = """
        SELECT
            music_track,
            COUNT(*) as usage_count,
            ROUND(AVG(actual_success_score), 2) as avg_score,
            MAX(actual_success_score) as peak_score
        FROM publications
        WHERE (channel = ? OR channel = ?)
          AND music_track IS NOT NULL
          AND music_track != ''
        GROUP BY music_track
        ORDER BY avg_score DESC, usage_count DESC
        LIMIT ?
    """
    results: List[Dict[str, Any]] = []
    with connect(db_path, read_only=True) as conn:
        for row in conn.execute(query, (channel, canon, max(1, limit))).fetchall():
            results.append({
                "music_track": str(row["music_track"]),
                "usage_count": int(row["usage_count"]),
                "avg_score": float(row["avg_score"] or 0.0),
                "peak_score": float(row["peak_score"] or 0.0),
            })
    return results


def get_video_by_sha256(
    video_sha256: str,
    db_path: str = DEFAULT_DB_PATH,
) -> Optional[PublishedVideoRecord]:
    """
    Sub-millisecond lookup of a published video record by its 64-character SHA256 digest.
    """
    if not video_sha256:
        return None
    with connect(db_path, read_only=True) as conn:
        row = conn.execute(
            "SELECT * FROM publications WHERE video_sha256 = ? LIMIT 1",
            (video_sha256,),
        ).fetchone()
        if row:
            return PublishedVideoRecord.from_row(row)
    return None


def sync_and_score_channel_publications(
    channel: str | CanonicalChannel,
    db_path: str = DEFAULT_DB_PATH,
    api_key: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Queries YouTube Data API v3 statistics for all published videos in a channel,
    computes empirical success scores, and persists updates atomically to SQLite.
    """
    canon = canonical_channel(channel).value
    syncer = YouTubeAnalyticsSyncer(db_path=db_path, api_key=api_key, dry_run=dry_run)
    records = get_published_inventory(db_path=db_path, channel=canon, limit=200)

    updated_count = 0
    scored_items: List[Dict[str, Any]] = []

    for rec in records:
        if not rec.video_id:
            continue
        stats = syncer.fetch_video_statistics(rec.video_id)
        views = stats.get("view_count", 0)
        likes = stats.get("like_count", 0)
        comments = stats.get("comment_count", 0)
        retention_pct = stats.get("retention_rate_pct", 0.0)

        score = calculate_empirical_score(
            views=views,
            likes=likes,
            comments=comments,
            retention_rate_pct=retention_pct,
        )

        if not dry_run:
            with connect(db_path) as conn:
                conn.execute(
                    "UPDATE publications SET actual_success_score = ?, view_count = ?, like_count = ?, comment_count = ? WHERE publication_id = ?",
                    (score, views, likes, comments, rec.publication_id),
                )
                conn.commit()
            syncer.sync_video_metrics(
                video_id=rec.video_id,
                story_id=rec.story_id,
                channel=canon,
                interval="24h",
            )

        updated_count += 1
        comment_level = classify_comment_level(comments, views)
        scored_items.append({
            "video_id": rec.video_id,
            "title": rec.title,
            "score": score,
            "views": views,
            "likes": likes,
            "comments": comments,
            "comment_level": comment_level,
        })

    return {
        "channel": canon,
        "updated_count": updated_count,
        "items": scored_items,
        "dry_run": dry_run,
    }
