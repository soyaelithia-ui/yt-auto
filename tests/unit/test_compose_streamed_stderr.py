"""Tests for plan item 3c — streamed compose stderr (YT_COMPOSE_STREAM_STDERR).

Default off (hermetic suite patches ``subprocess.run``); when enabled the
compose step routes ffmpeg stderr to a log file via ``run_ffmpeg`` instead of
buffering it in RAM, preserving the RuntimeError tail contract.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock
from unittest.mock import MagicMock, patch

from lib.video import compose_video


class _TempFiles:
    def __enter__(self):
        self.dir = tempfile.TemporaryDirectory(prefix="compose_stream_")
        self.audio_path = os.path.join(self.dir.name, "valid_audio.wav")
        with open(self.audio_path, "wb") as f:
            f.write(b"AUDIO_DATA")
        self.srt_path = os.path.join(self.dir.name, "subs.srt")
        with open(self.srt_path, "w") as f:
            f.write("1\n00:00:00,000 --> 00:02:50,000\nValid duration subtitle\n")
        self.output_video = os.path.join(self.dir.name, "out.mp4")
        return self

    def __exit__(self, *exc):
        self.dir.cleanup()
        return False


class TestComposeStreamedStderr(unittest.TestCase):
    """Integration through compose_video with the env gate flipped on."""

    def test_flag_off_uses_subprocess_run(self):
        """Legacy path (default) still patches cleanly via subprocess.run."""
        with _TempFiles() as tf:
            with patch.dict(os.environ, {"YT_COMPOSE_STREAM_STDERR": "0"}), \
                    patch("src.video.validate_video_format", return_value=True), \
                    patch("subprocess.run") as sp_mock:
                sp_mock.return_value = MagicMock(returncode=0)
                res = compose_video(
                    tf.audio_path, tf.srt_path, "", tf.output_video,
                    duration_sec=170.0, channel="moku",
                )
            self.assertEqual(res, tf.output_video)
            sp_mock.assert_called()  # legacy buffering path taken

    def test_flag_on_routes_stderr_to_file(self):
        """Flag=1 must call run_ffmpeg with stderr_file and skip subprocess.run."""
        captured = {}

        def fake_run_ffmpeg(args, timeout=None, check=False, stderr_file=None):
            captured["stderr_file"] = stderr_file
            captured["timeout"] = timeout
            # Emulate the real encoder: produce a non-empty output file.
            if args and str(args[-1]).endswith(".mp4"):
                with open(args[-1], "wb") as f:
                    f.write(b"\x00" * 2048)
            return SimpleNamespace(returncode=0, stderr="")

        with _TempFiles() as tf:
            log_expected = os.path.join(os.path.dirname(tf.output_video), "ffmpeg_compose.log")
            with patch.dict(os.environ, {"YT_COMPOSE_STREAM_STDERR": "1"}), \
                    patch("src.video.validate_video_format", return_value=True), \
                    mock.patch("lib.video.run_ffmpeg", side_effect=fake_run_ffmpeg), \
                    mock.patch("subprocess.run") as sp_mock:
                res = compose_video(
                    tf.audio_path, tf.srt_path, "" if False else "", tf.output_video,
                    duration_sec=170.0, channel="moku",
                )
            self.assertEqual(res, tf.output_video)
            self.assertEqual(captured.get("stderr_file"), log_expected)
            self.assertEqual(captured.get("timeout"), 3600.0)
            sp_mock.assert_not_called()

    def test_flag_on_failure_raises_with_tail(self):
        """Nonzero exit keeps the 'FFmpeg composition failed' RuntimeError contract."""

        def fake_run_ffmpeg(args, timeout=None, check=False, stderr_file=None):
            return SimpleNamespace(returncode=1, stderr="E" * 5000)

        with _TempFiles() as tf:
            with patch.dict(os.environ, {"YT_COMPOSE_STREAM_STDERR": "1"}), \
                    patch("src.video.validate_video_format", return_value=True), \
                    mock.patch("lib.video.run_ffmpeg", side_effect=fake_run_ffmpeg):
                with self.assertRaises(RuntimeError) as ctx:
                    compose_video(
                        tf.audio_path, tf.srt_path, "", tf.output_video,
                        duration_sec=170.0, channel="moku",
                    )
            self.assertIn("FFmpeg composition failed", str(ctx.exception))
            self.assertIn("EEE", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
