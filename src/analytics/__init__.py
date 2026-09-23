"""Analytics and performance telemetry package."""
from src.analytics.pruner import (
    AutonomousPruneReport,
    PruneCandidate,
    evaluate_prune_candidates,
    execute_autonomous_prune,
)
from src.analytics.scoring import (
    calculate_empirical_score,
    get_top_performing_music_tracks,
    get_video_by_sha256,
    sync_and_score_channel_publications,
)
from src.youtube.analytics import YouTubeAnalyticsSyncer

__all__ = [
    "AutonomousPruneReport",
    "PruneCandidate",
    "YouTubeAnalyticsSyncer",
    "calculate_empirical_score",
    "evaluate_prune_candidates",
    "execute_autonomous_prune",
    "get_top_performing_music_tracks",
    "get_video_by_sha256",
    "sync_and_score_channel_publications",
]
