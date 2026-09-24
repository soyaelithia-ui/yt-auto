"""
src/core/profiling/models.py - Core Telemetry and Profiling Models & Classes.

Defines CanonicalStage (13 stages), PhaseMetrics, ProfilingSummary, PhaseTimer,
PipelineProfiler, and profile_phase decorator.
"""
from __future__ import annotations

import contextlib
import functools
import json
import logging
import threading
import time
from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, List, Optional, TypeVar

from src.core.profiling.metrics_sampler import (
    _get_cpu_times,
    _get_peak_rss_bytes,
    _read_vm_rss_bytes,
    _sync_bytes_mb,
    _utc_now_iso,
    is_profiling_enabled,
)

logger = logging.getLogger("profiling")

F = TypeVar("F", bound=Callable[..., Any])

__all__ = [
    "CANONICAL_STAGES",
    "CanonicalStage",
    "PhaseMetrics",
    "PhaseTimer",
    "PipelineProfiler",
    "ProfilingReport",
    "ProfilingSummary",
    "normalize_stage_name",
    "profile_phase",
]


class CanonicalStage(str, Enum):
    """The 13 canonical production stages defined in PROJECT.md."""

    CLAIM_LEASE = "1_claim_lease"                   # Stage 1: Claim / Lease Acquisition
    INGEST_TRANSLATE = "2_ingest_translate"         # Stage 2: Content Ingest & Translation
    EDITORIAL_BARRIER = "3_editorial_barrier"       # Stage 3: Sanitization & Editorial Barrier
    MOOD_THEME = "4_mood_theme"                     # Stage 4: Mood & Theme Resolution
    TTS_SYNTHESIS = "5_tts_synthesis"               # Stage 5: TTS Synthesis & Audio Mastering
    DURATION_ALIGNMENT = "6_duration_alignment"     # Stage 6: Duration & Segment Alignment
    SUBTITLE_GENERATION = "7_subtitle_generation"   # Stage 7: Subtitle Generation & Layout
    LOOP_SCENE = "8_loop_scene"                     # Stage 8: Loop & Scene Resolution
    VIDEO_RENDERING = "9_video_rendering"           # Stage 9: Procedural & Realtime Rendering
    QA_GATING = "10_qa_gating"                      # Stage 10: Automated QA Gating
    THUMBNAIL_METADATA = "11_thumbnail_metadata"   # Stage 11: Thumbnail & Metadata Generation
    DEDUP_SIMHASH = "12_dedup_simhash"              # Stage 12: SimHash & Visual Deduplication
    BACKUP_PUBLISH = "13_backup_publish"           # Stage 13: Backup & Publication

    @property
    def phase_number(self) -> int:
        try:
            return int(self.value.split("_")[0])
        except (ValueError, IndexError):
            return 0

    @property
    def display_name(self) -> str:
        names = {
            "1_claim_lease": "1. Claim / Lease Acquisition",
            "2_ingest_translate": "2. Ingest & Translation",
            "3_editorial_barrier": "3. Editorial Barrier & Sanitization",
            "4_mood_theme": "4. Mood & Theme Resolution",
            "5_tts_synthesis": "5. TTS Narration & Audio",
            "6_duration_alignment": "6. Duration Alignment",
            "7_subtitle_generation": "7. Subtitle Generation",
            "8_loop_scene": "8. Loop / Scene Planning",
            "9_video_rendering": "9. Video Rendering",
            "10_qa_gating": "10. Automated QA Gating",
            "11_thumbnail_metadata": "11. Thumbnail & Metadata",
            "12_dedup_simhash": "12. Dedup & SimHash Check",
            "13_backup_publish": "13. Backup & Publication",
        }
        return names.get(self.value, self.value)

    @classmethod
    def from_stage_name(cls, name: str | CanonicalStage | None) -> CanonicalStage | None:
        if not name:
            return None
        if isinstance(name, CanonicalStage):
            return name
        raw = str(name).strip().lower()
        if raw in _STAGE_ALIASES:
            return _STAGE_ALIASES[raw]
        for member in cls:
            if member.value == raw or member.name.lower() == raw:
                return member
        return None


CANONICAL_STAGES: list[CanonicalStage] = list(CanonicalStage)

_STAGE_ALIASES: dict[str, CanonicalStage] = {
    "1": CanonicalStage.CLAIM_LEASE, "claim": CanonicalStage.CLAIM_LEASE,
    "claim_lease": CanonicalStage.CLAIM_LEASE, "1_claim_lease": CanonicalStage.CLAIM_LEASE,
    "leases": CanonicalStage.CLAIM_LEASE,

    "2": CanonicalStage.INGEST_TRANSLATE, "ingest": CanonicalStage.INGEST_TRANSLATE,
    "content_ingest": CanonicalStage.INGEST_TRANSLATE, "2_ingest_translate": CanonicalStage.INGEST_TRANSLATE,
    "translate": CanonicalStage.INGEST_TRANSLATE,

    "3": CanonicalStage.EDITORIAL_BARRIER, "editorial": CanonicalStage.EDITORIAL_BARRIER,
    "sanitization": CanonicalStage.EDITORIAL_BARRIER, "sanitization_barrier": CanonicalStage.EDITORIAL_BARRIER,
    "3_editorial_barrier": CanonicalStage.EDITORIAL_BARRIER, "editorial_barrier": CanonicalStage.EDITORIAL_BARRIER,

    "4": CanonicalStage.MOOD_THEME, "mood": CanonicalStage.MOOD_THEME, "theme": CanonicalStage.MOOD_THEME,
    "mood_theme": CanonicalStage.MOOD_THEME, "mood_theme_resolution": CanonicalStage.MOOD_THEME,
    "4_mood_theme": CanonicalStage.MOOD_THEME,

    "5": CanonicalStage.TTS_SYNTHESIS, "tts": CanonicalStage.TTS_SYNTHESIS,
    "tts_synthesis": CanonicalStage.TTS_SYNTHESIS, "5_tts_synthesis": CanonicalStage.TTS_SYNTHESIS,
    "speech": CanonicalStage.TTS_SYNTHESIS,

    "6": CanonicalStage.DURATION_ALIGNMENT, "duration": CanonicalStage.DURATION_ALIGNMENT,
    "duration_alignment": CanonicalStage.DURATION_ALIGNMENT, "6_duration_alignment": CanonicalStage.DURATION_ALIGNMENT,
    "alignment": CanonicalStage.DURATION_ALIGNMENT,

    "7": CanonicalStage.SUBTITLE_GENERATION, "subtitles": CanonicalStage.SUBTITLE_GENERATION,
    "subtitle_generation": CanonicalStage.SUBTITLE_GENERATION, "7_subtitle_generation": CanonicalStage.SUBTITLE_GENERATION,

    "8": CanonicalStage.LOOP_SCENE, "scene": CanonicalStage.LOOP_SCENE, "loop": CanonicalStage.LOOP_SCENE,
    "loop_scene": CanonicalStage.LOOP_SCENE, "scene_resolution": CanonicalStage.LOOP_SCENE,
    "8_loop_scene": CanonicalStage.LOOP_SCENE,

    "9": CanonicalStage.VIDEO_RENDERING, "render": CanonicalStage.VIDEO_RENDERING,
    "rendering": CanonicalStage.VIDEO_RENDERING, "video_rendering": CanonicalStage.VIDEO_RENDERING,
    "9_video_rendering": CanonicalStage.VIDEO_RENDERING, "compositor": CanonicalStage.VIDEO_RENDERING,

    "10": CanonicalStage.QA_GATING, "qa": CanonicalStage.QA_GATING,
    "qa_gating": CanonicalStage.QA_GATING, "automated_qa": CanonicalStage.QA_GATING,
    "10_qa_gating": CanonicalStage.QA_GATING,

    "11": CanonicalStage.THUMBNAIL_METADATA, "thumbnail": CanonicalStage.THUMBNAIL_METADATA,
    "metadata": CanonicalStage.THUMBNAIL_METADATA, "thumbnail_metadata": CanonicalStage.THUMBNAIL_METADATA,
    "11_thumbnail_metadata": CanonicalStage.THUMBNAIL_METADATA,

    "12": CanonicalStage.DEDUP_SIMHASH, "dedup": CanonicalStage.DEDUP_SIMHASH,
    "simhash": CanonicalStage.DEDUP_SIMHASH, "simhash_deduplication": CanonicalStage.DEDUP_SIMHASH,
    "12_dedup_simhash": CanonicalStage.DEDUP_SIMHASH,

    "13": CanonicalStage.BACKUP_PUBLISH, "backup": CanonicalStage.BACKUP_PUBLISH,
    "publish": CanonicalStage.BACKUP_PUBLISH, "publication": CanonicalStage.BACKUP_PUBLISH,
    "backup_publication": CanonicalStage.BACKUP_PUBLISH, "publication_backup": CanonicalStage.BACKUP_PUBLISH,
    "13_backup_publish": CanonicalStage.BACKUP_PUBLISH,
}


def normalize_stage_name(stage: str | CanonicalStage) -> str:
    """Normalize a stage name or alias to canonical form string."""
    if isinstance(stage, CanonicalStage):
        return stage.value
    raw = str(stage).strip().lower()
    if raw in _STAGE_ALIASES:
        return _STAGE_ALIASES[raw].value
    return str(stage)


@dataclass
class PhaseMetrics(Mapping[str, Any]):
    """Detailed telemetry record for a single pipeline stage execution."""

    stage_name: str = ""
    run_id: str | None = None
    story_id: str | None = None
    channel: str | None = None

    duration_sec: float = 0.0
    started_at: str = ""
    completed_at: str = ""

    cpu_user_sec: float = 0.0
    cpu_system_sec: float = 0.0
    cpu_children_user_sec: float = 0.0
    cpu_children_system_sec: float = 0.0
    cpu_total_sec: float = 0.0
    cpu_percent: float = 0.0

    start_rss_mb: float = 0.0
    end_rss_mb: float = 0.0
    rss_delta_mb: float = 0.0
    peak_rss_mb: float = 0.0

    start_rss_bytes: int = 0
    end_rss_bytes: int = 0
    rss_delta_bytes: int = 0
    delta_rss_bytes: int = 0
    peak_rss_bytes: int = 0

    success: bool = True
    error: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        stage_name: str | None = None,
        stage: str | None = None,
        run_id: str | None = None,
        story_id: str | None = None,
        channel: str | None = None,
        duration_sec: float = 0.0,
        started_at: str = "",
        completed_at: str = "",
        cpu_user_sec: float = 0.0,
        cpu_system_sec: float = 0.0,
        cpu_children_user_sec: float = 0.0,
        cpu_children_system_sec: float = 0.0,
        cpu_total_sec: float = 0.0,
        cpu_percent: float = 0.0,
        start_rss_mb: float = 0.0,
        end_rss_mb: float = 0.0,
        rss_delta_mb: float = 0.0,
        peak_rss_mb: float = 0.0,
        start_rss_bytes: int = 0,
        end_rss_bytes: int = 0,
        rss_delta_bytes: int = 0,
        delta_rss_bytes: int = 0,
        peak_rss_bytes: int = 0,
        success: bool = True,
        error: str | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.stage_name = str(stage_name or stage or "")
        self.run_id = run_id
        self.story_id = story_id
        self.channel = channel
        self.duration_sec = float(duration_sec)
        self.started_at = started_at
        self.completed_at = completed_at
        self.cpu_user_sec = float(cpu_user_sec)
        self.cpu_system_sec = float(cpu_system_sec)
        self.cpu_children_user_sec = float(cpu_children_user_sec)
        self.cpu_children_system_sec = float(cpu_children_system_sec)
        self.cpu_total_sec = float(cpu_total_sec or (self.cpu_user_sec + self.cpu_system_sec))
        self.cpu_percent = float(cpu_percent)

        self.start_rss_bytes, self.start_rss_mb = _sync_bytes_mb(start_rss_bytes, start_rss_mb)
        self.end_rss_bytes, self.end_rss_mb = _sync_bytes_mb(end_rss_bytes, end_rss_mb)
        self.rss_delta_bytes, self.rss_delta_mb = _sync_bytes_mb(rss_delta_bytes or delta_rss_bytes, rss_delta_mb)
        self.delta_rss_bytes = self.rss_delta_bytes
        self.peak_rss_bytes, self.peak_rss_mb = _sync_bytes_mb(peak_rss_bytes, peak_rss_mb)

        self.success = bool(success)
        self.error = error or error_message
        self.error_type = error_type or (error.split(":")[0] if error and ":" in error else ("Error" if error else None))
        self.error_message = error_message or self.error
        self.metadata = metadata or {}

    @property
    def stage(self) -> str:
        return self.stage_name

    def __getitem__(self, key: str) -> Any:
        if key == "stage":
            return self.stage_name
        if key in ("delta_rss_bytes", "rss_delta_bytes"):
            return self.rss_delta_bytes
        if key in ("delta_rss_mb", "rss_delta_mb"):
            return self.rss_delta_mb
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key) from None

    def __iter__(self) -> Iterator[str]:
        return iter(asdict(self))

    def __len__(self) -> int:
        return len(asdict(self))

    def get(self, key: str, default: Any = None) -> Any:
        if key == "stage":
            return self.stage_name
        if key in ("delta_rss_bytes", "rss_delta_bytes"):
            return self.rss_delta_bytes
        if key in ("delta_rss_mb", "rss_delta_mb"):
            return self.rss_delta_mb
        return getattr(self, key, default)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["stage"] = self.stage_name
        d["delta_rss_bytes"] = self.rss_delta_bytes
        d["rss_delta_bytes"] = self.rss_delta_bytes
        return d


@dataclass
class ProfilingSummary:
    """Aggregated multi-stage profiling summary for a complete pipeline run."""

    run_id: str | None
    story_id: str | None
    channel: str | None

    total_duration_sec: float
    started_at: str
    completed_at: str

    total_cpu_user_sec: float
    total_cpu_system_sec: float
    total_cpu_sec: float
    overall_cpu_percent: float

    initial_rss_mb: float
    final_rss_mb: float
    net_rss_delta_mb: float
    peak_rss_mb: float

    initial_rss_bytes: int = 0
    final_rss_bytes: int = 0
    net_rss_delta_bytes: int = 0
    peak_rss_bytes: int = 0

    phases_count: int = 0
    successful_phases: int = 0
    failed_phases: int = 0

    phase_breakdown: list[PhaseMetrics] = field(default_factory=list)

    @property
    def phases(self) -> dict[str, PhaseMetrics]:
        return {p.stage_name: p for p in self.phase_breakdown}

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["phase_breakdown"] = [p.to_dict() if isinstance(p, PhaseMetrics) else p for p in self.phase_breakdown]
        d["phases"] = {p.stage_name: (p.to_dict() if isinstance(p, PhaseMetrics) else p) for p in self.phase_breakdown}
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def format_table(self, color: bool = True) -> str:
        tot_dur = self.total_duration_sec if self.total_duration_sec > 0 else 1.0
        lines = [
            "=" * 110,
            f" PIPELINE PROFILING REPORT — Run: {self.run_id or 'N/A'} | Channel: {self.channel or 'N/A'} | Story: {self.story_id or 'N/A'}",
            "=" * 110,
        ]
        lines.append(
            f" {'#':<3} {'Stage Name':<28} {'Duration (s)':>12} {'% Time':>8} {'CPU User':>10} {'CPU Sys':>10} {'CPU %':>8} {'RSS Δ (MB)':>11} {'Peak RSS':>10} {'Status':>7}"
        )
        lines.append("-" * 110)

        for idx, p in enumerate(self.phase_breakdown, 1):
            pct_time = (p.duration_sec / tot_dur) * 100.0 if tot_dur > 0 else 0.0
            status_str = "PASS" if p.success else "FAIL"
            lines.append(
                f" {idx:<3} {p.stage_name:<28} {p.duration_sec:>12.2f} {pct_time:>7.1f}% {p.cpu_user_sec:>10.2f} {p.cpu_system_sec:>10.2f} {p.cpu_percent:>7.1f}% {p.rss_delta_mb:>+11.1f} {p.peak_rss_mb:>10.1f} {status_str:>7}"
            )

        lines.append("-" * 110)
        status_tot = f"{self.successful_phases}/{self.phases_count} OK"
        lines.append(
            f" {'TOTAL':<32} {self.total_duration_sec:>12.2f} {'100.0%':>8} {self.total_cpu_user_sec:>10.2f} {self.total_cpu_system_sec:>10.2f} {self.overall_cpu_percent:>7.1f}% {self.net_rss_delta_mb:>+11.1f} {self.peak_rss_mb:>10.1f} {status_tot:>7}"
        )
        lines.append("=" * 110)
        return "\n".join(lines)


ProfilingReport = ProfilingSummary


class PhaseTimer(contextlib.AbstractContextManager[PhaseMetrics]):
    """Non-intrusive stage profiling context manager and decorator."""

    __slots__ = (
        "stage_name", "run_id", "story_id", "channel", "profiler",
        "metadata", "update_context", "enabled", "auto_emit", "db_path",
        "_metrics", "_t0", "_cpu0", "_start_rss_bytes", "_prev_stage",
    )

    def __init__(
        self,
        stage_name: str | CanonicalStage,
        run_id: str | None = None,
        story_id: str | None = None,
        channel: str | None = None,
        profiler: PipelineProfiler | None = None,
        metadata: dict[str, Any] | None = None,
        update_context: bool = True,
        enabled: bool | None = None,
        auto_emit: bool = False,
        db_path: str | None = None,
    ) -> None:
        is_en = is_profiling_enabled() if enabled is None else bool(enabled)
        self.enabled = is_en

        if not is_en:
            self.stage_name = stage_name.value if isinstance(stage_name, CanonicalStage) else str(stage_name or "")
            self.run_id, self.story_id, self.channel, self.profiler = run_id, story_id, channel, profiler
            self.metadata = metadata or {}
            self.update_context, self.auto_emit, self.db_path = False, False, db_path
            self._metrics, self._t0, self._cpu0, self._start_rss_bytes, self._prev_stage = None, 0.0, (0.0, 0.0, 0.0, 0.0), 0, None
            return

        self.stage_name = normalize_stage_name(stage_name)
        self.run_id, self.story_id, self.channel, self.profiler = run_id, story_id, channel, profiler
        self.metadata = metadata or {}
        self.update_context, self.auto_emit, self.db_path = update_context, auto_emit, db_path
        self._metrics = PhaseMetrics(
            stage_name=self.stage_name, run_id=run_id, story_id=story_id, channel=channel, metadata=self.metadata,
        )
        self._t0, self._cpu0, self._start_rss_bytes, self._prev_stage = 0.0, (0.0, 0.0, 0.0, 0.0), 0, None

    @property
    def metrics(self) -> PhaseMetrics | None:
        return self._metrics if self.enabled else None

    def __enter__(self) -> PhaseMetrics | None:
        if not self.enabled:
            return None
        try:
            self._metrics.started_at = _utc_now_iso()
            self._t0 = time.perf_counter()
            self._cpu0 = _get_cpu_times()
            self._start_rss_bytes = _read_vm_rss_bytes()
            self._metrics.start_rss_bytes = int(self._start_rss_bytes)
            self._metrics.start_rss_mb = round(self._start_rss_bytes / (1024 * 1024), 2)

            if self.update_context:
                try:
                    from src.observability.context import get_run_context, update_run_context
                    ctx = get_run_context()
                    self._prev_stage = ctx.stage
                    if not self.run_id and ctx.run_id:
                        self._metrics.run_id = ctx.run_id
                    if not self.story_id and ctx.story_id:
                        self._metrics.story_id = ctx.story_id
                    if not self.channel and ctx.channel:
                        self._metrics.channel = ctx.channel
                    update_run_context(stage=self.stage_name)
                except Exception:
                    pass
        except Exception as exc:
            logger.debug("PhaseTimer entry metric error on %s: %s", self.stage_name, exc)
        return self._metrics

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        if not self.enabled:
            return False
        try:
            t1 = time.perf_counter()
            cpu1 = _get_cpu_times()
            end_rss_bytes = _read_vm_rss_bytes()
            peak_rss_bytes = _get_peak_rss_bytes()
            delta_bytes = end_rss_bytes - self._start_rss_bytes
            duration = max(0.0, t1 - self._t0)

            self._metrics.duration_sec = round(duration, 4)
            self._metrics.completed_at = _utc_now_iso()

            u_delta = max(0.0, cpu1[0] - self._cpu0[0])
            s_delta = max(0.0, cpu1[1] - self._cpu0[1])
            cu_delta = max(0.0, cpu1[2] - self._cpu0[2])
            cs_delta = max(0.0, cpu1[3] - self._cpu0[3])

            self._metrics.cpu_user_sec = round(u_delta + cu_delta, 4)
            self._metrics.cpu_system_sec = round(s_delta + cs_delta, 4)
            self._metrics.cpu_children_user_sec = round(cu_delta, 4)
            self._metrics.cpu_children_system_sec = round(cs_delta, 4)
            self._metrics.cpu_total_sec = round(self._metrics.cpu_user_sec + self._metrics.cpu_system_sec, 4)
            self._metrics.cpu_percent = round((self._metrics.cpu_total_sec / duration * 100.0) if duration > 0 else 0.0, 1)

            self._metrics.start_rss_bytes = int(self._start_rss_bytes)
            self._metrics.end_rss_bytes = int(end_rss_bytes)
            self._metrics.rss_delta_bytes = int(delta_bytes)
            self._metrics.delta_rss_bytes = int(delta_bytes)
            self._metrics.peak_rss_bytes = int(peak_rss_bytes)
            self._metrics.start_rss_mb = round(self._start_rss_bytes / (1024 * 1024), 2)
            self._metrics.end_rss_mb = round(end_rss_bytes / (1024 * 1024), 2)
            self._metrics.rss_delta_mb = round(delta_bytes / (1024 * 1024), 2)
            self._metrics.peak_rss_mb = round(peak_rss_bytes / (1024 * 1024), 2)

            self._metrics.success = exc_type is None
            if exc_val is not None:
                self._metrics.error = str(exc_val)
                self._metrics.error_type = exc_type.__name__ if exc_type else "Error"
                self._metrics.error_message = str(exc_val)

            if self.profiler is not None:
                self.profiler.record_phase(self._metrics)

            if self.auto_emit:
                try:
                    from src.observability.events import emit_event
                    emit_event(
                        "STAGE_PROFILED",
                        level="INFO" if self._metrics.success else "WARNING",
                        message=f"Stage {self.stage_name} completed in {self._metrics.duration_sec:.2f}s",
                        details=self._metrics.to_dict(),
                        db_path=self.db_path,
                        run_id=self._metrics.run_id,
                        story_id=self._metrics.story_id,
                        channel=self._metrics.channel,
                        component="profiler",
                        stage=self.stage_name,
                    )
                except Exception as emit_err:
                    logger.debug("Failed to auto-emit phase telemetry: %s", emit_err)

            if self.update_context:
                try:
                    from src.observability.context import update_run_context
                    update_run_context(stage=self._prev_stage)
                except Exception:
                    pass
        except Exception as exc:
            logger.debug("PhaseTimer exit metric error on %s: %s", self.stage_name, exc)

        return False

    def __call__(self, func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with self:
                return func(*args, **kwargs)
        return wrapper  # type: ignore[return-value]


def profile_phase(
    stage_name: str | CanonicalStage,
    profiler: PipelineProfiler | None = None,
    metadata: dict[str, Any] | None = None,
    enabled: bool | None = None,
    auto_emit: bool = False,
) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            timer = PhaseTimer(
                stage_name=stage_name, profiler=profiler, metadata=metadata, enabled=enabled, auto_emit=auto_emit,
            )
            with timer:
                return func(*args, **kwargs)
        return wrapper  # type: ignore[return-value]
    return decorator


class PipelineProfiler:
    """Thread-safe collector and aggregator of phase metrics across a pipeline run."""

    def __init__(
        self,
        run_id: str | None = None,
        story_id: str | None = None,
        channel: str | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.run_id = run_id
        self.story_id = story_id
        self.channel = channel
        self.enabled = is_profiling_enabled() if enabled is None else enabled
        self._phases: list[PhaseMetrics] = []
        self._lock = threading.Lock()
        self._started_at = _utc_now_iso()
        self._t0 = time.perf_counter()
        self._initial_rss_bytes = _read_vm_rss_bytes()

    def phase(
        self,
        stage_name: str | CanonicalStage,
        metadata: dict[str, Any] | None = None,
        update_context: bool = True,
        auto_emit: bool = False,
    ) -> PhaseTimer:
        return PhaseTimer(
            stage_name=stage_name,
            run_id=self.run_id,
            story_id=self.story_id,
            channel=self.channel,
            profiler=self,
            metadata=metadata,
            update_context=update_context,
            enabled=self.enabled,
            auto_emit=auto_emit,
        )

    def record_phase(self, metrics: PhaseMetrics) -> None:
        with self._lock:
            if not self.run_id and metrics.run_id:
                self.run_id = metrics.run_id
            if not self.story_id and metrics.story_id:
                self.story_id = metrics.story_id
            if not self.channel and metrics.channel:
                self.channel = metrics.channel
            self._phases.append(metrics)

    def record_error(
        self,
        error_detail: str,
        error_type: str | None = None,
        stage: str | CanonicalStage | None = None,
    ) -> None:
        with self._lock:
            if not self._phases:
                stage_name = normalize_stage_name(stage or CanonicalStage.CLAIM_LEASE)
                m = PhaseMetrics(
                    stage_name=stage_name,
                    run_id=self.run_id,
                    story_id=self.story_id,
                    channel=self.channel,
                    success=False,
                    error=error_detail,
                    error_type=error_type or "PipelineError",
                    error_message=error_detail,
                )
                self._phases.append(m)
            elif not any(not p.success for p in self._phases):
                last = self._phases[-1]
                last.success = False
                last.error = error_detail
                last.error_type = error_type or "PipelineError"
                last.error_message = error_detail

    def get_phase(self, stage_name: str | CanonicalStage) -> PhaseMetrics | None:
        target = normalize_stage_name(stage_name)
        with self._lock:
            for p in self._phases:
                if (
                    p.stage_name == target
                    or normalize_stage_name(p.stage_name) == target
                    or str(stage_name).lower() in p.stage_name.lower()
                ):
                    return p
        return None

    def get_phases(self) -> list[PhaseMetrics]:
        with self._lock:
            return list(self._phases)

    def get_summary(self) -> ProfilingSummary:
        with self._lock:
            phases = list(self._phases)

        completed_at = _utc_now_iso()
        total_duration = sum(p.duration_sec for p in phases)
        total_user_cpu = sum(p.cpu_user_sec for p in phases)
        total_sys_cpu = sum(p.cpu_system_sec for p in phases)
        total_cpu = total_user_cpu + total_sys_cpu
        overall_cpu_pct = round((total_cpu / total_duration * 100.0) if total_duration > 0 else 0.0, 1)

        initial_rss_bytes = int(self._initial_rss_bytes)
        initial_rss_mb = round(initial_rss_bytes / (1024 * 1024), 2)
        final_rss_bytes = int(_read_vm_rss_bytes())
        final_rss_mb = round(final_rss_bytes / (1024 * 1024), 2)
        net_rss_delta_bytes = final_rss_bytes - initial_rss_bytes
        net_rss_delta_mb = round(net_rss_delta_bytes / (1024 * 1024), 2)
        peak_rss_bytes = max([p.peak_rss_bytes for p in phases], default=_get_peak_rss_bytes())
        peak_rss_mb = max([p.peak_rss_mb for p in phases], default=round(peak_rss_bytes / (1024 * 1024), 2))

        return ProfilingSummary(
            run_id=self.run_id,
            story_id=self.story_id,
            channel=self.channel,
            total_duration_sec=round(total_duration, 4),
            started_at=self._started_at,
            completed_at=completed_at,
            total_cpu_user_sec=round(total_user_cpu, 4),
            total_cpu_system_sec=round(total_sys_cpu, 4),
            total_cpu_sec=round(total_cpu, 4),
            overall_cpu_percent=overall_cpu_pct,
            initial_rss_mb=initial_rss_mb,
            final_rss_mb=final_rss_mb,
            net_rss_delta_mb=net_rss_delta_mb,
            peak_rss_mb=peak_rss_mb,
            initial_rss_bytes=initial_rss_bytes,
            final_rss_bytes=final_rss_bytes,
            net_rss_delta_bytes=net_rss_delta_bytes,
            peak_rss_bytes=peak_rss_bytes,
            phases_count=len(phases),
            successful_phases=sum(1 for p in phases if p.success),
            failed_phases=sum(1 for p in phases if not p.success),
            phase_breakdown=phases,
        )

    def format_table(self, color: bool = True) -> str:
        return self.get_summary().format_table(color=color)

    def to_dict(self) -> dict[str, Any]:
        return self.get_summary().to_dict()

    def to_json(self, path: str | Path | None = None, indent: int = 2) -> str:
        data = self.to_dict()
        out = json.dumps(data, indent=indent, ensure_ascii=False)
        if path:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(out, encoding="utf-8")
        return out

    def emit_telemetry(
        self,
        db_path: str | None = None,
        record_in_production_metrics: bool = True,
    ) -> bool:
        if not self.enabled:
            return True

        summary = self.get_summary()
        payload = summary.to_dict()

        try:
            from src.observability.events import emit_event
            emit_event(
                "PIPELINE_PROFILED",
                level="INFO" if summary.failed_phases == 0 else "WARNING",
                message=f"Pipeline run {self.run_id or 'N/A'} completed in {summary.total_duration_sec:.2f}s across {summary.phases_count} stages",
                details=payload,
                db_path=db_path,
                run_id=self.run_id,
                story_id=self.story_id,
                channel=self.channel,
                component="profiler",
            )
        except Exception as exc:
            logger.debug("Failed to emit PIPELINE_PROFILED event: %s", exc)

        if record_in_production_metrics and self.run_id and self.story_id:
            try:
                from src.config import DEFAULT_DB_PATH
                from src.core.repository import QueueRepository

                tts_phase = self.get_phase(CanonicalStage.TTS_SYNTHESIS)
                render_phase = self.get_phase(CanonicalStage.VIDEO_RENDERING)

                tts_sec = tts_phase.duration_sec if tts_phase else None
                render_sec = render_phase.duration_sec if render_phase else summary.total_duration_sec

                repo = QueueRepository(db_path or str(DEFAULT_DB_PATH))
                repo.record_production_metrics(
                    run_id=self.run_id,
                    story_id=self.story_id,
                    audio_duration_sec=0.0,
                    render_time_sec=render_sec,
                    tts_time_sec=tts_sec,
                    video_size_bytes=0,
                    qa_audit_passed=(summary.failed_phases == 0),
                )
            except Exception as exc:
                logger.debug("Failed to record production_metrics in profiler: %s", exc)

        return True
