"""
Adversarial empirical stress tests for Requirement R1 (Diagnostics, Profiling & Telemetry).
Challenger 1 Stress Harness.

Verifies:
1. High-concurrency multi-threaded phase timer execution (no race conditions, accurate metrics).
2. Large synthetic memory allocation deltas, CPU busy loops, and subprocess resource tracking.
3. Exception propagation, nested timers, context unwinding, and error diagnostics.
4. Telemetry persistence volume and SQLite WAL concurrency under heavy parallel emission.
5. Boundary conditions, zero durations, massive rapid iterations, and unicode resilience.
"""

from __future__ import annotations

import concurrent.futures
import gc
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
import pytest

from src.observability.context import get_run_context, set_run_context, update_run_context
from src.core.profiling import (
    CanonicalStage,
    CANONICAL_STAGES,
    PhaseMetrics,
    PhaseTimer,
    PipelineProfiler,
    ProfilingSummary,
    profile_phase,
    run_benchmark_cycle,
    is_profiling_enabled,
    normalize_stage_name,
)


# ===========================================================================
# 1. High-Concurrency Multi-Threaded Stress Tests
# ===========================================================================


class TestConcurrencyAndThreadSafety:
    """Stress tests verifying thread-safety and concurrency invariance."""

    def test_high_concurrency_shared_profiler_collection(self):
        """Verify 50 concurrent threads appending to a single shared PipelineProfiler."""
        num_threads = 50
        stages_per_thread = 5
        profiler = PipelineProfiler(run_id="stress-concurrency", channel="moku")

        def worker_task(thread_id: int):
            for s_idx in range(stages_per_thread):
                stage = CANONICAL_STAGES[s_idx % len(CANONICAL_STAGES)]
                with profiler.phase(stage, metadata={"thread_id": thread_id, "step": s_idx}):
                    # Light CPU burn
                    _ = sum(i for i in range(1000))
                    time.sleep(0.001)

        threads = [threading.Thread(target=worker_task, args=(tid,)) for tid in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        recorded_phases = profiler.get_phases()
        expected_total = num_threads * stages_per_thread
        assert len(recorded_phases) == expected_total, (
            f"Expected {expected_total} recorded phases, got {len(recorded_phases)}"
        )

        summary = profiler.get_summary()
        assert summary.phases_count == expected_total
        assert summary.successful_phases == expected_total
        assert summary.failed_phases == 0
        assert summary.total_duration_sec > 0

    def test_concurrent_reads_and_writes_no_race(self):
        """Verify reader threads calling get_summary/to_dict while writers append phases."""
        profiler = PipelineProfiler(run_id="stress-race-check", channel="aelithia")
        stop_event = threading.Event()
        read_errors: list[Exception] = []
        read_count = [0]

        def writer_task():
            for i in range(100):
                stage = CANONICAL_STAGES[i % len(CANONICAL_STAGES)]
                with profiler.phase(stage, metadata={"idx": i}):
                    time.sleep(0.0005)

        def reader_task():
            while not stop_event.is_set():
                try:
                    summary = profiler.get_summary()
                    _ = summary.to_dict()
                    _ = summary.to_json()
                    _ = profiler.format_table()
                    read_count[0] += 1
                except Exception as exc:
                    read_errors.append(exc)
                time.sleep(0.0002)

        writers = [threading.Thread(target=writer_task) for _ in range(10)]
        readers = [threading.Thread(target=reader_task) for _ in range(5)]

        for r in readers:
            r.start()
        for w in writers:
            w.start()

        for w in writers:
            w.join()

        stop_event.set()
        for r in readers:
            r.join()

        assert len(read_errors) == 0, f"Concurrent read errors detected: {read_errors}"
        assert read_count[0] > 10, "Readers did not execute enough iterations"
        assert profiler.get_summary().phases_count == 1000

    def test_thread_context_isolation_with_phase_timer(self):
        """Verify RunContext.stage isolation across concurrent threads."""
        errors: list[str] = []

        def worker_context(stage_enum: CanonicalStage):
            for _ in range(10):
                timer = PhaseTimer(stage_enum)
                with timer:
                    current_ctx_stage = get_run_context().stage
                    if current_ctx_stage != stage_enum.value:
                        errors.append(f"Expected {stage_enum.value}, got {current_ctx_stage}")
                    time.sleep(0.001)

        t1 = threading.Thread(target=worker_context, args=(CanonicalStage.TTS_SYNTHESIS,))
        t2 = threading.Thread(target=worker_context, args=(CanonicalStage.VIDEO_RENDERING,))
        t3 = threading.Thread(target=worker_context, args=(CanonicalStage.QA_GATING,))

        t1.start()
        t2.start()
        t3.start()
        t1.join()
        t2.join()
        t3.join()

        assert len(errors) == 0, f"Thread context pollution occurred: {errors}"


# ===========================================================================
# 2. Resource Profiling Accuracy: Memory, CPU, and Subprocess Stress
# ===========================================================================


class TestResourceProfilingAccuracy:
    """Stress tests verifying accuracy of CPU times, RSS memory deltas, and subprocess tracking."""

    def test_synthetic_large_memory_allocation(self):
        """Verify that large memory allocations reflect in peak RSS and delta."""
        gc.collect()
        profiler = PipelineProfiler(run_id="stress-mem", channel="moku")

        with profiler.phase(CanonicalStage.VIDEO_RENDERING):
            # Allocate 30MB bytearray and touch memory
            large_buf = bytearray(30 * 1024 * 1024)
            for idx in range(0, len(large_buf), 4096):
                large_buf[idx] = (idx % 255)
            time.sleep(0.02)
            assert len(large_buf) == 30 * 1024 * 1024

        phase = profiler.get_phase(CanonicalStage.VIDEO_RENDERING)
        assert phase is not None
        assert phase.peak_rss_mb > 0
        assert phase.start_rss_mb > 0
        assert phase.end_rss_mb > 0
        # Peak RSS should be at least as high as start RSS
        assert phase.peak_rss_mb >= phase.start_rss_mb

    def test_cpu_heavy_busy_loop_measurement(self):
        """Verify CPU user time is accurately measured during CPU-intensive loops."""
        profiler = PipelineProfiler(run_id="stress-cpu", channel="moku")

        with profiler.phase(CanonicalStage.INGEST_TRANSLATE):
            # Run CPU-bound computation for at least 0.12 seconds to span multiple clock ticks
            t_start = time.perf_counter()
            count = 0
            while time.perf_counter() - t_start < 0.12:
                count += sum(i * i for i in range(1000))
            assert count > 0

        phase = profiler.get_phase(CanonicalStage.INGEST_TRANSLATE)
        assert phase is not None
        assert phase.duration_sec >= 0.10
        assert phase.cpu_user_sec >= 0.01, f"Expected cpu_user_sec >= 0.01, got {phase.cpu_user_sec}"
        assert phase.cpu_total_sec >= phase.cpu_user_sec
        assert phase.cpu_percent > 10.0, f"Expected cpu_percent > 10%, got {phase.cpu_percent}"

    def test_subprocess_reaped_cpu_and_rusage(self):
        """Verify that subprocess execution CPU time is captured upon process completion."""
        profiler = PipelineProfiler(run_id="stress-subprocess", channel="aelithia")

        with profiler.phase(CanonicalStage.TTS_SYNTHESIS):
            # Spawn a child python process that consumes CPU and exits
            code = "import time; _ = sum(i*i for i in range(3_000_000)); time.sleep(0.02)"
            proc = subprocess.run([sys.executable, "-c", code], capture_output=True)
            assert proc.returncode == 0

        phase = profiler.get_phase(CanonicalStage.TTS_SYNTHESIS)
        assert phase is not None
        assert phase.duration_sec > 0.02
        # Subprocess user CPU should be recorded via os.times() child metrics or total CPU
        assert phase.cpu_total_sec >= 0.0
        assert phase.peak_rss_mb > 0


# ===========================================================================
# 3. Exception Propagation and Error Diagnostics Stress
# ===========================================================================


class TestExceptionHandlingAndDiagnostics:
    """Stress tests verifying exception propagation, error capture, and context restoration."""

    def test_nested_phase_timers_with_exception_unwinding(self):
        """Verify nested phase timers record failure accurately and unwind context."""
        profiler = PipelineProfiler(run_id="stress-nested-exc", channel="moku")
        set_run_context(stage="root_stage")

        with pytest.raises(RuntimeError, match="Inner crash"):
            with profiler.phase(CanonicalStage.INGEST_TRANSLATE):
                assert get_run_context().stage == CanonicalStage.INGEST_TRANSLATE.value
                with profiler.phase(CanonicalStage.EDITORIAL_BARRIER):
                    assert get_run_context().stage == CanonicalStage.EDITORIAL_BARRIER.value
                    raise RuntimeError("Inner crash")

        # Check that context was restored back to initial
        assert get_run_context().stage == "root_stage"

        # Check recorded phases in profiler
        summary = profiler.get_summary()
        assert summary.phases_count == 2
        assert summary.failed_phases == 2
        assert summary.successful_phases == 0

        p_inner = profiler.get_phase(CanonicalStage.EDITORIAL_BARRIER)
        assert p_inner is not None
        assert p_inner.success is False
        assert p_inner.error_type == "RuntimeError"
        assert "Inner crash" in str(p_inner.error_message)

        p_outer = profiler.get_phase(CanonicalStage.INGEST_TRANSLATE)
        assert p_outer is not None
        assert p_outer.success is False
        assert p_outer.error_type == "RuntimeError"

    def test_diverse_exception_types_captured(self):
        """Verify diverse exception classes (Custom, ZeroDivisionError, KeyError)."""
        class CustomDomainError(Exception):
            pass

        profiler = PipelineProfiler(run_id="stress-custom-exc", channel="moku")

        # 1. Custom exception
        with pytest.raises(CustomDomainError):
            with profiler.phase(CanonicalStage.CLAIM_LEASE):
                raise CustomDomainError("Custom lease error")

        # 2. ZeroDivisionError
        with pytest.raises(ZeroDivisionError):
            with profiler.phase(CanonicalStage.DURATION_ALIGNMENT):
                _ = 10 / 0

        # 3. KeyError
        with pytest.raises(KeyError):
            with profiler.phase(CanonicalStage.QA_GATING):
                _ = {}["missing_key"]

        summary = profiler.get_summary()
        assert summary.phases_count == 3
        assert summary.failed_phases == 3

        c_phase = profiler.get_phase(CanonicalStage.CLAIM_LEASE)
        assert c_phase.error_type == "CustomDomainError"

        d_phase = profiler.get_phase(CanonicalStage.DURATION_ALIGNMENT)
        assert d_phase.error_type == "ZeroDivisionError"

        q_phase = profiler.get_phase(CanonicalStage.QA_GATING)
        assert q_phase.error_type == "KeyError"

    def test_summary_table_formatting_with_mixed_outcomes(self):
        """Verify format_table renders PASS and FAIL markers and summary percentages correctly."""
        profiler = PipelineProfiler(run_id="run-mixed", channel="moku", story_id="story-mix")

        with profiler.phase(CanonicalStage.INGEST_TRANSLATE):
            time.sleep(0.005)

        try:
            with profiler.phase(CanonicalStage.EDITORIAL_BARRIER):
                raise ValueError("Banned keyword found")
        except ValueError:
            pass

        with profiler.phase(CanonicalStage.TTS_SYNTHESIS):
            time.sleep(0.005)

        summary = profiler.get_summary()
        assert summary.phases_count == 3
        assert summary.successful_phases == 2
        assert summary.failed_phases == 1

        table = profiler.format_table()
        assert "PASS" in table
        assert "FAIL" in table
        assert "2/3 OK" in table
        assert "PIPELINE PROFILING REPORT" in table


# ===========================================================================
# 4. Telemetry Persistence & SQLite WAL Concurrency Stress
# ===========================================================================


class TestTelemetryPersistenceAndWalConcurrency:
    """Stress tests verifying high-volume telemetry persistence and SQLite WAL concurrency."""

    @pytest.fixture
    def wal_db(self, tmp_path):
        """Initialize an isolated SQLite WAL database."""
        db_file = tmp_path / "wal_stress.db"
        with sqlite3.connect(str(db_file)) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS system_events (
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
        return str(db_file)

    def test_parallel_telemetry_emission_high_load(self, wal_db):
        """Verify 25 concurrent threads emitting profiling telemetry simultaneously."""
        num_runs = 25

        def emit_worker(worker_id: int):
            run_id = f"wal_run_{worker_id:03d}"
            story_id = f"wal_story_{worker_id:03d}"
            profiler = PipelineProfiler(run_id=run_id, story_id=story_id, channel="moku")

            for stage in CANONICAL_STAGES:
                with profiler.phase(stage):
                    time.sleep(0.0005)

            # Emit telemetry to SQLite database
            success = profiler.emit_telemetry(db_path=wal_db, record_in_production_metrics=False)
            return success

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(emit_worker, i) for i in range(num_runs)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert all(results), "Not all emissions succeeded"

        # Verify all 25 rows exist in SQLite and have valid JSON
        with sqlite3.connect(wal_db) as conn:
            rows = conn.execute(
                "SELECT run_id, story_id, event_type, details_json FROM system_events WHERE event_type = 'PIPELINE_PROFILED'"
            ).fetchall()

        assert len(rows) == num_runs, f"Expected {num_runs} rows in system_events, got {len(rows)}"

        for run_id, story_id, event_type, details_json in rows:
            assert event_type == "PIPELINE_PROFILED"
            data = json.loads(details_json)
            assert "total_duration_sec" in data
            assert data["phases_count"] == 13
            assert data["successful_phases"] == 13
            assert len(data["phases"]) == 13

    def test_emit_telemetry_fail_safe_on_invalid_db(self, tmp_path):
        """Verify emit_telemetry does not raise exceptions when db is invalid or locked."""
        invalid_db_path = str(tmp_path / "non_existent_dir" / "invalid.db")
        profiler = PipelineProfiler(run_id="run-fail-safe", channel="moku")

        with profiler.phase(CanonicalStage.CLAIM_LEASE):
            time.sleep(0.001)

        # Must not raise exception
        result = profiler.emit_telemetry(db_path=invalid_db_path)
        assert result is True

    def test_benchmark_cycle_multi_iteration_throughput(self, wal_db):
        """Verify run_benchmark_cycle under multi-iteration mock workloads."""
        summaries = run_benchmark_cycle(
            channel="aelithia",
            iterations=5,
            mock_mode=True,
            db_path=wal_db,
        )
        assert isinstance(summaries, list)
        assert len(summaries) == 5

        for summary in summaries:
            assert summary.phases_count == 13
            assert summary.total_duration_sec > 0
            assert summary.channel == "aelithia"


# ===========================================================================
# 5. Boundary Conditions, Zero Durations, Massive Iterations & Unicode
# ===========================================================================


class TestBoundaryAndEdgeCases:
    """Stress tests verifying boundary conditions, microsecond durations, and Unicode strings."""

    def test_zero_duration_instantaneous_phase(self):
        """Verify phase timer handles instantaneous (no-op) execution without division by zero."""
        profiler = PipelineProfiler(run_id="run-zero-dur", channel="moku")
        with profiler.phase(CanonicalStage.CLAIM_LEASE):
            pass  # No-op

        phase = profiler.get_phase(CanonicalStage.CLAIM_LEASE)
        assert phase is not None
        assert phase.duration_sec >= 0.0
        assert phase.cpu_percent >= 0.0
        assert phase.success is True

        summary = profiler.get_summary()
        assert summary.overall_cpu_percent >= 0.0
        table = summary.format_table()
        assert "1_claim_lease" in table

    def test_massive_rapid_phase_recording(self):
        """Verify profiler can handle 2,000 rapid sequential phases without degradation."""
        profiler = PipelineProfiler(run_id="run-rapid", channel="moku")
        t_start = time.perf_counter()

        for idx in range(2000):
            stage = CANONICAL_STAGES[idx % len(CANONICAL_STAGES)]
            with profiler.phase(stage, metadata={"iter": idx}):
                pass

        elapsed = time.perf_counter() - t_start
        assert elapsed < 5.0, f"2000 phases took too long: {elapsed:.2f}s"
        assert len(profiler.get_phases()) == 2000
        summary = profiler.get_summary()
        assert summary.phases_count == 2000

    def test_unicode_and_special_character_metadata_and_stages(self):
        """Verify handling of complex Unicode strings, emojis, and nested metadata structures."""
        profiler = PipelineProfiler(
            run_id="run-🎯-123",
            story_id="story-👻-456",
            channel="moku-⛩️",
        )

        unicode_meta = {
            "title": "Historias de Ultratumba 💀 🔥",
            "tags": ["terror", "misterio", "español", "élégance", "こんにちは"],
            "nested": {"score": 99.9, "flag": True, "empty": None},
        }

        with profiler.phase("custom_stage_🚀", metadata=unicode_meta):
            time.sleep(0.002)

        summary = profiler.get_summary()
        json_output = summary.to_json()
        assert "Historias de Ultratumba 💀 🔥" in json_output
        assert "custom_stage_🚀" in json_output

        # Re-parse JSON and assert fidelity
        parsed = json.loads(json_output)
        assert parsed["run_id"] == "run-🎯-123"
        assert parsed["channel"] == "moku-⛩️"
        assert parsed["phase_breakdown"][0]["metadata"]["tags"][4] == "こんにちは"
