"""Unit tests for the Continuous Single-Loop Composition Engine and Prompt-Driven Thumbnails."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.media.interface import CatalogAssetNotFoundError
from src.media.loop_engine import LoopVideoEngine
from src.agents.seo_optimizer import SeoOptimizerAgent
from src.media.thumbnails.engine import ThumbnailConfig, ThumbnailEngine


@pytest.fixture
def temp_loop_dirs(tmp_path: Path):
    shorts = tmp_path / "assets" / "videos" / "shorts"
    longs = tmp_path / "assets" / "videos" / "longs"
    shorts.mkdir(parents=True, exist_ok=True)
    longs.mkdir(parents=True, exist_ok=True)
    (shorts / ".gitkeep").touch()
    (longs / ".gitkeep").touch()
    return shorts, longs


class TestContinuousSingleLoopEngine:
    """Tests for the Continuous Single-Loop Engine."""

    def test_fail_fast_safeguard_empty_shorts(self, temp_loop_dirs):
        shorts, longs = temp_loop_dirs
        engine = LoopVideoEngine()
        engine.shorts_videos_dir = shorts
        engine.longs_videos_dir = longs

        with pytest.raises(CatalogAssetNotFoundError) as exc_info:
            engine.resolve_continuous_loop(orientation="vertical", allow_test_mock=False)

        err_msg = str(exc_info.value)
        assert "No video loops found" in err_msg
        assert str(shorts) in err_msg
        assert "10s vertical 9:16" in err_msg

    def test_fail_fast_safeguard_empty_longs(self, temp_loop_dirs):
        shorts, longs = temp_loop_dirs
        engine = LoopVideoEngine()
        engine.shorts_videos_dir = shorts
        engine.longs_videos_dir = longs

        with pytest.raises(CatalogAssetNotFoundError) as exc_info:
            engine.resolve_continuous_loop(orientation="horizontal", allow_test_mock=False)

        err_msg = str(exc_info.value)
        assert "No video loops found" in err_msg
        assert str(longs) in err_msg
        assert "30s horizontal 16:9" in err_msg

    def test_round_robin_rotation_neutral(self, temp_loop_dirs):
        shorts, longs = temp_loop_dirs
        # Populate 3 clips in shorts
        clip1 = shorts / "loop_01.mp4"
        clip2 = shorts / "loop_02.mp4"
        clip3 = shorts / "loop_03.mp4"
        clip1.write_bytes(b"DATA_1")
        clip2.write_bytes(b"DATA_2")
        clip3.write_bytes(b"DATA_3")

        engine = LoopVideoEngine()
        engine.shorts_videos_dir = shorts
        engine.longs_videos_dir = longs
        LoopVideoEngine._rotation_indices["shorts"] = 0

        # Rotate across calls, channel agnostic
        pick1 = engine.resolve_continuous_loop(orientation="vertical")
        pick2 = engine.resolve_continuous_loop(orientation="vertical")
        pick3 = engine.resolve_continuous_loop(orientation="vertical")
        pick4 = engine.resolve_continuous_loop(orientation="vertical")

        assert pick1 == clip1
        assert pick2 == clip2
        assert pick3 == clip3
        assert pick4 == clip1  # wraps around

    def test_horizontal_longs_resolution(self, temp_loop_dirs):
        shorts, longs = temp_loop_dirs
        h_clip = longs / "long_loop_01.mp4"
        h_clip.write_bytes(b"LONG_DATA")

        engine = LoopVideoEngine()
        engine.shorts_videos_dir = shorts
        engine.longs_videos_dir = longs
        LoopVideoEngine._rotation_indices["longs"] = 0

        picked = engine.resolve_continuous_loop(orientation="horizontal")
        assert picked == h_clip

    def test_test_mock_fallback_when_allowed(self, temp_loop_dirs):
        shorts, longs = temp_loop_dirs
        engine = LoopVideoEngine()
        engine.shorts_videos_dir = shorts
        engine.longs_videos_dir = longs

        mock_loop = engine.resolve_continuous_loop(orientation="vertical", allow_test_mock=True)
        assert mock_loop.is_file()
        assert mock_loop.stat().st_size > 0


class TestPromptDrivenThumbnails:
    """Tests for prompt-driven real-time thumbnail generation."""

    def test_seo_optimizer_generates_chiaroscuro_and_3_to_5_word_hook(self):
        optimizer = SeoOptimizerAgent()
        meta = optimizer.optimize("El Misterio de SCP-087", target_format="short")

        assert "thumbnail_concepts" in meta
        concepts = meta["thumbnail_concepts"]
        assert len(concepts) >= 1

        first = concepts[0]
        assert "Claroscuro" in first["visual_layout"] or "Chiaroscuro" in first["visual_layout"]
        assert "sujeto focal misterioso" in first["visual_layout"].lower()

        # Headline hook must be 3-5 words
        words = first["big_headline"].split()
        assert 3 <= len(words) <= 6

    def test_thumbnail_engine_accepts_cover_prompt_and_viral_hook(self, tmp_path: Path):
        engine = ThumbnailEngine()
        out_thumb = tmp_path / "thumb.jpg"
        cfg = ThumbnailConfig(
            title="SCP-087: La Escalera Infinita",
            channel_id="moku",
            hook_text="¡NUNCA ENTRES AQUÍ! ⚠️",
            output_path=out_thumb,
            cover_prompt="Claroscuro de alto CTR con sujeto focal misterioso en penumbra",
            metadata={"visual_layout": "Claroscuro", "big_headline": "¡NUNCA ENTRES AQUÍ! ⚠️"},
        )
        res = engine.generate(config=cfg)
        assert res.is_file()
        assert res.stat().st_size > 5000
