import os
import sys
import signal
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import pytest

from src.core.lock import (
    ChannelLock,
    ChannelLockError,
    acquire_lock,
    release_lock,
    register_signal_handlers,
    _handle_signal,
)


class TestChannelLock(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_lock_path = os.path.join(self.temp_dir.name, "test_automation.lock")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_channel_lock_lifecycle_context_manager(self):
        """Scenario 1 & 6: Context manager enters, creates PID lock file, and removes it on exit."""
        lock = ChannelLock(channel_name="moku", lock_file_path=self.base_lock_path)
        expected_path = f"{self.base_lock_path}.moku"

        self.assertFalse(os.path.exists(expected_path))
        with lock:
            self.assertTrue(os.path.exists(expected_path))
            with open(expected_path, "r", encoding="utf-8") as f:
                pid = f.read().strip()
            self.assertEqual(pid, str(os.getpid()))

        self.assertFalse(os.path.exists(expected_path))

    def test_channel_lock_collision_rejection(self):
        """Scenario 5: Concurrent acquisition on the same channel raises ChannelLockError."""
        lock1 = ChannelLock(channel_name="moku", lock_file_path=self.base_lock_path)
        lock2 = ChannelLock(channel_name="moku", lock_file_path=self.base_lock_path, timeout=0.05, poll_interval=0.01)

        with lock1:
            with self.assertRaises(ChannelLockError) as cm:
                lock2.acquire()
            self.assertIn("moku", str(cm.exception))

    def test_channel_lock_multi_channel_isolation(self):
        """Scenario 7: Independent channels can hold locks concurrently without collision."""
        lock_moku = ChannelLock(channel_name="moku", lock_file_path=self.base_lock_path)
        lock_aelithia = ChannelLock(channel_name="aelithia", lock_file_path=self.base_lock_path)
        lock_global = ChannelLock(channel_name="global", lock_file_path=self.base_lock_path)

        with lock_moku:
            with lock_aelithia:
                with lock_global:
                    self.assertTrue(os.path.exists(f"{self.base_lock_path}.moku"))
                    self.assertTrue(os.path.exists(f"{self.base_lock_path}.aelithia"))
                    self.assertTrue(os.path.exists(self.base_lock_path))

        self.assertFalse(os.path.exists(f"{self.base_lock_path}.moku"))
        self.assertFalse(os.path.exists(f"{self.base_lock_path}.aelithia"))
        self.assertFalse(os.path.exists(self.base_lock_path))

    def test_channel_lock_exception_cleanup(self):
        """Scenario 6: Exception inside context manager block still releases and unlinks lock."""
        lock = ChannelLock(channel_name="moku", lock_file_path=self.base_lock_path)
        expected_path = f"{self.base_lock_path}.moku"

        with self.assertRaises(RuntimeError):
            with lock:
                self.assertTrue(os.path.exists(expected_path))
                raise RuntimeError("Something failed in pipeline")

        self.assertFalse(os.path.exists(expected_path))

    def test_channel_lock_pid_mismatch_does_not_unlink(self):
        """Releasing lock does not unlink file if PID inside file belongs to another process."""
        lock = ChannelLock(channel_name="moku", lock_file_path=self.base_lock_path)
        expected_path = f"{self.base_lock_path}.moku"

        lock.acquire()
        self.assertTrue(os.path.exists(expected_path))

        # Overwrite PID in file to simulate another process
        with open(expected_path, "w", encoding="utf-8") as f:
            f.write("9999999\n")

        lock.release()
        # File should remain because PID was different
        self.assertTrue(os.path.exists(expected_path))

    def test_channel_lock_idempotent_release(self):
        """Multiple calls to release() do not raise errors."""
        lock = ChannelLock(channel_name="moku", lock_file_path=self.base_lock_path)
        lock.acquire()
        lock.release()
        # Second release should be a no-op
        lock.release()
        self.assertFalse(os.path.exists(f"{self.base_lock_path}.moku"))

    def test_legacy_acquire_and_release_lock_shims(self):
        """Legacy acquire_lock and release_lock shims work as expected."""
        with patch("src.core.lock.LOCK_FILE_PATH", self.base_lock_path):
            acquire_lock("moku")
            expected_path = f"{self.base_lock_path}.moku"
            self.assertTrue(os.path.exists(expected_path))
            with open(expected_path, "r", encoding="utf-8") as f:
                self.assertEqual(f.read().strip(), str(os.getpid()))
            release_lock("moku")
            self.assertFalse(os.path.exists(expected_path))

    def test_signal_handler_lock_cleanup(self):
        """_handle_signal calls request_shutdown, releases locks, and exits with 0."""
        with patch("src.core.lock.release_lock") as mock_release, \
             patch("src.daemon.request_shutdown") as mock_shutdown, \
             self.assertRaises(SystemExit) as cm:
            _handle_signal(signal.SIGINT, None)

        self.assertEqual(cm.exception.code, 0)
        mock_shutdown.assert_called_once()
        mock_release.assert_called_once()

    def test_channel_lock_wait_timeout_expiry(self):
        """ChannelLock with timeout expires and raises ChannelLockError after deadline."""
        import time
        lock1 = ChannelLock(channel_name="moku", lock_file_path=self.base_lock_path)
        lock2 = ChannelLock(channel_name="moku", lock_file_path=self.base_lock_path, timeout=0.2, poll_interval=0.05)

        with lock1:
            t0 = time.monotonic()
            with self.assertRaises(ChannelLockError) as cm:
                lock2.acquire()
            elapsed = time.monotonic() - t0
            self.assertGreaterEqual(elapsed, 0.15)
            self.assertIn("moku", str(cm.exception))

    def test_channel_lock_wait_timeout_success(self):
        """ChannelLock waits and acquires successfully when previous holder releases within timeout."""
        import threading
        import time

        lock1 = ChannelLock(channel_name="moku", lock_file_path=self.base_lock_path)
        lock2 = ChannelLock(channel_name="moku", lock_file_path=self.base_lock_path, timeout=1.0, poll_interval=0.05)

        lock1.acquire()

        def _delayed_release():
            time.sleep(0.15)
            lock1.release()

        thread = threading.Thread(target=_delayed_release)
        thread.start()

        acquired = lock2.acquire()
        self.assertTrue(acquired)
        self.assertTrue(lock2.is_acquired)
        lock2.release()
        thread.join()

    def test_channel_lock_dir_resolution_global_and_named(self):
        """1.2.1 & 1.2.2: ChannelLock resolves paths properly with lock_dir."""
        lock_global = ChannelLock(channel_name="global", lock_dir=self.temp_dir.name)
        self.assertEqual(
            lock_global.path,
            os.path.join(self.temp_dir.name, "youtube_automation.lock")
        )

        lock_aelithia = ChannelLock(channel_name="aelithia", lock_dir=self.temp_dir.name)
        self.assertEqual(
            lock_aelithia.path,
            os.path.join(self.temp_dir.name, "youtube_automation.lock.aelithia")
        )

    def test_channel_lock_file_path_resolution(self):
        """1.2.3: ChannelLock resolves custom lock_file_path with channel suffix."""
        custom_lock = os.path.join(self.temp_dir.name, "custom.lock")
        lock_moku = ChannelLock(channel_name="moku", lock_file_path=custom_lock)
        self.assertEqual(
            lock_moku.path,
            f"{custom_lock}.moku"
        )

    def test_channel_lock_yt_lock_dir_env_precedence(self):
        """1.2.4: YT_LOCK_DIR environment variable resolves lock file inside env directory."""
        env_dir = os.path.join(self.temp_dir.name, "env_locks")
        os.makedirs(env_dir, exist_ok=True)
        with patch.dict(os.environ, {"YT_LOCK_DIR": env_dir}):
            lock_global = ChannelLock(channel_name="global")
            self.assertEqual(
                lock_global.path,
                os.path.join(env_dir, "youtube_automation.lock")
            )
            lock_moku = ChannelLock(channel_name="moku")
            self.assertEqual(
                lock_moku.path,
                os.path.join(env_dir, "youtube_automation.lock.moku")
            )

    def test_channel_lock_concurrent_isolation_across_dirs(self):
        """1.2.5: Concurrent locks targeting different directories do not collide."""
        dir1 = os.path.join(self.temp_dir.name, "worker1")
        dir2 = os.path.join(self.temp_dir.name, "worker2")
        lock1 = ChannelLock(channel_name="moku", lock_dir=dir1)
        lock2 = ChannelLock(channel_name="moku", lock_dir=dir2)

        with lock1:
            with lock2:
                self.assertTrue(lock1.is_acquired)
                self.assertTrue(lock2.is_acquired)
                self.assertTrue(os.path.exists(lock1.path))
                self.assertTrue(os.path.exists(lock2.path))

    def test_channel_lock_lifecycle_in_lock_dir(self):
        """1.2.6: Clean acquisition, context manager entry, release, and PID-verified unlinking."""
        target_dir = os.path.join(self.temp_dir.name, "lifecycle_dir")
        lock = ChannelLock(channel_name="moku", lock_dir=target_dir)

        self.assertFalse(os.path.exists(lock.path))
        with lock:
            self.assertTrue(lock.is_acquired)
            self.assertTrue(os.path.exists(lock.path))
            with open(lock.path, "r", encoding="utf-8") as f:
                self.assertEqual(f.read().strip(), str(os.getpid()))

        self.assertFalse(lock.is_acquired)
        self.assertFalse(os.path.exists(lock.path))

    def test_acquire_lock_legacy_wrapper_kwargs_propagation(self):
        """1.2.7: acquire_lock wrapper propagates lock_dir and lock_file_path."""
        target_dir = os.path.join(self.temp_dir.name, "wrapper_dir")
        acquire_lock(channel_name="moku", lock_dir=target_dir)
        expected_path = os.path.join(target_dir, "youtube_automation.lock.moku")
        self.assertTrue(os.path.exists(expected_path))
        with open(expected_path, "r", encoding="utf-8") as f:
            self.assertEqual(f.read().strip(), str(os.getpid()))
        release_lock("moku")
        self.assertFalse(os.path.exists(expected_path))


if __name__ == "__main__":
    unittest.main()

