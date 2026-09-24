"""
src/core/profiling/benchmarking.py - Standalone Pipeline Benchmarking Harness.

Executes synthetic or real pipeline benchmark cycles, tracking latency, CPU utilization,
and memory footprints across all 13 canonical production stages.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, List, Optional, Union

if TYPE_CHECKING:
    from src.core.profiling.models import PhaseMetrics, ProfilingSummary

__all__ = ["run_benchmark_cycle"]


def run_benchmark_cycle(
    channel: str = "horror",
    lane_id: Optional[str] = None,
    iterations: int = 1,
    mock_mode: bool = True,
    mock: Optional[bool] = None,
    stages: Optional[List[str]] = None,
    db_path: Optional[str] = None,
) -> List[Any]:
    """Run benchmark cycles measuring latency, CPU, and RSS per stage."""
    from src.core.profiling.models import (
        CANONICAL_STAGES,
        CanonicalStage,
        PhaseMetrics,
        PipelineProfiler,
        ProfilingSummary,
        normalize_stage_name,
    )

    if mock is not None:
        mock_mode = mock

    summaries: List[ProfilingSummary] = []
    target_stages = [normalize_stage_name(s) for s in stages] if stages else None

    for i in range(1, max(1, iterations) + 1):
        run_id = f"bench_run_{i:03d}_{int(time.time())}"
        story_id = f"bench_story_{i:03d}"
        profiler = PipelineProfiler(run_id=run_id, story_id=story_id, channel=channel)

        if mock_mode:
            for stage in CANONICAL_STAGES:
                stage_str = stage.value
                if target_stages and stage_str not in target_stages:
                    continue

                with profiler.phase(stage):
                    _simulate_stage_work(stage)

            profiler.emit_telemetry(db_path=db_path, record_in_production_metrics=False)
            summaries.append(profiler.get_summary())
        else:
            from src.pipeline import run_pipeline_once

            result = run_pipeline_once(
                channel=channel,
                db_path=db_path,
                generate_only=True,
                lane_id=lane_id,
            )
            if "profiling" in result and isinstance(result["profiling"], dict):
                p_data = result["profiling"]
                summary = ProfilingSummary(
                    run_id=p_data.get("run_id"),
                    story_id=p_data.get("story_id"),
                    channel=p_data.get("channel"),
                    total_duration_sec=p_data.get("total_duration_sec", 0.0),
                    started_at=p_data.get("started_at", ""),
                    completed_at=p_data.get("completed_at", ""),
                    total_cpu_user_sec=p_data.get("total_cpu_user_sec", 0.0),
                    total_cpu_system_sec=p_data.get("total_cpu_system_sec", 0.0),
                    total_cpu_sec=p_data.get("total_cpu_sec", 0.0),
                    overall_cpu_percent=p_data.get("overall_cpu_percent", 0.0),
                    initial_rss_mb=p_data.get("initial_rss_mb", 0.0),
                    final_rss_mb=p_data.get("final_rss_mb", 0.0),
                    net_rss_delta_mb=p_data.get("net_rss_delta_mb", 0.0),
                    peak_rss_mb=p_data.get("peak_rss_mb", 0.0),
                    phases_count=p_data.get("phases_count", 0),
                    successful_phases=p_data.get("successful_phases", 0),
                    failed_phases=p_data.get("failed_phases", 0),
                    phase_breakdown=[
                        PhaseMetrics(**p) if isinstance(p, dict) else p
                        for p in p_data.get("phase_breakdown", [])
                    ],
                )
                summaries.append(summary)

    return summaries


def _simulate_stage_work(stage: Any) -> None:
    """Simulate realistic non-blocking workload per canonical pipeline stage."""
    from src.core.profiling.models import CanonicalStage

    if stage == CanonicalStage.CLAIM_LEASE:
        time.sleep(0.005)
    elif stage == CanonicalStage.INGEST_TRANSLATE:
        _ = [hash(f"story_word_{k}") for k in range(10_000)]
        time.sleep(0.01)
    elif stage == CanonicalStage.EDITORIAL_BARRIER:
        text = "Sample horror story text for compliance checking " * 20
        _ = [text.replace("horror", "misterio") for _ in range(500)]
        time.sleep(0.005)
    elif stage == CanonicalStage.MOOD_THEME:
        time.sleep(0.005)
    elif stage == CanonicalStage.TTS_SYNTHESIS:
        _ = [sum(k * 0.5 for k in range(20_000))]
        time.sleep(0.02)
    elif stage == CanonicalStage.DURATION_ALIGNMENT:
        time.sleep(0.005)
    elif stage == CanonicalStage.SUBTITLE_GENERATION:
        _ = [f"00:00:{s:02d},000 --> 00:00:{s+1:02d},000\nWord {s}" for s in range(50)]
        time.sleep(0.005)
    elif stage == CanonicalStage.LOOP_SCENE:
        time.sleep(0.005)
    elif stage == CanonicalStage.VIDEO_RENDERING:
        _ = hash(b"lavfi_stream_copy_stub")
        time.sleep(0.008)
    elif stage == CanonicalStage.QA_GATING:
        time.sleep(0.005)
    elif stage == CanonicalStage.THUMBNAIL_METADATA:
        time.sleep(0.01)
    elif stage == CanonicalStage.DEDUP_SIMHASH:
        _ = [hash(f"hash_sample_{k}") for k in range(5_000)]
        time.sleep(0.005)
    elif stage == CanonicalStage.BACKUP_PUBLISH:
        time.sleep(0.005)
