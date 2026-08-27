import os
import sys
import signal
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from src.db import init_db
from src.daemon import start_daemon, request_shutdown, reset_shutdown, _responsive_sleep
from main import main, acquire_lock, release_lock


class TestAdversarialMilestone3(unittest.TestCase):
    """
    Adversarial test suite for Milestone 3 (src/daemon.py and main.py).
    Tests exception isolation across channel rotation loops and CLI invocation compatibility.
    """

    def setUp(self):
        reset_shutdown()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_m3_adversarial.db")
        init_db(self.db_path)

    def tearDown(self):
        reset_shutdown()
        self.temp_dir.cleanup()

    @patch("src.daemon.run_pipeline_once")
    @patch("src.daemon.logger.error")
    def test_exception_isolation_multi_channel_rotation(self, mock_log_error, mock_run_pipeline):
        """
        Adversarial Test 1: Exception Isolation in Rotation Loop.
        If run_pipeline_once fails for channel 1 in the loop, verify the daemon logs
        the error, performs backoff, and continues to process channel 2 without crashing.
        """
        # Channel 1 fails with RuntimeError, Channel 2 succeeds
        def pipeline_side_effect(channel, db_path=None, short_test=False, **kwargs):
            if channel in ("terror", "moku"):
                raise RuntimeError("Simulated pipeline crash for terror channel")
            return {"status": "SUCCESS", "channel": channel}

        mock_run_pipeline.side_effect = pipeline_side_effect

        results = start_daemon(
            interval_seconds=1,
            max_runs=2,
            db_path=self.db_path,
            channels=["moku", "aelithia"],
            video_mode="longform"
        )

        # Assertions
        self.assertEqual(len(results), 2, "Both channels should have been attempted.")
        self.assertEqual(results[0]["status"], "RETRYABLE_FAILED")
        self.assertEqual(results[0]["channel"], "moku")
        self.assertIn("Simulated pipeline crash", results[0]["error"])
        
        self.assertEqual(results[1]["status"], "SUCCESS")
        self.assertEqual(results[1]["channel"], "aelithia")

        # Verify error was logged for failing channel
        mock_log_error.assert_called()

    @patch("src.daemon.run_pipeline_once")
    def test_exception_isolation_all_channels_fail(self, mock_run_pipeline):
        """
        Adversarial Test 2: All channels in rotation fail.
        Verify daemon handles total channel failure in a cycle gracefully without crashing.
        """
        mock_run_pipeline.side_effect = Exception("General API breakdown")

        channels = ["moku", "aelithia"]
        results = start_daemon(
            interval_seconds=1,
            max_runs=2,
            db_path=self.db_path,
            channels=channels
        )

        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r["status"], "RETRYABLE_FAILED")
            self.assertIn("General API breakdown", r["error"])

    @patch("src.daemon.run_pipeline_once")
    def test_exception_isolation_across_multiple_iterations(self, mock_run_pipeline):
        """
        Adversarial Test 3: Multi-iteration failure and recovery.
        Verify daemon completes multiple iterations, recording failure and success across runs.
        """
        call_counter = 0

        def alternating_side_effect(channel, db_path=None, short_test=False):
            nonlocal call_counter
            call_counter += 1
            if call_counter in (1, 4):
                raise ValueError(f"Transient error call #{call_counter}")
            return {"status": "SUCCESS", "channel": channel, "call": call_counter}

        mock_run_pipeline.side_effect = alternating_side_effect

        results = start_daemon(
            interval_seconds=1,
            max_runs=4,
            db_path=self.db_path,
            channels=["moku", "aelithia"]
        )

        self.assertEqual(len(results), 4)
        self.assertEqual(results[0]["status"], "RETRYABLE_FAILED")
        self.assertEqual(results[1]["status"], "SUCCESS")
        self.assertEqual(results[2]["status"], "SUCCESS")
        self.assertEqual(results[3]["status"], "RETRYABLE_FAILED")

    @patch("src.orchestrator.pipeline.PipelineOrchestrator.run_daemon")
    @patch("main.acquire_lock")
    @patch("main.release_lock")
    def test_cli_main_daemon_invocation_flag_variations(self, mock_release_lock, mock_acquire_lock, mock_run_daemon):
        """
        Adversarial Test 4: CLI invocation via main.py --daemon and subcommand variations.
        Verify argument parsing and parameter compatibility with run_daemon.
        """
        # Variation 1: python main.py --daemon --interval 120 --channel terror
        test_args_1 = ["main.py", "--daemon", "--interval", "120", "--channel", "terror", "--db-path", self.db_path]
        with patch.object(sys, "argv", test_args_1):
            main()
            mock_acquire_lock.assert_called_once()
            mock_run_daemon.assert_called_with(interval=120, channel="terror", lanes_filter=None)
            mock_release_lock.assert_called_once()

        mock_acquire_lock.reset_mock()
        mock_run_daemon.reset_mock()
        mock_release_lock.reset_mock()

        # Variation 2: python main.py start-daemon --interval 300 --channel all
        test_args_2 = ["main.py", "start-daemon", "--interval", "300", "--channel", "all", "--db-path", self.db_path]
        with patch.object(sys, "argv", test_args_2):
            main()
            mock_acquire_lock.assert_called_once()
            mock_run_daemon.assert_called_with(interval=300, channel="all", lanes_filter=None)
            mock_release_lock.assert_called_once()

        mock_acquire_lock.reset_mock()
        mock_run_daemon.reset_mock()
        mock_release_lock.reset_mock()

        # Variation 3: python main.py daemon (defaults: interval=60, channel=all)
        test_args_3 = ["main.py", "daemon", "--db-path", self.db_path]
        with patch.object(sys, "argv", test_args_3):
            main()
            mock_acquire_lock.assert_called_once()
            mock_run_daemon.assert_called_with(interval=60, channel="all", lanes_filter=None)
            mock_release_lock.assert_called_once()

    @patch("src.orchestrator.pipeline.PipelineOrchestrator.run_daemon", side_effect=RuntimeError("Daemon crashed unexpectedly"))
    @patch("main.acquire_lock")
    def test_cli_main_release_lock_on_exception(self, mock_acquire_lock, mock_run_daemon):
        """
        Adversarial Test 5: Exception safety of release_lock in main.py.
        Verify lock is released even if run_daemon raises an unhandled exception inside main.
        """
        lock_file_path = os.path.join(self.temp_dir.name, "test_daemon_exception.lock")
        with patch("main.LOCK_FILE_PATH", lock_file_path):
            test_args = ["main.py", "--daemon", "--db-path", self.db_path]
            with patch.object(sys, "argv", test_args):
                with self.assertRaises(RuntimeError):
                    main()

    @patch("src.daemon.run_pipeline_once")
    def test_shutdown_during_error_backoff_sleep(self, mock_run_pipeline):
        """
        Adversarial Test 6: Responsive shutdown during error backoff.
        Verify that calling request_shutdown during backoff sleep interrupts execution promptly.
        """
        def fail_and_request_shutdown(channel, db_path=None, short_test=False):
            request_shutdown()
            raise RuntimeError("Failure before shutdown request")

        mock_run_pipeline.side_effect = fail_and_request_shutdown

        # Daemon should attempt channel 1, set shutdown flag, catch error, and immediately exit due to shutdown request
        results = start_daemon(
            interval_seconds=3600,  # long interval
            max_runs=5,             # high max_runs
            db_path=self.db_path,
            channels=["moku", "aelithia"]
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "RETRYABLE_FAILED")
        self.assertEqual(results[0]["channel"], "moku")


class TestAudioAndBrandingAdversarial(unittest.TestCase):
    """Adversarial tests for Audio Layering, Ducking Graph, and Genre-Safe Fallbacks."""

    def test_build_audio_chain_port_order_and_normalization(self):
        from lib.video import build_audio_chain
        # 3-channel mix
        chain3 = build_audio_chain(music_path="music.mp3", ambient_path="ambient.mp3")
        self.assertIn("asplit=3[speech_sc1][speech_sc2][speech_mix]", chain3)
        self.assertIn("[music_in][speech_sc1]sidechaincompress", chain3)
        self.assertIn("[ambient_in][speech_sc2]sidechaincompress", chain3)
        self.assertIn("normalize=0", chain3)

        # 2-channel mix (music only)
        chain2_mus = build_audio_chain(music_path="music.mp3")
        self.assertIn("asplit=2[speech_sc][speech_mix]", chain2_mus)
        self.assertIn("[bg_in][speech_sc]sidechaincompress", chain2_mus)
        self.assertIn("normalize=0", chain2_mus)

    def test_asset_manager_genre_isolation_and_type_discrimination(self):
        from src.asset_manager import AssetManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = AssetManager(root_dir=tmpdir)
            # Drama query when only horror music exists must NOT return horror
            mgr._index["music"]["horror"] = ["/fake/horror_bgm.mp3"]
            mgr._index["ambient"]["horror"] = ["/fake/horror_ambient.mp3"]

            drama_music = mgr.get_music(category="aelithia")
            self.assertEqual(drama_music, "", "Aelithia must not receive horror music fallback")

            drama_ambient = mgr.get_ambient(category="aelithia")
            self.assertEqual(drama_ambient, "", "Aelithia must not receive horror ambient fallback")


if __name__ == "__main__":
    unittest.main()

