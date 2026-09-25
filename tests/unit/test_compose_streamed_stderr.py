"""Contract tests for the local asset-only compose adapter."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lib.video import compose_video


class _TempFiles:
    def __enter__(self):
        self.dir = tempfile.TemporaryDirectory(prefix="compose_local_assets_")
        self.audio_path = os.path.join(self.dir.name, "valid_audio.wav")
        Path(self.audio_path).write_bytes(b"AUDIO_DATA")
        self.srt_path = os.path.join(self.dir.name, "subs.srt")
        Path(self.srt_path).write_text(
            "1\n00:00:00,000 --> 00:02:50,000\nLocal subtitle\n",
            encoding="utf-8",
        )
        self.output_video = os.path.join(self.dir.name, "out.mp4")
        return self

    def __exit__(self, *exc):
        self.dir.cleanup()
        return False


class TestComposeLocalAssets(unittest.TestCase):
    """The legacy adapter must delegate to LoopVideoEngine without graphics."""

    def test_delegates_to_loop_engine_with_stream_copy(self):
        with _TempFiles() as tf:
            with patch("src.media.loop_engine.LoopVideoEngine.compose", return_value=tf.output_video) as compose:
                result = compose_video(
                    tf.audio_path,
                    tf.srt_path,
                    "",
                    tf.output_video,
                    duration_sec=170.0,
                    channel="moku",
                )

        self.assertEqual(result, tf.output_video)
        compose.assert_called_once()
        call = compose.call_args.kwargs
        self.assertEqual(call["audio_path"], tf.audio_path)
        self.assertEqual(call["output_video_path"], tf.output_video)
        self.assertEqual(call["category"], "moku")
        self.assertEqual(call["orientation"], "vertical")
        self.assertTrue(call["include_subtitles"])
        self.assertTrue(call["stream_copy"])

    def test_rejects_duration_below_contract(self):
        with _TempFiles() as tf:
            with self.assertRaises(ValueError):
                compose_video(
                    tf.audio_path,
                    tf.srt_path,
                    "",
                    tf.output_video,
                    duration_sec=1.0,
                    min_duration=10.0,
                )


if __name__ == "__main__":
    unittest.main()
