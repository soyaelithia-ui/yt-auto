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

    def test_case_insensitive_mp4_resolution(self, temp_loop_dirs):
        shorts, longs = temp_loop_dirs
        clip1 = shorts / "LOOP_01.MP4"
        clip2 = shorts / "loop_02.mp4"
        clip1.write_bytes(b"DATA_UPPER")
        clip2.write_bytes(b"DATA_LOWER")

        engine = LoopVideoEngine()
        engine.shorts_videos_dir = shorts
        LoopVideoEngine._rotation_indices["shorts"] = 0

        p1 = engine.resolve_continuous_loop(orientation="vertical")
        p2 = engine.resolve_continuous_loop(orientation="vertical")
        assert {p1.name, p2.name} == {"LOOP_01.MP4", "loop_02.mp4"}

    def test_persistent_rotation_state(self, temp_loop_dirs, monkeypatch, tmp_path):
        shorts, longs = temp_loop_dirs
        c1 = shorts / "c1.mp4"
        c2 = shorts / "c2.mp4"
        c1.write_bytes(b"1")
        c2.write_bytes(b"2")

        state_file = tmp_path / "test_rotation_state.json"
        import src.media.loop_engine as le_mod
        monkeypatch.setattr(le_mod, "_ROTATION_STATE_FILE", state_file)

        LoopVideoEngine.reset_rotation_state("shorts")
        engine = LoopVideoEngine()
        engine.shorts_videos_dir = shorts

        # First call with persist=True
        first = engine.resolve_continuous_loop("vertical", persist=True)
        assert first == c1

        # Simulate new process instance with fresh in-memory indices
        LoopVideoEngine._rotation_indices = {"shorts": 0, "longs": 0}
        second = engine.resolve_continuous_loop("vertical", persist=True)
        assert second == c2

    def test_test_fixture_loop_profile_is_main_and_standard_durations(self):
        from lib.ffmpeg import probe_media
        v_fixture = LoopVideoEngine._get_or_create_test_fixture_loop("vertical")
        h_fixture = LoopVideoEngine._get_or_create_test_fixture_loop("horizontal")

        assert v_fixture.is_file()
        assert h_fixture.is_file()

        v_probe = probe_media(v_fixture)
        h_probe = probe_media(h_fixture)

        assert v_probe.video_streams
        assert h_probe.video_streams

        v_prof = str(v_probe.video_streams[0].profile).lower()
        h_prof = str(h_probe.video_streams[0].profile).lower()

        assert "main" in v_prof or "baseline" in v_prof
        assert "main" in h_prof or "baseline" in h_prof

        assert v_probe.video_streams[0].width == 1080
        assert v_probe.video_streams[0].height == 1920
        assert h_probe.video_streams[0].width == 1920
        assert h_probe.video_streams[0].height == 1080

    def test_ffconcat_escapes_single_quotes_in_path(self, temp_loop_dirs, tmp_path):
        import subprocess
        shorts, longs = temp_loop_dirs
        clip_with_quote = shorts / "horror's_loop.mp4"
        # Copy valid fixture content
        v_fix = LoopVideoEngine._get_or_create_test_fixture_loop("vertical")
        clip_with_quote.write_bytes(v_fix.read_bytes())

        engine = LoopVideoEngine()
        engine.shorts_videos_dir = shorts

        # Create valid test audio with real signal so loudnorm does not divide by zero
        dummy_wav = tmp_path / "test_audio.wav"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                "-c:a", "pcm_s16le",
                str(dummy_wav),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )

        out_mp4 = tmp_path / "out_quoted.mp4"
        res = engine.compose(
            audio_path=dummy_wav,
            output_video_path=out_mp4,
            orientation="vertical",
            video_loop_path=clip_with_quote,
            duration_sec=1.0,
        )
        assert Path(res).is_file()
        assert Path(res).stat().st_size > 0


class TestLocalAIThumbnails:
    """Thumbnail metadata delegates to the local text-free AI bank."""

    def test_seo_optimizer_requests_local_text_free_asset(self):
        optimizer = SeoOptimizerAgent()
        meta = optimizer.optimize("El Misterio de SCP-087", target_format="short")
        request = meta["thumbnail_asset_request"]
        assert request["bank"] == "local_ai"
        assert request["text_free"] is True

    def test_thumbnail_engine_accepts_cover_prompt_and_viral_hook(self, tmp_path: Path):
        engine = ThumbnailEngine()
        out_thumb = tmp_path / "thumb.jpg"
        cfg = ThumbnailConfig(
            title="SCP-087: La Escalera Infinita",
            channel_id="moku",
            hook_text="ignored metadata",
            output_path=out_thumb,
            cover_prompt="local AI atmospheric asset",
            metadata={"text_free": True},
        )
        res = engine.generate(config=cfg)
        assert res.is_file()
        assert res.stat().st_size > 5000
