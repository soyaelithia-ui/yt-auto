import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import pytest

from src.orchestrator.pipeline import (
    PipelineOrchestrator,
    PipelineRunResult,
    BatchRunResult,
    CanaryRunResult,
)
from src.core.lock import ChannelLockError


class TestPipelineOrchestrator(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_orchestrator.db")
        self.lock_patcher = patch("src.core.lock.LOCK_FILE_PATH", os.path.join(self.temp_dir.name, "test_orch.lock"))
        self.lock_patcher.start()
        self.orchestrator = PipelineOrchestrator(db_path=self.db_path)

    def tearDown(self):
        self.lock_patcher.stop()
        self.temp_dir.cleanup()

    def test_run_result_dataclasses_structure(self):
        """Verify typed dataclasses structure and properties."""
        p_res = PipelineRunResult(
            channel="moku",
            status="SUCCESS",
            story_id="story_123",
            work_dir="/tmp/work_123",
            run_id="run_123",
            raw_result={"status": "SUCCESS"},
        )
        self.assertEqual(p_res.channel, "moku")
        self.assertEqual(p_res.status, "SUCCESS")

        b_res = BatchRunResult(
            results={"moku": p_res},
            overall_status="SUCCESS",
            failed_channels=[],
            success_count=1,
            failure_count=0,
        )
        self.assertEqual(b_res.success_count, 1)
        self.assertEqual(b_res.overall_status, "SUCCESS")

        c_res = CanaryRunResult(
            channel="moku",
            status="SUCCESS",
            work_dir="/tmp/work_123",
            video_file="/tmp/work_123/video.mp4",
            telegram_ok=True,
        )
        self.assertTrue(c_res.telegram_ok)

    @patch("src.orchestrator.pipeline.run_pipeline_once")
    def test_run_channel_single_success(self, mock_run_pipeline):
        """Scenario 1: Single channel execution acquires lock, runs pipeline, returns PipelineRunResult."""
        mock_run_pipeline.return_value = {
            "status": "SUCCESS",
            "story_id": "story_abc",
            "work_dir": "/tmp/work_abc",
            "run_id": "run_abc",
        }

        result = self.orchestrator.run_channel(channel="horror")

        self.assertIsInstance(result, PipelineRunResult)
        self.assertEqual(result.channel, "horror")
        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(result.story_id, "story_abc")
        self.assertEqual(result.work_dir, "/tmp/work_abc")
        mock_run_pipeline.assert_called_once_with(
            channel="horror",
            db_path=self.db_path,
            generate_only=False,
            story_id=None,
            lane_id=None,
            visual_pipeline=None,
        )

    def test_run_channel_dry_run_mode(self):
        """Dry-run mode returns DRY_RUN status without executing pipeline."""
        with patch("src.orchestrator.pipeline.run_pipeline_once") as mock_run:
            result = self.orchestrator.run_channel(channel="horror", dry_run=True)
            self.assertEqual(result.status, "DRY_RUN")
            mock_run.assert_not_called()

    @patch("src.orchestrator.pipeline.run_pipeline_once")
    def test_run_channel_topic_ingestion_new_story(self, mock_run_pipeline):
        """Scenario 3: Topic-driven on-demand run synthesizes narrative, enqueues story, and executes."""
        mock_run_pipeline.return_value = {
            "status": "SUCCESS",
            "story_id": "auto-horror-el_misterio_del_faro",
            "work_dir": "/tmp/work_faro",
        }

        result = self.orchestrator.run_channel(
            channel="horror",
            topic="El Misterio del Faro",
            lane_id="horror-horror-long",
        )

        self.assertEqual(result.status, "SUCCESS")
        self.assertIn("auto-horror", result.story_id)
        mock_run_pipeline.assert_called_once()
        call_kwargs = mock_run_pipeline.call_args.kwargs
        self.assertTrue(str(call_kwargs["story_id"]).startswith("auto-horror-el_misterio_del_faro"))
        self.assertEqual(call_kwargs["lane_id"], "horror-horror-long")

    @patch("src.orchestrator.pipeline.run_pipeline_once")
    @patch("src.telegram.notifier.TelegramNotifier.send_video_preview")
    def test_run_channel_dispatch_telegram(self, mock_send_preview, mock_run_pipeline):
        """Dispatch telegram flag sends preview when video artifact exists."""
        work_dir = os.path.join(self.temp_dir.name, "run_tg")
        os.makedirs(work_dir, exist_ok=True)
        video_path = os.path.join(work_dir, "video.mp4")
        with open(video_path, "wb") as f:
            f.write(b"video_bytes")

        mock_run_pipeline.return_value = {
            "status": "SUCCESS",
            "story_id": "story_tg",
            "work_dir": work_dir,
            "run_id": "run_tg",
        }
        mock_delivery = MagicMock()
        mock_delivery.ok = True
        mock_delivery.message_id = 999
        mock_delivery.detail = "Sent"
        mock_delivery.error = None
        mock_send_preview.return_value = mock_delivery

        result = self.orchestrator.run_channel(
            channel="moku",
            dispatch_telegram=True,
        )

        self.assertEqual(result.status, "SUCCESS")
        self.assertIsNotNone(result.telegram_delivery)
        self.assertTrue(result.telegram_delivery["ok"])
        mock_send_preview.assert_called_once()

    @patch("src.orchestrator.pipeline.run_pipeline_once", side_effect=RuntimeError("Pipeline crash"))
    def test_run_channel_error_isolation(self, mock_run_pipeline):
        """Exception during single-channel execution returns FAILED PipelineRunResult."""
        result = self.orchestrator.run_channel(channel="moku")
        self.assertEqual(result.status, "FAILED")
        self.assertIn("Pipeline crash", result.error)

    @patch("src.orchestrator.pipeline.run_pipeline_once")
    def test_run_all_channels_sequential_batch(self, mock_run_pipeline):
        """Scenario 2: Multi-channel execution processes channels sequentially and aggregates result."""
        mock_run_pipeline.side_effect = [
            {"status": "SUCCESS", "story_id": "s1", "work_dir": "/tmp/w1"},
            {"status": "SUCCESS", "story_id": "s2", "work_dir": "/tmp/w2"},
        ]

        batch = self.orchestrator.run_all_channels(channels=["moku", "aelithia"])

        self.assertIsInstance(batch, BatchRunResult)
        self.assertEqual(batch.overall_status, "SUCCESS")
        self.assertEqual(batch.success_count, 2)
        self.assertEqual(batch.failure_count, 0)
        self.assertEqual(len(batch.results), 2)
        self.assertEqual(mock_run_pipeline.call_count, 2)

    @patch("src.orchestrator.pipeline.run_pipeline_once")
    def test_run_all_channels_failure_isolation(self, mock_run_pipeline):
        """Scenario 2 & 5: Failure in channel 1 does not prevent channel 2 from running."""
        mock_run_pipeline.side_effect = [
            RuntimeError("Channel moku exploded"),
            {"status": "SUCCESS", "story_id": "s2", "work_dir": "/tmp/w2"},
        ]

        batch = self.orchestrator.run_all_channels(channels=["moku", "aelithia"])

        self.assertEqual(batch.overall_status, "PARTIAL_FAILURE")
        self.assertEqual(batch.success_count, 1)
        self.assertEqual(batch.failure_count, 1)
        self.assertIn("moku", batch.failed_channels)
        self.assertEqual(batch.results["moku"].status, "FAILED")
        self.assertEqual(batch.results["aelithia"].status, "SUCCESS")

    @patch("src.orchestrator.pipeline.run_pipeline_once")
    @patch("src.telegram.notifier.TelegramNotifier.send_video_preview")
    def test_run_telegram_canary_success(self, mock_send_preview, mock_run_pipeline):
        """Scenario 4: Telegram canary forces generate_only=True and delivers preview."""
        work_dir = os.path.join(self.temp_dir.name, "run_canary")
        os.makedirs(work_dir, exist_ok=True)
        video_path = os.path.join(work_dir, "video.mp4")
        with open(video_path, "wb") as f:
            f.write(b"canary_video")

        mock_run_pipeline.return_value = {
            "status": "SUCCESS",
            "story_id": "canary_story",
            "work_dir": work_dir,
            "run_id": "canary_run",
        }
        mock_delivery = MagicMock()
        mock_delivery.ok = True
        mock_delivery.detail = "Sent to Telegram Canary"
        mock_send_preview.return_value = mock_delivery

        result = self.orchestrator.run_telegram_canary(channel="horror")

        self.assertIsInstance(result, CanaryRunResult)
        self.assertEqual(result.status, "SUCCESS")
        self.assertTrue(result.telegram_ok)
        self.assertEqual(result.video_file, video_path)
        mock_run_pipeline.assert_called_once_with(
            channel="horror",
            db_path=self.db_path,
            generate_only=True,
            story_id=None,
        )
        mock_send_preview.assert_called_once()

    @patch("src.orchestrator.pipeline.run_pipeline_once")
    def test_run_channel_topic_ingestion_existing_story(self, mock_run_pipeline):
        """Topic-driven run resets existing story to PENDING and deletes channel leases."""
        from src.core.repository import QueueRepository, connect
        repo = QueueRepository(self.db_path)
        repo.initialize()
        repo.enqueue("auto-horror-faro", "Old Topic", "Old Content", "http://old", "horror")

        with connect(self.db_path) as conn:
            conn.execute("INSERT INTO runs (run_id, channel, story_id, mode, status, owner, started_at, heartbeat_at) VALUES ('run-test-1', 'horror', 'auto-horror-faro', 'publish', 'RUNNING', 'w1', '2026-08-20T00:00:00Z', '2026-08-20T00:00:00Z')")
            conn.execute("INSERT OR REPLACE INTO leases (job_id, channel, owner, run_id, acquired_at, heartbeat_at, expires_at) VALUES ('auto-horror-faro', 'horror', 'w1', 'run-test-1', 100, 100, 9999999999)")
            conn.commit()

        mock_run_pipeline.return_value = {
            "status": "SUCCESS",
            "story_id": "auto-horror-faro",
        }

        result = self.orchestrator.run_channel(
            channel="horror",
            topic="Faro",
        )

        self.assertEqual(result.status, "SUCCESS")
        # A new unique auto- story is enqueued; the old leased row is left alone.
        call_kwargs = mock_run_pipeline.call_args.kwargs
        new_id = str(call_kwargs["story_id"])
        self.assertTrue(new_id.startswith("auto-horror-faro"))
        self.assertNotEqual(new_id, "auto-horror-faro")

    @patch("src.orchestrator.pipeline.run_pipeline_once")
    def test_run_telegram_canary_missing_video(self, mock_run_pipeline):
        """Telegram canary handles missing video file properly."""
        mock_run_pipeline.return_value = {
            "status": "SUCCESS",
            "story_id": "canary_story",
            "work_dir": "/tmp/non_existent_canary_workdir",
        }

        result = self.orchestrator.run_telegram_canary(channel="moku")
        self.assertFalse(result.telegram_ok)
        self.assertIn("not found", str(result.error))

    @patch("src.orchestrator.pipeline.run_pipeline_once")
    def test_run_all_channels_all_fail(self, mock_run_pipeline):
        """When all channels fail in a batch, overall_status is FAILED."""
        mock_run_pipeline.side_effect = [
            RuntimeError("Channel 1 failed"),
            RuntimeError("Channel 2 failed"),
        ]

        batch = self.orchestrator.run_all_channels(channels=["moku", "aelithia"])
        self.assertEqual(batch.overall_status, "FAILED")
        self.assertEqual(batch.success_count, 0)
        self.assertEqual(batch.failure_count, 2)

    @patch("src.orchestrator.pipeline.start_daemon_lanes")
    def test_run_daemon_delegation(self, mock_start_daemon_lanes):
        """Daemon command delegates to the multi-lane loop; format flags are gone."""
        with patch.dict(os.environ, {"TEST_MODE": "1"}):
            self.orchestrator.run_daemon(interval=600, channel="all")
            mock_start_daemon_lanes.assert_called_once_with(
                interval_seconds=600,
                db_path=self.db_path,
                lanes_filter=None,
            )

    @patch("src.core.lanes.load_lanes")
    @patch("src.orchestrator.pipeline.start_daemon_lanes")
    def test_run_daemon_channel_filter_uses_lanes(self, mock_start_daemon_lanes, mock_load_lanes):
        """A channel-scoped daemon restricts to that channel's configured lanes."""
        from src.core.lanes import fallback_lanes

        horror_lane = next(l for l in fallback_lanes() if l.channel.value == "horror")
        mock_load_lanes.return_value = (horror_lane,)
        with patch.dict(os.environ, {"TEST_MODE": "1"}):
            self.orchestrator.run_daemon(interval=60, channel="horror")
            assert mock_start_daemon_lanes.call_args.kwargs["lanes_filter"] == [horror_lane.id]


if __name__ == "__main__":
    unittest.main()
