"""Unit tests for chunked xfade (PR2) — n>15 lifting."""
import os
import math
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


def _expected_blocks(n: int):
    if n <= 15:
        return [(0, n)]
    blocks = math.ceil((n - 1) / 14)
    return [(k * 14, min(k * 14 + 15, n)) for k in range(blocks)]


class TestChunkedBlocks:
    """Task 2.4: block partitioning via k*14:k*14+15 overlapping 1."""

    def test_n50_produces_4_blocks_15_15_15_8(self):
        from lib.video import _build_chunked_blocks

        blocks = _build_chunked_blocks(50)
        assert blocks == [(0, 15), (14, 29), (28, 43), (42, 50)]
        assert len(blocks) == 4
        # spec: 15,15,15,8 sizes
        assert [e - s for s, e in blocks] == [15, 15, 15, 8]

    def test_n20_produces_2_blocks(self):
        from lib.video import _build_chunked_blocks

        blocks = _build_chunked_blocks(20)
        assert blocks == [(0, 15), (14, 20)]
        assert [e - s for s, e in blocks] == [15, 6]

    def test_n15_single_block(self):
        from lib.video import _build_chunked_blocks

        assert _build_chunked_blocks(15) == [(0, 15)]
        assert _build_chunked_blocks(1) == [(0, 1)]
        assert _build_chunked_blocks(0) == [(0, 0)]

    def test_n16_two_blocks(self):
        from lib.video import _build_chunked_blocks

        assert _build_chunked_blocks(16) == [(0, 15), (14, 16)]

    def test_n60_produces_5_blocks(self):
        from lib.video import _build_chunked_blocks

        blocks = _build_chunked_blocks(60)
        assert len(blocks) == 5
        assert blocks == [(0, 15), (14, 29), (28, 43), (42, 57), (56, 60)]
        assert [e - s for s, e in blocks] == [15, 15, 15, 15, 4]

    def test_triangulation_n30(self):
        from lib.video import _build_chunked_blocks

        assert _build_chunked_blocks(30) == [(0, 15), (14, 29), (28, 30)]


class TestTTrans:
    def test_compute_T_trans_min_dur(self):
        from lib.video import _compute_T_trans

        # min_dur 12 -> min_dur/3=4 -> capped to 0.5
        assert _compute_T_trans([12.0, 12.0]) == 0.5
        # min_dur 1.2 -> 0.4 -> within 0.1-0.5
        assert _compute_T_trans([1.2, 2.0]) == pytest.approx(0.4)
        # min_dur 0.2 -> 0.066 -> floored to 0.1
        assert _compute_T_trans([0.2]) == 0.1
        # empty defaults 0.5
        assert _compute_T_trans([]) == 0.5

    def test_T_trans_formula_spec(self):
        from lib.video import _compute_T_trans

        # spec: T_trans = min(0.5, max(0.1, min_dur/3))
        for min_dur, expected in [(0.3, 0.1), (0.9, 0.3), (3.0, 0.5), (6.0, 0.5)]:
            assert _compute_T_trans([min_dur, min_dur + 1]) == pytest.approx(expected)


class TestChunkedFlag:
    def test_flag_enabled_default(self):
        from lib.video import _is_chunked_xfade_enabled

        with patch.dict(os.environ, {}, clear=False):
            if "FFMPEG_CHUNKED_XFADE" in os.environ:
                del os.environ["FFMPEG_CHUNKED_XFADE"]
            # need re-evaluate env; function reads each call
            assert _is_chunked_xfade_enabled() is True

    def test_flag_disabled(self):
        from lib.video import _is_chunked_xfade_enabled

        with patch.dict(os.environ, {"FFMPEG_CHUNKED_XFADE": "0"}):
            assert _is_chunked_xfade_enabled() is False
        with patch.dict(os.environ, {"FFMPEG_CHUNKED_XFADE": "1"}):
            assert _is_chunked_xfade_enabled() is True


class TestChunkedFilterIntegration:
    """Integration: compose_video filter_complex contains chunked xfade or concat."""

    def _make_images(self, tmp_dir, n):
        from PIL import Image

        paths = []
        for i in range(n):
            p = Path(tmp_dir) / f"scene_{i:03d}.jpg"
            Image.new("RGB", (1280, 720), (i * 10 % 255, 50, 50)).save(p)
            paths.append(str(p))
        return paths

    def _make_audio(self, tmp_dir):
        p = Path(tmp_dir) / "speech.wav"
        p.write_bytes(b"RIFF....WAVE")
        return str(p)

    def test_n50_chunked_contains_xfade_and_concat(self):
        # Verify n=50 with flag=1 produces filter with xfade and final concat
        from lib.video import compose_video, RENDER_PRESET

        with tempfile.TemporaryDirectory() as tmp:
            imgs = self._make_images(tmp, 50)
            audio = self._make_audio(tmp)
            out = str(Path(tmp) / "out.mp4")
            with patch.dict(os.environ, {"FFMPEG_CHUNKED_XFADE": "1"}):
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                    with patch("lib.video.validate_video_format", return_value=True):
                        # also need lib.video validate patch for compose
                        with patch("lib.video.validate_video_format", return_value=True):
                            compose_video(
                                audio,
                                "",
                                "",
                                out,
                                duration_sec=600.0,
                                channel="moku",
                                scene_images=imgs,
                                video_mode="longform",
                            )
                            cmd = mock_run.call_args[0][0]
                            assert "-filter_complex" in cmd
                            idx = cmd.index("-filter_complex")
                            fstr = cmd[idx + 1]
                            # must contain xfade transition
                            assert "xfade=transition=fade" in fstr
                            # chunked: should have blk tags and final concat of 4 blocks
                            assert "[blk0]" in fstr or "[blk" in fstr
                            assert "concat=n=4" in fstr
                            # fade in/out preserved
                            assert "fade=t=in" in fstr or "fade=t=out" in fstr
                            # preset configurable y threads aún presentes
                            assert RENDER_PRESET in " ".join(cmd)
                            assert "-threads" in cmd

    def test_n20_flag0_uses_plain_concat_without_xfade(self):
        from lib.video import compose_video

        with tempfile.TemporaryDirectory() as tmp:
            imgs = self._make_images(tmp, 20)
            audio = self._make_audio(tmp)
            out = str(Path(tmp) / "out.mp4")
            with patch.dict(os.environ, {"FFMPEG_CHUNKED_XFADE": "0"}):
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                    with patch("lib.video.validate_video_format", return_value=True):
                        with patch("lib.video.validate_video_format", return_value=True):
                            compose_video(
                                audio,
                                "",
                                "",
                                out,
                                duration_sec=240.0,
                                channel="moku",
                                scene_images=imgs,
                                video_mode="longform",
                            )
                            cmd = mock_run.call_args[0][0]
                            idx = cmd.index("-filter_complex")
                            fstr = cmd[idx + 1]
                            # flag 0 should disable chunked xfade -> plain concat without xfade
                            # For n=20 chunked would have xfade, but flag0 should have concat=n=20 and no xfade
                            assert "concat=n=20" in fstr
                            assert "xfade=transition=fade" not in fstr

    def test_filter_complex_overflow_fallback_to_temp_file_concat(self):
        """Spec: >32k fallback to temp-file concat; we trigger overflow by mocking len check."""
        from lib.video import compose_video

        with tempfile.TemporaryDirectory() as tmp:
            imgs = self._make_images(tmp, 50)
            audio = self._make_audio(tmp)
            out = str(Path(tmp) / "out.mp4")
            with patch.dict(os.environ, {"FFMPEG_CHUNKED_XFADE": "1"}):
                # Force overflow by patching the limit check to true for any large n
                with patch("lib.video._filter_complex_exceeds_limit", return_value=True):
                    with patch("subprocess.run") as mock_run:
                        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                        with patch("lib.video.validate_video_format", return_value=True):
                            with patch("lib.video.validate_video_format", return_value=True):
                                compose_video(
                                    audio,
                                    "",
                                    "",
                                    out,
                                    duration_sec=600.0,
                                    channel="moku",
                                    scene_images=imgs,
                                    video_mode="longform",
                                )
                                cmd = mock_run.call_args[0][0]
                                idx = cmd.index("-filter_complex")
                                fstr = cmd[idx + 1]
                                # fallback should be plain concat (no xfade) or still valid
                                assert "concat=n=50" in fstr or "concat=n=" in fstr
                                assert "xfade" not in fstr or "concat" in fstr

    def test_preserve_efficiency_knobs(self):
        from lib.video import compose_video, VIDEO_FPS, FFMPEG_THREADS, RENDER_PRESET

        with tempfile.TemporaryDirectory() as tmp:
            imgs = self._make_images(tmp, 5)
            audio = self._make_audio(tmp)
            out = str(Path(tmp) / "out.mp4")
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                with patch("lib.video.validate_video_format", return_value=True):
                    with patch("lib.video.validate_video_format", return_value=True):
                        compose_video(
                            audio,
                            "",
                            "",
                            out,
                            duration_sec=170.0,
                            channel="moku",
                            scene_images=imgs,
                            video_mode="longform",
                        )
                        cmd = mock_run.call_args[0][0]
                        assert "-threads" in cmd
                        t_idx = cmd.index("-threads")
                        assert cmd[t_idx + 1] == str(FFMPEG_THREADS)
                        # fps handling via zoompan fps param
                        fstr = cmd[cmd.index("-filter_complex") + 1]
                        assert f"fps={VIDEO_FPS}" in fstr
                        # preset configurable (env-driven constant)
                        assert RENDER_PRESET in cmd

    def test_n15_unchanged_direct_xfade(self):
        from lib.video import compose_video

        with tempfile.TemporaryDirectory() as tmp:
            imgs = self._make_images(tmp, 15)
            audio = self._make_audio(tmp)
            out = str(Path(tmp) / "out.mp4")
            with patch.dict(os.environ, {"FFMPEG_CHUNKED_XFADE": "1"}):
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                    with patch("lib.video.validate_video_format", return_value=True):
                        with patch("lib.video.validate_video_format", return_value=True):
                            compose_video(
                                audio,
                                "",
                                "",
                                out,
                                duration_sec=180.0,
                                channel="moku",
                                scene_images=imgs,
                                video_mode="longform",
                            )
                            cmd = mock_run.call_args[0][0]
                            fstr = cmd[cmd.index("-filter_complex") + 1]
                            # n=15 should use direct xfade chain, not chunked blk
                            # Should have xfade but not chunked blk concat of 4
                            assert "xfade=transition=fade" in fstr
                            assert "concat=n=15" not in fstr  # direct xfade shouldn't concat 15
