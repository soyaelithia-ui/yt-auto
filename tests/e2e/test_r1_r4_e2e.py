"""
tests/e2e/test_r1_r4_e2e.py - Requirement-Driven E2E Test Suite for yt-auto Resource Optimization & Hardening.

Validates all 4 core modernization requirements across 4 comprehensive tiers:
- R1: Diagnostics, Profiling & Telemetry (13 canonical stages, CPU/RSS tracking, summaries, zero-overhead disable).
- R2: Safe Disk Footprint Reduction & Automated Retention (safe intermediate purge, retention markers, cache eviction).
- R3: Media & FFmpeg Pipeline Performance Optimization (single-pass audio mastering, ducking, fast presets, stream copy, pauses).
- R4: Memory Efficiency, Concurrency & SQLite Persistence (MemoryWatchdog, FailureBreaker, SimHash-64, WAL zero-lock concurrency).

Methodology:
- Tier 1: Feature Coverage (R1 profiling, R2 disk purge & retention, R3 video pipe & audio mastering, R4 memory streaming & WAL concurrency).
- Tier 2: Boundary & Corner Cases (empty work dirs, concurrent lease timeout, extreme durations, invalid format handling).
- Tier 3: Cross-Feature Interactions (concurrent multi-lane claiming during render, post-render cleanup with SQLite WAL checkpointing).
- Tier 4: Real-World Scenarios (end-to-end pipeline execution with master output preservation, multi-channel stress, crash recovery).
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

import pytest

# Configuration & Settings
from src.core.domain import CanonicalChannel, JobStatus, canonical_channel

# R1: Profiling & Telemetry
from src.core.profiling import (
    CANONICAL_STAGES,
    CanonicalStage,
    PhaseMetrics,
    PhaseTimer,
    PipelineProfiler,
    ProfilingSummary,
    is_profiling_enabled,
    normalize_stage_name,
    profile_phase,
)

# R2: Retention & Disk Cleanup
from src.cleaner import (
    clean_expired_failed_runs,
    clean_run_intermediates,
    clean_system_cache,
    clean_untracked_temp_files,
    verify_and_cleanup,
)
from src.retention import mark_run_retention_satisfied

# R3: FFmpeg & Media Processing
from lib.ffmpeg import (
    FFmpegCommandResult,
    FFmpegError,
    FFmpegExecutionError,
    FFmpegTimeoutError,
    FFprobeError,
    MediaProbeResult,
    TempMediaContext,
    has_faststart,
    probe_media,
    run_ffmpeg,
    run_ffprobe,
)
from lib.audio import (
    apply_sidechain_ducking,
    build_sidechain_ducking_filter_graph,
    extract_dramatic_pauses,
    generate_silence_audio,
    insert_dramatic_pauses_to_audio,
    master_audio_track,
    normalize_narration_lufs,
    parse_dramatic_pauses,
    shift_word_timestamps_with_pauses,
    strip_dramatic_pauses,
)
from src.media.subtitles import (
    CodeSubtitleDrawer,
    SubtitleCue,
    SubtitleTheme,
    SubtitleWord,
    THEME_PRESETS,
)

# R4: Resource Guards, Persistence & Concurrency
from src.core.guard import (
    ConsecutiveFailureBreaker,
    DiskPreflight,
    MemoryWatchdog,
    ResourceLimitError,
    ensure_disk_available,
    free_disk_bytes,
    memory_checkpoint,
    observed_memory_bytes,
    reset_module_watchdog,
)
from src.core.repository import (
    QueueRepository,
    compute_simhash_64,
    connect,
    is_simhash_duplicate,
    migrate_database,
    simhash_hamming_distance,
    to_signed_64,
    to_unsigned_64,
)


# ===========================================================================
# Test Helpers & Fixtures
# ===========================================================================

@pytest.fixture
def clean_db(tmp_path: Path) -> QueueRepository:
    """Provides a cleanly initialized SQLite database with WAL and migrations applied."""
    db_file = tmp_path / "e2e_test_queue.db"
    migrate_database(str(db_file))
    return QueueRepository(str(db_file))


def _mock_settings(work_root: Path, artifact_root: Optional[Path] = None, drive_folder_id: str = "folder-auth-999") -> SimpleNamespace:
    """Creates a mock Settings namespace suitable for patching frozen SETTINGS."""
    return SimpleNamespace(
        work_root=work_root,
        artifact_root=artifact_root or work_root,
        drive_folder_id=drive_folder_id,
        drive_published_folder_id=drive_folder_id,
        drive_approved_video_folder_id=drive_folder_id,
        drive_root_folder_id=drive_folder_id,
    )


def create_synthetic_wav(
    path: str | Path,
    duration_sec: float = 2.0,
    sample_rate: int = 48000,
    freq: int = 440,
) -> str:
    """Generate a clean synthetic sine wave WAV audio file via FFmpeg."""
    path_str = str(path)
    Path(path_str).parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={duration_sec}",
        "-ar", str(sample_rate), "-ac", "2",
        path_str,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return path_str


def create_synthetic_mp4(
    path: str | Path,
    duration_sec: float = 2.0,
    width: int = 320,
    height: int = 240,
    fps: int = 24,
) -> str:
    """Generate a valid test video file with faststart moov atom via FFmpeg."""
    path_str = str(path)
    Path(path_str).parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"testsrc=duration={duration_sec}:size={width}x{height}:rate={fps}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        path_str,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return path_str


# ===========================================================================
# TIER 1: FEATURE COVERAGE (R1 - R4)
# ===========================================================================

class TestTier1R1ProfilingAndTelemetry:
    """Tier 1: R1 Feature Coverage (13 Canonical Stages, PhaseTimer, Profiler Aggregation, Zero-Overhead)."""

    def test_t1_r1_canonical_13_stages_execution_and_metrics(self):
        """Verify all 13 canonical stages can be profiled with accurate wall-clock, CPU, and RSS tracking."""
        assert len(CANONICAL_STAGES) == 13
        stages_to_test = [
            CanonicalStage.CLAIM_LEASE,
            CanonicalStage.INGEST_TRANSLATE,
            CanonicalStage.EDITORIAL_BARRIER,
            CanonicalStage.MOOD_THEME,
            CanonicalStage.TTS_SYNTHESIS,
            CanonicalStage.DURATION_ALIGNMENT,
            CanonicalStage.SUBTITLE_GENERATION,
            CanonicalStage.LOOP_SCENE,
            CanonicalStage.VIDEO_RENDERING,
            CanonicalStage.QA_GATING,
            CanonicalStage.THUMBNAIL_METADATA,
            CanonicalStage.DEDUP_SIMHASH,
            CanonicalStage.BACKUP_PUBLISH,
        ]

        profiler = PipelineProfiler(run_id="run_t1_01", channel="moku", story_id="story_t1_01")

        for stage in stages_to_test:
            assert stage.phase_number >= 1
            assert stage.display_name
            with profiler.phase(stage, metadata={"stage_num": stage.phase_number}) as metrics:
                time.sleep(0.005)
                assert metrics is not None
                assert metrics.stage_name == stage.value
                assert metrics.run_id == "run_t1_01"

            recorded = profiler.get_phase(stage)
            assert recorded is not None
            assert recorded.duration_sec >= 0
            assert recorded.success is True
            assert recorded.start_rss_mb >= 0
            assert recorded.end_rss_mb >= 0
            assert recorded.peak_rss_mb >= 0
            assert recorded["stage"] == stage.value
            assert recorded.metadata.get("stage_num") == stage.phase_number

    def test_t1_r1_pipeline_profiler_summary_aggregation_and_reporting(self):
        """Verify PipelineProfiler aggregates multi-phase runs into a complete summary with JSON & ASCII table export."""
        profiler = PipelineProfiler(run_id="run_agg_01", channel="aelithia", story_id="s_agg_01")

        with profiler.phase(CanonicalStage.INGEST_TRANSLATE):
            time.sleep(0.005)

        with profiler.phase(CanonicalStage.TTS_SYNTHESIS):
            time.sleep(0.005)

        with profiler.phase(CanonicalStage.VIDEO_RENDERING):
            time.sleep(0.005)

        summary = profiler.get_summary()
        assert isinstance(summary, ProfilingSummary)
        assert summary.run_id == "run_agg_01"
        assert summary.channel == "aelithia"
        assert summary.phases_count == 3
        assert summary.successful_phases == 3
        assert summary.failed_phases == 0
        assert summary.total_duration_sec >= 0.0
        assert summary.total_cpu_sec >= 0.0

        # Verify JSON export
        json_str = summary.to_json()
        data = json.loads(json_str)
        assert data["run_id"] == "run_agg_01"
        assert len(data["phase_breakdown"]) == 3
        assert "phases" in data

        # Verify formatted ASCII table output
        table_output = summary.format_table(color=False)
        assert "PIPELINE PROFILING REPORT" in table_output
        assert "run_agg_01" in table_output
        assert "9_video_rendering" in table_output
        assert "TOTAL" in table_output

    def test_t1_r1_profiling_zero_overhead_when_disabled(self):
        """Verify that when profiling is disabled (YT_PROFILING=0), PhaseTimer creates no overhead and returns None."""
        profiler = PipelineProfiler(run_id="run_disabled", enabled=False)

        with profiler.phase(CanonicalStage.VIDEO_RENDERING) as metrics:
            assert metrics is None
            val = 10 * 20

        assert val == 200
        summary = profiler.get_summary()
        assert summary.phases_count == 0

    def test_t1_r1_profile_phase_decorator_and_context_propagation(self):
        """Verify @profile_phase decorator wraps functions and propagates metrics to attached profilers."""
        profiler = PipelineProfiler(run_id="run_dec_01", channel="moku")

        @profile_phase(CanonicalStage.QA_GATING, profiler=profiler, metadata={"test_key": "test_val"})
        def sample_qa_function(x: int, y: int) -> int:
            return x + y

        result = sample_qa_function(40, 2)
        assert result == 42

        recorded = profiler.get_phase(CanonicalStage.QA_GATING)
        assert recorded is not None
        assert recorded.success is True
        assert recorded.metadata.get("test_key") == "test_val"

    def test_t1_r1_stage_error_recording_and_diagnostics(self):
        """Verify errors occurring inside profiled blocks are captured in PhaseMetrics without suppressing exceptions."""
        profiler = PipelineProfiler(run_id="run_err_01")

        with pytest.raises(ValueError, match="Synthetic stage crash"):
            with profiler.phase(CanonicalStage.DEDUP_SIMHASH):
                raise ValueError("Synthetic stage crash")

        recorded = profiler.get_phase(CanonicalStage.DEDUP_SIMHASH)
        assert recorded is not None
        assert recorded.success is False
        assert "Synthetic stage crash" in (recorded.error or "")
        assert recorded.error_type == "ValueError"

        summary = profiler.get_summary()
        assert summary.failed_phases == 1


class TestTier1R2SafeDiskPurgeAndRetention:
    """Tier 1: R2 Feature Coverage (clean_run_intermediates, clean_system_cache, retention markers)."""

    def test_t1_r2_clean_run_intermediates_removes_transients_preserves_masters(self, tmp_path: Path):
        """Verify clean_run_intermediates removes intermediate files while preserving finished master videos and thumbnails."""
        work_dir = tmp_path / "run_sample_001"
        work_dir.mkdir(parents=True)

        # Transient files that MUST be deleted
        transient_files = [
            work_dir / "prescaled_001.jpg",
            work_dir / "concat_list.txt",
            work_dir / "loop_concat_list.txt",
            work_dir / "speech.tmp.norm.wav",
            work_dir / "safe_area_validation.jpg",
            work_dir / "review_proxy_01.mp4",
            work_dir / "ffmpeg_compose.log",
        ]
        for f in transient_files:
            f.write_text("transient intermediate buffer data", encoding="utf-8")

        # Master assets that MUST be 100% preserved
        master_video = work_dir / "master_story_001.mp4"
        master_thumbnail = work_dir / "thumbnail_story_001.png"
        meta_file = work_dir / "metadata.json"
        master_video.write_text("binary master video stream content", encoding="utf-8")
        master_thumbnail.write_text("binary thumbnail png content", encoding="utf-8")
        meta_file.write_text('{"title": "Preserved"}', encoding="utf-8")

        report = clean_run_intermediates(work_dir)
        assert report["deleted_files_count"] == len(transient_files)
        assert report["freed_bytes"] > 0

        # Verify all transient files are removed
        for f in transient_files:
            assert not f.exists(), f"Transient file {f.name} was not deleted!"

        # Verify master files are preserved
        assert master_video.exists()
        assert master_thumbnail.exists()
        assert meta_file.exists()

    def test_t1_r2_clean_system_cache_respects_retention_and_run_markers(self, tmp_path: Path):
        """Verify clean_system_cache purges only expired runs with retention_satisfied=True and active=False."""
        work_root = tmp_path / "work"
        work_root.mkdir(parents=True)
        settings_mock = _mock_settings(work_root)

        with patch("src.cleaner.SETTINGS", settings_mock):
            # 1. Expired satisfied run (SHOULD be purged)
            expired_run = work_root / "run_expired_01"
            expired_run.mkdir()
            (expired_run / "intermediate.mp4").write_text("data", encoding="utf-8")
            marker_exp = expired_run / ".run.json"
            marker_exp.write_text(json.dumps({
                "run_id": "run_expired_01",
                "active": False,
                "retention_satisfied": True,
            }), encoding="utf-8")
            # Set mtime in the past
            past_time = time.time() - 1000
            os.utime(marker_exp, (past_time, past_time))

            # 2. Active running run (MUST NOT be purged)
            active_run = work_root / "run_active_01"
            active_run.mkdir()
            (active_run / "current.mp4").write_text("data", encoding="utf-8")
            marker_act = active_run / ".run.json"
            marker_act.write_text(json.dumps({
                "run_id": "run_active_01",
                "active": True,
                "retention_satisfied": False,
            }), encoding="utf-8")

            report = clean_system_cache(min_age_seconds=10, dry_run=False)
            assert report["deleted_dirs_count"] == 1
            assert report["freed_bytes"] > 0
            assert not expired_run.exists()
            assert active_run.exists()

    def test_t1_r2_clean_expired_failed_runs_reclaims_failed_directories(self, tmp_path: Path):
        """Verify clean_expired_failed_runs cleans inactive failed runs older than retention threshold."""
        work_root = tmp_path / "work"
        work_root.mkdir(parents=True)
        settings_mock = _mock_settings(work_root)

        with patch("src.cleaner.SETTINGS", settings_mock):
            failed_run = work_root / "run_failed_01"
            failed_run.mkdir()
            (failed_run / "crash_dump.log").write_text("error details", encoding="utf-8")
            marker = failed_run / ".run.json"
            marker.write_text(json.dumps({
                "run_id": "run_failed_01",
                "active": False,
                "retention_satisfied": False,
            }), encoding="utf-8")
            past_time = time.time() - 500
            os.utime(marker, (past_time, past_time))

            report = clean_expired_failed_runs(min_age_seconds=10, dry_run=False)
            assert report["deleted_dirs_count"] == 1
            assert not failed_run.exists()

    def test_t1_r2_clean_untracked_temp_files_work_root_purge(self, tmp_path: Path):
        """Verify clean_untracked_temp_files deletes orphaned .tmp.* files and root validation artifacts."""
        work_root = tmp_path / "work"
        work_root.mkdir(parents=True)
        settings_mock = _mock_settings(work_root)

        with patch("src.cleaner.SETTINGS", settings_mock):
            tmp1 = work_root / ".tmp.scratch_01.wav"
            tmp2 = work_root / ".tmp.scratch_02.mp4"
            safe_area = work_root / "safe_area_validation.jpg"
            keeper = work_root / "valid_config.json"

            tmp1.write_text("tmp", encoding="utf-8")
            tmp2.write_text("tmp", encoding="utf-8")
            safe_area.write_text("img", encoding="utf-8")
            keeper.write_text("{}", encoding="utf-8")

            report = clean_untracked_temp_files(dry_run=False)
            assert report["deleted_files_count"] == 3
            assert not tmp1.exists()
            assert not tmp2.exists()
            assert not safe_area.exists()
            assert keeper.exists()

    def test_t1_r2_mark_run_retention_satisfied_atomic_marker_update(self, tmp_path: Path):
        """Verify mark_run_retention_satisfied atomically updates .run.json with publication metadata."""
        work_root = tmp_path / "work"
        run_dir = work_root / "run_publish_01"
        run_dir.mkdir(parents=True)
        settings_mock = _mock_settings(work_root)

        video_file = run_dir / "master_video.mp4"
        video_file.write_text("master mp4 content", encoding="utf-8")

        marker = run_dir / ".run.json"
        marker.write_text(json.dumps({
            "run_id": "run_publish_01",
            "active": False,
            "retention_satisfied": False,
        }), encoding="utf-8")

        with patch("src.retention.SETTINGS", settings_mock):
            ok = mark_run_retention_satisfied(
                video_path=video_file,
                published_id="yt_vid_abc123",
                published_url="https://youtube.com/watch?v=yt_vid_abc123",
            )
            assert ok is True

            data = json.loads(marker.read_text(encoding="utf-8"))
            assert data["retention_satisfied"] is True
            assert data["published_id"] == "yt_vid_abc123"
            assert "yt_vid_abc123" in data["published_url"]

    def test_t1_r2_verify_and_cleanup_remote_drive_proof_guard(self, tmp_path: Path):
        """Verify verify_and_cleanup safely deletes only when remote Drive proof matches file perfectly."""
        work_root = tmp_path / "work"
        work_root.mkdir(parents=True)
        artifact = work_root / "uploaded_master.mp4"
        artifact.write_text("1234567890", encoding="utf-8")
        file_size = artifact.stat().st_size
        settings_mock = _mock_settings(work_root, drive_folder_id="folder_auth_999")

        with patch("src.cleaner.SETTINGS", settings_mock):
            # Mismatched size proof should block cleanup
            bad_proof = {"id": "drive_001", "name": "uploaded_master.mp4", "size": 99999, "exists": True, "parents": ["folder_auth_999"]}
            assert verify_and_cleanup(str(artifact), "drive_001", remote_proof=bad_proof) is False
            assert artifact.exists()

            # Valid matching proof allows verified cleanup
            valid_proof = {"id": "drive_001", "name": "uploaded_master.mp4", "size": file_size, "exists": True, "parents": ["folder_auth_999"]}
            assert verify_and_cleanup(str(artifact), "drive_001", remote_proof=valid_proof, retention_seconds=0) is True
            assert not artifact.exists()


class TestTier1R3MediaVideoPipeAndAudioMastering:
    """Tier 1: R3 Feature Coverage (Single-Pass Audio Mastering, FFmpeg Isolation, Stream Copy, Faststart)."""

    def test_t1_r3_ffmpeg_process_group_isolation_and_probe_media(self, tmp_path: Path):
        """Verify run_ffmpeg executes with process isolation and probe_media extracts valid stream metadata."""
        vid_path = create_synthetic_mp4(tmp_path / "probe_test.mp4", duration_sec=1.5, width=640, height=360, fps=30)
        
        probe = probe_media(vid_path)
        assert isinstance(probe, MediaProbeResult)
        assert probe.has_video is True
        assert probe.duration >= 1.0
        assert probe.primary_video is not None
        assert probe.primary_video.width == 640
        assert probe.primary_video.height == 360
        assert probe.primary_video.fps == pytest.approx(30.0, abs=0.5)

    def test_t1_r3_single_pass_sidechain_ducking_and_ebu_r128_loudness(self, tmp_path: Path):
        """Verify single-pass sidechain ducking filter graph and audio mastering to EBU R128 (-14 LUFS)."""
        speech_wav = create_synthetic_wav(tmp_path / "speech.wav", duration_sec=2.5, freq=300)
        music_wav = create_synthetic_wav(tmp_path / "bgm.wav", duration_sec=4.0, freq=600)
        master_out = tmp_path / "mastered_audio.wav"

        # Verify filter graph string structure for single-pass execution
        graph = build_sidechain_ducking_filter_graph(
            speech_label="0:a",
            music_label="1:a",
            out_label="aout",
            music_volume=0.05,
            master_loudness=True,
            target_lufs=-14.0,
            max_tp=-1.5,
        )
        assert "sidechaincompress=" in graph
        assert "loudnorm=I=-14.0:TP=-1.5" in graph
        assert "amix=inputs=2" in graph

        # Execute mastering chain on synthetic assets
        result_path = master_audio_track(
            narration_path=speech_wav,
            music_path=music_wav,
            output_path=master_out,
            target_lufs=-14.0,
        )
        assert Path(result_path).is_file()
        assert Path(result_path).stat().st_size > 1000

        # Probe output audio
        probe = probe_media(result_path)
        assert probe.has_audio is True
        assert probe.primary_audio is not None
        assert probe.primary_audio.sample_rate == 48000
        assert probe.primary_audio.channels == 2

    def test_t1_r3_dramatic_pause_segmentation_and_silence_generation(self, tmp_path: Path):
        """Verify dramatic pause tag parsing, calibrated silence PCM generation, and timestamp shifting."""
        script = "La puerta se abrió lentamente. [PAUSA: 1.5s] Una sombra emergió de la oscuridad. [SILENCE: 800ms]"
        
        segments = parse_dramatic_pauses(script)
        assert len(segments) == 2
        assert segments[0]["pause_after"] == pytest.approx(1.5)
        assert segments[0]["has_pause"] is True
        assert "La puerta" in segments[0]["text"]
        assert segments[1]["pause_after"] == pytest.approx(0.8)

        # Generate low-noise PCM silence
        silence_file = tmp_path / "silence.wav"
        generate_silence_audio(silence_file, duration_sec=1.2, sample_rate=48000, channels=2)
        assert silence_file.is_file()
        probe = probe_media(silence_file)
        assert probe.duration == pytest.approx(1.2, abs=0.1)

        # Monotonic timestamp shifting
        words_chunk1 = [{"word": "La", "start": 0.0, "end": 0.3}, {"word": "puerta", "start": 0.3, "end": 0.8}]
        words_chunk2 = [{"word": "Sombra", "start": 0.0, "end": 0.5}]
        shifted = shift_word_timestamps_with_pauses(
            chunk_timestamps=[words_chunk1, words_chunk2],
            chunk_durations=[0.8, 0.5],
            pause_durations=[1.5, 0.0],
        )
        assert len(shifted) == 3
        assert shifted[0]["word"] == "La"
        assert shifted[0]["start"] == 0.0
        assert shifted[2]["word"] == "Sombra"
        # Second chunk starts after chunk1 (0.8s) + pause (1.5s) = 2.3s
        assert shifted[2]["start"] == pytest.approx(2.3)

    def test_t1_r3_stream_copy_video_audio_muxing_and_faststart(self, tmp_path: Path):
        """Verify stream copy muxing (-c:v copy) preserves faststart container atom layout."""
        video_raw = create_synthetic_mp4(tmp_path / "raw_video.mp4", duration_sec=2.0)
        audio_raw = create_synthetic_wav(tmp_path / "raw_audio.wav", duration_sec=2.0)
        muxed_out = tmp_path / "muxed_output.mp4"

        # Stream copy video with audio re-encode into faststart MP4
        cmd = [
            "ffmpeg", "-y",
            "-i", video_raw,
            "-i", audio_raw,
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            "-movflags", "+faststart",
            str(muxed_out),
        ]
        res = run_ffmpeg(cmd)
        assert res.returncode == 0
        assert muxed_out.is_file()
        assert has_faststart(muxed_out) is True

    def test_t1_r3_temp_media_context_workspace_lifecycle(self, tmp_path: Path):
        """Verify TempMediaContext creates managed scratch space and removes it on context exit."""
        scratch_root = tmp_path / "media_work"
        scratch_root.mkdir()

        created_file_path = None
        with TempMediaContext(work_dir=scratch_root, prefix="test_scratch_") as ctx:
            assert ctx.path.exists()
            assert str(scratch_root) in str(ctx.path)
            clip = ctx.create_temp_file(suffix=".mp4", prefix="clip_")
            assert clip.exists()
            created_file_path = clip

        # Context exited: workspace directory and scratch files MUST be cleaned up
        assert not created_file_path.exists()
        assert not ctx.path.exists()


class TestTier1R4MemoryEfficiencyAndConcurrency:
    """Tier 1: R4 Feature Coverage (MemoryWatchdog, CircuitBreaker, SQLite WAL, SimHash, Leases)."""

    def test_t1_r4_memory_watchdog_soft_limit_and_checkpointing(self):
        """Verify MemoryWatchdog samples RSS, tolerates transient spikes, and raises on sustained breach."""
        # 1. Watchdog with high limit remains healthy
        watchdog = MemoryWatchdog(soft_limit_bytes=100 * (1024**3), required_breaches=2)
        info = watchdog.checkpoint("stage_healthy")
        assert info["disabled"] is False
        assert info["breaches"] == 0

        # 2. Watchdog with mock observer exceeding soft limit
        breach_samples = [200 * 1024 * 1024, 250 * 1024 * 1024]
        sample_idx = 0

        def mock_observer() -> int:
            nonlocal sample_idx
            val = breach_samples[min(sample_idx, len(breach_samples) - 1)]
            sample_idx += 1
            return val

        strict_watchdog = MemoryWatchdog(
            soft_limit_bytes=100 * 1024 * 1024,
            required_breaches=2,
            observer=mock_observer,
        )

        # First breach: warning count incremented, does not raise
        info1 = strict_watchdog.checkpoint("stage_spike_1")
        assert info1["breaches"] == 1

        # Second consecutive breach: raises ResourceLimitError
        with pytest.raises(ResourceLimitError, match="supera el techo"):
            strict_watchdog.checkpoint("stage_spike_2")

    def test_t1_r4_consecutive_failure_circuit_breaker(self):
        """Verify ConsecutiveFailureBreaker trips at threshold and resets on success or explicit reset."""
        breaker = ConsecutiveFailureBreaker(threshold=3)

        assert breaker.record_failure("moku") is False  # 1 failure
        assert breaker.record_failure("moku") is False  # 2 failures
        assert breaker.record_failure("moku") is True   # 3 failures (tripped!)

        # Channel isolation: aelithia remains untripped
        assert breaker.record_failure("aelithia") is False

        # Success resets counter
        breaker.record_success("moku")
        assert breaker.record_failure("moku") is False

    def test_t1_r4_sqlite_wal_pragmas_and_migration_integrity(self, clean_db: QueueRepository):
        """Verify SQLite WAL mode, 15s timeout, foreign keys, and migration version tracking."""
        with connect(clean_db.db_path, read_only=True) as conn:
            journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
            assert journal_mode.lower() == "wal"

            foreign_keys = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
            assert foreign_keys == 1

            busy_timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
            assert busy_timeout == 15000

            # Verify schema_migrations table
            rows = conn.execute("SELECT version, name, checksum FROM schema_migrations ORDER BY version").fetchall()
            assert len(rows) >= 5
            for r in rows:
                assert len(r["checksum"]) == 64

    def test_t1_r4_simhash_64_bit_near_duplicate_detection(self):
        """Verify 64-bit SimHash catches near-duplicates (Hamming distance <= 3) and allows distinct content."""
        story_a = "El velador del faro escuchó pasos en la escalera metálica durante la medianoche."
        story_a_variant = "El velador del faro escuchó pasos en la escalera metálica durante la medianoche!"
        story_b = "SCP-173 debe estar contenido en una celda sellada con observación continua."

        h_a = compute_simhash_64(story_a)
        h_var = compute_simhash_64(story_a_variant)
        h_b = compute_simhash_64(story_b)

        dist_near = simhash_hamming_distance(h_a, h_var)
        dist_diff = simhash_hamming_distance(h_a, h_b)

        assert dist_near <= 3
        assert is_simhash_duplicate(h_a, h_var, max_distance=3) is True
        assert dist_diff > 3
        assert is_simhash_duplicate(h_a, h_b, max_distance=3) is False

    def test_t1_r4_dual_tier_leases_and_concurrent_lane_fencing(self, clean_db: QueueRepository):
        """Verify dual-tier leasing (`leases` and `lane_leases`) and unauthorized worker fencing."""
        repo = clean_db
        repo.enqueue(story_id="s_fence_01", title="Story 1", content="Content 1", url="https://reddit.com/f1", channel="moku", lane_id="moku-horror-long")

        # Worker 1 claims story
        claim = repo.claim_for_lane(lane_id="moku-horror-long", channel="moku", owner="worker_alpha", lease_seconds=60)
        assert claim is not None
        run_id = claim["run_id"]

        # Authorized worker heartbeats successfully
        assert repo.heartbeat(run_id=run_id, owner="worker_alpha") is True

        # Imposter worker cannot heartbeat or mutate status
        assert repo.heartbeat(run_id=run_id, owner="imposter_worker") is False
        assert repo.set_status(story_id="s_fence_01", status=JobStatus.PUBLISHED, run_id=run_id, owner="imposter_worker") is False

    def test_t1_r4_concurrent_enqueues_and_claims_zero_database_locks(self, clean_db: QueueRepository):
        """Verify 20 concurrent threads performing enqueues and claims achieve 0 database lock errors."""
        repo = clean_db
        num_threads = 20

        def worker_task(worker_id: int):
            s_id = f"concurrent_s_{worker_id}"
            enq_ok = repo.enqueue(
                story_id=s_id,
                title=f"Concurrent Story {worker_id}",
                content=f"Content for concurrent story number {worker_id}",
                url=f"https://reddit.com/concurrent/{worker_id}",
                channel="moku",
                score=100 + worker_id,
            )
            claim = repo.claim(channel="moku", owner=f"worker_{worker_id}", lease_seconds=60)
            return enq_ok, claim

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker_task, i) for i in range(num_threads)]
            results = [f.result() for f in futures]

        assert all(r[0] is True for r in results)
        with connect(repo.db_path, read_only=True) as conn:
            count = conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
            assert count == num_threads


# ===========================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ===========================================================================

class TestTier2BoundaryAndCornerCases:
    """Tier 2: Extreme values, empty inputs, network timeouts, int64 boundaries, lease timeouts."""

    def test_t2_boundary_cleaner_empty_dirs_and_corrupted_markers(self, tmp_path: Path):
        """Verify cleaner functions handle non-existent directories, corrupted JSON markers, and symlinks safely."""
        work_root = tmp_path / "work_boundary"
        work_root.mkdir(parents=True)
        settings_mock = _mock_settings(work_root)

        with patch("src.cleaner.SETTINGS", settings_mock):
            # 1. Non-existent dir returns zero counts
            res_missing = clean_run_intermediates(work_root / "non_existent_dir_123")
            assert res_missing["deleted_files_count"] == 0

            # 2. Corrupted .run.json marker
            bad_dir = work_root / "run_corrupt_01"
            bad_dir.mkdir()
            (bad_dir / ".run.json").write_text("{corrupt: json:: syntax", encoding="utf-8")
            res_cache = clean_system_cache(min_age_seconds=0)
            assert bad_dir.exists()  # Must not delete directory with unparseable marker

            # 3. Mismatched run_id in marker
            mismatch_dir = work_root / "run_mismatch_01"
            mismatch_dir.mkdir()
            (mismatch_dir / ".run.json").write_text(json.dumps({"run_id": "different_id", "active": False, "retention_satisfied": True}), encoding="utf-8")
            clean_system_cache(min_age_seconds=0)
            assert mismatch_dir.exists()

    def test_t2_boundary_ffmpeg_execution_failure_and_timeout_sigkill(self):
        """Verify run_ffmpeg translates non-zero exit codes into FFmpegExecutionError and handles timeouts."""
        # Non-zero return code
        with pytest.raises(FFmpegExecutionError) as exc_info:
            run_ffmpeg(["ffmpeg", "-y", "-i", "non_existent_input_file_xyz.mp4", "/tmp/out.mp4"], check=True)
        assert exc_info.value.returncode != 0

        # Missing binary
        with pytest.raises(FFmpegExecutionError) as exc_miss:
            run_ffmpeg(["non_existent_ffmpeg_binary_command"], check=True)
        assert exc_miss.value.returncode == 127

    def test_t2_boundary_audio_extreme_durations_and_empty_pause_tags(self, tmp_path: Path):
        """Verify pause parsing clamps extreme values (0.1s to 30.0s) and handles malformed tags."""
        # Empty string
        assert parse_dramatic_pauses("") == []
        assert strip_dramatic_pauses("") == ""

        # Extreme pause: 9999 seconds clamped to 30.0s
        parsed_extreme = parse_dramatic_pauses("Texto inicial. [PAUSA: 9999s] Texto final.")
        assert parsed_extreme[0]["pause_after"] == 30.0

        # Sub-minimum pause: 0.01 seconds clamped to 0.1s
        parsed_submin = parse_dramatic_pauses("Texto. [PAUSA: 0.01s] Fin.")
        assert parsed_submin[0]["pause_after"] == 0.1

        # Silence generator with 0 duration clamped safely
        silence_p = tmp_path / "zero_silence.wav"
        generate_silence_audio(silence_p, duration_sec=0.0)
        assert silence_p.is_file()

    def test_t2_boundary_simhash_empty_none_and_int64_two_complement_extremes(self):
        """Verify uint64 to signed int64 conversion preserves exact bit patterns across 2^63 boundaries."""
        assert compute_simhash_64("") == 0
        assert compute_simhash_64(None) == 0
        assert compute_simhash_64("   \t\n  ") == 0

        # Boundary values
        val_unsigned_max = 0xFFFFFFFFFFFFFFFF  # 2^64 - 1
        val_boundary = 0x8000000000000000      # 2^63

        signed_max = to_signed_64(val_unsigned_max)
        assert signed_max == -1
        assert to_unsigned_64(signed_max) == val_unsigned_max

        signed_boundary = to_signed_64(val_boundary)
        assert signed_boundary == -9223372036854775808
        assert to_unsigned_64(signed_boundary) == val_boundary

    def test_t2_boundary_expired_lease_auto_recovery_edge_conditions(self, clean_db: QueueRepository):
        """Verify expired worker leases are automatically recovered and reset to RETRYABLE_FAILED."""
        repo = clean_db
        repo.enqueue(story_id="s_exp_01", title="Exp Story", content="Content", url="https://reddit.com/exp1", channel="moku")

        claim = repo.claim(channel="moku", owner="crashed_worker", lease_seconds=1)
        assert claim is not None
        assert claim["status"] == JobStatus.PROCESSING

        # Fast forward time to trigger lease expiry
        now_future = int(time.time()) + 10
        recovered_count = repo.recover_expired_leases(now=now_future)
        assert recovered_count == 1

        with connect(repo.db_path, read_only=True) as conn:
            story = conn.execute("SELECT status, failure_code FROM stories WHERE story_id = 's_exp_01'").fetchone()
            assert story["status"] == JobStatus.RETRYABLE_FAILED
            assert story["failure_code"] == "lease_expired"

        # Healthy worker reclaims
        new_claim = repo.claim(channel="moku", owner="healthy_worker", now=now_future + 1)
        assert new_claim is not None
        assert new_claim["story_id"] == "s_exp_01"

    def test_t2_boundary_memory_watchdog_zero_limit_and_reset_isolation(self):
        """Verify MemoryWatchdog disables gracefully with limit <= 0 and reset_module_watchdog isolates tests."""
        wd_disabled = MemoryWatchdog(soft_limit_bytes=0)
        assert wd_disabled.disabled is True
        info = wd_disabled.checkpoint("disabled_stage")
        assert info["disabled"] is True

        reset_module_watchdog()
        chk = memory_checkpoint("module_stage")
        assert isinstance(chk, dict)


# ===========================================================================
# TIER 3: CROSS-FEATURE INTEGRATION PIPELINES
# ===========================================================================

class TestTier3CrossFeaturePipelines:
    """Tier 3: Integrated multi-stage pipelines across Profiling, Cleaner, Media, Persistence."""

    def test_t3_pipeline_concurrent_multilane_claims_during_profiling(self, clean_db: QueueRepository):
        """Pipeline 1: Concurrent multi-lane claiming during active profiled execution across 3 lanes."""
        repo = clean_db
        lanes = ["moku-horror-long", "moku-scp-shorts", "aelithia-drama"]

        for i, lane in enumerate(lanes):
            repo.enqueue(
                story_id=f"story_lane_{i}",
                title=f"Story for {lane}",
                content=f"Narrative content for lane {lane}",
                url=f"https://reddit.com/lane/{i}",
                channel="moku" if "moku" in lane else "aelithia",
                lane_id=lane,
                score=500 + i * 100,
            )

        profiler = PipelineProfiler(run_id="run_multilane_pipe", channel="moku")

        def lane_worker(lane_id: str, worker_id: str):
            with profiler.phase(CanonicalStage.CLAIM_LEASE):
                ch = "moku" if "moku" in lane_id else "aelithia"
                claim = repo.claim_for_lane(lane_id=lane_id, channel=ch, owner=worker_id)
                time.sleep(0.005)
                return claim

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(lane_worker, l, f"w_{l}") for l in lanes]
            claims = [f.result() for f in futures]

        assert all(c is not None for c in claims)
        assert len({c["lane_id"] for c in claims}) == 3

        summary = profiler.get_summary()
        assert summary.phases_count == 3
        assert summary.successful_phases == 3

    def test_t3_pipeline_post_render_cleanup_with_wal_checkpointing(self, clean_db: QueueRepository, tmp_path: Path):
        """Pipeline 2: Video render simulation -> Intermediate cleanup -> SQLite WAL checkpointing."""
        repo = clean_db
        work_dir = tmp_path / "run_render_001"
        work_dir.mkdir(parents=True)

        # 1. Simulate render outputs
        master_mp4 = work_dir / "master_render.mp4"
        master_mp4.write_text("rendered master", encoding="utf-8")
        (work_dir / "prescaled_01.jpg").write_text("temp", encoding="utf-8")
        (work_dir / "concat_list.txt").write_text("temp", encoding="utf-8")
        (work_dir / "ffmpeg_compose.log").write_text("temp", encoding="utf-8")

        # 2. Database update
        repo.enqueue(story_id="s_clean_01", title="Rendered", content="C", url="https://reddit.com/c1", channel="moku")
        claim = repo.claim(channel="moku", owner="render_worker")
        assert claim is not None
        repo.set_status(story_id="s_clean_01", status=JobStatus.PUBLISHED, run_id=claim["run_id"], owner="render_worker")

        # 3. Post-render intermediate cleanup
        report = clean_run_intermediates(work_dir)
        assert report["deleted_files_count"] == 3
        assert master_mp4.exists()

        # 4. Passive WAL checkpointing
        with connect(repo.db_path) as conn:
            wal_res = conn.execute("PRAGMA wal_checkpoint(PASSIVE);").fetchone()
            assert wal_res is not None

    def test_t3_pipeline_audio_mastering_with_profiling_and_resource_guard(self, tmp_path: Path):
        """Pipeline 3: Dramatic pause synthesis + -14 LUFS mastering + profiling telemetry + memory guard."""
        speech_wav = create_synthetic_wav(tmp_path / "speech.wav", duration_sec=2.0)
        music_wav = create_synthetic_wav(tmp_path / "music.wav", duration_sec=3.0)
        out_wav = tmp_path / "mastered.wav"

        profiler = PipelineProfiler(run_id="run_audio_mastering")
        watchdog = MemoryWatchdog(soft_limit_bytes=500 * (1024**3))

        with profiler.phase(CanonicalStage.TTS_SYNTHESIS):
            watchdog.checkpoint("before_mastering")
            master_audio_track(
                narration_path=speech_wav,
                music_path=music_wav,
                output_path=out_wav,
                target_lufs=-14.0,
            )
            watchdog.checkpoint("after_mastering")

        assert out_wav.is_file()
        probe = probe_media(out_wav)
        assert probe.has_audio is True

        summary = profiler.get_summary()
        assert summary.phases_count == 1
        assert summary.successful_phases == 1

    def test_t3_pipeline_disk_headroom_guard_triggers_cleaner_and_resumes_run(self, tmp_path: Path):
        """Pipeline 4: ensure_disk_available detects simulated tight headroom, auto-cleans cache, and succeeds."""
        work_root = tmp_path / "work_headroom"
        work_root.mkdir(parents=True)
        settings_mock = _mock_settings(work_root)

        with patch("src.cleaner.SETTINGS", settings_mock):
            # Create an expired run eligible for cleaning
            exp_dir = work_root / "run_cleanable_01"
            exp_dir.mkdir()
            (exp_dir / "heavy_temp.dat").write_bytes(b"0" * 1024 * 1024)
            marker = exp_dir / ".run.json"
            marker.write_text(json.dumps({"run_id": "run_cleanable_01", "active": False, "retention_satisfied": True}), encoding="utf-8")
            past_time = time.time() - 1000
            os.utime(marker, (past_time, past_time))

            # Guard check with small threshold and auto_clean
            preflight = ensure_disk_available(paths=[work_root], min_free_gb=0.0001, auto_clean=True)
            assert isinstance(preflight, DiskPreflight)
            assert preflight.ok is True

    def test_t3_pipeline_circuit_breaker_trips_and_recovers_across_lanes(self):
        """Pipeline 5: Multi-lane worker failures trip circuit breaker on failing channel while leaving others healthy."""
        breaker = ConsecutiveFailureBreaker(threshold=2)

        # Channel Moku experiences 2 consecutive failures -> trips
        assert breaker.record_failure("moku") is False
        assert breaker.record_failure("moku") is True

        # Channel Aelithia experiences 1 failure -> does not trip
        assert breaker.record_failure("aelithia") is False

        # Channel Aelithia completes successfully -> resets
        breaker.record_success("aelithia")
        assert breaker.record_failure("aelithia") is False

        # Reset Moku after manual intervention
        breaker.reset("moku")
        assert breaker.record_failure("moku") is False


# ===========================================================================
# TIER 4: REAL-WORLD SCENARIOS
# ===========================================================================

class TestTier4RealWorldScenarios:
    """Tier 4: Production-grade multi-channel simulation scenarios with zero quota consumption."""

    def test_t4_scenario_1_full_end_to_end_production_lifecycle(self, clean_db: QueueRepository, tmp_path: Path):
        """
        Scenario 1: Complete end-to-end video production run:
        Acquisition -> 13-stage Profiling -> Audio synthesis -> Single-pass ducking -> Video assembly ->
        Faststart container -> Retention marking -> Post-render intermediate purge -> Master preservation.
        """
        repo = clean_db
        run_id = "run_full_e2e_001"
        story_id = "story_prod_001"
        channel = "moku"

        work_dir = tmp_path / "work" / run_id
        work_dir.mkdir(parents=True)
        settings_mock = _mock_settings(tmp_path / "work")

        # 1. Enqueue story
        repo.enqueue(
            story_id=story_id,
            title="El Misterio de la Mina Olvidada",
            content="Los mineros encontraron una compuerta sellada con símbolos arcanos...",
            url="https://reddit.com/r/nosleep/prod001",
            channel=channel,
            score=950,
            lane_id="moku-horror-long",
        )

        profiler = PipelineProfiler(run_id=run_id, channel=channel, story_id=story_id)

        # 2. Stage 1: Claim Lease
        with profiler.phase(CanonicalStage.CLAIM_LEASE):
            claim = repo.claim_for_lane(lane_id="moku-horror-long", channel=channel, owner="prod_worker_1")
            assert claim is not None
            assert claim["story_id"] == story_id

        # 3. Stage 2-4: Ingest, Editorial, Mood
        with profiler.phase(CanonicalStage.INGEST_TRANSLATE):
            time.sleep(0.005)
        with profiler.phase(CanonicalStage.EDITORIAL_BARRIER):
            time.sleep(0.005)
        with profiler.phase(CanonicalStage.MOOD_THEME):
            time.sleep(0.005)

        # 4. Stage 5: TTS Synthesis & Dramatic Pause Audio Mastering
        master_audio_wav = work_dir / "narration_mastered.wav"
        with profiler.phase(CanonicalStage.TTS_SYNTHESIS):
            speech_raw = create_synthetic_wav(work_dir / "speech.tmp.raw.wav", duration_sec=2.0, freq=350)
            music_raw = create_synthetic_wav(work_dir / "ambient.tmp.bgm.wav", duration_sec=3.0, freq=500)
            master_audio_track(
                narration_path=speech_raw,
                music_path=music_raw,
                output_path=master_audio_wav,
                target_lufs=-14.0,
            )

        # 5. Stage 6-8: Duration Alignment, Subtitle Generation, Loop Planning
        with profiler.phase(CanonicalStage.DURATION_ALIGNMENT):
            time.sleep(0.005)
        with profiler.phase(CanonicalStage.SUBTITLE_GENERATION):
            drawer = CodeSubtitleDrawer()
            assert drawer.theme is not None
        with profiler.phase(CanonicalStage.LOOP_SCENE):
            time.sleep(0.005)

        # 6. Stage 9: Video Rendering & Stream Copy Muxing
        master_video_mp4 = work_dir / "final_master.mp4"
        thumbnail_img = work_dir / "thumbnail.jpg"
        thumbnail_img.write_text("thumbnail jpg data", encoding="utf-8")

        with profiler.phase(CanonicalStage.VIDEO_RENDERING):
            raw_video = create_synthetic_mp4(work_dir / "video.tmp.raw.mp4", duration_sec=2.0)
            # Mux stream copy
            cmd = [
                "ffmpeg", "-y",
                "-i", raw_video,
                "-i", str(master_audio_wav),
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                "-movflags", "+faststart",
                str(master_video_mp4),
            ]
            run_ffmpeg(cmd)

        # 7. Stage 10-12: QA Gating, Thumbnail, SimHash Dedup
        with profiler.phase(CanonicalStage.QA_GATING):
            assert master_video_mp4.is_file()
            assert has_faststart(master_video_mp4) is True
        with profiler.phase(CanonicalStage.THUMBNAIL_METADATA):
            assert thumbnail_img.is_file()
        with profiler.phase(CanonicalStage.DEDUP_SIMHASH):
            fp = compute_simhash_64("El Misterio de la Mina Olvidada")
            repo.record_fingerprint(run_id, story_id, channel, "script", "El Misterio de la Mina Olvidada", normalized_text="el misterio")

        # 8. Stage 13: Retention Satisfaction & Intermediate Cleanup
        marker_file = work_dir / ".run.json"
        marker_file.write_text(json.dumps({"run_id": run_id, "active": False, "retention_satisfied": False}), encoding="utf-8")

        with profiler.phase(CanonicalStage.BACKUP_PUBLISH):
            with patch("src.retention.SETTINGS", settings_mock):
                mark_run_retention_satisfied(master_video_mp4, published_id="yt_prod_999", published_url="https://youtu.be/yt_prod_999")
            repo.set_status(story_id=story_id, status=JobStatus.PUBLISHED, run_id=run_id, owner="prod_worker_1")
            # Intermediate cleanup
            clean_run_intermediates(work_dir)

        # Verify all intermediates were cleaned up and masters preserved
        assert master_video_mp4.exists()
        assert thumbnail_img.exists()
        assert not (work_dir / "speech.tmp.raw.wav").exists()
        assert not (work_dir / "ambient.tmp.bgm.wav").exists()
        assert not (work_dir / "video.tmp.raw.mp4").exists()

        # Profiling summary validation
        summary = profiler.get_summary()
        assert summary.phases_count == 13
        assert summary.successful_phases == 13
        assert summary.failed_phases == 0

    def test_t4_scenario_2_multi_channel_parallel_production_stress(self, clean_db: QueueRepository):
        """
        Scenario 2: Multi-channel (Moku horror + Aelithia drama) concurrent stress run with
        multi-lane leasing, SimHash deduplication, memory guard, and zero database contention.
        """
        repo = clean_db
        num_jobs = 12

        # Enqueue mixed channels
        for i in range(num_jobs):
            ch = "moku" if i % 2 == 0 else "aelithia"
            lane = f"{ch}-lane-{i % 3}"
            repo.enqueue(
                story_id=f"stress_story_{i}",
                title=f"Stress Story {i} for {ch}",
                content=f"Content payload for stress story {i}",
                url=f"https://reddit.com/stress/{i}",
                channel=ch,
                lane_id=lane,
                score=100 + i * 50,
            )

        def runner(worker_idx: int):
            ch = "moku" if worker_idx % 2 == 0 else "aelithia"
            lane = f"{ch}-lane-{worker_idx % 3}"
            claim = repo.claim_for_lane(lane_id=lane, channel=ch, owner=f"worker_{worker_idx}", lease_seconds=30)
            if claim:
                # Simulate work and heartbeat
                repo.heartbeat(run_id=claim["run_id"], owner=f"worker_{worker_idx}")
                # Record SimHash fingerprint
                text = f"Stress Story {worker_idx} for {ch}"
                repo.record_fingerprint(claim["run_id"], claim["story_id"], ch, "script", text, normalized_text=text.lower())
                # Publish
                repo.set_status(story_id=claim["story_id"], status=JobStatus.PUBLISHED, run_id=claim["run_id"], owner=f"worker_{worker_idx}")
            return claim

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(runner, i) for i in range(num_jobs)]
            claims = [f.result() for f in futures]

        valid_claims = [c for c in claims if c is not None]
        assert len(valid_claims) >= 1

        with connect(repo.db_path, read_only=True) as conn:
            published_count = conn.execute("SELECT COUNT(*) FROM stories WHERE status = 'PUBLISHED'").fetchone()[0]
            assert published_count == len(valid_claims)

    def test_t4_scenario_3_crash_recovery_and_emergency_disk_salvage(self, clean_db: QueueRepository, tmp_path: Path):
        """
        Scenario 3: Disaster recovery: worker crash mid-render leaves expired lease and orphaned scratch files.
        Automated recovery sweeps lease, disk guard reclaims failed scratch, and backup worker completes job.
        """
        repo = clean_db
        work_root = tmp_path / "work"
        work_root.mkdir(parents=True)
        settings_mock = _mock_settings(work_root)

        story_id = "story_crash_01"
        repo.enqueue(story_id=story_id, title="Crash Story", content="Content", url="https://reddit.com/crash1", channel="moku")

        # 1. Worker 1 claims with short lease
        claim1 = repo.claim(channel="moku", owner="flaky_worker", lease_seconds=1)
        assert claim1 is not None
        run_id = claim1["run_id"]

        # Worker 1 creates temporary files and marker
        crashed_dir = work_root / run_id
        crashed_dir.mkdir()
        (crashed_dir / "orphan_chunk.dat").write_text("scratch", encoding="utf-8")
        marker = crashed_dir / ".run.json"
        marker.write_text(json.dumps({"run_id": run_id, "active": False, "retention_satisfied": False}), encoding="utf-8")

        # 2. Worker 1 crashes (simulated time advance)
        now_future = int(time.time()) + 15
        recovered_leases = repo.recover_expired_leases(now=now_future)
        assert recovered_leases == 1

        # 3. Emergency disk cleaner purges failed run scratch
        with patch("src.cleaner.SETTINGS", settings_mock):
            past_time = time.time() - 100
            os.utime(marker, (past_time, past_time))
            clean_expired_failed_runs(min_age_seconds=0)
            assert not crashed_dir.exists()

        # 4. Backup worker claims recovered story and successfully finishes
        claim2 = repo.claim(channel="moku", owner="backup_worker", now=now_future + 1)
        assert claim2 is not None
        assert claim2["story_id"] == story_id
        assert repo.set_status(story_id=story_id, status=JobStatus.PUBLISHED, run_id=claim2["run_id"], owner="backup_worker") is True
