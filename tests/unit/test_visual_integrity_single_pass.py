"""Unit tests for probe_visual_integrity_single_pass (R3).

Validates:
1. Exact command arguments with explicit filtergraph output mapping (-map "[vb]" -map "[vl]").
2. Extraction of black durations and signalstats YAVG from combined stderr.
3. Resilience to missing, empty, or corrupt files.
4. Metric calculations: average luminance, dark ratio, and pass/fail thresholds.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.quality import (
    LUMINANCE_SAMPLE_FPS,
    probe_visual_integrity_single_pass,
)


class TestVisualIntegritySinglePass:
    """Test suite for the single-pass QA visual probe."""

    def test_missing_or_empty_file_returns_degraded_structure(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent.mp4"
        result = probe_visual_integrity_single_pass(missing)
        assert result["passed"] is False
        assert result["degraded"] is True
        assert "artifact missing or empty" in result["degraded_reason"]

        empty = tmp_path / "empty.mp4"
        empty.touch()
        result_empty = probe_visual_integrity_single_pass(empty)
        assert result_empty["passed"] is False
        assert result_empty["degraded"] is True

    @patch("subprocess.run")
    def test_ffmpeg_command_structure_and_explicit_mapping(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        video = tmp_path / "sample.mp4"
        video.write_bytes(b"dummy_mp4_bytes")

        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stderr = (
            "[blackdetect @ 0x1] black_start:1.00 black_end:2.00 black_duration:1.00\n"
            "lavfi.signalstats.YAVG=45.2\n"
            "lavfi.signalstats.YAVG=50.1\n"
        )
        mock_run.return_value = mock_res

        result = probe_visual_integrity_single_pass(video, threads=2)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ffmpeg"
        assert "-threads" in cmd and cmd[cmd.index("-threads") + 1] == "2"
        assert "-i" in cmd and cmd[cmd.index("-i") + 1] == str(video)
        assert "-filter_complex" in cmd

        fc = cmd[cmd.index("-filter_complex") + 1]
        assert "[0:v]blackdetect=d=0.5:pix_th=0.10[vb]" in fc
        assert f"[0:v]fps={LUMINANCE_SAMPLE_FPS},signalstats,metadata=print:key=lavfi.signalstats.YAVG[vl]" in fc

        # Explicit stream mapping requirement
        maps = [cmd[i + 1] for i in range(len(cmd) - 1) if cmd[i] == "-map"]
        assert "[vb]" in maps
        assert "[vl]" in maps
        assert "-f" in cmd and cmd[cmd.index("-f") + 1] == "null"
        assert cmd[-1] == "-"

        assert result["longest_black_seconds"] == 1.00
        assert result["black_segments"] == [1.00]
        assert 47.0 < result["avg_luminance"] < 48.0
        assert result["passed"] is True
        assert result["black_passed"] is True
        assert result["luminance_passed"] is True

    @patch("subprocess.run")
    def test_black_duration_exceeding_threshold_fails(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        video = tmp_path / "dark.mp4"
        video.write_bytes(b"dummy_mp4_bytes")

        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stderr = (
            "[blackdetect @ 0x1] black_start:0.00 black_end:3.50 black_duration:3.50\n"
            "lavfi.signalstats.YAVG=55.0\n"
        )
        mock_run.return_value = mock_res

        result = probe_visual_integrity_single_pass(video)
        assert result["longest_black_seconds"] == 3.50
        assert result["black_passed"] is False
        assert result["passed"] is False

    @patch("subprocess.run")
    def test_low_luminance_fails(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        video = tmp_path / "pitch_black.mp4"
        video.write_bytes(b"dummy_mp4_bytes")

        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stderr = (
            "lavfi.signalstats.YAVG=5.0\n"
            "lavfi.signalstats.YAVG=6.2\n"
        )
        mock_run.return_value = mock_res

        result = probe_visual_integrity_single_pass(video)
        assert result["avg_luminance"] < 22.0
        assert result["luminance_passed"] is False
        assert result["passed"] is False
