"""
src/core/profiling.py - Diagnostics, Profiling & Telemetry Facade.

Backward-compatible facade delegating directly to the modular `src.core.profiling` subpackage.
"""
from __future__ import annotations

from src.core.profiling.benchmarking import run_benchmark_cycle
from src.core.profiling.metrics_sampler import (
    _get_cpu_times,
    _get_peak_rss_bytes,
    _read_vm_rss_bytes,
    _sync_bytes_mb,
    _utc_now_iso,
    is_profiling_enabled,
)
from src.core.profiling.models import (
    CANONICAL_STAGES,
    CanonicalStage,
    PhaseMetrics,
    PhaseTimer,
    PipelineProfiler,
    ProfilingReport,
    ProfilingSummary,
    normalize_stage_name,
    profile_phase,
)

__all__ = [
    "CANONICAL_STAGES",
    "CanonicalStage",
    "PhaseMetrics",
    "PhaseTimer",
    "PipelineProfiler",
    "ProfilingReport",
    "ProfilingSummary",
    "_get_cpu_times",
    "_get_peak_rss_bytes",
    "_read_vm_rss_bytes",
    "_sync_bytes_mb",
    "_utc_now_iso",
    "is_profiling_enabled",
    "normalize_stage_name",
    "profile_phase",
    "run_benchmark_cycle",
]
