import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.cleaner import (
    clean_all_work_roots,
    clean_expired_failed_runs,
    clean_orphaned_development_dirs,
    clean_proxy_cache,
    clean_run_intermediates,
    clean_system_cache,
    clean_test_artifacts,
    clean_tts_cache,
    clean_untracked_temp_files,
    delete_local_post_publication,
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

    def test_clean_run_intermediates_expanded_patterns(self):
        run_dir = self.work_root / "run_expanded"
        run_dir.mkdir()
        scratch_files_to_clean = [
            "procedural_ambient_drama.wav",
            "procedural_synth.wav",
            "scene_001.mp4",
            "segment_002.mp4",
            "loop_003.mp4",
            "concat_procedural_scenes.txt",
            "frame_0001.png",
            "ffmpeg_master.log",
        ]
        canonical_files_to_preserve = [
            "speech.wav",
            "narration.wav",
            "subtitles.ass",
            "subtitles.srt",
            "subtitles.json",
        ]
        for name in scratch_files_to_clean + canonical_files_to_preserve:
            (run_dir / name).write_bytes(b"DATA")

        keep_video = run_dir / "video.mp4"
        keep_video.write_bytes(b"FINAL_VIDEO")
        keep_thumb = run_dir / "thumbnail.jpg"
        keep_thumb.write_bytes(b"THUMBNAIL")
        keep_marker = run_dir / ".run.json"
        keep_marker.write_text('{"run_id": "run_expanded", "active": false}')

        report = clean_run_intermediates(run_dir)
        self.assertEqual(report["deleted_files_count"], len(scratch_files_to_clean))
        self.assertTrue(keep_video.exists())
        self.assertTrue(keep_thumb.exists())
        self.assertTrue(keep_marker.exists())
        for name in scratch_files_to_clean:
            self.assertFalse((run_dir / name).exists())
        for name in canonical_files_to_preserve:
            self.assertTrue((run_dir / name).exists())

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

    def test_clean_orphaned_development_dirs(self):
        orphan_dir = self.work_root / "scp_short_12345"
        orphan_dir.mkdir()
        (orphan_dir / "draft.txt").write_bytes(b"DRAFT")

        system_dir = self.work_root / "cli"
        system_dir.mkdir()
        (system_dir / "keep.txt").write_bytes(b"KEEP")

        active_run = self.work_root / "active_run_999"
        active_run.mkdir()
        (active_run / ".run.json").write_text('{"run_id": "active_run_999", "active": true}')
        (active_run / "video.mp4").write_bytes(b"IN_PROGRESS")

        report = clean_orphaned_development_dirs(work_root=self.work_root, min_age_seconds=0)
        self.assertEqual(report["deleted_dirs_count"], 1)
        self.assertFalse(orphan_dir.exists())
        self.assertTrue(system_dir.exists())
        self.assertTrue(active_run.exists())

    def test_clean_tts_cache_ttl_and_lru(self):
        tts_root = self.work_root / "tts_cache"
        bucket = tts_root / "ab"
        bucket.mkdir(parents=True)
        
        # Entry 1: Old entry (1000s ago)
        wav1 = bucket / "abcdef123456.wav"
        json1 = bucket / "abcdef123456.json"
        wav1.write_bytes(b"WAV1" * 100)
        json1.write_text('{"sample": 1}')
        old_time = time.time() - 1000
        os.utime(wav1, (old_time, old_time))
        os.utime(json1, (old_time, old_time))

        # Entry 2: Fresh entry (10s ago, larger size)
        wav2 = bucket / "ab9999999999.wav"
        json2 = bucket / "ab9999999999.json"
        wav2.write_bytes(b"WAV2" * 500)
        json2.write_text('{"sample": 2}')
        fresh_time = time.time() - 10
        os.utime(wav2, (fresh_time, fresh_time))
        os.utime(json2, (fresh_time, fresh_time))

        # TTL eviction (max_age_seconds=500 -> removes entry 1)
        rep1 = clean_tts_cache(work_root=self.work_root, max_age_seconds=500)
        self.assertEqual(rep1["deleted_files_count"], 2)
        self.assertFalse(wav1.exists())
        self.assertFalse(json1.exists())
        self.assertTrue(wav2.exists())

        # LRU max_size_bytes eviction (max_size_bytes=10 -> removes entry 2)
        rep2 = clean_tts_cache(work_root=self.work_root, max_size_bytes=10)
        self.assertEqual(rep2["deleted_files_count"], 2)
        self.assertFalse(wav2.exists())

    def test_clean_proxy_cache_ttl_and_lru(self):
        proxy_root = self.work_root / "proxy_cache"
        proxy_root.mkdir(parents=True)
        
        p1 = proxy_root / "proxy_old.mp4"
        p1.write_bytes(b"PROXY1" * 100)
        old_time = time.time() - 1000
        os.utime(p1, (old_time, old_time))

        p2 = proxy_root / "proxy_new.mp4"
        p2.write_bytes(b"PROXY2" * 500)
        fresh_time = time.time() - 10
        os.utime(p2, (fresh_time, fresh_time))

        # TTL test
        rep1 = clean_proxy_cache(work_root=self.work_root, max_age_seconds=500)
        self.assertEqual(rep1["deleted_files_count"], 1)
        self.assertFalse(p1.exists())
        self.assertTrue(p2.exists())

        # LRU size limit test
        rep2 = clean_proxy_cache(work_root=self.work_root, max_size_bytes=50)
        self.assertEqual(rep2["deleted_files_count"], 1)
        self.assertFalse(p2.exists())

    def test_clean_test_artifacts(self):
        test_dir = self.work_root / "test"
        sub_test = test_dir / "test_run_1"
        sub_test.mkdir(parents=True)
        (sub_test / "ambient.wav").write_bytes(b"AMBIENT")
        (sub_test / "output.mp4").write_bytes(b"OUTPUT")

        report = clean_test_artifacts(test_work_root=test_dir, min_age_seconds=0)
        self.assertEqual(report["deleted_dirs_count"], 1)
        self.assertEqual(report["deleted_files_count"], 2)
        self.assertFalse(sub_test.exists())

    def test_clean_all_work_roots(self):
        cli_work = self.work_root / "cli"
        cli_work.mkdir(parents=True)
        run1 = cli_work / "run_failed_abc"
        run1.mkdir()
        (run1 / ".run.json").write_text('{"run_id": "run_failed_abc", "active": false, "retention_satisfied": false}')
        (run1 / "temp.wav").write_bytes(b"FAILED_AUDIO")

        tts_dir = cli_work / "tts_cache" / "12"
        tts_dir.mkdir(parents=True)
        (tts_dir / "1234.wav").write_bytes(b"TTS_AUDIO")
        (tts_dir / "1234.json").write_text('{}')

        with patch("src.cleaner.is_test_environment", return_value=True):
            report = clean_all_work_roots(
                work_roots=[cli_work],
                dry_run=False,
                include_caches=True,
                include_tests=False,
                max_cache_age_seconds=0,
            )
            self.assertGreater(report["freed_bytes"], 0)
            self.assertGreater(report["deleted_files_count"], 0)
            self.assertFalse(run1.exists())

    def test_delete_local_post_publication(self):
        run_dir = self.work_root / "run_published_123"
        run_dir.mkdir(parents=True)
        video = run_dir / "video.mp4"
        video.write_bytes(b"FINAL_VIDEO_BYTES" * 100)
        voice = run_dir / "voice.wav"
        voice.write_bytes(b"VOICE_AUDIO_BYTES" * 50)
        audio_mp3 = run_dir / "tts.mp3"
        audio_mp3.write_bytes(b"TTS_AUDIO_BYTES" * 50)
        concat = run_dir / "concat_list.txt"
        concat.write_text("file 'seg.mp4'")
        marker = run_dir / ".run.json"
        marker.write_text('{"run_id": "run_published_123", "retention_satisfied": true}')
        metadata = run_dir / "story.json"
        metadata.write_text('{"title": "Story Title"}')

        report = delete_local_post_publication(run_dir, video_path=video)

        self.assertGreater(report["freed_bytes"], 0)
        self.assertGreaterEqual(report["deleted_files_count"], 4)
        # Video, TTS audios, and concat list deleted
        self.assertFalse(video.exists())
        self.assertFalse(voice.exists())
        self.assertFalse(audio_mp3.exists())
        self.assertFalse(concat.exists())
        # Lightweight metadata preserved
        self.assertTrue(marker.exists())
        self.assertTrue(metadata.exists())


if __name__ == "__main__":
    unittest.main()
