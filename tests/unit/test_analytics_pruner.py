"""Unit tests for Autonomous Underperforming Video Pruner (src/analytics/pruner.py)."""
import os
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.analytics.pruner import (
    evaluate_prune_candidates,
    execute_autonomous_prune,
    AutonomousPruneReport,
)
from src.core.inventory import record_published_inventory
from src.core.repository.migrations import connect


def _create_sample_inventory(db_path: str):
    now = datetime.now(timezone.utc)
    old_time_3d = (now - timedelta(days=3)).isoformat(timespec="seconds")
    old_time_48h = (now - timedelta(hours=48)).isoformat(timespec="seconds")
    fresh_time_6h = (now - timedelta(hours=6)).isoformat(timespec="seconds")

    # 1. Fresh video (< 24h) with 0 score -> MUST be protected by grace period
    record_published_inventory(
        db_path=db_path,
        run_id="run-fresh",
        story_id="story-fresh",
        video_id="vid_fresh_6h",
        url="https://youtube.com/watch?v=vid_fresh_6h",
        channel="moku",
        title="Fresh Short",
        description="Fresh desc",
        verified_at=fresh_time_6h,
        actual_success_score=5.0,
    )

    # 2. Old video (48h) with poor score (10.0) -> SHOULD be a candidate
    record_published_inventory(
        db_path=db_path,
        run_id="run-poor-1",
        story_id="story-poor-1",
        video_id="vid_poor_1",
        url="https://youtube.com/watch?v=vid_poor_1",
        channel="moku",
        title="Poor Short 1",
        description="Poor desc 1",
        verified_at=old_time_48h,
        actual_success_score=10.0,
    )

    # 3. Old video (3 days) with very poor score (5.0) -> SHOULD be a candidate
    record_published_inventory(
        db_path=db_path,
        run_id="run-poor-2",
        story_id="story-poor-2",
        video_id="vid_poor_2",
        url="https://youtube.com/watch?v=vid_poor_2",
        channel="moku",
        title="Poor Short 2",
        description="Poor desc 2",
        verified_at=old_time_3d,
        actual_success_score=5.0,
    )

    # 4. Old video (3 days) with another poor score (15.0) -> 3rd candidate
    record_published_inventory(
        db_path=db_path,
        run_id="run-poor-3",
        story_id="story-poor-3",
        video_id="vid_poor_3",
        url="https://youtube.com/watch?v=vid_poor_3",
        channel="moku",
        title="Poor Short 3",
        description="Poor desc 3",
        verified_at=old_time_3d,
        actual_success_score=15.0,
    )

    # 5. Old video with high score (85.0) -> NEVER a candidate
    record_published_inventory(
        db_path=db_path,
        run_id="run-good",
        story_id="story-good",
        video_id="vid_good",
        url="https://youtube.com/watch?v=vid_good",
        channel="moku",
        title="Good Short",
        description="Good desc",
        verified_at=old_time_3d,
        actual_success_score=85.0,
    )


def test_grace_period_protects_fresh_videos():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = tmp.name
        _create_sample_inventory(db_path)

        candidates = evaluate_prune_candidates(
            channel="moku",
            db_path=db_path,
            min_score=25.0,
            grace_hours=24.0,
        )
        cand_ids = [c.video_id for c in candidates]
        assert "vid_fresh_6h" not in cand_ids
        assert "vid_good" not in cand_ids
        assert "vid_poor_2" in cand_ids  # score 5.0
        assert "vid_poor_1" in cand_ids  # score 10.0


def test_daily_ceiling_limits_prune_to_max_2():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = tmp.name
        _create_sample_inventory(db_path)

        candidates = evaluate_prune_candidates(
            channel="moku",
            db_path=db_path,
            min_score=25.0,
            grace_hours=24.0,
            max_candidates=2,
        )
        assert len(candidates) == 2
        # Lowest scores first: 5.0 and 10.0
        assert candidates[0].video_id == "vid_poor_2"
        assert candidates[1].video_id == "vid_poor_1"


def test_kill_switch_halts_pruning():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = tmp.name
        _create_sample_inventory(db_path)

        with patch.dict(os.environ, {"AUTO_PRUNE_ENABLED": "false"}):
            report = execute_autonomous_prune(
                channel="moku",
                db_path=db_path,
                dry_run=False,
            )
            assert report.pruned_count == 0
            assert report.skipped_count > 0


def test_dry_run_does_not_mutate_state():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = tmp.name
        _create_sample_inventory(db_path)

        mock_youtube = MagicMock()
        report = execute_autonomous_prune(
            channel="moku",
            db_path=db_path,
            dry_run=True,
            youtube_service=mock_youtube,
        )
        assert report.pruned_count == 0
        assert not mock_youtube.videos().delete.called

        # Status in DB stories table remains PUBLISHED
        with connect(db_path) as conn:
            row = conn.execute("SELECT status FROM stories WHERE story_id = 'story-poor-2'").fetchone()
            assert row is not None
            assert row["status"] == "PUBLISHED"


def test_live_prune_deletes_and_updates_db():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = tmp.name
        _create_sample_inventory(db_path)

        mock_youtube = MagicMock()
        mock_delete = MagicMock()
        mock_delete.execute.return_value = ""
        mock_youtube.videos().delete.return_value = mock_delete

        with patch.dict(os.environ, {"AUTO_PRUNE_ENABLED": "true"}):
            report = execute_autonomous_prune(
                channel="moku",
                db_path=db_path,
                dry_run=False,
                youtube_service=mock_youtube,
            )
            assert report.pruned_count == 2
            assert mock_delete.execute.call_count == 2

            # Check DB updated
            with connect(db_path) as conn:
                row = conn.execute("SELECT status FROM stories WHERE story_id = 'story-poor-2'").fetchone()
                assert row is not None
                assert row["status"] == "PURGED"


def test_purged_stories_are_excluded_from_prune_candidates():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = tmp.name
        _create_sample_inventory(db_path)

        # Before marking purged, we should find candidates
        cands_before = evaluate_prune_candidates(channel="moku", db_path=db_path, max_candidates=10)
        candidate_story_ids_before = [c.story_id for c in cands_before]
        assert "story-poor-1" in candidate_story_ids_before
        assert "story-poor-2" in candidate_story_ids_before

        # Mark story-poor-2 as PURGED
        with connect(db_path) as conn:
            conn.execute("UPDATE stories SET status = 'PURGED' WHERE story_id = 'story-poor-2'")
            conn.commit()

        # After marking purged, story-poor-2 must NOT be included in candidates
        cands_after = evaluate_prune_candidates(channel="moku", db_path=db_path, max_candidates=10)
        candidate_story_ids_after = [c.story_id for c in cands_after]
        assert "story-poor-2" not in candidate_story_ids_after
        assert "story-poor-1" in candidate_story_ids_after
