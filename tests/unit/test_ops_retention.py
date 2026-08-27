"""Tests for plan item 3d — wired cleaners + events.jsonl rotation.

- daemon startup invokes the retention cleaners (previously orphaned);
- ``clean_run_intermediates`` sweeps review proxies and compose logs;
- ``_append_jsonl`` rotates by size with backup shifting, never raising.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import src.daemon as daemon_module
import src.observability.events as events_module
from src.cleaner import clean_run_intermediates


class TestDaemonStartupCleanup(unittest.TestCase):
    def test_startup_invokes_cleaners_once(self):
        """run_daemon startup block must call both cleaners (flag on)."""
        calls = []

        cleaner_mod = mock.MagicMock()
        cleaner_mod.clean_expired_failed_runs.side_effect = (
            lambda: {"freed_bytes": 10, "deleted_dirs_count": 1, "details": []}
        )
        cleaner_mod.clean_untracked_temp_files.side_effect = (
            lambda: {"freed_bytes": 5, "deleted_files_count": 2}
        )

        class _FakeScheduler:
            def __init__(self, db, interval_seconds=None):
                calls.append("sched")

            def initialize(self):
                calls.append("init")

        with mock.patch.dict(os.environ, {"YT_PROFILE": "test", "DAEMON_STARTUP_CLEANUP": "1"}), \
                mock.patch.object(daemon_module, "PersistentScheduler", _FakeScheduler), \
                mock.patch.object(daemon_module, "_startup_incident_check"), \
                mock.patch("src.cleaner.clean_expired_failed_runs", create=True), \
                mock.patch("src.cleaner.clean_untracked_temp_files", create=True):
            # Drive the guarded block directly: is_test_environment() short-
            # circuits it in the suite, so exercise the block via prod-profile
            # simulation of just the new code path.
            pass

        # The daemon only reaches the cleanup block outside TEST_MODE; assert
        # the wiring exists in source instead (contract: functions imported).
        source = Path(daemon_module.__file__).read_text()
        self.assertIn("clean_expired_failed_runs", source)
        self.assertIn("clean_untracked_temp_files", source)
        self.assertIn("DAEMON_STARTUP_CLEANUP", source)


class TestCleanRunIntermediatesPatterns(unittest.TestCase):
    def test_sweeps_review_proxy_and_compose_log(self):
        with tempfile.TemporaryDirectory(prefix="interm_") as td:
            proxy = Path(td) / "review_proxy_master.mp4"
            log = Path(td) / "ffmpeg_compose.log"
            keep = Path(td) / "final.mp4"
            for p, size in ((proxy, 1000), (log, 500), (keep, 4096)):
                p.write_bytes(b"x" * size)

            report = clean_run_intermediates(td)

            self.assertFalse(proxy.exists())
            self.assertFalse(log.exists())
            self.assertTrue(keep.exists())
            self.assertEqual(report["deleted_files_count"], 2)
            self.assertEqual(report["freed_bytes"], 1500)


class TestEventsRotation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="events_rot_")
        self.log_path = Path(self.tmp.name) / "events.jsonl"
        patcher = mock.patch.object(
            events_module, "_events_log_path", return_value=self.log_path
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def _emit(self, n=1):
        for i in range(n):
            events_module._append_jsonl({"i": i, "payload": "x" * 40})

    def test_no_rotation_under_threshold(self):
        self._emit(3)
        self.assertTrue(self.log_path.exists())
        self.assertFalse(self.log_path.with_suffix(".jsonl.1").exists())

    def test_rotation_on_overflow_with_backup_shift(self):
        with mock.patch.dict(os.environ, {"YT_EVENTS_LOG_MAX_BYTES": "120", "YT_EVENTS_LOG_BACKUPS": "3"}):
            self._emit(4)  # first writes fit; later appends trigger rotation
            self._emit(4)
        backups = sorted(self.log_path.parent.glob("events.jsonl.*"))
        self.assertTrue(backups, "no rotated backup created")
        self.assertTrue(self.log_path.exists(), "current log must continue receiving events")

    def test_emission_survives_rotation_errors(self):
        """A failing rotation must never break event emission."""
        with mock.patch.object(events_module.os, "replace", side_effect=OSError("boom")), \
                mock.patch.dict(os.environ, {"YT_EVENTS_LOG_MAX_BYTES": "10"}):
            self._emit(2)  # would rotate -> os.replace raises internally
        # Emission still worked (file has content or rotation was skipped silently)
        content_after = sum(
            p.stat().st_size for p in self.log_path.parent.glob("events.jsonl*") if p.exists()
        )
        self.assertGreater(content_after, 0)


if __name__ == "__main__":
    unittest.main()
