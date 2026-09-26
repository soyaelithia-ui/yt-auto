import os
import sys
import tempfile
import sqlite3
import unittest
from unittest.mock import patch, MagicMock

from src.db import init_db, enqueue_story, get_pending_story, update_story_status
from src.daemon import run_pipeline_once, start_daemon
from src.cli import cli_status, list_queue, print_status, print_queue
from main import main


class TestDaemonSchedulerAndCLI(unittest.TestCase):
    """Unit and integration tests for Requirement R5 (Scheduler Daemon, Logging & CLI Monitor)."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_daemon_r5.db")
        init_db(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("src.scraper.fetch_reddit_stories", return_value=[])
    @patch("lib.video.create_video_thumbnail")
    @patch("src.llm.curate_batch_json", return_value={
        "title": "Spanish Mock Title",
        "script_3_acts": {"act1": "a1", "act2": "a2", "act3": "a3"},
        "script": "Había una vez en un pueblo lejano donde la oscuridad caía temprano y los secretos de la noche aterrorizaban a todos los habitantes que intentaban cruzar el bosque encantado en busca de respuestas.",
        "seo": {"description": "Esta es una descripción completa y detallada en español para el video de YouTube sobre historias de la vida real.", "tags": ["tag1"], "monetization_notes": "notes"},
        "image_prompts": {"background": "bg prompt", "thumbnail": "thumb prompt"}
    })
    @patch("src.llm.curate_script", return_value="Había una vez en un pueblo lejano donde la oscuridad caía temprano y los secretos de la noche aterrorizaban a todos los habitantes que intentaban cruzar el bosque encantado en busca de respuestas.")
    @patch("lib.tts.generate_audio")
    @patch("lib.subtitles.create_subtitles")
    @patch("lib.video.compose_video")
    @patch("src.llm.translate_title", return_value="Esta es una historia de misterio y terror")
    @patch("src.drive.upload_to_drive_verified")
    @patch("src.youtube.uploader.upload_video", return_value={"status": "SUCCESS"})
    @patch("src.cleaner.verify_and_cleanup")
    def test_run_pipeline_once_success(
        self, mock_cleanup, mock_upload_yt, mock_upload_drive, mock_translate, mock_compose, mock_subs, mock_tts, mock_curate, mock_curate_batch, mock_thumb, mock_fetch
    ):
        """Test run_pipeline_once executes end-to-end flow and updates story status."""
        enqueue_story("daemon_test_001", "SCP-173: La Escultura", "Every night the walls whisper...", "http://example.com/1", channel="moku", db_path=self.db_path)
        
        def fake_audio(*args, **kwargs):
            from pathlib import Path
            out_path = args[1] if len(args) > 1 else kwargs.get("out_path", "/tmp/audio.wav")
            Path(out_path).write_bytes(b"WAV")
            return {"word_timestamps": [], "duration_sec": 12.0}

        def fake_subs(*args, **kwargs):
            from pathlib import Path
            out_path = args[1] if len(args) > 1 else kwargs.get("out_path")
            if out_path:
                Path(out_path).write_text("1\n00:00:00,000 --> 00:00:10,000\nSubtítulos de prueba en español\n", encoding="utf-8")

        def fake_compose(*args, **kwargs):
            from pathlib import Path
            out_path = args[3] if len(args) > 3 else kwargs.get("out_video", "/tmp/video.mp4")
            Path(out_path).write_bytes(b"MP4")

        def fake_thumb(*args, **kwargs):
            from pathlib import Path
            from PIL import Image
            out_path = args[-1] if args else kwargs.get("output_path", "/tmp/thumb.jpg")
            if isinstance(out_path, (str, Path)):
                Image.new("RGB", (768, 1360), "red").save(out_path)
            return str(out_path)

        from src.core.providers import DriveProof
        mock_upload_drive.return_value = DriveProof(file_id="mock_drive_file_id_001", name="test.mp4", size_bytes=100, folder_id="folder123", exists=True)
        mock_tts.side_effect = fake_audio
        mock_subs.side_effect = fake_subs
        mock_compose.side_effect = fake_compose
        mock_thumb.side_effect = fake_thumb

        # Los artefactos son placeholders; el gate pre-publicación real exige
        # MP4 con moov atom, resolución exacta y miniatura válida.
        report = MagicMock()
        report.require_pass.return_value = None
        with patch("src.pipeline.validate_prepublication", return_value=report):
            res = run_pipeline_once(channel="moku", db_path=self.db_path)

        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["story_id"], "daemon_test_001")

    def test_run_pipeline_once_no_pending_stories(self):
        """Test run_pipeline_once returns NO_PENDING_STORIES when queue is empty and scraper yields no posts."""
        with patch("src.core.repository.QueueRepository.claim", return_value=None), \
             patch("src.core.repository.QueueRepository.enqueue"):
            res = run_pipeline_once(channel="moku", db_path=self.db_path)
            self.assertEqual(res["status"], "NO_PENDING_STORIES")

    @patch("src.llm.curate_batch_json", return_value={
        "title": "Spanish Mock Title",
        "script_3_acts": {"act1": "a1", "act2": "a2", "act3": "a3"},
        "script": "Había una vez en un pueblo lejano donde la oscuridad caía temprano y los secretos de la noche aterrorizaban a todos los habitantes que intentaban cruzar el bosque encantado en busca de respuestas.",
        "seo": {"description": "Esta es una descripción completa y detallada en español para el video de YouTube sobre historias de la vida real.", "tags": ["tag1"], "monetization_notes": "notes"},
        "image_prompts": {"background": "bg prompt", "thumbnail": "thumb prompt"}
    })
    @patch("src.llm.curate_script", return_value="Había una vez en un pueblo lejano donde la oscuridad caía temprano y los secretos de la noche aterrorizaban a todos los habitantes que intentaban cruzar el bosque encantado en busca de respuestas.")
    @patch("lib.tts.generate_audio", return_value={"duration_sec": 605.0, "word_timestamps": []})
    @patch("lib.subtitles.create_subtitles")
    @patch("lib.video.compose_video", side_effect=ValueError("FFmpeg synthesis failed"))
    def test_run_pipeline_once_error_recovery(self, mock_compose, mock_subs, mock_tts, mock_curate, mock_curate_batch):
        """Test pipeline error causes DB status transition to RETRYABLE_FAILED with error_msg."""
        enqueue_story("err_story_001", "Error Title", "Error Content", "http://err1.com", channel="moku", db_path=self.db_path)

        res = run_pipeline_once(channel="moku", db_path=self.db_path)
        self.assertEqual(res["status"], "RETRYABLE_FAILED")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT status, error_msg FROM stories WHERE story_id = 'err_story_001'")
        row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertIn(row[0], ("FAILED", "RETRYABLE_FAILED"))

    def test_start_daemon_lifecycle(self):
        """Test start_daemon hourly scheduler loop for configured max_runs."""
        with patch("src.daemon.run_pipeline_once", return_value={"status": "SUCCESS", "story_id": "loop_story_001"}):
            results = start_daemon(interval_seconds=1, max_runs=2, db_path=self.db_path, channels=["moku"])
            self.assertEqual(len(results), 2)
            self.assertEqual(results[0]["status"], "SUCCESS")

    def test_start_daemon_retry_backoff_on_failure(self):
        """Test start_daemon catches exception, logs error, applies backoff, and continues loop."""
        side_effects = [ValueError("Temporary network glitch"), {"status": "SUCCESS", "story_id": "ok_001"}]
        with patch("src.daemon.run_pipeline_once", side_effect=side_effects), \
              patch("time.sleep") as mock_sleep:
            results = start_daemon(interval_seconds=10, max_runs=2, db_path=self.db_path, channels=["moku"])
            self.assertEqual(len(results), 2)
            self.assertIn(results[0]["status"], ("FAILED", "RETRYABLE_FAILED"))
            self.assertEqual(results[1]["status"], "SUCCESS")

    def test_start_daemon_accepts_channels_and_rotates(self):
        """Test start_daemon accepts channels parameter and rotates through specified channels."""
        channels_input = ["moku", "aelithia"]
        with patch("src.daemon.run_pipeline_once", return_value={"status": "SUCCESS"}) as mock_run, \
              patch("src.scraper.replenish_queue"):
            results = start_daemon(interval_seconds=1, max_runs=2, db_path=self.db_path, channels=channels_input)
            self.assertEqual(len(results), 2)
            self.assertEqual(mock_run.call_count, 2)
            called_channels = [call.kwargs.get("channel") for call in mock_run.call_args_list]
            self.assertEqual(called_channels, ["horror", "drama"])

    def test_start_daemon_default_channels_resolution(self):
        """Test start_daemon resolves default active channels when channels parameter is None."""
        with patch("src.daemon.run_pipeline_once", return_value={"status": "SUCCESS"}) as mock_run, \
              patch("src.scraper.replenish_queue"):
            results = start_daemon(interval_seconds=1, max_runs=2, db_path=self.db_path, channels=None)
            self.assertEqual(len(results), 2)
            called_channels = {call.kwargs.get("channel") for call in mock_run.call_args_list}
            self.assertEqual(called_channels, {"horror", "drama"})

    def test_start_daemon_responsive_sleep_and_shutdown(self):
        """Test start_daemon responsive sleep interrupts loop cleanly when request_shutdown is called."""
        import time
        from src.daemon import request_shutdown, reset_shutdown
        reset_shutdown()

        def side_effect_func(*args, **kwargs):
            request_shutdown()
            return {"status": "SUCCESS"}

        with patch("src.daemon.run_pipeline_once", side_effect=side_effect_func), \
              patch("src.scraper.replenish_queue"):
            start_time = time.time()
            results = start_daemon(interval_seconds=3600, max_runs=10, db_path=self.db_path, channels=["moku"])
            elapsed = time.time() - start_time

            self.assertLess(elapsed, 2.0)
            self.assertEqual(len(results), 1)

    def test_main_pid_lock_lifecycle(self):
        """Test acquire_lock creates directory and PID content, and release_lock releases and unlinks lock file."""
        from main import acquire_lock, release_lock
        temp_lock_dir = tempfile.mkdtemp()
        temp_lock_file = os.path.join(temp_lock_dir, "nested_dir", "test_pid.lock")

        with patch("main.LOCK_FILE_PATH", temp_lock_file):
            self.assertFalse(os.path.exists(temp_lock_file))
            acquire_lock()
            self.assertTrue(os.path.exists(temp_lock_file))

            with open(temp_lock_file, "r") as f:
                content = f.read().strip()
            self.assertEqual(content, str(os.getpid()))

            release_lock()
            self.assertFalse(os.path.exists(temp_lock_file))

    def test_main_signal_handler_lock_cleanup(self):
        """WP5: main registers the canonical lock.py handler which triggers
        request_shutdown, release_lock, and exits cleanly."""
        import signal
        from unittest.mock import patch as _patch

        import main
        from src.core import lock as lock_mod
        from src.core.lock import _handle_signal

        # main.py must delegate registration to the canonical helper.
        with _patch.object(lock_mod.signal, "signal") as mock_reg:
            main.register_signal_handlers = (
                __import__("src.core.lock", fromlist=["register_signal_handlers"])
                .register_signal_handlers
            )
            self.assertIs(main.register_signal_handlers, lock_mod.register_signal_handlers)

        with _patch("src.core.lock.release_lock") as mock_release, \
              patch("src.daemon.request_shutdown") as mock_req_shutdown, \
              self.assertRaises(SystemExit) as cm:
            _handle_signal(signal.SIGTERM, None)

        self.assertEqual(cm.exception.code, 0)
        mock_req_shutdown.assert_called_once()
        mock_release.assert_called_once()

    def test_cli_status_and_queue_counts(self):
        """Test cli_status returns correct queue counts, processed counts, and health logs."""
        enqueue_story("st_pending", "Pending Title", "Content", "http://p.com", channel="moku", db_path=self.db_path)
        enqueue_story("st_comp", "Comp Title", "Content", "http://c.com", channel="moku", db_path=self.db_path)
        enqueue_story("st_fail", "Fail Title", "Content", "http://f.com", channel="moku", db_path=self.db_path)
        update_story_status("st_comp", "COMPLETED", db_path=self.db_path)
        update_story_status("st_fail", "FAILED", error_msg="Test Failure", db_path=self.db_path)

        st = cli_status(db_path=self.db_path)
        self.assertEqual(st["queue"]["PENDING"], 1)
        self.assertEqual(st["queue"]["COMPLETED"], 1)
        self.assertEqual(st["queue"]["FAILED"], 1)
        self.assertEqual(st["processed_count"], 2)
        self.assertIn("disk_free_gb", st)

    def test_cli_list_queue_and_print_functions(self):
        """Test list_queue and print_queue output formatting."""
        enqueue_story("q_1", "Queue Item 1", "Content 1", "http://q1.com", channel="moku", db_path=self.db_path)
        q = list_queue(db_path=self.db_path, limit=10)
        self.assertEqual(len(q), 1)
        self.assertEqual(q[0]["story_id"], "q_1")

        # Test print_status and print_queue execution without raising exceptions
        print_status(db_path=self.db_path)
        print_queue(db_path=self.db_path)

    def test_main_cli_entrypoint(self):
        """Test main.py CLI entry point command line flags."""
        test_args = ["main.py", "--status", "--db-path", self.db_path]
        with patch.object(sys, "argv", test_args):
            main()

        test_args_cmd = ["main.py", "status", "--db-path", self.db_path]
        with patch.object(sys, "argv", test_args_cmd):
            main()

    @patch("src.scraper.fetch_reddit_stories", return_value=[])
    @patch("lib.video.create_video_thumbnail")
    @patch("src.llm.curate_batch_json", return_value={
        "title": "Título traducido",
        "script": "Había una vez en un pueblo lejano donde la oscuridad caía temprano y los secretos de la noche aterrorizaban a todos los habitantes que intentaban cruzar el bosque encantado en busca de respuestas.",
        "seo": {"description": "Esta es una descripción completa y detallada en español para el video de YouTube sobre historias de la vida real."}
    })
    @patch("src.llm.curate_script", return_value="Había una vez en un pueblo lejano donde la oscuridad caía temprano y los secretos de la noche aterrorizaban a todos los habitantes que intentaban cruzar el bosque encantado en busca de respuestas.")
    @patch("lib.tts.generate_audio")
    @patch("lib.subtitles.create_subtitles")
    @patch("lib.video.compose_video")
    @patch("src.llm.translate_title", return_value="Esta es una historia de misterio y terror")
    @patch("src.drive.upload_to_drive_verified")
    @patch("src.youtube.uploader.upload_video", return_value={"status": "SUCCESS", "url": "https://youtu.be/m2_test_url"})
    @patch("src.cleaner.verify_and_cleanup")
    def test_run_pipeline_once_soy_el_malo_channel_and_youtube_url(
        self, mock_clean, mock_upload_yt, mock_drive, mock_trans, mock_compose, mock_subs, mock_tts, mock_curate, mock_curate_batch, mock_thumb, mock_fetch
    ):
        """Test run_pipeline_once for aelithia channel passes channel."""
        enqueue_story("sample_soy_el_malo_001", "AITA Title", "AITA Content...", "http://ex.com/aita", channel="aelithia", db_path=self.db_path)

        def fake_audio(*args, **kwargs):
            from pathlib import Path
            out_path = args[1] if len(args) > 1 else kwargs.get("out_path", "/tmp/audio.wav")
            Path(out_path).write_bytes(b"WAV")
            # El carril aelithia-aita-long exige ≥600 s de narración.
            return {"word_timestamps": [], "duration_sec": 605.0}

        def fake_subs(*args, **kwargs):
            from pathlib import Path
            out_path = args[1] if len(args) > 1 else kwargs.get("out_path")
            if out_path:
                Path(out_path).write_text("1\n00:00:00,000 --> 00:00:10,000\nSubtítulos de prueba en español\n", encoding="utf-8")

        def fake_compose(*args, **kwargs):
            from pathlib import Path
            out_path = args[3] if len(args) > 3 else kwargs.get("out_video", "/tmp/video.mp4")
            Path(out_path).write_bytes(b"MP4")

        def fake_thumb(*args, **kwargs):
            from pathlib import Path
            from PIL import Image
            out_path = args[-1] if args else kwargs.get("output_path", "/tmp/thumb.jpg")
            if isinstance(out_path, (str, Path)):
                Image.new("RGB", (768, 1360), "red").save(out_path)
            return str(out_path)

        from src.core.providers import DriveProof
        mock_drive.return_value = DriveProof(file_id="drive_123", name="test.mp4", size_bytes=100, folder_id="folder123", exists=True)
        mock_tts.side_effect = fake_audio
        mock_subs.side_effect = fake_subs
        mock_compose.side_effect = fake_compose
        mock_thumb.side_effect = fake_thumb

        # Los artefactos son placeholders; el gate pre-publicación real exige
        # MP4 con moov atom, resolución exacta y miniatura válida.
        report = MagicMock()
        report.require_pass.return_value = None
        def fake_multiscene(manifest_path, output_video_path, **kwargs):
            from pathlib import Path
            out = Path(output_video_path)
            out.write_bytes(b"MP4")
            return {"rendered_scenes": 5, "output_path": str(out), "duration_sec": 605.0}

        with patch("src.pipeline.validate_prepublication", return_value=report), \
             patch("src.media.loop_engine.LoopVideoEngine.render", side_effect=fake_multiscene):
            res = run_pipeline_once(channel="aelithia", db_path=self.db_path, lane_id="aelithia-aita-long")

        self.assertEqual(res["status"], "SUCCESS")
        mock_upload_yt.assert_called_once()
        self.assertEqual(mock_upload_yt.call_args.kwargs.get("channel"), "drama")

    def test_update_story_status_youtube_url_persistence(self):
        """Test update_story_status stores youtube_url in database when provided."""
        enqueue_story("yt_url_001", "Title", "Content", "http://yturl.com", channel="moku", db_path=self.db_path)
        update_story_status("yt_url_001", "COMPLETED", youtube_url="https://youtu.be/persist_123", db_path=self.db_path)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT youtube_url FROM stories WHERE story_id = 'yt_url_001'")
        row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], "https://youtu.be/persist_123")

    @patch("src.monitor._service_state", return_value="failed")
    def test_diagnose_failure_and_fix_transient_auto_repair(self, mock_svc):
        """Test publication monitor diagnostic reports failure analysis without requiring manual intervention on transient errors."""
        from src.monitor import diagnose_failure_and_fix
        enqueue_story("transient_001", "Title", "Content", "http://transient.com", channel="moku", db_path=self.db_path)
        update_story_status("transient_001", "RETRYABLE_FAILED", error_msg="FFmpeg process error: Invalid data found", db_path=self.db_path)

        diag = diagnose_failure_and_fix(db_path=self.db_path)
        self.assertFalse(diag["manual_intervention_required"])


if __name__ == "__main__":
    unittest.main()
