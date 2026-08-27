"""Unit tests for centralized FFmpeg/FFprobe runner and lifecycle manager (Strict TDD)."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lib.ffmpeg import (
    AudioStreamInfo,
    FFmpegCommandResult,
    FFmpegError,
    FFmpegExecutionError,
    FFmpegTimeoutError,
    FFprobeError,
    MediaProbeResult,
    TempMediaContext,
    VideoStreamInfo,
    has_faststart,
    probe_media,
    run_ffmpeg,
    run_ffprobe,
)


class TestFFmpegRunnerExecution:
    """Test suite for run_ffmpeg and run_ffprobe core execution."""

    def test_run_ffmpeg_success(self):
        """Scenario 1: Successful subprocess execution within isolated process group."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("output-line-1\n", "debug-log\n")
        mock_proc.returncode = 0

        with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
            cmd = ["ffmpeg", "-version"]
            result = run_ffmpeg(cmd, timeout=10.0)

            mock_popen.assert_called_once_with(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=None,
                start_new_session=True,
            )
            assert isinstance(result, FFmpegCommandResult)
            assert result.command == cmd
            assert result.returncode == 0
            assert result.stdout == "output-line-1\n"
            assert result.stderr == "debug-log\n"
            assert result.duration_sec >= 0.0

    def test_run_ffmpeg_timeout_kills_process_group(self):
        """Scenario 2: Timeout triggers SIGKILL on process group and raises FFmpegTimeoutError."""
        mock_proc = MagicMock()
        mock_proc.pid = 99999
        mock_proc.communicate.side_effect = subprocess.TimeoutExpired(cmd=["ffmpeg"], timeout=5.0)

        with patch("subprocess.Popen", return_value=mock_proc), \
             patch("os.killpg") as mock_killpg:
            cmd = ["ffmpeg", "-i", "input.mp4", "output.mp4"]
            with pytest.raises(FFmpegTimeoutError) as exc_info:
                run_ffmpeg(cmd, timeout=5.0, check=True)

            mock_killpg.assert_called_once_with(99999, signal.SIGKILL)
            mock_proc.wait.assert_called_once()
            err = exc_info.value
            assert err.timeout == 5.0
            assert err.command == cmd
            assert "5.0" in str(err) or "timed out" in str(err).lower()

    def test_run_ffmpeg_nonzero_exit_raises_execution_error(self):
        """Scenario 3: Non-zero exit code translated to FFmpegExecutionError."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("", "Invalid filter graph: no such filter\n")
        mock_proc.returncode = 1

        with patch("subprocess.Popen", return_value=mock_proc):
            cmd = ["ffmpeg", "-filter_complex", "invalid", "out.mp4"]
            with pytest.raises(FFmpegExecutionError) as exc_info:
                run_ffmpeg(cmd, check=True)

            err = exc_info.value
            assert err.returncode == 1
            assert "Invalid filter graph" in err.stderr
            assert err.command == cmd

    def test_run_ffmpeg_nocheck_returns_result_on_nonzero(self):
        """When check=False, non-zero returncode returns result without raising."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("", "Some non-fatal warning")
        mock_proc.returncode = 2

        with patch("subprocess.Popen", return_value=mock_proc):
            cmd = ["ffmpeg", "-i", "bad.mp4"]
            result = run_ffmpeg(cmd, check=False)
            assert result.returncode == 2
            assert result.stderr == "Some non-fatal warning"

    def test_run_ffmpeg_missing_binary_raises_execution_error(self):
        """Scenario 4: Missing ffmpeg executable raised as explicit binary error."""
        with patch("subprocess.Popen", side_effect=FileNotFoundError("No such file or directory: 'ffmpeg'")):
            cmd = ["ffmpeg", "-version"]
            with pytest.raises(FFmpegExecutionError) as exc_info:
                run_ffmpeg(cmd, check=True)

            err = exc_info.value
            assert err.returncode == 127
            assert "binary not found" in str(err).lower() or "not found" in err.stderr.lower()

    def test_run_ffprobe_success(self):
        """run_ffprobe executes with start_new_session=True and returns FFmpegCommandResult."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ('{"streams": []}', "")
        mock_proc.returncode = 0

        with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
            cmd = ["ffprobe", "-show_format", "video.mp4"]
            result = run_ffprobe(cmd, timeout=15.0)

            mock_popen.assert_called_once_with(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=None,
                start_new_session=True,
            )
            assert result.returncode == 0
            assert result.stdout == '{"streams": []}'

    def test_run_ffprobe_failure_raises_ffprobe_error(self):
        """run_ffprobe non-zero return code raises FFprobeError."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("", "Invalid data found when processing input")
        mock_proc.returncode = 1

        with patch("subprocess.Popen", return_value=mock_proc):
            cmd = ["ffprobe", "corrupt.mp4"]
            with pytest.raises(FFprobeError) as exc_info:
                run_ffprobe(cmd)

            err = exc_info.value
            assert err.returncode == 1
            assert "Invalid data" in err.stderr


class TestMediaMetadataProbing:
    """Test suite for probe_media and has_faststart."""

    def test_probe_media_valid_payload(self, tmp_path):
        """Scenario 5: Structured media probe parses streams, format, dimensions, fps."""
        dummy_file = tmp_path / "valid.mp4"
        dummy_file.write_bytes(b"dummy")

        payload = {
            "format": {
                "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
                "duration": "120.500000",
                "size": "5000000",
                "bit_rate": "331950",
            },
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 768,
                    "height": 1360,
                    "r_frame_rate": "30/1",
                    "pix_fmt": "yuv420p",
                    "duration": "120.5",
                    "bit_rate": "250000",
                    "nb_frames": "3615",
                },
                {
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "sample_rate": "44100",
                    "channels": 2,
                    "duration": "120.48",
                    "bit_rate": "128000",
                },
            ],
        }

        mock_res = FFmpegCommandResult(
            command=["ffprobe"],
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
            duration_sec=0.1,
        )

        with patch("lib.ffmpeg.run_ffprobe", return_value=mock_res):
            result = probe_media(dummy_file)

            assert isinstance(result, MediaProbeResult)
            assert result.format_name == "mov,mp4,m4a,3gp,3g2,mj2"
            assert result.duration == pytest.approx(120.5)
            assert result.size_bytes == 5000000
            assert result.bit_rate == 331950

            assert len(result.video_streams) == 1
            v = result.primary_video
            assert v is not None
            assert v.codec_name == "h264"
            assert v.width == 768
            assert v.height == 1360
            assert v.fps == pytest.approx(30.0)
            assert v.pix_fmt == "yuv420p"
            assert v.duration == pytest.approx(120.5)
            assert v.bit_rate == 250000
            assert v.nb_frames == 3615

            assert len(result.audio_streams) == 1
            a = result.primary_audio
            assert a is not None
            assert a.codec_name == "aac"
            assert a.sample_rate == 44100
            assert a.channels == 2
            assert a.duration == pytest.approx(120.48)
            assert a.bit_rate == 128000

    def test_probe_media_nonexistent_file_raises_ffprobe_error(self):
        """Non-existent media file raises FFprobeError."""
        with pytest.raises(FFprobeError, match="File not found"):
            probe_media("/nonexistent/path/video.mp4")

    def test_probe_media_corrupted_json_raises_ffprobe_error(self, tmp_path):
        """Scenario 6: Corrupted JSON stdout from ffprobe raises FFprobeError."""
        dummy_file = tmp_path / "corrupt.mp4"
        dummy_file.write_bytes(b"corrupt")

        mock_res = FFmpegCommandResult(
            command=["ffprobe"],
            returncode=0,
            stdout="INVALID_JSON_STREAM{{{",
            stderr="warning: header corrupted",
            duration_sec=0.1,
        )

        with patch("lib.ffmpeg.run_ffprobe", return_value=mock_res):
            with pytest.raises(FFprobeError, match="JSON"):
                probe_media(dummy_file)

    def test_probe_media_no_video_stream(self, tmp_path):
        """Audio-only media returns empty video_streams and primary_video is None."""
        dummy_file = tmp_path / "audio.wav"
        dummy_file.write_bytes(b"audio_bytes")

        payload = {
            "format": {"format_name": "wav", "duration": "10.0", "size": "1000", "bit_rate": "800"},
            "streams": [
                {"codec_type": "audio", "codec_name": "pcm_s16le", "sample_rate": "44100", "channels": 1, "duration": "10.0"}
            ],
        }
        mock_res = FFmpegCommandResult(command=["ffprobe"], returncode=0, stdout=json.dumps(payload), stderr="", duration_sec=0.05)

        with patch("lib.ffmpeg.run_ffprobe", return_value=mock_res):
            result = probe_media(dummy_file)
            assert result.primary_video is None
            assert result.primary_audio is not None
            assert result.primary_audio.codec_name == "pcm_s16le"

    def test_has_faststart_moov_before_mdat(self, tmp_path):
        """has_faststart returns True when moov atom precedes mdat."""
        video = tmp_path / "faststart.mp4"
        # Atom structure: 8 bytes ftyp, 8 bytes moov, 8 bytes mdat
        # Size=8 (0x00000008), atom=ftyp; size=8, atom=moov; size=8, atom=mdat
        video.write_bytes(
            b"\x00\x00\x00\x08ftyp"
            b"\x00\x00\x00\x08moov"
            b"\x00\x00\x00\x08mdat"
        )
        assert has_faststart(video) is True

    def test_has_faststart_mdat_before_moov(self, tmp_path):
        """has_faststart returns False when mdat atom precedes moov."""
        video = tmp_path / "slowstart.mp4"
        video.write_bytes(
            b"\x00\x00\x00\x08ftyp"
            b"\x00\x00\x00\x08mdat"
            b"\x00\x00\x00\x08moov"
        )
        assert has_faststart(video) is False

    def test_has_faststart_empty_or_nonexistent(self, tmp_path):
        """has_faststart returns False on empty file and handles nonexistent gracefully."""
        empty = tmp_path / "empty.mp4"
        empty.write_bytes(b"")
        assert has_faststart(empty) is False
        assert has_faststart(tmp_path / "nonexistent.mp4") is False


class TestTempMediaContextLifecycle:
    """Test suite for TempMediaContext workspace isolation and cleanup."""

    def test_temp_media_context_normal_exit_cleanup(self, tmp_path):
        """Lifecycle Scenario 1: Scratch directory and all files deleted on normal exit."""
        temp_dir_path = None
        with TempMediaContext(work_dir=tmp_path, prefix="test_media_") as ctx:
            temp_dir_path = ctx.path
            assert temp_dir_path.exists()
            assert temp_dir_path.parent == tmp_path

            temp_file = ctx.create_temp_file(suffix=".mp4", prefix="clip_")
            assert temp_file.exists()
            assert temp_file.parent == temp_dir_path
            temp_file.write_bytes(b"sample video bytes")

        # After block exit, workspace MUST be removed
        assert not temp_dir_path.exists()

    def test_temp_media_context_cleanup_on_exception(self, tmp_path):
        """Lifecycle Scenario 2: Guaranteed cleanup even when exception is raised."""
        temp_dir_path = None
        with pytest.raises(ValueError, match="simulated composition error"):
            with TempMediaContext(work_dir=tmp_path, retain_on_error=False) as ctx:
                temp_dir_path = ctx.path
                temp_file = ctx.create_temp_file(suffix=".wav")
                temp_file.write_bytes(b"scratch audio")
                raise ValueError("simulated composition error")

        assert temp_dir_path is not None
        assert not temp_dir_path.exists()

    def test_temp_media_context_retain_on_error(self, tmp_path):
        """Lifecycle Scenario 3: Debug retention preserves directory when retain_on_error=True."""
        temp_dir_path = None
        with pytest.raises(RuntimeError, match="fatal render glitch"):
            with TempMediaContext(work_dir=tmp_path, retain_on_error=True) as ctx:
                temp_dir_path = ctx.path
                temp_file = ctx.create_temp_file(suffix=".mp4", prefix="debug_")
                temp_file.write_bytes(b"debug artifacts")
                raise RuntimeError("fatal render glitch")

        assert temp_dir_path is not None
        assert temp_dir_path.exists()
        # Clean up preserved debug directory
        import shutil
        shutil.rmtree(temp_dir_path, ignore_errors=True)

    def test_temp_media_context_concurrent_isolation(self, tmp_path):
        """Lifecycle Scenario 4: Concurrent contexts operate in strictly isolated directories."""
        with TempMediaContext(work_dir=tmp_path, prefix="worker1_") as ctx1:
            with TempMediaContext(work_dir=tmp_path, prefix="worker2_") as ctx2:
                assert ctx1.path != ctx2.path
                f1 = ctx1.create_temp_file(suffix=".mp4", prefix="w1_")
                f2 = ctx2.create_temp_file(suffix=".mp4", prefix="w2_")
                f1.write_bytes(b"worker 1 data")
                f2.write_bytes(b"worker 2 data")

                assert f1.parent == ctx1.path
                assert f2.parent == ctx2.path
                assert f1.exists() and f2.exists()

            # ctx2 has exited -> ctx2 directory deleted, but ctx1 remains
            assert not ctx2.path.exists()
            assert ctx1.path.exists()
            assert f1.exists()

        assert not ctx1.path.exists()
