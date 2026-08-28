import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.cleaner import (
    clean_expired_failed_runs,
    clean_run_intermediates,
    clean_untracked_temp_files,
    verify_and_cleanup,
)


class TestVPSCleaner(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.work_root = self.root / "work"
        self.artifact_root = self.root / "artifacts"
        self.work_root.mkdir()
        self.artifact_root.mkdir()
        self.dummy_file = self.work_root / "cleanup_video.mp4"
        self.dummy_file.write_bytes(b"CLEANUP_TEST_DATA")
        os.utime(self.dummy_file, (1, 1))
        self.settings = SimpleNamespace(
            work_root=self.work_root,
            artifact_root=self.artifact_root,
            drive_folder_id="folder-verified",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def _proof(self, **overrides):
        proof = {
            "id": "drive-real-123",
            "name": self.dummy_file.name,
            "size": self.dummy_file.stat().st_size,
            "parents": ["folder-verified"],
            "exists": True,
        }
        proof.update(overrides)
        return proof

    def test_cleanup_requires_complete_verified_remote_proof(self):
        with patch("src.cleaner.SETTINGS", self.settings):
            self.assertTrue(
                verify_and_cleanup(
                    str(self.dummy_file),
                    "drive-real-123",
                    remote_proof=self._proof(),
                    retention_seconds=0,
                )
            )
        self.assertFalse(self.dummy_file.exists())

    def test_empty_or_fabricated_id_preserves_file(self):
        with patch("src.cleaner.SETTINGS", self.settings):
            self.assertFalse(
                verify_and_cleanup(
                    str(self.dummy_file),
                    "",
                    remote_proof=self._proof(),
                    retention_seconds=0,
                )
            )
            self.assertFalse(
                verify_and_cleanup(
                    str(self.dummy_file),
                    "drive_id_cleanup_video.mp4",
                    remote_proof=None,
                    retention_seconds=0,
                )
            )
        self.assertTrue(self.dummy_file.exists())

    def test_cleanup_is_limited_to_project_roots(self):
        outside = self.root / "outside.mp4"
        outside.write_bytes(b"DO_NOT_DELETE")
        os.utime(outside, (1, 1))
        with patch("src.cleaner.SETTINGS", self.settings):
            self.assertFalse(
                verify_and_cleanup(
                    str(outside),
                    "drive-real-123",
                    remote_proof={
                        "id": "drive-real-123",
                        "name": outside.name,
                        "size": outside.stat().st_size,
                        "parents": ["folder-verified"],
                        "exists": True,
                    },
                    retention_seconds=0,
                )
            )
        self.assertTrue(outside.exists())

    def test_mismatch_and_retention_preserve_file(self):
        with patch("src.cleaner.SETTINGS", self.settings):
            self.assertFalse(
                verify_and_cleanup(
                    str(self.dummy_file),
                    "drive-real-123",
                    remote_proof=self._proof(size=999),
                    retention_seconds=0,
                )
            )
            self.assertFalse(
                verify_and_cleanup(
                    str(self.dummy_file),
                    "drive-real-123",
                    remote_proof=self._proof(),
                    retention_seconds=10**12,
                )
            )
        self.assertTrue(self.dummy_file.exists())

    def test_nonexistent_local_file_returns_false(self):
        with patch("src.cleaner.SETTINGS", self.settings):
            self.assertFalse(
                verify_and_cleanup(
                    str(self.work_root / "missing.mp4"),
                    "drive-real-123",
                    remote_proof={},
                )
            )

    def test_clean_expired_failed_runs(self):
        failed_run = self.work_root / "run_failed_123"
        failed_run.mkdir()
        marker = failed_run / ".run.json"
        marker.write_text('{"run_id": "run_failed_123", "active": false, "retention_satisfied": false}')
        os.utime(marker, (1, 1))
        (failed_run / "temp.txt").write_bytes(b"FAILED_DATA")

        with patch("src.cleaner.SETTINGS", self.settings):
            report = clean_expired_failed_runs(min_age_seconds=0)
            self.assertEqual(report["deleted_dirs_count"], 1)
            self.assertFalse(failed_run.exists())

    def test_clean_run_intermediates(self):
        run_dir = self.work_root / "run_456"
        run_dir.mkdir()
        prescaled = run_dir / "prescaled_0.jpg"
        prescaled.write_bytes(b"JPEG")
        concat_txt = run_dir / "concat_list.txt"
        concat_txt.write_text("file 'prescaled_0.jpg'")
        tmp_file = run_dir / "audio.tmp.norm.wav"
        tmp_file.write_bytes(b"WAV")
        video = run_dir / "video.mp4"
        video.write_bytes(b"VIDEO")

        report = clean_run_intermediates(run_dir)
        self.assertEqual(report["deleted_files_count"], 3)
        self.assertFalse(prescaled.exists())
        self.assertFalse(concat_txt.exists())
        self.assertFalse(tmp_file.exists())
        self.assertTrue(video.exists())

    def test_clean_run_intermediates_includes_loop_concat_and_safe_area(self):
        run_dir = self.work_root / "run_loop_789"
        run_dir.mkdir()
        loop_concat = run_dir / "loop_concat_list.txt"
        loop_concat.write_text("file 'loop.mp4'")
        safe_area = run_dir / "safe_area_validation.jpg"
        safe_area.write_bytes(b"VALIDATION")
        video = run_dir / "video.mp4"
        video.write_bytes(b"VIDEO")

        report = clean_run_intermediates(run_dir)
        self.assertEqual(report["deleted_files_count"], 2)
        self.assertFalse(loop_concat.exists())
        self.assertFalse(safe_area.exists())
        self.assertTrue(video.exists())

    def test_cleanup_accepts_published_or_approved_drive_folders(self):
        settings_published = SimpleNamespace(
            work_root=self.work_root,
            artifact_root=self.artifact_root,
            drive_folder_id="folder-verified",
            drive_published_folder_id="folder-published-123",
            drive_approved_video_folder_id="folder-approved-456",
            drive_root_folder_id="",
        )
        dummy2 = self.work_root / "published_video.mp4"
        dummy2.write_bytes(b"PUBLISHED_VIDEO_DATA")
        os.utime(dummy2, (1, 1))

        proof_published = {
            "id": "drive-pub-123",
            "name": dummy2.name,
            "size": dummy2.stat().st_size,
            "parents": ["folder-published-123"],
            "exists": True,
        }
        with patch("src.cleaner.SETTINGS", settings_published):
            self.assertTrue(
                verify_and_cleanup(
                    str(dummy2),
                    "drive-pub-123",
                    remote_proof=proof_published,
                    retention_seconds=0,
                )
            )
        self.assertFalse(dummy2.exists())

    def test_clean_untracked_temp_files(self):
        tmp1 = self.work_root / ".tmp.orphaned.mp3"
        tmp1.write_bytes(b"TEMP")
        safe_area = self.work_root / "safe_area_validation.jpg"
        safe_area.write_bytes(b"VALIDATION")

        with patch("src.cleaner.SETTINGS", self.settings):
            report = clean_untracked_temp_files()
            self.assertEqual(report["deleted_files_count"], 2)
            self.assertFalse(tmp1.exists())
            self.assertFalse(safe_area.exists())


if __name__ == "__main__":
    unittest.main()
