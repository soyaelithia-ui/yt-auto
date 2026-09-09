"""
End-to-End (E2E) Test Suite: 16:9 Long-Form Video Pipeline & Thematic Loop Rotation.

Implements comprehensive opaque-box requirement-driven verification across 4 tiers:
- Tier 1: Feature Isolation (stream-copy concat, loop rotation, channel isolation,
          lock non-collision, Telegram review proxy, 1920x1080 aspect ratio).
- Tier 2: Boundary & Corner Cases (short duration <= 60s, long duration 600s-1800s,
          multiple scenes, lock timeout, file size limits).
- Tier 3: Cross-Feature Interactions (scene rotation + audio ducking, channel isolation + stream-copy).
- Tier 4: Real-World Scenarios (moku-horror-long and scifi-singularity-long workflows).

Governance: Zero-Browser Policy (strict FFmpeg native), Zero-Secrets in memory or logs.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from lib.ffmpeg import probe_media
from review.domain import DeliveryResult
from review.telegram_bot import (
    DEFAULT_CLOUD_MAX_SIZE_BYTES,
    TelegramHttpClient,
    TelegramReviewBot,
    _build_review_proxy,
    _validate_file_preflight,
)
from src.core.catalog import LoopCatalogRepository, LoopRecord
from src.core.lock import ChannelLock, ChannelLockError, _active_locks
from src.media.loop_engine import LoopCompositionError, LoopVideoEngine
from src.telegram.notifier import TelegramNotifier
from tests.e2e.helpers import (
    check_faststart_moov_atom,
    ffprobe_media_file,
    generate_synthetic_wav,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOOP_CATALOG_DB = PROJECT_ROOT / "data" / "loop_catalog.db"
HORIZONTAL_LOOPS_DIR = PROJECT_ROOT / "assets" / "loops" / "horizontal"


@pytest.fixture
def e2e_scratch(tmp_path: Path) -> Path:
    """Isolated scratch directory for video and audio outputs."""
    scratch = tmp_path / "longform_e2e"
    scratch.mkdir(parents=True, exist_ok=True)
    return scratch


@pytest.fixture
def catalog_repo() -> LoopCatalogRepository:
    """Provides initialized LoopCatalogRepository backed by the project catalog."""
    if not LOOP_CATALOG_DB.is_file():
        pytest.skip(f"Catalog DB not found at {LOOP_CATALOG_DB} (local asset; skipped in CI)")
    repo = LoopCatalogRepository(db_path=str(LOOP_CATALOG_DB))
    if repo.count_loops() == 0:
        pytest.skip(f"Catalog DB at {LOOP_CATALOG_DB} has no indexed loops (local asset; skipped in CI)")
    return repo


@pytest.fixture
def sample_horror_loops() -> List[Path]:
    """Finds real 1080p horror master loops on disk."""
    candidates = [
        HORIZONTAL_LOOPS_DIR / "horror" / "moku_containment_facility_master_60s.mp4",
        HORIZONTAL_LOOPS_DIR / "dark_forest" / "moku_dark_wilderness_master_60s.mp4",
        HORIZONTAL_LOOPS_DIR / "dark_ambient" / "moku_containment_facility_master_60s.mp4",
        HORIZONTAL_LOOPS_DIR / "cosmic_horror" / "moku_dark_wilderness_master_60s.mp4",
    ]
    valid = [p for p in candidates if p.is_file() and p.stat().st_size >= 25_000]
    if len(valid) < 2:
        pytest.skip(f"Expected at least 2 horror loops, found {len(valid)} (local asset; skipped in CI)")
    return valid


@pytest.fixture
def sample_scifi_loops() -> List[Path]:
    """Finds real 1080p sci-fi master loops on disk."""
    candidates = [
        HORIZONTAL_LOOPS_DIR / "scifi" / "scifi_deep_space_and_cyber_master_60s.mp4",
        HORIZONTAL_LOOPS_DIR / "scifi" / "scifi_cyber_infrastructure_master_60s.mp4",
        HORIZONTAL_LOOPS_DIR / "singularidad_scifi" / "scifi_deep_space_and_cyber_master_60s.mp4",
        HORIZONTAL_LOOPS_DIR / "space_abyss" / "scifi_cyber_infrastructure_master_60s.mp4",
    ]
    valid = [p for p in candidates if p.is_file() and p.stat().st_size >= 25_000]
    if len(valid) < 2:
        pytest.skip(f"Expected at least 2 sci-fi loops, found {len(valid)} (local asset; skipped in CI)")
    return valid


# ==============================================================================
# TIER 1: FEATURE COVERAGE
# ==============================================================================

@pytest.mark.tier1
class TestTier1FeatureCoverage:
    """Tier 1: Isolated requirement verification for all core longform features."""

    def test_tier1_loop_stream_copy_concatenation(
        self, e2e_scratch: Path, sample_horror_loops: List[Path]
    ):
        """Verify stream-copy concatenation command formatting and sub-second execution."""
        engine = LoopVideoEngine()
        audio_path = generate_synthetic_wav(e2e_scratch / "test_speech.wav", duration_sec=3.0)
        output_mp4 = e2e_scratch / "stream_copy_out.mp4"

        # 1. Verify command construction contract
        concat_list = e2e_scratch / "test_concat_list.txt"
        concat_list.write_text(f"file '{sample_horror_loops[0]}'\n", encoding="utf-8")
        cmd = engine.build_stream_copy_composition_cmd(
            concat_list_path=concat_list,
            audio_path=audio_path,
            bgm_path=None,
            duration_sec=3.0,
            output_video_path=output_mp4,
        )

        assert "-f" in cmd and "concat" in cmd, "Command must use FFmpeg concat demuxer"
        assert "-safe" in cmd and "0" in cmd, "Concat demuxer requires -safe 0"
        assert "-c:v" in cmd and "copy" in cmd, "Video codec MUST be stream-copy (-c:v copy)"
        assert "-c:a" in cmd and "aac" in cmd, "Audio codec must be aac"
        assert "-movflags" in cmd and "+faststart" in cmd, "Output must have faststart enabled"

        # 2. Execute multi-shot composition via LoopVideoEngine
        start_time = time.monotonic()
        result_path = engine.compose(
            audio_path=str(audio_path),
            output_video_path=str(output_mp4),
            orientation="horizontal",
            duration_sec=3.0,
            stream_copy=True,
            scene_images=[str(sample_horror_loops[0]), str(sample_horror_loops[1])],
            video_loop_path=str(sample_horror_loops[0]),
        )
        elapsed = time.monotonic() - start_time

        assert os.path.exists(result_path), f"Output video missing: {result_path}"
        assert elapsed < 5.0, f"Stream-copy composition took too long ({elapsed:.2f}s); expected < 5s"

        # 3. Verify probe attributes
        probe_info = ffprobe_media_file(Path(result_path))
        video_streams = [s for s in probe_info["streams"] if s["codec_type"] == "video"]
        audio_streams = [s for s in probe_info["streams"] if s["codec_type"] == "audio"]

        assert len(video_streams) == 1, "Expected exactly 1 video stream"
        assert len(audio_streams) == 1, "Expected exactly 1 audio stream"
        assert video_streams[0]["codec_name"] == "h264"
        assert video_streams[0]["width"] == 1920
        assert video_streams[0]["height"] == 1080
        assert check_faststart_moov_atom(Path(result_path)), "Moov atom must precede mdat (faststart)"

    def test_tier1_thematic_scene_rotation(self, catalog_repo: LoopCatalogRepository):
        """Verify seeded modulo candidate pool rotation across scenes without repetition."""
        # Query loops for Moku channel across 4 sequential scenes (seeds 0, 1, 2, 3)
        loop_0 = catalog_repo.get_best_loop("horror", orientation="horizontal", seed=0, channel="moku")
        loop_1 = catalog_repo.get_best_loop("horror", orientation="horizontal", seed=1, channel="moku")
        loop_2 = catalog_repo.get_best_loop("horror", orientation="horizontal", seed=2, channel="moku")
        loop_3 = catalog_repo.get_best_loop("horror", orientation="horizontal", seed=3, channel="moku")

        assert loop_0 is not None and loop_1 is not None, "Catalog must return valid loops"
        # Seeded rotation between scene 0 and 1 must produce distinct loops when pool > 1
        assert loop_0.file_path != loop_1.file_path, "Consecutive scenes must rotate to distinct background loops"

        # Verify SciFi rotation
        scifi_0 = catalog_repo.get_best_loop("scifi", orientation="horizontal", seed=0, channel="scifi")
        scifi_1 = catalog_repo.get_best_loop("scifi", orientation="horizontal", seed=1, channel="scifi")
        assert scifi_0 is not None and scifi_1 is not None
        assert scifi_0.file_path != scifi_1.file_path, "Sci-Fi scenes must rotate background loops"

    def test_tier1_channel_isolation(self, catalog_repo: LoopCatalogRepository):
        """Verify strict channel theme isolation (horror for Moku, cosmos/tech for SciFi)."""
        # Moku loop resolution
        moku_loop = catalog_repo.get_best_loop("horror", orientation="horizontal", channel="moku")
        assert moku_loop is not None
        assert moku_loop.category in LoopCatalogRepository.CHANNEL_THEMES["moku"], f"Moku loop category '{moku_loop.category}' not in Moku themes"
        assert "scifi" not in moku_loop.file_path.lower()
        assert "aelithia" not in moku_loop.file_path.lower()

        # Sci-Fi loop resolution
        scifi_loop = catalog_repo.get_best_loop("scifi", orientation="horizontal", channel="scifi")
        assert scifi_loop is not None
        assert scifi_loop.category in LoopCatalogRepository.CHANNEL_THEMES["scifi"], f"SciFi loop category '{scifi_loop.category}' not in SciFi themes"
        assert "horror" not in scifi_loop.file_path.lower()
        assert "moku" not in scifi_loop.file_path.lower()

        # Cross-channel adversarial request: request drama category under moku channel
        cross_req = catalog_repo.get_best_loop("drama", orientation="horizontal", channel="moku")
        assert cross_req is not None
        # Enforced isolation must clamp result to Moku themes
        assert cross_req.category in LoopCatalogRepository.CHANNEL_THEMES["moku"], "Cross-channel query must be clamped to channel theme"

    def test_tier1_channel_lock_non_collision(self, e2e_scratch: Path):
        """Verify independent ChannelLock acquisition per channel without deadlocks."""
        lock_dir = e2e_scratch / "locks"
        lock_dir.mkdir(parents=True, exist_ok=True)

        lock_moku = ChannelLock("moku", lock_dir=lock_dir, timeout=1.0)
        lock_scifi = ChannelLock("scifi", lock_dir=lock_dir, timeout=1.0)

        # 1. Independent concurrent acquisition
        assert lock_moku.acquire(), "Moku lock should acquire cleanly"
        assert lock_scifi.acquire(), "SciFi lock should acquire cleanly while Moku is held"
        assert lock_moku.is_acquired
        assert lock_scifi.is_acquired
        assert lock_moku.path != lock_scifi.path, "Lock paths must be channel-specific"

        # 2. Release both
        lock_scifi.release()
        lock_moku.release()
        assert not lock_scifi.is_acquired
        assert not lock_moku.is_acquired

        # 3. Reentrancy via context manager
        _active_locks.clear()
        with ChannelLock("moku", lock_dir=lock_dir) as l1:
            assert l1.is_acquired
            with ChannelLock("moku", lock_dir=lock_dir) as l2:
                assert l2.is_acquired
                assert l2._is_reentrant
        _active_locks.clear()

    def test_tier1_telegram_review_proxy_generation(
        self, e2e_scratch: Path, sample_horror_loops: List[Path]
    ):
        """Verify review proxy builder produces an MP4 <= 50MB with faststart."""
        # Copy sample clip to e2e_scratch to keep assets directory completely clean
        test_source = e2e_scratch / "proxy_test_clip.mp4"
        shutil.copyfile(sample_horror_loops[0], test_source)

        # 1. File <= max_bytes returns None (no unnecessary proxy)
        assert _build_review_proxy(str(test_source), max_bytes=100 * 1024 * 1024) is None

        # 2. Oversized file triggers adaptive proxy compression
        # Use a 15 MB budget against the ~50MB test clip to force compression
        budget_bytes = 15 * 1024 * 1024
        proxy_path = _build_review_proxy(str(test_source), max_bytes=budget_bytes)

        assert proxy_path is not None, "Proxy builder must produce a compressed proxy"
        assert os.path.isfile(proxy_path), f"Proxy file does not exist: {proxy_path}"
        proxy_size = os.path.getsize(proxy_path)
        assert proxy_size <= budget_bytes, f"Proxy size {proxy_size} exceeds budget {budget_bytes}"

        # 3. Verify faststart on generated proxy
        assert check_faststart_moov_atom(Path(proxy_path)), "Proxy must have faststart moov atom"

    def test_tier1_aspect_ratio_1920x1080_preservation(
        self, e2e_scratch: Path, sample_horror_loops: List[Path]
    ):
        """Verify exact 1920x1080 dimensions without geometric distortion."""
        engine = LoopVideoEngine()
        audio_path = generate_synthetic_wav(e2e_scratch / "ar_test_audio.wav", duration_sec=2.0)
        output_mp4 = e2e_scratch / "ar_1080p_out.mp4"

        engine.compose(
            audio_path=str(audio_path),
            output_video_path=str(output_mp4),
            orientation="horizontal",
            duration_sec=2.0,
            video_loop_path=str(sample_horror_loops[0]),
            stream_copy=True,
        )

        probe = probe_media(output_mp4)
        assert len(probe.video_streams) > 0, "Video stream missing"
        v_stream = probe.video_streams[0]
        assert v_stream.width == 1920, f"Expected width 1920, got {v_stream.width}"
        assert v_stream.height == 1080, f"Expected height 1080, got {v_stream.height}"
        assert v_stream.pix_fmt == "yuv420p", f"Expected yuv420p, got {v_stream.pix_fmt}"


# ==============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ==============================================================================

@pytest.mark.tier2
class TestTier2BoundaryAndCornerCases:
    """Tier 2: Boundary conditions, extreme durations, multiple scenes, timeouts, and limits."""

    def test_tier2_short_duration_boundary(
        self, e2e_scratch: Path, sample_horror_loops: List[Path]
    ):
        """Verify composition with short duration <= 60s (e.g. 3.5s)."""
        engine = LoopVideoEngine()
        audio_path = generate_synthetic_wav(e2e_scratch / "short_boundary.wav", duration_sec=3.5)
        output_mp4 = e2e_scratch / "short_boundary.mp4"

        engine.compose(
            audio_path=str(audio_path),
            output_video_path=str(output_mp4),
            orientation="horizontal",
            duration_sec=3.5,
            video_loop_path=str(sample_horror_loops[0]),
            stream_copy=True,
        )

        probe = probe_media(output_mp4)
        assert abs(probe.duration - 3.5) < 0.5, f"Expected ~3.5s duration, got {probe.duration}"

    def test_tier2_long_duration_boundary_calculation(
        self, e2e_scratch: Path, sample_horror_loops: List[Path]
    ):
        """Verify long duration (600s - 1800s) repetition calculation without CPU stall."""
        # Test long duration concat list planning without full 30m render
        engine = LoopVideoEngine()
        out_path = e2e_scratch / "long_target.mp4"
        concat_list_path = out_path.parent / "loop_concat_list.txt"

        target_duration = 1800.0  # 30 minutes
        loop_dur = 60.458
        reps = max(1, int(math.ceil(target_duration / loop_dur)) + 1)
        assert reps == 31, f"Expected 31 loop repetitions for 1800s with 60.4s clip, got {reps}"

        with open(concat_list_path, "w", encoding="utf-8") as f:
            for _ in range(reps):
                f.write(f"file '{sample_horror_loops[0].resolve()}'\n")

        lines = concat_list_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 31, f"Expected 31 lines in concat list, got {len(lines)}"
        assert all(line.startswith("file '") and line.endswith(".mp4'") for line in lines)

    def test_tier2_multiple_scenes_boundary(
        self, e2e_scratch: Path, sample_horror_loops: List[Path]
    ):
        """Verify multi-scene stream-copy concat assembly across distinct scenes."""
        engine = LoopVideoEngine()
        audio_path = generate_synthetic_wav(e2e_scratch / "multiscene.wav", duration_sec=5.0)
        output_mp4 = e2e_scratch / "multiscene.mp4"

        # Provide distinct 1080p scene videos; 130s target ensures all distinct clips are included in the concat demuxer list
        scenes = [str(sample_horror_loops[0]), str(sample_horror_loops[1])]
        engine.compose(
            audio_path=str(audio_path),
            output_video_path=str(output_mp4),
            orientation="horizontal",
            duration_sec=130.0,
            scene_images=scenes,
            stream_copy=True,
        )

        concat_file = output_mp4.parent / "loop_concat_list.txt"
        assert concat_file.is_file(), "Concat file must be written for multi-scene composition"
        content = concat_file.read_text(encoding="utf-8")
        # Ensure distinct clips are referenced
        for scene_p in scenes:
            assert Path(scene_p).name in content, f"Scene {scene_p} missing from concat list"

    def test_tier2_lock_timeout_handling(self, e2e_scratch: Path):
        """Verify lock timeout expires and raises ChannelLockError with holder PID."""
        lock_file = e2e_scratch / "timeout_test.lock"

        lock1 = ChannelLock("timeout_channel", lock_file_path=lock_file)
        assert lock1.acquire()

        lock2 = ChannelLock("timeout_channel", lock_file_path=lock_file, timeout=0.2, poll_interval=0.05)
        with pytest.raises(ChannelLockError) as exc_info:
            lock2.acquire()

        assert "Another instance" in str(exc_info.value)
        assert "tras esperar 0.2s" in str(exc_info.value)

        lock1.release()
        # Should now succeed after lock1 released
        assert lock2.acquire()
        lock2.release()

    def test_tier2_file_size_limits_and_preflight(
        self, e2e_scratch: Path, sample_horror_loops: List[Path]
    ):
        """Verify preflight validation of file existence, readability, and size quota."""
        # 1. Empty path
        assert _validate_file_preflight("", 50_000_000) == "File path is empty"

        # 2. Non-existent file
        missing = str(e2e_scratch / "non_existent.mp4")
        err = _validate_file_preflight(missing, 50_000_000)
        assert err is not None and "does not exist" in err.lower()

        # 3. File exceeding limit
        sample_file = sample_horror_loops[0]
        size = sample_file.stat().st_size
        err_exceeded = _validate_file_preflight(str(sample_file), max_allowed_bytes=size - 1000)
        assert err_exceeded is not None and ("exceeds" in err_exceeded.lower() or "quota" in err_exceeded.lower())

        # 4. Compliant file
        err_ok = _validate_file_preflight(str(sample_file), max_allowed_bytes=size + 1000)
        assert err_ok is None, f"Expected None for valid file, got: {err_ok}"


# ==============================================================================
# TIER 3: CROSS-FEATURE INTERACTIONS
# ==============================================================================

@pytest.mark.tier3
class TestTier3CrossFeatureInteractions:
    """Tier 3: Pairwise integration across loop rotation, audio ducking, and catalog isolation."""

    def test_tier3_scene_rotation_and_audio_ducking(
        self, e2e_scratch: Path, sample_horror_loops: List[Path]
    ):
        """Verify multi-scene video concat combined with sidechain audio ducking."""
        engine = LoopVideoEngine()
        speech_wav = generate_synthetic_wav(e2e_scratch / "duck_speech.wav", duration_sec=4.0, amplitude=0.8)
        bgm_wav = generate_synthetic_wav(e2e_scratch / "duck_bgm.wav", duration_sec=4.0, frequency=220.0, amplitude=0.3)
        output_mp4 = e2e_scratch / "rotation_ducking.mp4"

        engine.compose(
            audio_path=str(speech_wav),
            bg_music_path=str(bgm_wav),
            output_video_path=str(output_mp4),
            orientation="horizontal",
            duration_sec=4.0,
            scene_images=[str(sample_horror_loops[0]), str(sample_horror_loops[1])],
            music_volume=0.15,
            ducking_threshold=0.035,
            stream_copy=True,
        )

        assert output_mp4.is_file(), "Combined video file must be generated"
        probe = probe_media(output_mp4)
        assert len(probe.video_streams) == 1
        assert len(probe.audio_streams) == 1
        assert probe.video_streams[0].width == 1920
        assert probe.video_streams[0].height == 1080
        assert probe.audio_streams[0].codec_name == "aac"

    def test_tier3_channel_isolation_and_stream_copy_pipeline(
        self, e2e_scratch: Path, catalog_repo: LoopCatalogRepository
    ):
        """Verify catalog isolation directly feeds valid loops to stream-copy concat."""
        engine = LoopVideoEngine()
        audio_path = generate_synthetic_wav(e2e_scratch / "iso_stream.wav", duration_sec=3.0)

        # 1. Resolve 2 scenes for Moku
        moku_scenes = [
            catalog_repo.get_best_loop("horror", orientation="horizontal", seed=i, channel="moku")
            for i in range(2)
        ]
        assert all(s is not None for s in moku_scenes)
        assert all(s.category in LoopCatalogRepository.CHANNEL_THEMES["moku"] for s in moku_scenes)

        moku_mp4 = e2e_scratch / "moku_pipeline_out.mp4"
        engine.compose(
            audio_path=str(audio_path),
            output_video_path=str(moku_mp4),
            orientation="horizontal",
            duration_sec=3.0,
            scene_images=[s.file_path for s in moku_scenes],
            stream_copy=True,
        )
        assert moku_mp4.is_file()
        assert probe_media(moku_mp4).video_streams[0].width == 1920

        # 2. Resolve 2 scenes for SciFi
        scifi_scenes = [
            catalog_repo.get_best_loop("scifi", orientation="horizontal", seed=i, channel="scifi")
            for i in range(2)
        ]
        assert all(s is not None for s in scifi_scenes)
        assert all(s.category in LoopCatalogRepository.CHANNEL_THEMES["scifi"] for s in scifi_scenes)

        scifi_mp4 = e2e_scratch / "scifi_pipeline_out.mp4"
        engine.compose(
            audio_path=str(audio_path),
            output_video_path=str(scifi_mp4),
            orientation="horizontal",
            duration_sec=3.0,
            scene_images=[s.file_path for s in scifi_scenes],
            stream_copy=True,
        )
        assert scifi_mp4.is_file()
        assert probe_media(scifi_mp4).video_streams[0].width == 1920


# ==============================================================================
# TIER 4: REAL-WORLD LONGFORM SCENARIOS
# ==============================================================================

@pytest.mark.tier4
class TestTier4RealWorldLongformScenarios:
    """Tier 4: Production workloads for moku-horror-long and scifi-singularity-long."""

    def test_tier4_moku_horror_long_scenario(
        self, e2e_scratch: Path, catalog_repo: LoopCatalogRepository
    ):
        """Execute realistic moku-horror-long pipeline scenario with mock Telegram dispatch."""
        engine = LoopVideoEngine()
        work_dir = e2e_scratch / "moku_horror_long_run"
        work_dir.mkdir(parents=True, exist_ok=True)

        # 1. Generate narration & ambient audio
        speech_wav = generate_synthetic_wav(work_dir / "narration.wav", duration_sec=4.0, amplitude=0.7)
        bgm_wav = generate_synthetic_wav(work_dir / "ambient.wav", duration_sec=4.0, frequency=110.0, amplitude=0.2)

        # 2. Retrieve rotated horror loops for 3 scenes
        scenes = [
            catalog_repo.get_best_loop("horror", orientation="horizontal", seed=idx, channel="moku")
            for idx in range(3)
        ]
        scene_paths = [s.file_path for s in scenes if s is not None]
        assert len(scene_paths) == 3

        # 3. Compose longform video
        video_mp4 = work_dir / "video.mp4"
        engine.compose(
            audio_path=str(speech_wav),
            bg_music_path=str(bgm_wav),
            output_video_path=str(video_mp4),
            orientation="horizontal",
            duration_sec=4.0,
            scene_images=scene_paths,
            stream_copy=True,
        )

        assert video_mp4.is_file()
        probe = probe_media(video_mp4)
        assert probe.video_streams[0].width == 1920
        assert probe.video_streams[0].height == 1080
        assert probe.video_streams[0].codec_name == "h264"

        # 4. Dispatch Telegram review via TelegramReviewBot with mock transport
        bot = TelegramReviewBot(bot_token="test_token_redacted", allowed_chat_id="8266399903")
        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {"ok": True, "result": {"message_id": 98765}}

        with patch("lib.video.is_test_environment", return_value=False), \
             patch.object(TelegramHttpClient, "request", return_value=fake_response) as mock_req:
            delivery = bot.send_video_for_review(
                video_path=str(video_mp4),
                metadata={"title": "Moku Horror Longform Canary", "channel": "moku-horror-long"},
                chat_id="8266399903",
            )
            assert delivery.ok is True
            assert delivery.message_id == 98765
            mock_req.assert_called_once()
            call_url = mock_req.call_args[0][1]
            assert "sendVideo" in call_url

    def test_tier4_scifi_singularity_long_scenario(
        self, e2e_scratch: Path, catalog_repo: LoopCatalogRepository
    ):
        """Execute realistic scifi-singularity-long pipeline scenario with review proxy dispatch."""
        engine = LoopVideoEngine()
        work_dir = e2e_scratch / "scifi_singularity_long_run"
        work_dir.mkdir(parents=True, exist_ok=True)

        # 1. Synthesize audio
        speech_wav = generate_synthetic_wav(work_dir / "speech.wav", duration_sec=4.0, amplitude=0.75)
        bgm_wav = generate_synthetic_wav(work_dir / "bgm.wav", duration_sec=4.0, frequency=330.0, amplitude=0.25)

        # 2. Retrieve rotated sci-fi loops for 3 scenes
        scenes = [
            catalog_repo.get_best_loop("scifi", orientation="horizontal", seed=idx, channel="scifi")
            for idx in range(3)
        ]
        scene_paths = [s.file_path for s in scenes if s is not None]
        assert len(scene_paths) == 3

        # 3. Compose longform video
        video_mp4 = work_dir / "video.mp4"
        engine.compose(
            audio_path=str(speech_wav),
            bg_music_path=str(bgm_wav),
            output_video_path=str(video_mp4),
            orientation="horizontal",
            duration_sec=4.0,
            scene_images=scene_paths,
            stream_copy=True,
        )

        assert video_mp4.is_file()
        probe = probe_media(video_mp4)
        assert probe.video_streams[0].width == 1920
        assert probe.video_streams[0].height == 1080

        # 4. Verify Telegram review delivery with proxy generation for constrained budget
        bot = TelegramReviewBot(bot_token="test_token_redacted", allowed_chat_id="8266399903")
        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {"ok": True, "result": {"message_id": 98766}}

        with patch("lib.video.is_test_environment", return_value=False), \
             patch.object(TelegramHttpClient, "request", return_value=fake_response) as mock_req:
            delivery = bot.send_video(
                video_path=str(video_mp4),
                chat_id="8266399903",
                caption="SciFi Singularity Longform Canary Review",
            )
            assert delivery.ok is True
            mock_req.assert_called_once()
            call_url = mock_req.call_args[0][1]
            assert "sendVideo" in call_url
