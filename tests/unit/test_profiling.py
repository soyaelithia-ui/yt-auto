"""
Unit tests for the diagnostic, profiling, and telemetry framework (Requirement R1).
Tests PhaseMetrics, CanonicalStage, PhaseTimer, PipelineProfiler, and CLI handlers.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.observability.context import get_run_context, set_run_context, update_run_context
from src.core.profiling import (
    CanonicalStage,
    PhaseMetrics,
    PhaseTimer,
    PipelineProfiler,
    ProfilingSummary,
    profile_phase,
    run_benchmark_cycle,
)
from src.cli.handlers.profile import handle_profile


def _consume_wall_time(seconds: float = 0.01) -> None:
    """Busy-wait so PhaseTimer can record duration_sec > 0.

    tests/conftest.py autouse-patches time.sleep to a no-op. On fast CI the
    remaining decorator/context overhead can round to 0.0000s (4 decimals).
    """
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        pass


class TestCanonicalStage:
    def test_canonical_stage_count_and_members(self):
        # Must have exactly 13 canonical production stages
        assert len(CanonicalStage) == 13

        expected_stages = [
            "CLAIM_LEASE",
            "INGEST_TRANSLATE",
            "EDITORIAL_BARRIER",
            "MOOD_THEME",
            "TTS_SYNTHESIS",
            "DURATION_ALIGNMENT",
            "SUBTITLE_GENERATION",
            "LOOP_SCENE",
            "VIDEO_RENDERING",
            "THUMBNAIL_METADATA",
            "DEDUP_SIMHASH",
            "QA_GATING",
            "BACKUP_PUBLISH",
        ]
        for name in expected_stages:
            assert hasattr(CanonicalStage, name)
            stage = getattr(CanonicalStage, name)
            assert stage.display_name
            assert stage.phase_number >= 1

    def test_from_stage_name_resolution(self):
        assert CanonicalStage.from_stage_name("1_claim_lease") == CanonicalStage.CLAIM_LEASE
        assert CanonicalStage.from_stage_name("CLAIM_LEASE") == CanonicalStage.CLAIM_LEASE
        assert CanonicalStage.from_stage_name("5_tts_synthesis") == CanonicalStage.TTS_SYNTHESIS
        assert CanonicalStage.from_stage_name("tts") == CanonicalStage.TTS_SYNTHESIS
        assert CanonicalStage.from_stage_name("render") == CanonicalStage.VIDEO_RENDERING
        assert CanonicalStage.from_stage_name("dedup") == CanonicalStage.DEDUP_SIMHASH
        assert CanonicalStage.from_stage_name("unknown_stage") is None


class TestPhaseMetrics:
    def test_metrics_mapping_interface(self):
        metrics = PhaseMetrics(
            stage="test_stage",
            duration_sec=1.234,
            cpu_user_sec=0.5,
            cpu_system_sec=0.1,
            cpu_total_sec=0.6,
            start_rss_bytes=1000,
            end_rss_bytes=1500,
            delta_rss_bytes=500,
            peak_rss_bytes=2000,
            success=True,
        )
        assert metrics["duration_sec"] == 1.234
        assert metrics["cpu_total_sec"] == 0.6
        assert metrics.get("stage") == "test_stage"
        assert metrics.get("nonexistent", "default") == "default"
        assert "duration_sec" in metrics
        assert len(metrics) > 5
        assert isinstance(list(metrics.keys()), list)
        assert isinstance(list(metrics.values()), list)
        assert isinstance(list(metrics.items()), list)

        d = metrics.to_dict()
        assert isinstance(d, dict)
        assert d["stage"] == "test_stage"
        assert d["duration_sec"] == 1.234
        assert d["delta_rss_bytes"] == 500
        assert d["rss_delta_bytes"] == 500

    def test_metrics_rss_bytes_and_mb_synchronization(self):
        # 1. Provide integer bytes -> float MB computed
        m1 = PhaseMetrics(
            stage="sync_stage",
            start_rss_bytes=10 * 1024 * 1024,
            end_rss_bytes=15 * 1024 * 1024,
            rss_delta_bytes=5 * 1024 * 1024,
            peak_rss_bytes=20 * 1024 * 1024,
        )
        assert m1.start_rss_bytes == 10485760
        assert m1.start_rss_mb == 10.0
        assert m1.end_rss_bytes == 15728640
        assert m1.end_rss_mb == 15.0
        assert m1.rss_delta_bytes == 5242880
        assert m1.delta_rss_bytes == 5242880
        assert m1.rss_delta_mb == 5.0
        assert m1.peak_rss_bytes == 20971520
        assert m1.peak_rss_mb == 20.0
        assert m1["rss_delta_bytes"] == 5242880
        assert m1["delta_rss_bytes"] == 5242880

        # 2. Provide float MB -> integer bytes computed
        m2 = PhaseMetrics(
            stage="sync_mb",
            start_rss_mb=12.5,
            end_rss_mb=17.5,
            rss_delta_mb=5.0,
            peak_rss_mb=25.0,
        )
        assert m2.start_rss_mb == 12.5
        assert m2.start_rss_bytes == int(12.5 * 1024 * 1024)
        assert m2.end_rss_mb == 17.5
        assert m2.end_rss_bytes == int(17.5 * 1024 * 1024)
        assert m2.rss_delta_mb == 5.0
        assert m2.rss_delta_bytes == int(5.0 * 1024 * 1024)
        assert m2.delta_rss_bytes == m2.rss_delta_bytes


class TestPhaseTimer:
    def test_phase_timer_records_duration_and_cpu(self):
        timer = PhaseTimer(CanonicalStage.CLAIM_LEASE)
        with timer:
            # Consume minimal CPU and time
            _ = sum(i * i for i in range(50000))
            time.sleep(0.01)

        metrics = timer.metrics
        assert metrics is not None
        assert metrics.stage == "1_claim_lease"
        assert metrics.duration_sec > 0
        assert metrics.success is True
        assert metrics.error_type is None
        assert metrics.cpu_total_sec >= 0.0
        assert metrics.start_rss_bytes >= 0
        assert metrics.end_rss_bytes >= 0
        assert metrics.rss_delta_bytes is not None
        assert metrics.peak_rss_bytes >= 0

    def test_phase_timer_disabled_zero_overhead(self):
        timer = PhaseTimer("disabled_stage", enabled=False)
        assert timer._metrics is None
        with timer as ctx_res:
            assert ctx_res is None
            time.sleep(0.001)
        assert timer.metrics is None

    def test_phase_timer_captures_exceptions_and_reraises(self):
        timer = PhaseTimer(CanonicalStage.EDITORIAL_BARRIER)
        with pytest.raises(ValueError, match="Editorial violation"):
            with timer:
                raise ValueError("Editorial violation")

        metrics = timer.metrics
        assert metrics is not None
        assert metrics.success is False
        assert metrics.error_type == "ValueError"
        assert "Editorial violation" in str(metrics.error_message)

    def test_phase_timer_as_decorator(self):
        profiler = PipelineProfiler(run_id="run-dec", story_id="story-dec", channel="ch-dec")

        @profiler.phase(CanonicalStage.TTS_SYNTHESIS)
        def mock_synthesize(text: str) -> str:
            _consume_wall_time(0.01)
            return f"audio:{text}"

        res = mock_synthesize("Hola mundo")
        assert res == "audio:Hola mundo"
        phase = profiler.get_phase(CanonicalStage.TTS_SYNTHESIS)
        assert phase is not None
        assert phase.duration_sec > 0

    def test_profile_phase_standalone_decorator(self):
        @profile_phase(CanonicalStage.SUBTITLE_GENERATION)
        def make_subs():
            time.sleep(0.01)
            return "subs.srt"

        res = make_subs()
        assert res == "subs.srt"

    def test_run_context_stage_propagation(self):
        set_run_context(stage="initial")
        timer = PhaseTimer(CanonicalStage.VIDEO_RENDERING)
        with timer:
            assert get_run_context().stage == "9_video_rendering"
        assert get_run_context().stage == "initial"


class TestPipelineProfiler:
    def test_multi_stage_collection_and_summary(self):
        profiler = PipelineProfiler(run_id="run-1", story_id="story-1", channel="moku")

        with profiler.phase(CanonicalStage.INGEST_TRANSLATE):
            _consume_wall_time(0.01)

        with profiler.phase(CanonicalStage.TTS_SYNTHESIS):
            _consume_wall_time(0.01)

        summary = profiler.get_summary()
        assert isinstance(summary, ProfilingSummary)
        assert summary.total_duration_sec > 0
        assert len(summary.phases) == 2
        assert CanonicalStage.INGEST_TRANSLATE.value in summary.phases
        assert CanonicalStage.TTS_SYNTHESIS.value in summary.phases

        # Table formatting test
        table_str = profiler.format_table()
        assert "PROFILING REPORT" in table_str
        assert "100.0%" in table_str
        assert "2_ingest_translate" in table_str
        assert "5_tts_synthesis" in table_str

        # Dict export test
        d = profiler.to_dict()
        assert d["run_id"] == "run-1"
        assert d["story_id"] == "story-1"
        assert d["channel"] == "moku"
        assert "phases" in d
        assert "total_duration_sec" in d

    def test_emit_telemetry_persists_to_db_and_events(self, tmp_path):
        db_path = tmp_path / "test_profiling.db"
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE system_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    level TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    run_id TEXT,
                    story_id TEXT,
                    channel TEXT,
                    component TEXT,
                    stage TEXT,
                    error_code TEXT,
                    message TEXT,
                    details_json TEXT
                )
                """
            )
            conn.commit()

        profiler = PipelineProfiler(run_id="run-telemetry-1", story_id="story-tel-1", channel="aelithia")
        with profiler.phase(CanonicalStage.CLAIM_LEASE):
            time.sleep(0.01)

        profiler.emit_telemetry(db_path=str(db_path))

        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute("SELECT event_type, run_id, story_id, details_json FROM system_events WHERE event_type = 'PIPELINE_PROFILED'").fetchone()
            assert row is not None
            event_type, run_id, story_id, details_json = row
            assert event_type == "PIPELINE_PROFILED"
            assert run_id == "run-telemetry-1"
            assert story_id == "story-tel-1"
            payload = json.loads(details_json)
            assert "total_duration_sec" in payload
            assert "phases" in payload


class TestBenchmarkAndCli:
    def test_run_benchmark_cycle_mock(self):
        summaries = run_benchmark_cycle(channel="moku", iterations=1, mock=True)
        summary = summaries[0] if isinstance(summaries, list) else summaries
        assert isinstance(summary, ProfilingSummary)
        assert len(summary.phases) == 13
        for stage in CanonicalStage:
            assert stage.value in summary.phases
            metrics = summary.phases[stage.value]
            assert metrics.duration_sec >= 0
            assert metrics.success is True

    def test_cli_handle_profile_mock_table(self, capsys, tmp_path):
        args = MagicMock()
        args.mock = True
        args.iterations = 1
        args.channel = "moku"
        args.json = False
        args.history = False
        args.export_json = None
        args.output = None
        args.lane = None
        args.stages = None
        args.db_path = str(tmp_path / "test_profiling.db")

        code = handle_profile(args)
        assert code == 0
        captured = capsys.readouterr()
        assert "PROFILING REPORT" in captured.out
        assert "TOTAL" in captured.out

    def test_cli_handle_profile_mock_json(self, capsys, tmp_path):
        args = MagicMock()
        args.mock = True
        args.iterations = 1
        args.channel = "aelithia"
        args.json = True
        args.history = False
        args.export_json = None
        args.output = None
        args.lane = None
        args.stages = None
        args.db_path = str(tmp_path / "test_profiling.db")

        code = handle_profile(args)
        assert code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "total_duration_sec" in data or "summaries" in data
        if "summaries" in data:
            assert len(data["summaries"]) == 1

    def test_cli_handle_profile_history(self, tmp_path, capsys):
        db_path = tmp_path / "history.db"
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE system_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    level TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    run_id TEXT,
                    story_id TEXT,
                    channel TEXT,
                    component TEXT,
                    stage TEXT,
                    error_code TEXT,
                    message TEXT,
                    details_json TEXT
                )
                """
            )
            payload = json.dumps({"total_duration_sec": 12.34, "total_cpu_sec": 5.67, "phases": {}})
            conn.execute(
                "INSERT INTO system_events (ts, level, event_type, channel, run_id, story_id, details_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("2026-08-28T04:00:00Z", "INFO", "PIPELINE_PROFILED", "moku", "run-hist-1", "story-hist-1", payload),
            )
            conn.commit()

        args = MagicMock()
        args.mock = False
        args.history = True
        args.channel = "moku"
        args.db_path = str(db_path)
        args.limit = 10
        args.json = False

        code = handle_profile(args)
        assert code == 0
        captured = capsys.readouterr()
        assert "run-hist-1" in captured.out
        assert "12.34s" in captured.out


class TestPipelineErrorTelemetry:
    """Verify error path telemetry and profiling dictionary population in pipeline."""

    def test_profiler_record_error_and_summary_sync(self):
        profiler = PipelineProfiler(run_id="err-run-1", story_id="err-story-1", channel="moku")
        profiler.record_error("Simulated capability failure", "CapabilityUnavailable")

        summary = profiler.get_summary()
        assert summary.failed_phases >= 1
        assert summary.successful_phases == 0

        p = profiler.get_phases()[0]
        assert p.success is False
        assert p.error == "Simulated capability failure"
        assert p.error_type == "CapabilityUnavailable"

    def test_pipeline_error_path_populates_profiling_and_emits_telemetry(self, tmp_path):
        from src.core.domain import JobStatus
        from src.core.providers import CapabilityUnavailable
        from src.core.repository import QueueRepository
        from src.pipeline import run_pipeline_once

        db_path = str(tmp_path / "test_pipeline_err.db")
        repo = QueueRepository(db_path)
        repo.initialize()
        repo.enqueue("story-err-1", "Test Title", "Test Content", "http://example.invalid", "moku")

        with patch("src.pipeline.curate_script", side_effect=CapabilityUnavailable("gemini_offline", "API down")):
            result = run_pipeline_once(
                channel="moku",
                db_path=db_path,
                story_id="story-err-1",
                generate_only=True,
            )

        assert result["status"] == JobStatus.RETRYABLE_FAILED.value
        assert "profiling" in result
        assert isinstance(result["profiling"], dict)
        assert result["profiling"]["failed_phases"] >= 1

        # Verify telemetry was emitted to DB
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT event_type, details_json FROM system_events WHERE event_type = 'PIPELINE_PROFILED'"
            ).fetchone()
            assert row is not None
            assert "PIPELINE_PROFILED" in row[0]
            data = json.loads(row[1])
            assert data["failed_phases"] >= 1
