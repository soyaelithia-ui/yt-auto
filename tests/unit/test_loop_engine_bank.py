"""
Unit tests for LoopVideoEngine master loop bank, catalog defaults, path traversal,
and FFmpeg timeout handling (Phase 1).
"""
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lib.ffmpeg import FFmpegTimeoutError
from src.config import BASE_DIR, DEFAULT_DB_PATH
from src.core.catalog import LoopCatalogRepository, LoopRecord
from src.media.loop_engine import (
    LoopCompositionError,
    LoopVideoAssetError,
    LoopVideoEngine,
)


class TestLoopEngineBankDefaultsAndSecurity:
    """Test suite for catalog default path, path traversal prevention, and timeout handling."""

    def test_catalog_db_default_path_selection(self):
        """Engine defaults catalog DB to data/loop_catalog.db when present on disk."""
        catalog_file = BASE_DIR / "data" / "loop_catalog.db"
        engine = LoopVideoEngine()
        if catalog_file.is_file():
            assert engine.db_path == str(catalog_file)
            assert engine.catalog.db_path == str(catalog_file)
        else:
            assert engine.db_path == DEFAULT_DB_PATH

    def test_enable_live_synth_defaults_to_false(self):
        """enable_live_synth is False by default when no env var or flag is passed."""
        with patch.dict(os.environ, {}, clear=True):
            engine = LoopVideoEngine()
            assert engine.enable_live_synth is False

    def test_enable_live_synth_via_flag_or_env(self):
        """enable_live_synth is True when explicitly passed or ENABLE_LIVE_LOOP_SYNTH=1."""
        engine = LoopVideoEngine(enable_live_synth=True)
        assert engine.enable_live_synth is True

        with patch.dict(os.environ, {"ENABLE_LIVE_LOOP_SYNTH": "1"}):
            engine_env = LoopVideoEngine()
            assert engine_env.enable_live_synth is True

    def test_path_traversal_in_mock_loop_record_raises_asset_error(self):
        """
        Threat matrix: Mock loop record pointing to ../../etc/passwd or /etc/passwd outside assets
        must raise LoopVideoAssetError.
        """
        engine = LoopVideoEngine()
        fake_traversal_record = LoopRecord(
            loop_id="malicious_traversal",
            category="dark_ambient",
            technology="ffmpeg_lavfi",
            orientation="vertical",
            width=1080,
            height=1920,
            duration_sec=60.0,
            fps=30,
            file_path="../../etc/passwd",
            file_size_bytes=1024,
            sha256="abc123",
        )
        engine.catalog = MagicMock()
        engine.catalog.get_best_loop.return_value = fake_traversal_record

        with pytest.raises(LoopVideoAssetError) as exc_info:
            engine.resolve_loop_video(category="dark_ambient", allow_fallback=False)
        assert any(term in str(exc_info.value).lower() for term in ("traversal", "not found", "invalid", "security"))

    def test_path_traversal_absolute_file_path_raises_asset_error(self):
        """
        Threat matrix: Mock loop record pointing to /etc/passwd outside assets
        must raise LoopVideoAssetError.
        """
        engine = LoopVideoEngine()
        fake_traversal_record = LoopRecord(
            loop_id="malicious_absolute_traversal",
            category="dark_ambient",
            technology="ffmpeg_lavfi",
            orientation="vertical",
            width=1080,
            height=1920,
            duration_sec=60.0,
            fps=30,
            file_path="/etc/passwd",
            file_size_bytes=1024,
            sha256="abc123",
        )
        engine.catalog = MagicMock()
        engine.catalog.get_best_loop.return_value = fake_traversal_record

        with pytest.raises(LoopVideoAssetError) as exc_info:
            engine.resolve_loop_video(category="dark_ambient", allow_fallback=False)
        assert any(term in str(exc_info.value).lower() for term in ("traversal", "not found", "invalid", "security"))

    def test_path_traversal_in_category_name_raises_asset_error(self):
        """
        Threat matrix: Attempting path traversal via category name raises LoopVideoAssetError.
        """
        engine = LoopVideoEngine()
        with pytest.raises(LoopVideoAssetError) as exc_info:
            engine.resolve_loop_video(category="../../etc/passwd", allow_fallback=False)
        assert any(term in str(exc_info.value).lower() for term in ("traversal", "passwd", "no video loops found", "no loop video"))

    def test_ffmpeg_timeout_raises_timeout_error(self, tmp_path):
        """
        Threat matrix: Subprocess hang in FFmpeg raises FFmpegTimeoutError.
        """
        engine = LoopVideoEngine()
        dummy_audio = tmp_path / "audio.wav"
        dummy_audio.write_bytes(b"RIFF" + b"\x00" * 40)
        dummy_video = tmp_path / "video.mp4"
        dummy_video.write_bytes(b"ftyp" + b"\x00" * 40)
        output_file = tmp_path / "out.mp4"

        with patch("src.media.loop_engine.run_ffmpeg", side_effect=FFmpegTimeoutError("FFmpeg timed out", timeout=5.0)):
            with pytest.raises(FFmpegTimeoutError):
                engine.compose(
                    audio_path=dummy_audio,
                    output_video_path=output_file,
                    category="dark_ambient",
                    timeout=5.0,
                )
