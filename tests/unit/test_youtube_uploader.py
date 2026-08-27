import os
import json
import tempfile
import unittest
import pytest
from unittest.mock import patch, MagicMock

from src.youtube.uploader import (
    upload_video,
    upload_video_via_api,
    upload_video_via_playwright,
    format_cookies_for_playwright,
)


@pytest.mark.live
class TestYouTubeUploader(unittest.TestCase):
    """Legacy direct-uploader scenarios, opt-in only.

    The production adapter now requires a canonical channel, explicit token,
    verified thumbnail and Playwright identity. These scenarios invoke the
    Node/Playwright route directly, so they cannot run in the offline suite.
    """
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dummy_video = os.path.join(self.temp_dir.name, "sample_video.mp4")
        with open(self.dummy_video, "wb") as f:
            f.write(b"SAMPLE_VIDEO_BYTES_DATA")

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

    def tearDown(self):
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

    @patch("googleapiclient.discovery.build")
    @patch("subprocess.run")
    @patch("os.path.exists")
    def test_strategy_a_api_success(self, mock_exists, mock_run, mock_build):
        """Test Strategy A API upload when API credentials are set."""
        def exists_side_effect(path):
            if "sample_video.mp4" in path:
                return True
            return False
        mock_exists.side_effect = exists_side_effect
        mock_run.return_value = MagicMock(stdout="mock_token", returncode=0)

        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_insert = mock_service.videos().insert
        mock_insert.return_value.execute.return_value = {"id": "yt_api_123"}

        res = upload_video_via_api(
            self.dummy_video, "API Title", "API Description", ["tag1"]
        )
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["method"], "API")
        self.assertEqual(res["video_id"], "yt_api_123")

    @patch("subprocess.run", side_effect=Exception("no gcloud"))
    @patch("os.path.exists", return_value=False)
    def test_strategy_a_api_missing_token_raises_runtime_error(self, mock_exists, mock_run):
        """Test Strategy A raises RuntimeError when API credentials are absent."""
        # Setup mock_exists to return True only for dummy_video path so FileNotFoundError is not raised
        def exists_side_effect(path):
            if "sample_video.mp4" in path:
                return True
            return False
        mock_exists.side_effect = exists_side_effect

        with self.assertRaises(RuntimeError):
            upload_video_via_api(
                self.dummy_video, "API Title", "API Description", ["tag1"]
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
            from src.config import BASE_DIR
            expected_token_path = os.environ.get("YOUTUBE_TOKEN_PATH", str(BASE_DIR / "secrets" / "youtube_token.json"))
            mock_api.assert_called_once_with(
                self.dummy_video, "Title", "Desc", ["creepypasta", "nosleep", "horror"], thumbnail_path=None, token_path=expected_token_path
            )

    def test_playwright_upload_success(self):
        """Test upload_video_via_playwright with valid cookies and video file."""
        res = upload_video_via_playwright(
            self.dummy_video,
            "PW Title",
            "PW Desc",
            ["horror"],
            cookies_path=self.dummy_cookies_file,
        )
        self.assertIn(res["status"], ["SUCCESS", "uploaded"])
        self.assertEqual(res["method"], "PLAYWRIGHT")
        self.assertTrue(res["video_id"].startswith("yt_playwright_"))

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
        with patch.dict(os.environ, {"MOCK_YOUTUBE_UPLOAD": "uploaded"}):
            res = upload_video_via_playwright(
                self.dummy_video,
                "Mock Title",
                "Mock Desc",
                ["mock"],
                cookies_path=self.dummy_cookies_file,
            )
            self.assertEqual(res["status"], "uploaded")
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
        mock_pw.assert_called_once_with(
            self.dummy_video, "Soy El Malo Title", "Soy El Malo Desc", ["creepypasta", "nosleep", "horror"],
            cookies_path=self.dummy_cookies_file, dry_run=False, thumbnail_path=None
        )

    @patch("src.youtube.uploader.upload_video_via_playwright")
    def test_channel_cookies_resolution_when_unspecified(self, mock_pw):
        """Test that upload_video automatically resolves channel2 cookies when channel='soy_el_malo'."""
        from src.config import COOKIES_CHANNEL2_PATH
        mock_pw.return_value = {"status": "SUCCESS", "method": "PLAYWRIGHT", "video_id": "yt_pw_chan2"}
        res = upload_video(
            self.dummy_video,
            "Soy El Malo Title",
            "Soy El Malo Desc",
            channel="soy_el_malo",
            token_path=os.path.join(self.temp_dir.name, "non_existent_token.json")
        )
        self.assertEqual(res["status"], "SUCCESS")
        mock_pw.assert_called_once_with(
            self.dummy_video, "Soy El Malo Title", "Soy El Malo Desc", ["creepypasta", "nosleep", "horror"],
            cookies_path=COOKIES_CHANNEL2_PATH, dry_run=False, thumbnail_path=None
        )

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

    @patch("googleapiclient.discovery.build")
    def test_upload_video_via_api_respects_token_path_parameter(self, mock_build):
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

        res = upload_video_via_api(
            self.dummy_video, "Token Path Title", "Token Path Desc", ["tag1"], token_path=custom_token
        )
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["video_id"], "yt_api_token_path")

    @patch("src.youtube.uploader.is_test_environment", return_value=False)
    @patch("src.youtube.uploader.sync_playwright")
    def test_playwright_upload_browser_close_on_exception(self, mock_sync_pw, mock_is_test):
        """Test upload_video_via_playwright closes browser in finally block when an exception occurs."""
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page
        mock_page.goto.side_effect = RuntimeError("Playwright navigation failed")

        mock_p = MagicMock()
        mock_p.chromium.launch.return_value = mock_browser

        with patch.dict(os.environ, {"MOCK_YOUTUBE_UPLOAD": ""}):
            mock_sync_pw.return_value.__enter__.return_value = mock_p
            with self.assertRaises(RuntimeError):
                upload_video_via_playwright(
                    self.dummy_video, "Title", "Desc", ["tag"], cookies_path=self.dummy_cookies_file
                )

            # Confirm browser.close() was invoked despite the exception
            mock_browser.close.assert_called()


if __name__ == "__main__":
    unittest.main()
