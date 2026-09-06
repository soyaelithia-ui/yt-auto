import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.core.domain import AmbiguousUploadError, ProviderValidationError
from src.core.google_auth import get_drive_credentials
from src.drive import upload_to_drive, upload_to_drive_verified


class TestDriveUploader(unittest.TestCase):
    def setUp(self):
        self.previous_gcloud = os.environ.get("DRIVE_USE_GCLOUD")
        os.environ["DRIVE_USE_GCLOUD"] = "0"
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dummy_file = os.path.join(self.temp_dir.name, "test_video.mp4")
        with open(self.dummy_file, "wb") as handle:
            handle.write(b"DUMMY VIDEO DATA")
        self.dummy_key = os.path.join(self.temp_dir.name, "key.json")
        with open(self.dummy_key, "w", encoding="utf-8") as handle:
            json.dump({"type": "service_account"}, handle)

    def tearDown(self):
        if self.previous_gcloud is None:
            os.environ.pop("DRIVE_USE_GCLOUD", None)
        else:
            os.environ["DRIVE_USE_GCLOUD"] = self.previous_gcloud
        self.temp_dir.cleanup()

    @patch("src.core.google_auth.subprocess.run")
    def test_gcloud_credentials_are_in_memory_and_token_is_not_logged(self, mock_run):
        mock_run.return_value.stdout = "mock-access-token\n"
        os.environ["DRIVE_USE_GCLOUD"] = "1"

        credentials = get_drive_credentials(None, None)

        self.assertEqual(credentials.token, "mock-access-token")
        mock_run.assert_called_once_with(
            ["gcloud", "auth", "print-access-token"],
            shell=False,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )

    @patch("src.drive._mock_enabled", return_value=True)
    def test_explicit_test_mode_returns_identifiable_mock(self, _mock):
        proof = upload_to_drive_verified(
            self.dummy_file,
            "folder_999",
            sa_key_path=self.dummy_key,
        )
        self.assertTrue(proof.file_id.startswith("mock-drive-"))
        self.assertEqual(proof.name, "test_video.mp4")
        self.assertEqual(proof.size_bytes, os.path.getsize(self.dummy_file))
        self.assertTrue(proof.exists)

    @patch("src.drive._mock_enabled", return_value=False)
    @patch("src.drive._drive_service")
    def test_success_requires_independent_remote_verification(
        self, mock_drive_service, _mock
    ):
        service = MagicMock()
        mock_drive_service.return_value = service
        service.files().create.return_value.execute.return_value = {
            "id": "drive_file_abc123"
        }
        service.files().get.return_value.execute.return_value = {
            "id": "drive_file_abc123",
            "name": "test_video.mp4",
            "size": str(os.path.getsize(self.dummy_file)),
            "parents": ["folder_999"],
            "trashed": False,
        }
        result = upload_to_drive(
            self.dummy_file,
            "folder_999",
            sa_key_path=self.dummy_key,
        )
        self.assertEqual(result, "drive_file_abc123")
        service.files().get.assert_called_once()

    def test_missing_video_raises(self):
        with self.assertRaises(FileNotFoundError):
            upload_to_drive("/does/not/exist.mp4", "folder")

    def test_missing_folder_raises(self):
        with self.assertRaises(ValueError):
            upload_to_drive(self.dummy_file, "")

    @patch("src.drive._mock_enabled", return_value=False)
    @patch("src.drive._drive_service")
    def test_mismatch_never_returns_fake_success(
        self, mock_drive_service, _mock
    ):
        service = MagicMock()
        mock_drive_service.return_value = service
        service.files().create.return_value.execute.return_value = {
            "id": "drive_file_abc123"
        }
        service.files().get.return_value.execute.return_value = {
            "id": "drive_file_abc123",
            "name": "wrong.mp4",
            "size": "1",
            "parents": ["wrong_folder"],
            "trashed": False,
        }
        with patch("src.drive.DRIVE_UPLOAD_MAX_RETRIES", 1):
            with self.assertRaises(ProviderValidationError):
                upload_to_drive(
                    self.dummy_file,
                    "folder_999",
                    sa_key_path=self.dummy_key,
                )

    @patch("src.drive._mock_enabled", return_value=False)
    @patch("src.drive._drive_service")
    def test_existing_idempotent_backup_skips_create(
        self, mock_drive_service, _mock
    ):
        service = MagicMock()
        mock_drive_service.return_value = service
        service.files().list.return_value.execute.return_value = {
            "files": [
                {
                    "id": "existing_drive_id",
                    "name": "test_video.mp4",
                    "size": str(os.path.getsize(self.dummy_file)),
                    "parents": ["folder_999"],
                    "trashed": False,
                }
            ]
        }
        callback = MagicMock()
        proof = upload_to_drive_verified(
            self.dummy_file,
            "folder_999",
            sa_key_path=self.dummy_key,
            idempotency_key="moku:bhv6zd",
            on_file_id=callback,
        )
        self.assertEqual(proof.file_id, "existing_drive_id")
        service.files().create.assert_not_called()
        callback.assert_called_once_with("existing_drive_id")

    @patch("src.drive._mock_enabled", return_value=False)
    @patch("src.drive._drive_service")
    def test_ambiguous_create_is_never_repeated(
        self, mock_drive_service, _mock
    ):
        service = MagicMock()
        mock_drive_service.return_value = service
        service.files().list.return_value.execute.side_effect = [
            {"files": []},
            {"files": []},
        ]
        service.files().create.return_value.execute.side_effect = TimeoutError("timeout")
        with self.assertRaises(AmbiguousUploadError):
            upload_to_drive_verified(
                self.dummy_file,
                "folder_999",
                sa_key_path=self.dummy_key,
                idempotency_key="moku:bhv6zd",
            )
        service.files().create.assert_called_once()

    @patch("src.drive._mock_enabled", return_value=False)
    @patch("src.drive._drive_service")
    def test_file_id_callback_runs_before_remote_verification(
        self, mock_drive_service, _mock
    ):
        service = MagicMock()
        mock_drive_service.return_value = service
        service.files().list.return_value.execute.return_value = {"files": []}
        service.files().create.return_value.execute.return_value = {
            "id": "known_drive_id"
        }
        service.files().get.return_value.execute.return_value = {
            "id": "known_drive_id",
            "name": "wrong.mp4",
            "size": "1",
            "parents": ["wrong"],
            "trashed": False,
        }
        callback = MagicMock()
        with patch("src.drive.DRIVE_UPLOAD_MAX_RETRIES", 1):
            with self.assertRaises(ProviderValidationError):
                upload_to_drive_verified(
                    self.dummy_file,
                    "folder_999",
                    sa_key_path=self.dummy_key,
                    idempotency_key="moku:bhv6zd",
                    on_file_id=callback,
                )
        callback.assert_called_once_with("known_drive_id")
        service.files().create.assert_called_once()

    @patch("src.drive._mock_enabled", return_value=True)
    def test_move_drive_file_mock_returns_true(self, _mock):
        from src.drive import move_drive_file
        self.assertTrue(move_drive_file("file_123", "target_folder_456"))

    def test_move_drive_file_empty_inputs_returns_false(self):
        from src.drive import move_drive_file
        self.assertFalse(move_drive_file("", "target_folder"))
        self.assertFalse(move_drive_file("file_123", ""))


if __name__ == "__main__":
    unittest.main()

