import os
import json
import tempfile
import unittest
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock

from src.youtube.uploader import (
    upload_video,
    upload_video_via_api,
    upload_video_via_playwright,
    format_cookies_for_playwright,
)


@pytest.mark.unit
class TestYouTubeUploader(unittest.TestCase):
    """Direct-uploader scenarios with mock isolation."""
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dummy_video = os.path.join(self.temp_dir.name, "sample_video.mp4")
        with open(self.dummy_video, "wb") as f:
            f.write(b"SAMPLE_VIDEO_BYTES_DATA")

        self.dummy_thumb = os.path.join(self.temp_dir.name, "thumbnail.jpg")
        with open(self.dummy_thumb, "wb") as f:
            f.write(b"SAMPLE_THUMBNAIL_BYTES")

        self.dummy_token = os.path.join(self.temp_dir.name, "youtube_token.json")
        with open(self.dummy_token, "w", encoding="utf-8") as f:
            json.dump({"token": "valid_token", "refresh_token": "valid_refresh"}, f)

        self.dummy_cookies_file = os.path.join(self.temp_dir.name, "cookies.json")
        self.sample_cookies = [
            {
                "name": "APISID",
                "value": "sample_val_1",
                "domain": "youtube.com",
                "path": "/",
                "expirationDate": 1800000000.123,
                "sameSite": "unspecified",
                "secure": False,
                "httpOnly": False,
            },
            {
                "name": "LOGIN_INFO",
                "value": "sample_val_2",
                "domain": ".youtube.com",
                "path": "/",
                "expirationDate": 1800000000.456,
                "sameSite": "no_restriction",
                "secure": True,
                "httpOnly": True,
            },
            {
                "name": "STRICT_COOKIE",
                "value": "sample_val_3",
                "domain": "youtube.com",
                "path": "/",
                "sameSite": "strict",
                "secure": True,
                "httpOnly": True,
            },
        ]
        with open(self.dummy_cookies_file, "w", encoding="utf-8") as f:
            json.dump(self.sample_cookies, f)

        self.env_patcher = patch.dict(os.environ, {
            "TEST_MODE": "0",
            "MOCK_YOUTUBE_UPLOAD": "0",
            "YOUTUBE_TOKEN_PATH": self.dummy_token,
            "COOKIES_PATH": self.dummy_cookies_file,
            "HORROR_COOKIES_PATH": self.dummy_cookies_file,
            "DRAMA_COOKIES_PATH": self.dummy_cookies_file,
            "CHANNEL_COOKIES_PATH": self.dummy_cookies_file,
            "CHANNEL_YOUTUBE_TOKEN_PATH": self.dummy_token,
            "HORROR_YOUTUBE_TOKEN_PATH": self.dummy_token,
        })
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()
        self.temp_dir.cleanup()

    def test_format_cookies_for_playwright(self):
        """Test cookie normalization for Playwright context.add_cookies()."""
        formatted = format_cookies_for_playwright(self.sample_cookies)
        self.assertEqual(len(formatted), 3)

        c1 = formatted[0]
        self.assertEqual(c1["name"], "APISID")
        self.assertEqual(c1["expires"], 1800000000.123)
        self.assertEqual(c1["sameSite"], "Lax")
        self.assertTrue(c1["domain"].startswith("."))

        c2 = formatted[1]
        self.assertEqual(c2["name"], "LOGIN_INFO")
        self.assertEqual(c2["expires"], 1800000000.456)
        self.assertEqual(c2["sameSite"], "None")

        c3 = formatted[2]
        self.assertEqual(c3["name"], "STRICT_COOKIE")
        self.assertEqual(c3["sameSite"], "Strict")

    def test_format_cookies_edge_cases(self):
        """Test format_cookies_for_playwright with invalid or non-list entries."""
        self.assertEqual(format_cookies_for_playwright("not a list"), [])
        bad_cookies = [None, "invalid", {}, {"name": "only_name"}]
        self.assertEqual(format_cookies_for_playwright(bad_cookies), [])

    @patch("src.youtube.uploader._verify_uploaded_video")
    @patch("googleapiclient.discovery.build")
    @patch("subprocess.run")
    @patch("os.path.exists", return_value=True)
    def test_strategy_a_api_success(self, mock_exists, mock_run, mock_build, mock_verify):
        """Test Strategy A API upload when API credentials are set."""
        mock_run.return_value = MagicMock(stdout="mock_token", returncode=0)

        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_insert = mock_service.videos().insert
        mock_insert.return_value.execute.return_value = {"id": "yt_api_123"}
        mock_verify.return_value = {
            "snippet": {"title": "API Title", "description": "API Description", "channelId": "UC_TEST"},
            "status": {"privacyStatus": "public"},
        }

        res = upload_video_via_api(
            self.dummy_video, "API Title", "API Description", ["tag1"],
            token_path=self.dummy_token,
            thumbnail_path=self.dummy_thumb,
        )
        self.assertIn(res["status"], ["SUCCESS", "PUBLISHED"])
        self.assertEqual(res["method"], "API")
        self.assertEqual(res["video_id"], "yt_api_123")

    @patch("subprocess.run", side_effect=Exception("no gcloud"))
    @patch("os.path.exists", return_value=False)
    def test_strategy_a_api_missing_token_raises_runtime_error(self, mock_exists, mock_run):
        """Test Strategy A raises RuntimeError when API credentials are absent."""
        with self.assertRaises(RuntimeError):
            upload_video_via_api(
                self.dummy_video, "API Title", "API Description", ["tag1"],
                thumbnail_path=self.dummy_thumb,
            )

    def test_strategy_a_missing_video_file(self):
        """Test Strategy A raises FileNotFoundError on non-existent video file."""
        non_existent = os.path.join(self.temp_dir.name, "missing.mp4")
        with self.assertRaises(FileNotFoundError):
            upload_video_via_api(non_existent, "Title", "Desc", ["tag"])

    @patch("src.youtube.uploader.upload_video_via_api")
    def test_hybrid_uploader_api_success(self, mock_api):
        """Test hybrid upload_video using Strategy A when API token is available."""
        mock_api.return_value = {"status": "SUCCESS", "method": "API", "video_id": "yt_api_123"}
        res = upload_video(self.dummy_video, "Title", "Desc")
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["method"], "API")

    @patch("src.youtube.uploader.upload_video_via_api", side_effect=RuntimeError("API failed"))
    @patch("src.youtube.uploader.upload_video_via_playwright")
    def test_hybrid_uploader_fallback_to_strategy_b(self, mock_pw, mock_api):
        """Test hybrid upload_video falling back to Strategy B when API fails."""
        mock_pw.return_value = {"status": "SUCCESS", "method": "PLAYWRIGHT", "video_id": "yt_pw_123"}
        res = upload_video(
            self.dummy_video,
            "Fallback Title",
            "Fallback Desc",
            cookies_path=self.dummy_cookies_file,
        )
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["method"], "PLAYWRIGHT")

    def test_hybrid_uploader_default_tags(self):
        """Test default tags assignment in upload_video when tags is None."""
        with patch("src.youtube.uploader.upload_video_via_api") as mock_api:
            mock_api.return_value = {"status": "SUCCESS", "method": "API", "video_id": "yt_1"}
            upload_video(self.dummy_video, "Title", "Desc", tags=None)
            from src.branding import get_channel_branding
            from src.config import get_channel_settings
            expected_token_path = os.environ.get("YOUTUBE_TOKEN_PATH", str(get_channel_settings("horror").youtube_token_path))
            mock_api.assert_called_once_with(
                self.dummy_video,
                "Title",
                "Desc",
                get_channel_branding("horror").tags,
                thumbnail_path=self.dummy_thumb,
                token_path=expected_token_path,
                channel="horror",
                expected_channel_id=get_channel_settings("horror").expected_youtube_channel_id,
                on_video_id=None,
            )

    def test_playwright_upload_success(self):
        """Test upload_video_via_playwright with valid cookies and video file."""
        with patch("src.youtube.uploader.session.is_test_environment", return_value=True):
            res = upload_video_via_playwright(
                self.dummy_video,
                "PW Title",
                "PW Desc",
                ["horror"],
                cookies_path=self.dummy_cookies_file,
            )
            self.assertEqual(res["status"], "TEST_MOCK")
            self.assertEqual(res["method"], "PLAYWRIGHT")

    def test_playwright_upload_missing_video_file(self):
        """Test upload_video_via_playwright raises FileNotFoundError if video is missing."""
        non_existent = os.path.join(self.temp_dir.name, "missing_video.mp4")
        with self.assertRaises(FileNotFoundError):
            upload_video_via_playwright(
                non_existent, "Title", "Desc", ["tag"], cookies_path=self.dummy_cookies_file
            )

    def test_playwright_upload_missing_cookies_file(self):
        """Test upload_video_via_playwright raises FileNotFoundError if cookies file missing."""
        non_existent_cookies = os.path.join(self.temp_dir.name, "no_cookies.json")
        with self.assertRaises(FileNotFoundError):
            upload_video_via_playwright(
                self.dummy_video, "Title", "Desc", ["tag"], cookies_path=non_existent_cookies
            )

    def test_playwright_upload_invalid_json_cookies(self):
        """Test upload_video_via_playwright raises ValueError on malformed JSON cookies."""
        bad_json_file = os.path.join(self.temp_dir.name, "bad.json")
        with open(bad_json_file, "w", encoding="utf-8") as f:
            f.write("{invalid_json: true")

        with self.assertRaises(ValueError):
            upload_video_via_playwright(
                self.dummy_video, "Title", "Desc", ["tag"], cookies_path=bad_json_file
            )

    def test_playwright_upload_invalid_schema_cookies(self):
        """Test upload_video_via_playwright raises ValueError when cookies is not a list."""
        non_list_cookies_file = os.path.join(self.temp_dir.name, "non_list.json")
        with open(non_list_cookies_file, "w", encoding="utf-8") as f:
            json.dump({"cookies": "not_a_list"}, f)

        with self.assertRaises(ValueError):
            upload_video_via_playwright(
                self.dummy_video, "Title", "Desc", ["tag"], cookies_path=non_list_cookies_file
            )

    def test_mock_youtube_upload_env_variable(self):
        """Test mock response handling with MOCK_YOUTUBE_UPLOAD environment variable."""
        with patch.dict(os.environ, {"MOCK_YOUTUBE_UPLOAD": "1"}):
            res = upload_video_via_playwright(
                self.dummy_video,
                "Mock Title",
                "Mock Desc",
                ["mock"],
                cookies_path=self.dummy_cookies_file,
            )
            self.assertEqual(res["status"], "TEST_MOCK")
            self.assertEqual(res["method"], "PLAYWRIGHT")

    @patch("src.youtube.uploader.upload_video_via_playwright")
    @patch("src.youtube.uploader.upload_video_via_api")
    def test_channel_separation_bypasses_missing_token_to_playwright(self, mock_api, mock_pw):
        """Test that channel without API token bypasses Strategy A and uses Strategy B directly."""
        mock_pw.return_value = {"status": "SUCCESS", "method": "PLAYWRIGHT", "video_id": "yt_pw_chan2"}
        res = upload_video(
            self.dummy_video,
            "Soy El Malo Title",
            "Soy El Malo Desc",
            cookies_path=self.dummy_cookies_file,
            channel="soy_el_malo",
            token_path=os.path.join(self.temp_dir.name, "non_existent_token.json")
        )
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["method"], "PLAYWRIGHT")
        mock_api.assert_not_called()
        mock_pw.assert_called_once()

    @patch("src.youtube.uploader.upload_video_via_playwright")
    def test_channel_cookies_resolution_when_unspecified(self, mock_pw):
        """Test that upload_video automatically resolves channel cookies when channel='soy_el_malo'."""
        mock_pw.return_value = {"status": "SUCCESS", "method": "PLAYWRIGHT", "video_id": "yt_pw_chan2"}
        res = upload_video(
            self.dummy_video,
            "Soy El Malo Title",
            "Soy El Malo Desc",
            channel="soy_el_malo",
            cookies_path=self.dummy_cookies_file,
            token_path=os.path.join(self.temp_dir.name, "non_existent_token.json")
        )
        self.assertEqual(res["status"], "SUCCESS")
        mock_pw.assert_called_once()

    def test_resolve_google_credentials_reads_exact_sa_key_path(self):
        """Test resolve_google_credentials reads exact sa_key_path provided instead of forcing youtube_token.json."""
        from src.config import resolve_google_credentials
        custom_token_file = os.path.join(self.temp_dir.name, "custom_channel_token.json")
        token_payload = {
            "access_token": "custom_access_token_abc",
            "refresh_token": "custom_refresh_token_xyz",
            "client_id": "custom_client_id",
            "client_secret": "custom_client_secret"
        }
        with open(custom_token_file, "w", encoding="utf-8") as f:
            json.dump(token_payload, f)

        creds = resolve_google_credentials(sa_key_path=custom_token_file)
        self.assertIsNotNone(creds)
        self.assertEqual(creds.token, "custom_access_token_abc")
        self.assertEqual(creds.refresh_token, "custom_refresh_token_xyz")

    @patch("src.youtube.uploader._verify_uploaded_video")
    @patch("googleapiclient.discovery.build")
    def test_upload_video_via_api_respects_token_path_parameter(self, mock_build, mock_verify):
        """Test upload_video_via_api loads token from token_path parameter."""
        custom_token = os.path.join(self.temp_dir.name, "chan2_token.json")
        token_data = {
            "access_token": "chan2_access_token_123",
            "refresh_token": "chan2_refresh_token_456",
            "client_id": "client_id_test",
            "client_secret": "client_secret_test"
        }
        with open(custom_token, "w", encoding="utf-8") as f:
            json.dump(token_data, f)

        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_insert = mock_service.videos().insert
        mock_insert.return_value.execute.return_value = {"id": "yt_api_token_path"}
        mock_verify.return_value = {
            "snippet": {"title": "Token Path Title", "description": "Token Path Desc", "channelId": "UC_TEST"},
            "status": {"privacyStatus": "public"},
        }

        res = upload_video_via_api(
            self.dummy_video, "Token Path Title", "Token Path Desc", ["tag1"],
            token_path=custom_token,
            thumbnail_path=self.dummy_thumb,
        )
        self.assertIn(res["status"], ["SUCCESS", "PUBLISHED"])
        self.assertEqual(res["video_id"], "yt_api_token_path")

    @patch("src.core.cookies.validate_youtube_session_cookies")
    @patch("src.youtube.uploader.session.is_test_environment", return_value=False)
    @patch("src.youtube.uploader.session.sync_playwright")
    def test_playwright_upload_browser_close_on_exception(self, mock_sync_pw, mock_is_test, mock_validate_cookies):
        """Test upload_video_via_playwright closes browser in finally block when an exception occurs."""
        from src.core.cookies import SessionHealthResult, SessionStatus
        mock_validate_cookies.return_value = SessionHealthResult(status=SessionStatus.HEALTHY, detail="OK", total_cookies=3)
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_p = MagicMock()
        mock_p.chromium.launch_persistent_context.return_value = mock_context
        mock_context.pages = [mock_page]
        mock_page.goto.side_effect = RuntimeError("Playwright navigation failed")

        with patch.dict(os.environ, {"MOCK_YOUTUBE_UPLOAD": ""}):
            mock_sync_pw.return_value.__enter__.return_value = mock_p
            with self.assertRaises(RuntimeError):
                upload_video_via_playwright(
                    self.dummy_video, "Title", "Desc", ["tag"], cookies_path=self.dummy_cookies_file
                )

            mock_context.close.assert_called()


@pytest.mark.unit
class TestTokenResolutionAndPreflight(unittest.TestCase):
    """Tests for channel token resolution and preflight checks in src/youtube/uploader/api.py."""

    def test_resolve_channel_token_path_canonical_and_fallback(self):
        from src.youtube.uploader.api import resolve_channel_token_path
        with tempfile.TemporaryDirectory() as td:
            base_dir = Path(td)
            tokens_dir = base_dir / "secrets" / "tokens"
            tokens_dir.mkdir(parents=True)

            # Test canonical horror token exists
            horror_token = tokens_dir / "horror.json"
            horror_token.write_text('{"token": "horror_123"}', encoding="utf-8")

            with patch("src.youtube.uploader.api.BASE_DIR", base_dir), \
                 patch("src.core.google_auth.BASE_DIR", base_dir):
                path = resolve_channel_token_path("horror")
                self.assertTrue(path.endswith("horror.json"))

            # Test fallback to moku.json when horror.json is absent
            horror_token.unlink()
            moku_token = tokens_dir / "moku.json"
            moku_token.write_text('{"token": "moku_fallback"}', encoding="utf-8")

            with patch("src.youtube.uploader.api.BASE_DIR", base_dir), \
                 patch("src.core.google_auth.BASE_DIR", base_dir):
                fallback_path = resolve_channel_token_path("horror")
                self.assertTrue(fallback_path.endswith("moku.json"))

    def test_preflight_youtube_api_success(self):
        from src.youtube.uploader.api import preflight_youtube_api
        mock_service = MagicMock()
        mock_service.channels().list().execute.return_value = {
            "items": [{"id": "UC_CANONICAL_123", "snippet": {"title": "Expedientes de Terror"}}]
        }
        with patch("src.youtube.uploader.api._youtube_service", return_value=mock_service):
            info = preflight_youtube_api(
                channel="horror",
                token_path="/dummy/token.json",
                expected_channel_id="UC_CANONICAL_123",
            )
            self.assertEqual(info["channel_id"], "UC_CANONICAL_123")
            self.assertEqual(info["title"], "Expedientes de Terror")

    def test_preflight_youtube_api_mismatch(self):
        from src.youtube.uploader.api import preflight_youtube_api
        mock_service = MagicMock()
        mock_service.channels().list().execute.return_value = {
            "items": [{"id": "UC_WRONG_CHAN", "snippet": {"title": "Wrong"}}]
        }
        with patch("src.youtube.uploader.api._youtube_service", return_value=mock_service):
            with self.assertRaises(RuntimeError) as ctx:
                preflight_youtube_api(
                    channel="horror",
                    token_path="/dummy/token.json",
                    expected_channel_id="UC_CANONICAL_123",
                )
            self.assertIn("no pertenece", str(ctx.exception).lower())

    def test_preflight_youtube_api_missing_expected(self):
        from src.youtube.uploader.api import preflight_youtube_api
        with self.assertRaises(RuntimeError) as ctx:
            preflight_youtube_api(
                channel="horror",
                token_path="/dummy/token.json",
                expected_channel_id="",
            )
        self.assertIn("channelid", str(ctx.exception).lower())


@pytest.mark.unit
class TestPlaywright6StagesLifecycle(unittest.TestCase):
    """Tests asserting the 6 discrete linear Playwright stage functions."""

    def test_stage1_init_playwright_context(self):
        from src.youtube.uploader.session import _init_playwright_context
        mock_p = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_p.chromium.launch_persistent_context.return_value = mock_context
        mock_context.pages = [mock_page]

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump([{"name": "LOGIN_INFO", "value": "xyz", "domain": ".youtube.com", "path": "/"}], f)
            cookie_path = f.name

        try:
            browser, ctx, page = _init_playwright_context(
                mock_p,
                cookies_path=cookie_path,
                channel="horror",
                headless=True,
            )
            self.assertIs(ctx, mock_context)
            self.assertIs(page, mock_page)
            mock_p.chromium.launch_persistent_context.assert_called_once()
        finally:
            if os.path.exists(cookie_path):
                os.remove(cookie_path)

    def test_stage2_navigate_and_check_auth(self):
        from src.youtube.uploader.session import _navigate_and_check_auth
        mock_page = MagicMock()
        mock_page.url = "https://studio.youtube.com/channel/UC123"
        mock_page.locator.return_value.inner_text.return_value = "expedientes horror studio"
        mock_page.locator.return_value.count.return_value = 0

        # Success case
        _navigate_and_check_auth(
            mock_page,
            channel="horror",
            expected_channel_id="UC123",
            expected_identity="horror|expedientes",
        )
        mock_page.goto.assert_called_once()

        # Auth failure case (redirected to Google login)
        mock_page.url = "https://accounts.google.com/signin/v2"
        with self.assertRaises(RuntimeError) as ctx:
            _navigate_and_check_auth(
                mock_page,
                channel="horror",
                expected_channel_id="UC123",
                expected_identity="horror",
            )
        self.assertIn("authentication failed", str(ctx.exception).lower())

        # Identity mismatch case
        mock_page.url = "https://studio.youtube.com/channel/UC123"
        mock_page.locator.return_value.inner_text.return_value = "unrelated other channel"
        with self.assertRaises(RuntimeError) as ctx:
            _navigate_and_check_auth(
                mock_page,
                channel="horror",
                expected_channel_id="UC123",
                expected_identity="horror",
            )
        self.assertIn("no confirmó la identidad", str(ctx.exception).lower())

    def test_stage3_upload_file_payload_success(self):
        from src.youtube.uploader.session import _upload_file_payload
        mock_page = MagicMock()
        mock_file_input = MagicMock()
        mock_page.locator.return_value.first = mock_file_input
        # No 2FA dialog
        mock_page.locator.return_value.count.return_value = 0

        _upload_file_payload(mock_page, "/dummy/video.mp4")
        mock_file_input.set_input_files.assert_called_once_with("/dummy/video.mp4")

    def test_stage3_upload_file_payload_2fa_blocked(self):
        from src.youtube.uploader.session import _upload_file_payload, PlaywrightPrePublishError
        mock_page = MagicMock()
        mock_file_input = MagicMock()
        
        def locator_side_effect(selector):
            mock_loc = MagicMock()
            if 'input[type="file"]' in selector:
                mock_loc.first = mock_file_input
                mock_loc.count.return_value = 1
                return mock_loc
            if "Verifica tu identidad" in selector:
                mock_loc.count.return_value = 1
                return mock_loc
            mock_loc.count.return_value = 0
            return mock_loc

        mock_page.locator.side_effect = locator_side_effect
        with self.assertRaises(PlaywrightPrePublishError) as ctx:
            _upload_file_payload(mock_page, "/dummy/video.mp4")
        self.assertIn("google identity verification", str(ctx.exception).lower())

    def test_stage4_fill_video_metadata(self):
        from src.youtube.uploader.session import _fill_video_metadata
        mock_page = MagicMock()
        mock_title_box = MagicMock()
        mock_desc_box = MagicMock()
        mock_thumb_input = MagicMock()

        def locator_side_effect(selector):
            mock_loc = MagicMock()
            if "#textbox" in selector:
                mock_loc.first = mock_title_box
                mock_loc.nth.return_value = mock_desc_box
                return mock_loc
            if 'input[type="file"]' in selector:
                mock_loc.count.return_value = 1
                mock_loc.first = mock_thumb_input
                return mock_loc
            if "VIDEO_MADE_FOR_KIDS_NOT_MFK" in selector:
                mock_loc.count.return_value = 1
                mock_loc.first.get_attribute.return_value = "true"
                return mock_loc
            mock_loc.count.return_value = 0
            return mock_loc

        mock_page.locator.side_effect = locator_side_effect

        with tempfile.NamedTemporaryFile("wb", suffix=".jpg", delete=False) as f:
            f.write(b"thumb_data")
            thumb_path = f.name

        try:
            _fill_video_metadata(
                mock_page,
                title="Stage 4 Title",
                description="Stage 4 Description",
                thumbnail_path=thumb_path,
            )
            mock_title_box.fill.assert_called_once_with("Stage 4 Title")
            mock_desc_box.fill.assert_called_once_with("Stage 4 Description")
            mock_thumb_input.set_input_files.assert_called_once_with(thumb_path)
        finally:
            if os.path.exists(thumb_path):
                os.remove(thumb_path)

    def test_stage5_select_visibility_and_publish(self):
        from src.youtube.uploader.session import _select_visibility_and_publish
        mock_page = MagicMock()

        def locator_side_effect(selector):
            mock_loc = MagicMock()
            if "PUBLIC" in selector or "Público" in selector:
                mock_loc.count.return_value = 1
                mock_loc.first.get_attribute.return_value = "true"
                return mock_loc
            if "#next-button" in selector or "#done-button" in selector:
                mock_loc.count.return_value = 1
                mock_loc.first.is_visible.return_value = True
                return mock_loc
            mock_loc.count.return_value = 0
            return mock_loc

        mock_page.locator.side_effect = locator_side_effect
        _select_visibility_and_publish(mock_page, visibility="PUBLIC")
        # Should click next steps and done
        self.assertTrue(mock_page.locator.called)

    def test_stage6_await_processing_and_extract_videoid(self):
        from src.youtube.uploader.session import _await_processing_and_extract_videoid
        mock_page = MagicMock()
        mock_link = MagicMock()
        mock_link.first.get_attribute.return_value = "https://youtu.be/video_xyz_789"
        mock_page.locator.return_value.count.return_value = 1
        mock_page.locator.return_value.first.get_attribute.return_value = "https://youtu.be/video_xyz_789"

        vid_id, final_url = _await_processing_and_extract_videoid(mock_page)
        self.assertEqual(vid_id, "video_xyz_789")
        self.assertEqual(final_url, "https://youtu.be/video_xyz_789")


@pytest.mark.unit
class TestPublicationClaimGate(unittest.TestCase):
    """Tests for 2PC atomic publication lease claim, verify, and consume."""

    def test_publication_gate_requires_job_id_in_prod(self):
        from src.youtube.uploader import upload_video
        dummy_video = "/tmp/dummy_video_gate.mp4"
        with open(dummy_video, "wb") as f:
            f.write(b"data")

        try:
            with patch("src.youtube.uploader.is_test_environment", return_value=False):
                with self.assertRaises(RuntimeError) as ctx:
                    upload_video(dummy_video, "Title", "Desc", job_id=None)
                self.assertIn("Publication gate requires job_id", str(ctx.exception))
        finally:
            if os.path.exists(dummy_video):
                os.remove(dummy_video)

    def test_claim_and_consume_publication_gate(self):
        from src.youtube.uploader.claim_gate import _claim_publication_gate, _consume_publication_claim
        mock_store = MagicMock()
        mock_job = MagicMock()
        mock_job.status = "APPROVED"
        mock_store.get_job.return_value = mock_job

        mock_gate = MagicMock()

        with patch("review.ReviewStateStore", return_value=mock_store), \
             patch("review.PublicationGate", return_value=mock_gate):
            job_id, ver, gate = _claim_publication_gate("/tmp/vid.mp4", job_id="job-101", version=1)
            self.assertEqual(job_id, "job-101")
            self.assertEqual(ver, 1)
            mock_gate.verify_and_claim_publication.assert_called_once_with("job-101", 1, "/tmp/vid.mp4")

            # Consume claim
            normalized = {"status": "PUBLISHED", "verified": True, "video_id": "vid_999", "url": "https://youtu.be/vid_999"}
            _consume_publication_claim(gate, job_id, ver, normalized)
            mock_gate.confirm_publication_success.assert_called_once_with(
                "job-101", 1, published_id="vid_999", published_url="https://youtu.be/vid_999"
            )

    def test_verify_publication_claim_gate_db(self):
        from src.youtube.uploader.claim_gate import verify_publication_claim_gate
        import sqlite3
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            with sqlite3.connect(db_path) as conn:
                conn.execute("CREATE TABLE review_jobs (job_id TEXT, status TEXT, published_id TEXT)")
                conn.execute("INSERT INTO review_jobs VALUES ('job-202', 'PUBLISHED', 'v123')")

            self.assertTrue(verify_publication_claim_gate(db_path, "job-202", "v123"))
            self.assertFalse(verify_publication_claim_gate(db_path, "job-nonexistent", "v123"))
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)


@pytest.mark.unit
class TestUploaderFacadeAndFunctionBudgets(unittest.TestCase):
    """Verifies facade exports, contract markers, and function line budgets."""

    def test_facade_reexports_all_symbols(self):
        import src.youtube.uploader as uploader_mod
        expected_symbols = [
            "upload_video",
            "upload_video_via_api",
            "upload_video_via_playwright",
            "upload_video_via_playwright_ts",
            "preflight_youtube_api",
            "verify_youtube_credentials_preflight",
            "verify_existing_video_via_api",
            "_verify_uploaded_video",
            "_youtube_service",
            "resolve_channel_token_path",
            "validate_title_content_alignment",
            "format_cookies_for_playwright",
            "_safe_preupload_failure",
            "_click_dialog_button",
            "click_next",
            "click_done",
            "_get_playwright_pids",
            "_claim_publication_gate",
            "_consume_publication_claim",
            "verify_publication_claim_gate",
            "PlaywrightPrePublishError",
            "_normalize_upload_result",
        ]
        for sym in expected_symbols:
            self.assertTrue(
                hasattr(uploader_mod, sym),
                f"Facade missing expected symbol: {sym}"
            )
            self.assertIn(
                sym,
                uploader_mod.__all__,
                f"Symbol {sym} missing from __all__"
            )

    def test_contract_markers_present(self):
        root = Path(__file__).resolve().parents[2]
        facade_content = (root / "src" / "youtube" / "uploader.py").read_text(encoding="utf-8")
        package_content = (root / "src" / "youtube" / "uploader" / "__init__.py").read_text(encoding="utf-8")
        alias_content = (root / "src" / "youtube_uploader.py").read_text(encoding="utf-8")

        for content in (facade_content, package_content, alias_content):
            self.assertIn("PublicationGate", content)
            self.assertIn("Publication gate requires job_id", content)
            self.assertIn("single atomic publication claim", content)

    def test_function_length_under_100_lines(self):
        """Uphold Rule 8.1 budget: all functions in src/youtube/uploader/ <= ~100 executable lines."""
        import ast
        root = Path(__file__).resolve().parents[2]
        uploader_dir = root / "src" / "youtube" / "uploader"
        self.assertTrue(uploader_dir.is_dir(), "src/youtube/uploader directory must exist")

        violations = []
        for py_file in uploader_dir.glob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    lines = node.end_lineno - node.lineno + 1
                    # Budget is ~100 executable lines
                    if lines > 100:
                        violations.append(f"{py_file.name}:{node.name} has {lines} lines (>100)")

        self.assertEqual(violations, [], f"Functions exceeded line budget: {violations}")


if __name__ == "__main__":
    unittest.main()

