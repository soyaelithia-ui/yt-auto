"""Unit tests for Telegram 2-hour rejection window and auto-publish sweep.

Enforces:
1. Jobs under 2 hours (7200s) remain in PENDING_REVIEW and are NOT picked up by the sweep.
2. Jobs older than 2 hours (7200s) are picked up by the auto-publish sweep (fail-open).
3. Jobs with code_verdict metadata are NOT skipped by the sweep after 2 hours.
4. Human rejection before the 2-hour window transitions status to REJECTED and blocks auto-publish.
5. Atomic publication gate prevents race conditions between human action and the auto-publish sweep.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from review import ReviewJobManager, ReviewStatus
from review.db import ReviewStateStore
from review.domain import ReviewJob
from review.publication_gate import PublicationGate
from src.telegram.approval import (
    AUTO_PUBLISH_TIMEOUT_HOURS,
    get_expired_pending_videos,
)


class TestTelegramRejectionWindow(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "review_window.db")
        os.environ["VIDEO_REVIEW_DB_PATH"] = self.db_path
        self.store = ReviewStateStore(self.db_path)
        self.bot = MagicMock()
        self.manager = ReviewJobManager(store=self.store, bot=self.bot)

    def tearDown(self) -> None:
        self.tmp.cleanup()
        os.environ.pop("VIDEO_REVIEW_DB_PATH", None)

    def test_default_timeout_is_2_hours(self) -> None:
        """Verify that default AUTO_PUBLISH_TIMEOUT_HOURS is 2."""
        self.assertEqual(AUTO_PUBLISH_TIMEOUT_HOURS, 2)

    def test_job_stays_pending_review_under_2_hours(self) -> None:
        """Jobs created 7100s ago (< 2h) must NOT be picked up by the sweep."""
        now = datetime.now(timezone.utc)
        under_2h = (now - timedelta(seconds=7100)).isoformat()

        job = ReviewJob(
            job_id="story-young",
            channel="moku",
            title="SCP Under 2h",
            original_video_path="/tmp/fake.mp4",
            status=ReviewStatus.PENDING_REVIEW.value,
            created_at=under_2h,
            metadata={},
        )
        self.store.create_job(job)

        expired = get_expired_pending_videos()
        expired_ids = [j["job_id"] for j in expired]
        self.assertNotIn("story-young", expired_ids)

    def test_job_auto_publishes_after_2_hours(self) -> None:
        """Jobs created 7205s ago (>= 2h) MUST be picked up by the sweep."""
        now = datetime.now(timezone.utc)
        over_2h = (now - timedelta(seconds=7205)).isoformat()

        job = ReviewJob(
            job_id="story-ripe",
            channel="moku",
            title="SCP Over 2h",
            original_video_path="/tmp/fake.mp4",
            status=ReviewStatus.PENDING_REVIEW.value,
            created_at=over_2h,
            metadata={},
        )
        self.store.create_job(job)

        expired = get_expired_pending_videos()
        expired_ids = [j["job_id"] for j in expired]
        self.assertIn("story-ripe", expired_ids)

    def test_job_with_code_verdict_is_not_skipped_by_sweep(self) -> None:
        """Jobs with metadata.code_verdict older than 2h MUST be picked up."""
        now = datetime.now(timezone.utc)
        over_2h = (now - timedelta(seconds=7210)).isoformat()

        job = ReviewJob(
            job_id="story-verdict-ripe",
            channel="aelithia",
            title="AITA Drama Over 2h",
            original_video_path="/tmp/fake.mp4",
            status=ReviewStatus.PENDING_REVIEW.value,
            created_at=over_2h,
            metadata={"code_verdict": {"passed": True, "score": 100}},
        )
        self.store.create_job(job)

        expired = get_expired_pending_videos()
        expired_ids = [j["job_id"] for j in expired]
        self.assertIn("story-verdict-ripe", expired_ids)

    def test_human_rejection_prevents_sweep_publication(self) -> None:
        """An operator rejecting in Telegram before 2h prevents auto-publishing after 2h."""
        now = datetime.now(timezone.utc)
        created_ts = (now - timedelta(seconds=7150)).isoformat()

        job = ReviewJob(
            job_id="story-veto",
            channel="moku",
            title="Vetoed Video",
            original_video_path="/tmp/fake.mp4",
            status=ReviewStatus.PENDING_REVIEW.value,
            created_at=created_ts,
            metadata={},
        )
        created = self.store.create_job(job)

        # Operator presses Reject in Telegram
        self.manager.action_reject("story-veto", created.version)
        refreshed = self.store.get_job("story-veto", created.version)
        self.assertEqual(refreshed.status, ReviewStatus.REJECTED.value)

        # Time moves past 2 hours (simulated since cutoff is now)
        expired = get_expired_pending_videos(cutoff_time=now)
        expired_ids = [j["job_id"] for j in expired]
        self.assertNotIn("story-veto", expired_ids)

    def test_atomic_claim_race_condition(self) -> None:
        """PublicationGate atomic claim ensures only one actor publishes."""
        now = datetime.now(timezone.utc)
        created_ts = (now - timedelta(seconds=7300)).isoformat()

        job = ReviewJob(
            job_id="story-race",
            channel="aelithia",
            title="Race Condition Video",
            original_video_path="/tmp/fake.mp4",
            status=ReviewStatus.APPROVED.value,
            created_at=created_ts,
            metadata={},
        )
        created = self.store.create_job(job)

        gate = PublicationGate(self.store)

        # First claim succeeds and transitions to PUBLISHING
        claimed_job = gate.verify_and_claim_publication("story-race", created.version)
        self.assertEqual(claimed_job.status, ReviewStatus.PUBLISHING.value)

        # Second claim while PUBLISHING raises RuntimeError
        with self.assertRaises(RuntimeError):
            gate.verify_and_claim_publication("story-race", created.version)


if __name__ == "__main__":
    unittest.main()
