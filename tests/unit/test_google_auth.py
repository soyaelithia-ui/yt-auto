"""Unit tests for official Google Auth, token management, and service building."""

import json
import os
import stat
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from google.oauth2.credentials import Credentials

from src.core.domain import AuthenticationError
from src.core.google_auth import (
    DEFAULT_SCOPES,
    DRIVE_SCOPES,
    YOUTUBE_SCOPES,
    build_client_config,
    build_drive_service,
    build_youtube_service,
    create_oauth_flow,
    get_drive_credentials,
    load_authorized_user_credentials,
    save_credentials,
    standardize_token_file,
)


class TestGoogleAuth(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_client_id = "test-client-id.apps.googleusercontent.com"
        self.test_client_secret = "test-client-secret"
        self.legacy_token_path = os.path.join(self.temp_dir.name, "legacy_token.json")
        self.standard_token_path = os.path.join(self.temp_dir.name, "standard_token.json")

        self.legacy_data = {
            "access_token": "ya29.test_access_token",
            "refresh_token": "1//test_refresh_token",
            "scope": "https://www.googleapis.com/auth/youtube https://www.googleapis.com/auth/drive",
            "token_type": "Bearer",
            "client_id": self.test_client_id,
            "client_secret": self.test_client_secret,
        }
        with open(self.legacy_token_path, "w", encoding="utf-8") as f:
            json.dump(self.legacy_data, f)

        self.standard_data = {
            "token": "ya29.test_standard_token",
            "refresh_token": "1//test_refresh_token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": self.test_client_id,
            "client_secret": self.test_client_secret,
            "scopes": DEFAULT_SCOPES,
            "universe_domain": "googleapis.com",
            "expiry": "2026-08-27T18:00:00.000000Z",
        }
        with open(self.standard_token_path, "w", encoding="utf-8") as f:
            json.dump(self.standard_data, f)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_build_client_config(self):
        config = build_client_config(
            client_id=self.test_client_id,
            client_secret=self.test_client_secret,
        )
        self.assertIn("installed", config)
        installed = config["installed"]
        self.assertEqual(installed["client_id"], self.test_client_id)
        self.assertEqual(installed["client_secret"], self.test_client_secret)
        self.assertEqual(installed["auth_uri"], "https://accounts.google.com/o/oauth2/auth")
        self.assertEqual(installed["token_uri"], "https://oauth2.googleapis.com/token")
        self.assertIn("http://localhost:8585/", installed["redirect_uris"])

    def test_create_oauth_flow(self):
        flow = create_oauth_flow(
            client_id=self.test_client_id,
            client_secret=self.test_client_secret,
            scopes=YOUTUBE_SCOPES,
            redirect_uri="http://localhost:8585/",
        )
        self.assertEqual(flow.redirect_uri, "http://localhost:8585/")
        auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
        self.assertIn("accounts.google.com", auth_url)
        self.assertIn(self.test_client_id, auth_url)
        self.assertIn("youtube", auth_url)

    def test_load_authorized_user_credentials_standard(self):
        creds = load_authorized_user_credentials(self.standard_token_path, auto_refresh=False)
        self.assertEqual(creds.token, "ya29.test_standard_token")
        self.assertEqual(creds.refresh_token, "1//test_refresh_token")
        self.assertEqual(creds.client_id, self.test_client_id)
        self.assertEqual(creds.client_secret, self.test_client_secret)
        self.assertEqual(creds.scopes, DEFAULT_SCOPES)

    def test_load_authorized_user_credentials_legacy_normalized(self):
        creds = load_authorized_user_credentials(self.legacy_token_path, auto_refresh=False)
        self.assertEqual(creds.token, "ya29.test_access_token")
        self.assertEqual(creds.refresh_token, "1//test_refresh_token")
        self.assertEqual(
            creds.scopes,
            ["https://www.googleapis.com/auth/youtube", "https://www.googleapis.com/auth/drive"],
        )

    def test_save_credentials_writes_canonical_json_and_mode_0600(self):
        creds = Credentials(
            token="ya29.sample_saved_token",
            refresh_token="1//sample_saved_refresh",
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.test_client_id,
            client_secret=self.test_client_secret,
            scopes=DEFAULT_SCOPES,
        )
        dest_path = os.path.join(self.temp_dir.name, "saved_token.json")
        save_credentials(creds, dest_path)

        self.assertTrue(os.path.isfile(dest_path))
        file_mode = stat.S_IMODE(os.stat(dest_path).st_mode)
        self.assertEqual(file_mode, 0o600)

        with open(dest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["token"], "ya29.sample_saved_token")
        self.assertEqual(data["refresh_token"], "1//sample_saved_refresh")
        self.assertEqual(data["client_id"], self.test_client_id)

    def test_standardize_token_file(self):
        ok = standardize_token_file(self.legacy_token_path)
        self.assertTrue(ok)
        with open(self.legacy_token_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("token", data)
        self.assertIn("scopes", data)
        self.assertEqual(data["token"], "ya29.test_access_token")

    def test_missing_token_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_authorized_user_credentials(os.path.join(self.temp_dir.name, "nonexistent.json"))

    def test_malformed_json_raises(self):
        bad_path = os.path.join(self.temp_dir.name, "bad.json")
        with open(bad_path, "w", encoding="utf-8") as f:
            f.write("NOT VALID JSON {{{")
        with self.assertRaises(AuthenticationError):
            load_authorized_user_credentials(bad_path)

    @patch("src.core.google_auth.build")
    def test_build_youtube_service(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        service = build_youtube_service(token_path=self.standard_token_path)
        self.assertEqual(service, mock_service)
        mock_build.assert_called_once()
        args, kwargs = mock_build.call_args
        self.assertEqual(args[0], "youtube")
        self.assertEqual(args[1], "v3")
        self.assertIsInstance(kwargs["credentials"], Credentials)

    @patch("src.core.google_auth.build")
    def test_build_drive_service(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        service = build_drive_service(token_path=self.standard_token_path)
        self.assertEqual(service, mock_service)
        mock_build.assert_called_once()
        args, kwargs = mock_build.call_args
        self.assertEqual(args[0], "drive")
        self.assertEqual(args[1], "v3")
        self.assertIsInstance(kwargs["credentials"], Credentials)


if __name__ == "__main__":
    unittest.main()
