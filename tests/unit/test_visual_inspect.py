"""Unit tests for Visual QA Inspection, Keyframe Extraction, and Artifact Detection."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.cli.visual_inspect import (
    VisualQAResult,
    compute_keyframe_timestamps,
    inspect_video_media,
    parse_blackdetect_output,
    parse_freezedetect_output,
)


class TestKeyframeTimestamps:
    """Requirement 1: 5-Point Canonical Keyframe Timing."""

    def test_sixty_second_video_timestamps(self):
        ts = compute_keyframe_timestamps(60.0)
        assert len(ts) == 5
        assert ts == [6.0, 18.0, 30.0, 42.0, 54.0]

    def test_subsecond_video_timestamps(self):
        ts = compute_keyframe_timestamps(0.8)
        assert len(ts) == 5
        assert ts == [0.08, 0.24, 0.4, 0.56, 0.72]
        # Strictly ascending and non-colliding
        for i in range(len(ts) - 1):
            assert ts[i] < ts[i + 1]


class TestArtifactDetectionParsers:
    """Requirements 2 & 3: blackdetect and freezedetect parsing."""

    def test_parse_blackdetect_clean_output(self):
        stderr = """
        [Parsed_blackdetect_0 @ 0x55d142] black_start: 0.1 black_end: 0.3 black_duration: 0.2
        """
        # Duration < 0.5 should not trigger violation
        intervals = parse_blackdetect_output(stderr, min_duration=0.5)
        assert len(intervals) == 0

    def test_parse_blackdetect_violation(self):
        stderr = """
        [blackdetect @ 0x55a1b0] black_start:14.000000 black_end:15.200000 black_duration:1.200000
        """
        intervals = parse_blackdetect_output(stderr, min_duration=0.5)
        assert len(intervals) == 1
        assert pytest.approx(intervals[0]["start"], 0.01) == 14.0
        assert pytest.approx(intervals[0]["end"], 0.01) == 15.2
        assert pytest.approx(intervals[0]["duration"], 0.01) == 1.2

    def test_parse_freezedetect_clean_output(self):
        stderr = """
        [freezedetect @ 0x55c110] lavfi.freezedetect.freeze_start: 10.0
        [freezedetect @ 0x55c110] lavfi.freezedetect.freeze_duration: 1.5
        [freezedetect @ 0x55c110] lavfi.freezedetect.freeze_end: 11.5
        """
        # Duration < 2.0 should not trigger violation
        intervals = parse_freezedetect_output(stderr, min_duration=2.0)
        assert len(intervals) == 0

    def test_parse_freezedetect_violation(self):
        stderr = """
        [freezedetect @ 0x55c110] lavfi.freezedetect.freeze_start: 20.000
        [freezedetect @ 0x55c110] lavfi.freezedetect.freeze_duration: 3.500
        [freezedetect @ 0x55c110] lavfi.freezedetect.freeze_end: 23.500
        """
        intervals = parse_freezedetect_output(stderr, min_duration=2.0)
        assert len(intervals) == 1
        assert pytest.approx(intervals[0]["start"], 0.01) == 20.0
        assert pytest.approx(intervals[0]["duration"], 0.01) == 3.5
        assert pytest.approx(intervals[0]["end"], 0.01) == 23.5


    def test_parse_freezedetect_trailing_freeze_without_end(self):
        stderr = """
        [freezedetect @ 0x55c110] lavfi.freezedetect.freeze_start: 15.000
        [freezedetect @ 0x55c110] lavfi.freezedetect.freeze_duration: 5.000
        """
        intervals = parse_freezedetect_output(stderr, min_duration=2.0)
        assert len(intervals) == 1
        assert intervals[0]["start"] == 15.0
        assert intervals[0]["duration"] == 5.0
        assert intervals[0]["end"] == 20.0


class TestInspectVideoMediaWorkflow:
    """Requirement 4: End-to-end visual inspection and aggregation."""

    @patch("src.cli.visual_inspect.run_ffmpeg")
    @patch("src.cli.visual_inspect.probe_media")
    def test_inspect_clean_video_passes(self, mock_probe, mock_run_ffmpeg, tmp_path: Path):
        mock_probe.return_value = {
            "format": {"duration": "30.0"},
            "streams": [{"codec_type": "video", "width": 1080, "height": 1920}],
        }
        def _mock_ffmpeg(cmd, check=False):
            if len(cmd) > 0 and str(cmd[-1]).endswith(".png"):
                p = Path(cmd[-1])
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b"dummy_png_keyframe_data")
            return MagicMock(returncode=0, stderr="")

        mock_run_ffmpeg.side_effect = _mock_ffmpeg

        video_file = tmp_path / "test.mp4"
        video_file.touch()

        out_dir = tmp_path / "qa_output"
        result = inspect_video_media(video_file, out_dir)

        assert isinstance(result, VisualQAResult)
        assert result.duration_sec == 30.0
        assert result.resolution == (1080, 1920)
        assert len(result.keyframe_paths) == 5
        assert result.black_intervals == []
        assert result.freeze_intervals == []
        assert result.overall_pass is True

    @patch("src.cli.visual_inspect.run_ffmpeg")
    @patch("src.cli.visual_inspect.probe_media")
    def test_inspect_missing_keyframes_fails_overall_pass(self, mock_probe, mock_run_ffmpeg, tmp_path: Path):
        mock_probe.return_value = {
            "format": {"duration": "30.0"},
            "streams": [{"codec_type": "video", "width": 1080, "height": 1920}],
        }
        # Does not create PNG files
        mock_run_ffmpeg.return_value = MagicMock(returncode=1, stderr="Failed to extract")

        video_file = tmp_path / "test.mp4"
        video_file.touch()

        out_dir = tmp_path / "qa_output"
        result = inspect_video_media(video_file, out_dir)

        assert len(result.keyframe_paths) == 0
        assert result.overall_pass is False

    @patch("src.cli.visual_inspect.run_ffmpeg")
    @patch("src.cli.visual_inspect.probe_media")
    def test_inspect_black_artifact_fails(self, mock_probe, mock_run_ffmpeg, tmp_path: Path):
        mock_probe.return_value = {
            "format": {"duration": "20.0"},
            "streams": [{"codec_type": "video", "width": 1080, "height": 1920}],
        }
        def _mock_ffmpeg(cmd, check=False):
            if len(cmd) > 0 and str(cmd[-1]).endswith(".png"):
                p = Path(cmd[-1])
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b"dummy_png_keyframe_data")
                return MagicMock(returncode=0, stderr="")
            return MagicMock(
                returncode=0,
                stderr="[blackdetect @ 0x1] black_start:5.0 black_end:7.0 black_duration:2.0",
            )

        mock_run_ffmpeg.side_effect = _mock_ffmpeg

        video_file = tmp_path / "corrupt_black.mp4"
        video_file.touch()

        out_dir = tmp_path / "qa_output"
        result = inspect_video_media(video_file, out_dir)

        assert result.overall_pass is False
        assert len(result.black_intervals) == 1

    @patch("src.cli.visual_inspect.probe_media")
    def test_inspect_nonexistent_file_fails(self, mock_probe, tmp_path: Path):
        from lib.ffmpeg import FFprobeError

        mock_probe.side_effect = FFprobeError("File not found")
        non_existent = tmp_path / "missing.mp4"
        out_dir = tmp_path / "qa_output"

        with pytest.raises((FFprobeError, FileNotFoundError)):
            inspect_video_media(non_existent, out_dir)
