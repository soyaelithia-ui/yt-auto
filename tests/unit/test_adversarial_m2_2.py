import os
import sys
import json
import shutil
import tempfile
import sqlite3
import subprocess
import unittest
from unittest.mock import patch, MagicMock

from src.config import DEFAULT_DB_PATH, LONG_MIN_WORDS
from src.db import init_db, enqueue_story, update_story_status, get_pending_story
from src.daemon import run_pipeline_once
from src.youtube.uploader import upload_video_via_playwright
from src.monitor import diagnose_failure_and_fix


class TestAdversarialM2_2(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_m2_2.db")
        init_db(db_path=self.db_path)

        self.cookies_path = os.path.join(self.test_dir, "test_cookies.json")
        with open(self.cookies_path, "w") as f:
            json.dump([{"name": "test_cookie", "value": "test_val", "domain": ".youtube.com", "path": "/"}], f)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. Adversarial Challenge: lane-governed pipeline parameters
    # -------------------------------------------------------------------------
    # El formato ya no se elige por flag: cada carril (config/lanes.json)
    # define su presupuesto de palabras y su duración mínima.
    # -------------------------------------------------------------------------
    @patch("src.pipeline.validate_prepublication")
    @patch("src.video.create_video_thumbnail")
    @patch("src.llm.curate_batch_json", return_value={
        "title": "Short Title",
        "script": "Había una vez en un pueblo lejano donde la oscuridad caía temprano y los secretos de la noche aterrorizaban a todos los habitantes que intentaban cruzar el bosque encantado en busca de respuestas.",
        "seo": {"description": "Esta es una descripción completa y detallada en español para el video de YouTube sobre historias de la vida real."}
    })
    @patch("src.llm.translate_title", side_effect=lambda x, *a, **k: x)
    @patch("src.llm.clean_title", side_effect=lambda x: x)
    @patch("src.llm.curate_script")
    @patch("src.tts.generate_audio")
    @patch("src.subtitles.create_subtitles")
    @patch("src.video.compose_video")
    @patch("src.drive.upload_to_drive_verified")
    @patch("src.youtube.uploader.upload_video")
    @patch("src.cleaner.verify_and_cleanup")
    @patch("src.scraper.fetch_reddit_stories")
    def test_short_lane_pipeline_parameters(
        self, mock_fetch, mock_cleanup, mock_yt, mock_drive, mock_compose, mock_subs, mock_audio, mock_curate, mock_clean_t, mock_trans_t, mock_curate_batch, mock_thumb, mock_val_prep
    ):
        """Verify the vertical SCP short lane passes its word budget and min_duration=0.0."""
        mock_val_prep.return_value.require_pass.return_value = None
        mock_fetch.return_value = []
        enqueue_story("story_short_1", "SCP-173: La Escultura", "Short content...", "http://example.com/1", channel="moku", db_path=self.db_path)
        
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
        mock_proof = DriveProof(file_id="drive_123", name="test.mp4", size_bytes=100, folder_id="folder123", exists=True)
        mock_drive.return_value = mock_proof
        mock_audio.side_effect = fake_audio
        mock_subs.side_effect = fake_subs
        mock_compose.side_effect = fake_compose
        mock_thumb.side_effect = fake_thumb
        mock_curate.return_value = "Había una vez en un pueblo lejano donde la oscuridad caía temprano y los secretos de la noche aterrorizaban a todos los habitantes que intentaban cruzar el bosque encantado en busca de respuestas."
        mock_yt.return_value = {"status": "SUCCESS", "url": "https://youtu.be/test12345"}

        res = run_pipeline_once(channel="moku", db_path=self.db_path, lane_id="moku-scp-shorts")

        self.assertEqual(res["status"], "SUCCESS")

        # Check curate_script called with the lane's word budget (min 160)
        mock_curate.assert_called_once()
        curate_kwargs = mock_curate.call_args[1]
        self.assertGreaterEqual(curate_kwargs.get("min_words"), 160)
        self.assertLess(curate_kwargs.get("min_words"), 300)

        # Check compose_video called with min_duration=0.0
        mock_compose.assert_called_once()
        compose_kwargs = mock_compose.call_args[1]
        self.assertEqual(compose_kwargs.get("min_duration"), 0.0)

    @patch("src.pipeline.validate_prepublication")
    @patch("src.video.create_video_thumbnail")
    @patch("src.llm.curate_batch_json", return_value={
        "title": "Short Title",
        "script": "Había una vez en un pueblo lejano donde la oscuridad caía temprano y los secretos de la noche aterrorizaban a todos los habitantes que intentaban cruzar el bosque encantado en busca de respuestas.",
        "seo": {"description": "Esta es una descripción completa y detallada en español para el video de YouTube sobre historias de la vida real."}
    })
    @patch("src.llm.translate_title", side_effect=lambda x, *a, **k: x)
    @patch("src.llm.clean_title", side_effect=lambda x: x)
    @patch("src.llm.curate_script")
    @patch("src.tts.generate_audio")
    @patch("src.subtitles.create_subtitles")
    @patch("src.video.compose_video")
    @patch("src.drive.upload_to_drive_verified")
    @patch("src.youtube.uploader.upload_video")
    @patch("src.cleaner.verify_and_cleanup")
    @patch("src.scraper.fetch_reddit_stories")
    def test_normal_mode_pipeline_parameters(
        self, mock_fetch, mock_cleanup, mock_yt, mock_drive, mock_compose, mock_subs, mock_audio, mock_curate, mock_clean_t, mock_trans_t, mock_curate_batch, mock_thumb, mock_val_prep
    ):
        """Verify that the horror long lane passes its word budget and min_duration=LONG_MIN_DURATION_SEC to compose_video."""
        mock_fetch.return_value = []
        enqueue_story("story_norm_1", "SCP-173: La Escultura", "Long content...", "http://example.com/2", channel="moku", db_path=self.db_path)
        
        def fake_audio(*args, **kwargs):
            from pathlib import Path
            out_path = args[1] if len(args) > 1 else kwargs.get("out_path", "/tmp/audio.wav")
            Path(out_path).write_bytes(b"WAV")
            return {"word_timestamps": [], "duration_sec": 610.0}

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
        mock_proof = DriveProof(file_id="drive_123", name="test.mp4", size_bytes=100, folder_id="folder123", exists=True)
        mock_audio.side_effect = fake_audio
        mock_subs.side_effect = fake_subs
        mock_compose.side_effect = fake_compose
        mock_thumb.side_effect = fake_thumb
        mock_drive.return_value = mock_proof
        mock_curate.return_value = "Esta es una historia misteriosa en español para narrar en el canal Moku. " * 350
        mock_yt.return_value = {"status": "SUCCESS", "url": "https://youtu.be/norm12345"}

        res = run_pipeline_once(channel="moku", db_path=self.db_path, lane_id="moku-horror-long")

        self.assertEqual(res["status"], "SUCCESS")

        # Check curate_script called with the horror long lane's word budget
        curate_kwargs = mock_curate.call_args[1]
        self.assertEqual(curate_kwargs.get("min_words"), max(LONG_MIN_WORDS, 2600))

        # Check compose_video called with min_duration=120.0
        compose_kwargs = mock_compose.call_args[1]
        from src.config import LONG_MIN_DURATION_SEC
        self.assertEqual(compose_kwargs.get("min_duration"), float(LONG_MIN_DURATION_SEC))

    @patch("src.pipeline.validate_prepublication")
    @patch("src.video.create_video_thumbnail")
    @patch("src.llm.curate_batch_json", return_value={
        "title": "Short Title",
        "script": "Había una vez en un pueblo lejano donde la oscuridad caía temprano y los secretos de la noche aterrorizaban a todos los habitantes que intentaban cruzar el bosque encantado en busca de respuestas.",
        "seo": {"description": "Esta es una descripción completa y detallada en español para el video de YouTube sobre historias de la vida real."}
    })
    @patch("src.llm.translate_title", side_effect=lambda x, *a, **k: x)
    @patch("src.llm.clean_title", side_effect=lambda x: x)
    @patch("src.llm.curate_script")
    @patch("src.tts.generate_audio")
    @patch("src.subtitles.create_subtitles")
    @patch("src.video.compose_video")
    @patch("src.drive.upload_to_drive_verified")
    @patch("src.youtube.uploader.upload_video")
    @patch("src.cleaner.verify_and_cleanup")
    @patch("src.scraper.fetch_reddit_stories")
    def test_short_lane_does_not_consume_additional_stories(
        self, mock_fetch, mock_cleanup, mock_yt, mock_drive, mock_compose, mock_subs, mock_audio, mock_curate, mock_clean_t, mock_trans_t, mock_curate_batch, mock_thumb, mock_val_prep
    ):
        """Verify a directed run processes only the claimed story and leaves other pending stories untouched."""
        mock_val_prep.return_value.require_pass.return_value = None
        mock_fetch.return_value = []
        enqueue_story("story_s1", "SCP-173: La Escultura", "Short text", "http://ex.com/1", channel="moku", db_path=self.db_path)
        enqueue_story("story_s2", "SCP-173: La Escultura 2", "Short text 2", "http://ex.com/2", channel="moku", db_path=self.db_path)
        enqueue_story("story_s3", "SCP-173: La Escultura 3", "Short text 3", "http://ex.com/3", channel="moku", db_path=self.db_path)

        def fake_audio(*args, **kwargs):
            from pathlib import Path
            out_path = args[1] if len(args) > 1 else kwargs.get("out_path", "/tmp/audio.wav")
            Path(out_path).write_bytes(b"WAV")
            return {"word_timestamps": [], "duration_sec": 15.0}

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
        mock_proof = DriveProof(file_id="drive_123", name="test.mp4", size_bytes=100, folder_id="folder123", exists=True)
        mock_audio.side_effect = fake_audio
        mock_subs.side_effect = fake_subs
        mock_compose.side_effect = fake_compose
        mock_thumb.side_effect = fake_thumb
        mock_drive.return_value = mock_proof
        mock_curate.return_value = "Había una vez en un pueblo lejano donde la oscuridad caía temprano y los secretos de la noche aterrorizaban a todos los habitantes que intentaban cruzar el bosque encantado en busca de respuestas."
        mock_yt.return_value = {"status": "SUCCESS", "url": "https://youtu.be/short"}

        res = run_pipeline_once(channel="moku", db_path=self.db_path, lane_id="moku-scp-shorts")

        self.assertEqual(res["status"], "SUCCESS")

        # Verify story_s2 and story_s3 are still PENDING
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT story_id, status FROM stories WHERE story_id IN ('story_s2', 'story_s3')")
        statuses = dict(cursor.fetchall())
        conn.close()

        self.assertEqual(statuses["story_s2"], "PENDING")
        self.assertEqual(statuses["story_s3"], "PENDING")

    # -------------------------------------------------------------------------
    # 2. Adversarial Challenge: Playwright browser cleanup & zero zombie processes
    # -------------------------------------------------------------------------
    @patch("src.youtube.uploader.is_test_environment", return_value=False)
    @patch("src.youtube.uploader.upload_video_via_playwright_ts", side_effect=RuntimeError("Simulated network timeout during upload"))
    def test_playwright_cleanup_on_simulated_exception(self, mock_ts, mock_is_test):
        """Simulate an exception during Playwright upload and verify exception is propagated without process leaks."""
        video_dummy = os.path.join(self.test_dir, "dummy_video.mp4")
        with open(video_dummy, "wb") as f:
            f.write(b"0" * 1024)

        with self.assertRaises(RuntimeError) as ctx:
            upload_video_via_playwright(video_dummy, "Test Title", "Test Desc", tags=["test"], cookies_path=self.cookies_path)
        self.assertIn("Simulated network timeout", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 3. Adversarial Challenge: monitor_publication.py auto-repair
    # -------------------------------------------------------------------------
    @patch("src.monitor._service_state", return_value="failed")
    def test_monitor_auto_repairs_transient_errors(self, mock_svc):
        """Verify that transient non-auth errors report diagnosis without requiring manual intervention."""
        enqueue_story("transient_1", "Title 1", "Content 1", "url1", channel="moku", db_path=self.db_path)
        update_story_status("transient_1", "RETRYABLE_FAILED", error_msg="FFmpeg error: Non-zero exit code 1", db_path=self.db_path)

        enqueue_story("transient_2", "Title 2", "Content 2", "url2", channel="aelithia", db_path=self.db_path)
        update_story_status("transient_2", "RETRYABLE_FAILED", error_msg="ConnectionResetError: Connection reset by peer", db_path=self.db_path)

        res = diagnose_failure_and_fix(db_path=self.db_path)

        self.assertFalse(res["manual_intervention_required"])

    @patch("src.monitor._service_state", return_value="failed")
    def test_monitor_suspends_channel_on_auth_failure(self, mock_svc):
        """Verify that Google 2FA / auth errors flag manual_intervention_required in monitor diagnostic."""
        from src.core.repository import QueueRepository
        enqueue_story("auth_fail_1", "Title Auth", "Content", "url", channel="moku", db_path=self.db_path)
        QueueRepository(self.db_path).set_status("auth_fail_1", "PERMANENT_FAILED", error_code="authentication", error_detail="Google Identity Verification (2FA) blocked the upload.")

        res = diagnose_failure_and_fix(db_path=self.db_path)

        self.assertTrue(res["manual_intervention_required"])

    @patch("src.monitor._service_state", return_value="failed")
    def test_monitor_suspends_channel_on_account_termination(self, mock_svc):
        """Verify that account termination error flags manual_intervention_required in monitor diagnostic."""
        from src.core.repository import QueueRepository
        enqueue_story("term_1", "Title Term", "Content", "url", channel="aelithia", db_path=self.db_path)
        QueueRepository(self.db_path).set_status("term_1", "PERMANENT_FAILED", error_code="manual_intervention", error_detail="YouTube account has been terminated.")

        res = diagnose_failure_and_fix(db_path=self.db_path)

        self.assertTrue(res["manual_intervention_required"])


if __name__ == "__main__":
    unittest.main()
