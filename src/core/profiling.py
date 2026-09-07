"""Diagnostics, Profiling & Telemetry framework (Requirement R1).

Provides non-intrusive, zero-overhead, stdlib-only profiling of wall-clock time,
CPU times (in-process and reaped children), and resident memory (RSS) footprints
across all 13 canonical production stages of the audiovisual pipeline.
"""

from __future__ import annotations

import contextlib
import functools
import json
import logging
import os
import resource
import threading
import time
from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, TypeVar

logger = logging.getLogger("profiling")

F = TypeVar("F", bound=Callable[..., Any])


# ---------------------------------------------------------------------------
# 1. Canonical Stage Registry
# ---------------------------------------------------------------------------


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
        """1-based canonical index (1..13)."""
        try:
            return int(self.value.split("_")[0])
        except (ValueError, IndexError):
            return 0

    @property
    def display_name(self) -> str:
        """Human-readable display name for logs and dashboards."""
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
        """Resolve a stage name, number, or alias to CanonicalStage."""
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
    "1": CanonicalStage.CLAIM_LEASE,
    "claim": CanonicalStage.CLAIM_LEASE,
    "claim_lease": CanonicalStage.CLAIM_LEASE,
    "1_claim_lease": CanonicalStage.CLAIM_LEASE,
    "leases": CanonicalStage.CLAIM_LEASE,

    "2": CanonicalStage.INGEST_TRANSLATE,
    "ingest": CanonicalStage.INGEST_TRANSLATE,
    "content_ingest": CanonicalStage.INGEST_TRANSLATE,
    "2_ingest_translate": CanonicalStage.INGEST_TRANSLATE,
    "translate": CanonicalStage.INGEST_TRANSLATE,

    "3": CanonicalStage.EDITORIAL_BARRIER,
    "editorial": CanonicalStage.EDITORIAL_BARRIER,
    "sanitization": CanonicalStage.EDITORIAL_BARRIER,
    "sanitization_barrier": CanonicalStage.EDITORIAL_BARRIER,
    "3_editorial_barrier": CanonicalStage.EDITORIAL_BARRIER,
    "editorial_barrier": CanonicalStage.EDITORIAL_BARRIER,

    "4": CanonicalStage.MOOD_THEME,
    "mood": CanonicalStage.MOOD_THEME,
    "theme": CanonicalStage.MOOD_THEME,
    "mood_theme": CanonicalStage.MOOD_THEME,
    "mood_theme_resolution": CanonicalStage.MOOD_THEME,
    "4_mood_theme": CanonicalStage.MOOD_THEME,

    "5": CanonicalStage.TTS_SYNTHESIS,
    "tts": CanonicalStage.TTS_SYNTHESIS,
    "tts_synthesis": CanonicalStage.TTS_SYNTHESIS,
    "5_tts_synthesis": CanonicalStage.TTS_SYNTHESIS,
    "speech": CanonicalStage.TTS_SYNTHESIS,

    "6": CanonicalStage.DURATION_ALIGNMENT,
    "duration": CanonicalStage.DURATION_ALIGNMENT,
    "duration_alignment": CanonicalStage.DURATION_ALIGNMENT,
    "6_duration_alignment": CanonicalStage.DURATION_ALIGNMENT,
    "alignment": CanonicalStage.DURATION_ALIGNMENT,

    "7": CanonicalStage.SUBTITLE_GENERATION,
    "subtitles": CanonicalStage.SUBTITLE_GENERATION,
    "subtitle_generation": CanonicalStage.SUBTITLE_GENERATION,
    "7_subtitle_generation": CanonicalStage.SUBTITLE_GENERATION,

    "8": CanonicalStage.LOOP_SCENE,
    "scene": CanonicalStage.LOOP_SCENE,
    "loop": CanonicalStage.LOOP_SCENE,
    "loop_scene": CanonicalStage.LOOP_SCENE,
    "scene_resolution": CanonicalStage.LOOP_SCENE,
    "8_loop_scene": CanonicalStage.LOOP_SCENE,

    "9": CanonicalStage.VIDEO_RENDERING,
    "render": CanonicalStage.VIDEO_RENDERING,
    "rendering": CanonicalStage.VIDEO_RENDERING,
    "video_rendering": CanonicalStage.VIDEO_RENDERING,
    "9_video_rendering": CanonicalStage.VIDEO_RENDERING,
    "compositor": CanonicalStage.VIDEO_RENDERING,

    "10": CanonicalStage.QA_GATING,
    "qa": CanonicalStage.QA_GATING,
    "qa_gating": CanonicalStage.QA_GATING,
    "automated_qa": CanonicalStage.QA_GATING,
    "10_qa_gating": CanonicalStage.QA_GATING,

    "11": CanonicalStage.THUMBNAIL_METADATA,
    "thumbnail": CanonicalStage.THUMBNAIL_METADATA,
    "metadata": CanonicalStage.THUMBNAIL_METADATA,
    "thumbnail_metadata": CanonicalStage.THUMBNAIL_METADATA,
    "11_thumbnail_metadata": CanonicalStage.THUMBNAIL_METADATA,

    "12": CanonicalStage.DEDUP_SIMHASH,
    "dedup": CanonicalStage.DEDUP_SIMHASH,
    "simhash": CanonicalStage.DEDUP_SIMHASH,
    "simhash_deduplication": CanonicalStage.DEDUP_SIMHASH,
    "12_dedup_simhash": CanonicalStage.DEDUP_SIMHASH,

    "13": CanonicalStage.BACKUP_PUBLISH,
    "backup": CanonicalStage.BACKUP_PUBLISH,
    "publish": CanonicalStage.BACKUP_PUBLISH,
    "publication": CanonicalStage.BACKUP_PUBLISH,
    "backup_publication": CanonicalStage.BACKUP_PUBLISH,
    "publication_backup": CanonicalStage.BACKUP_PUBLISH,
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


_PROFILING_ENABLED_CACHED: bool = True
_PROFILING_ENV_SNAPSHOT: str | None = "__UNSET__"


def is_profiling_enabled() -> bool:
    """Check if profiling is enabled via environment variable (default: True). Fast cached."""
    global _PROFILING_ENABLED_CACHED, _PROFILING_ENV_SNAPSHOT
    env_val = os.environ.get("YT_PROFILING")
    if env_val is not _PROFILING_ENV_SNAPSHOT:
        _PROFILING_ENV_SNAPSHOT = env_val
        if env_val is None:
            _PROFILING_ENABLED_CACHED = True
        else:
            val = env_val.strip().lower()
            _PROFILING_ENABLED_CACHED = val not in ("0", "false", "no", "off")
    return _PROFILING_ENABLED_CACHED


# ---------------------------------------------------------------------------
# 2. Low-Level Resource Samplers
# ---------------------------------------------------------------------------


def _utc_now_iso() -> str:
    """Current UTC ISO-8601 timestamp with millisecond precision."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _read_vm_rss_bytes() -> int:
    """Read current process VmRSS in bytes from /proc/self/status (or fallback)."""
    try:
        if os.path.exists("/proc/self/status"):
            with open("/proc/self/status", encoding="ascii") as handle:
                for line in handle:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) * 1024
    except Exception:
        pass
    try:
        ru = resource.getrusage(resource.RUSAGE_SELF)
        multiplier = 1024 if os.name == "posix" and not (hasattr(os, "uname") and os.uname().sysname.lower().startswith("darwin")) else 1
        return int(ru.ru_maxrss * multiplier)
    except Exception:
        return 0


def _get_peak_rss_bytes() -> int:
    """Return process + child peak RSS in bytes via /proc/self/status or getrusage."""
    try:
        if os.path.exists("/proc/self/status"):
            with open("/proc/self/status", encoding="ascii") as handle:
                for line in handle:
                    if line.startswith("VmHWM:"):
                        return int(line.split()[1]) * 1024
    except Exception:
        pass
    try:
        ru_self = resource.getrusage(resource.RUSAGE_SELF)
        ru_children = resource.getrusage(resource.RUSAGE_CHILDREN)
        multiplier = 1024 if os.name == "posix" and not (hasattr(os, "uname") and os.uname().sysname.lower().startswith("darwin")) else 1
        self_peak = int(ru_self.ru_maxrss * multiplier)
        child_peak = int(ru_children.ru_maxrss * multiplier)
        return max(self_peak, child_peak)
    except Exception:
        return 0


def _get_cpu_times() -> tuple[float, float, float, float]:
    """Return (user, system, children_user, children_system) in seconds."""
    try:
        t = os.times()
        return (t.user, t.system, t.children_user, t.children_system)
    except Exception:
        return (0.0, 0.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# 3. Data Models: PhaseMetrics and ProfilingSummary
# ---------------------------------------------------------------------------


@dataclass
class PhaseMetrics(Mapping[str, Any]):
    """Detailed telemetry record for a single pipeline stage execution.

    Implements the Mapping protocol for transparent dict unpacking, indexing,
    and iteration, while allowing direct attribute access.
    """

    stage_name: str = ""
    run_id: str | None = None
    story_id: str | None = None
    channel: str | None = None

    # Timing (Wall-Clock)
    duration_sec: float = 0.0
    started_at: str = ""
    completed_at: str = ""

    # CPU Usage (in seconds)
    cpu_user_sec: float = 0.0           # Current process user CPU
    cpu_system_sec: float = 0.0         # Current process system CPU
    cpu_children_user_sec: float = 0.0  # Subprocesses user CPU (ffmpeg, playwright)
    cpu_children_system_sec: float = 0.0  # Subprocesses sys CPU
    cpu_total_sec: float = 0.0          # Sum of user + system + child user + child sys
    cpu_percent: float = 0.0            # (cpu_total_sec / duration_sec) * 100

    # Memory Usage (in Megabytes and Bytes)
    start_rss_mb: float = 0.0           # Resident memory at stage entry (MB)
    end_rss_mb: float = 0.0             # Resident memory at stage exit (MB)
    rss_delta_mb: float = 0.0           # end_rss_mb - start_rss_mb
    peak_rss_mb: float = 0.0            # Peak RSS observed at exit (MB)

    # Legacy / bytes aliases
    start_rss_bytes: int = 0
    end_rss_bytes: int = 0
    rss_delta_bytes: int = 0
    delta_rss_bytes: int = 0
    peak_rss_bytes: int = 0

    # Outcome & Diagnostics
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

        # Synchronize start RSS
        if start_rss_bytes:
            self.start_rss_bytes = int(start_rss_bytes)
            self.start_rss_mb = float(start_rss_mb or round(start_rss_bytes / (1024 * 1024), 2))
        elif start_rss_mb:
            self.start_rss_mb = float(start_rss_mb)
            self.start_rss_bytes = int(round(start_rss_mb * 1024 * 1024))
        else:
            self.start_rss_bytes = 0
            self.start_rss_mb = 0.0

        # Synchronize end RSS
        if end_rss_bytes:
            self.end_rss_bytes = int(end_rss_bytes)
            self.end_rss_mb = float(end_rss_mb or round(end_rss_bytes / (1024 * 1024), 2))
        elif end_rss_mb:
            self.end_rss_mb = float(end_rss_mb)
            self.end_rss_bytes = int(round(end_rss_mb * 1024 * 1024))
        else:
            self.end_rss_bytes = 0
            self.end_rss_mb = 0.0

        # Synchronize delta RSS
        raw_delta_b = rss_delta_bytes or delta_rss_bytes
        if raw_delta_b:
            self.rss_delta_bytes = int(raw_delta_b)
            self.delta_rss_bytes = int(raw_delta_b)
            self.rss_delta_mb = float(rss_delta_mb or round(raw_delta_b / (1024 * 1024), 2))
        elif rss_delta_mb:
            self.rss_delta_mb = float(rss_delta_mb)
            self.rss_delta_bytes = int(round(rss_delta_mb * 1024 * 1024))
            self.delta_rss_bytes = self.rss_delta_bytes
        else:
            self.rss_delta_bytes = 0
            self.delta_rss_bytes = 0
            self.rss_delta_mb = 0.0

        # Synchronize peak RSS
        if peak_rss_bytes:
            self.peak_rss_bytes = int(peak_rss_bytes)
            self.peak_rss_mb = float(peak_rss_mb or round(peak_rss_bytes / (1024 * 1024), 2))
        elif peak_rss_mb:
            self.peak_rss_mb = float(peak_rss_mb)
            self.peak_rss_bytes = int(round(peak_rss_mb * 1024 * 1024))
        else:
            self.peak_rss_bytes = 0
            self.peak_rss_mb = 0.0

        self.success = bool(success)
        self.error = error or error_message
        self.error_type = error_type or (error.split(":")[0] if error and ":" in error else ("Error" if error else None))
        self.error_message = error_message or self.error
        self.metadata = metadata or {}

    @property
    def stage(self) -> str:
        return self.stage_name

    # --- Mapping Interface Implementation ---

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
        """Convert PhaseMetrics to a plain JSON-serializable dictionary."""
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

    # Timing Totals
    total_duration_sec: float
    started_at: str
    completed_at: str

    # CPU Totals
    total_cpu_user_sec: float
    total_cpu_system_sec: float
    total_cpu_sec: float
    overall_cpu_percent: float

    # Memory Totals (in MB)
    initial_rss_mb: float
    final_rss_mb: float
    net_rss_delta_mb: float
    peak_rss_mb: float

    # Memory Totals (in Bytes)
    initial_rss_bytes: int = 0
    final_rss_bytes: int = 0
    net_rss_delta_bytes: int = 0
    peak_rss_bytes: int = 0

    # Execution Stats
    phases_count: int = 0
    successful_phases: int = 0
    failed_phases: int = 0

    # Granular Breakdown
    phase_breakdown: list[PhaseMetrics] = field(default_factory=list)

    @property
    def phases(self) -> dict[str, PhaseMetrics]:
        """Dictionary of stage_name -> PhaseMetrics for easy inspection."""
        return {p.stage_name: p for p in self.phase_breakdown}

    def to_dict(self) -> dict[str, Any]:
        """Convert summary and breakdown to dictionary."""
        d = asdict(self)
        d["phase_breakdown"] = [
            p.to_dict() if isinstance(p, PhaseMetrics) else p for p in self.phase_breakdown
        ]
        d["phases"] = {p.stage_name: (p.to_dict() if isinstance(p, PhaseMetrics) else p) for p in self.phase_breakdown}
        return d

    def to_json(self, indent: int = 2) -> str:
        """Serialize summary to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def format_table(self, color: bool = True) -> str:
        """Render a formatted ASCII table breakdown of all phases."""
        tot_dur = self.total_duration_sec if self.total_duration_sec > 0 else 1.0

        lines: list[str] = []
        sep = "=" * 110
        thin_sep = "-" * 110

        header = f" PIPELINE PROFILING REPORT — Run: {self.run_id or 'N/A'} | Channel: {self.channel or 'N/A'} | Story: {self.story_id or 'N/A'}"
        lines.append(sep)
        lines.append(header)
        lines.append(sep)
        lines.append(
            f" {'#':<3} {'Stage Name':<28} {'Duration (s)':>12} {'% Time':>8} {'CPU User':>10} {'CPU Sys':>10} {'CPU %':>8} {'RSS Δ (MB)':>11} {'Peak RSS':>10} {'Status':>7}"
        )
        lines.append(thin_sep)

        for idx, p in enumerate(self.phase_breakdown, 1):
            pct_time = (p.duration_sec / tot_dur) * 100.0 if tot_dur > 0 else 0.0
            status_str = "PASS" if p.success else "FAIL"
            delta_str = f"{p.rss_delta_mb:+.1f}"
            lines.append(
                f" {idx:<3} {p.stage_name:<28} {p.duration_sec:>12.2f} {pct_time:>7.1f}% {p.cpu_user_sec:>10.2f} {p.cpu_system_sec:>10.2f} {p.cpu_percent:>7.1f}% {delta_str:>11} {p.peak_rss_mb:>10.1f} {status_str:>7}"
            )

        lines.append(thin_sep)
        tot_delta_str = f"{self.net_rss_delta_mb:+.1f}"
        status_tot = f"{self.successful_phases}/{self.phases_count} OK"
        lines.append(
            f" {'TOTAL':<32} {self.total_duration_sec:>12.2f} {'100.0%':>8} {self.total_cpu_user_sec:>10.2f} {self.total_cpu_system_sec:>10.2f} {self.overall_cpu_percent:>7.1f}% {tot_delta_str:>11} {self.peak_rss_mb:>10.1f} {status_tot:>7}"
        )
        lines.append(sep)
        return "\n".join(lines)


# Backward compatibility alias
ProfilingReport = ProfilingSummary


# ---------------------------------------------------------------------------
# 4. PhaseTimer Context Manager & Decorator
# ---------------------------------------------------------------------------


class PhaseTimer(contextlib.AbstractContextManager[PhaseMetrics]):
    """Non-intrusive stage profiling context manager and decorator.

    Measures:
    1. High-resolution wall-clock time via time.perf_counter()
    2. CPU user and system times (in-process + reaped subprocesses) via os.times()
    3. Resident Set Size (RSS) delta and peak RSS via /proc/self/status and getrusage()

    Guarantees:
    - Zero/negligible overhead when disabled (< 50 ns).
    - Never raises exceptions from internal metric gathering failures.
    - Automatically updates and restores observability RunContext.stage.
    - Yields PhaseMetrics with full dict protocol support.
    - Never suppresses exceptions raised in the wrapped block.
    """

    __slots__ = (
        "stage_name",
        "run_id",
        "story_id",
        "channel",
        "profiler",
        "metadata",
        "update_context",
        "enabled",
        "auto_emit",
        "db_path",
        "_metrics",
        "_t0",
        "_cpu0",
        "_start_rss_bytes",
        "_prev_stage",
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
            self.stage_name = (
                stage_name.value
                if isinstance(stage_name, CanonicalStage)
                else str(stage_name or "")
            )
            self.run_id = run_id
            self.story_id = story_id
            self.channel = channel
            self.profiler = profiler
            self.metadata = metadata or {}
            self.update_context = False
            self.auto_emit = False
            self.db_path = db_path
            self._metrics = None
            self._t0 = 0.0
            self._cpu0 = (0.0, 0.0, 0.0, 0.0)
            self._start_rss_bytes = 0
            self._prev_stage = None
            return

        self.stage_name = normalize_stage_name(stage_name)
        self.run_id = run_id
        self.story_id = story_id
        self.channel = channel
        self.profiler = profiler
        self.metadata = metadata or {}
        self.update_context = update_context
        self.auto_emit = auto_emit
        self.db_path = db_path

        # Metrics object lazily allocated only when profiling is enabled
        self._metrics = PhaseMetrics(
            stage_name=self.stage_name,
            run_id=run_id,
            story_id=story_id,
            channel=channel,
            metadata=self.metadata,
        )
        self._t0 = 0.0
        self._cpu0 = (0.0, 0.0, 0.0, 0.0)
        self._start_rss_bytes = 0
        self._prev_stage = None

    @property
    def metrics(self) -> PhaseMetrics | None:
        """Return captured metrics if enabled, or None if disabled."""
        if not self.enabled:
            return None
        return self._metrics

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

            # Wall clock duration
            duration = max(0.0, t1 - self._t0)
            self._metrics.duration_sec = round(duration, 4)
            self._metrics.completed_at = _utc_now_iso()

            # CPU times delta (process + children)
            u_delta = max(0.0, cpu1[0] - self._cpu0[0])
            s_delta = max(0.0, cpu1[1] - self._cpu0[1])
            cu_delta = max(0.0, cpu1[2] - self._cpu0[2])
            cs_delta = max(0.0, cpu1[3] - self._cpu0[3])

            self._metrics.cpu_user_sec = round(u_delta + cu_delta, 4)
            self._metrics.cpu_system_sec = round(s_delta + cs_delta, 4)
            self._metrics.cpu_children_user_sec = round(cu_delta, 4)
            self._metrics.cpu_children_system_sec = round(cs_delta, 4)
            self._metrics.cpu_total_sec = round(
                self._metrics.cpu_user_sec + self._metrics.cpu_system_sec, 4
            )
            self._metrics.cpu_percent = round(
                (self._metrics.cpu_total_sec / duration * 100.0) if duration > 0 else 0.0, 1
            )

            # Resident memory (synchronized MB and Bytes)
            self._metrics.start_rss_bytes = int(self._start_rss_bytes)
            self._metrics.end_rss_bytes = int(end_rss_bytes)
            self._metrics.rss_delta_bytes = int(delta_bytes)
            self._metrics.delta_rss_bytes = int(delta_bytes)
            self._metrics.peak_rss_bytes = int(peak_rss_bytes)

            self._metrics.start_rss_mb = round(self._start_rss_bytes / (1024 * 1024), 2)
            self._metrics.end_rss_mb = round(end_rss_bytes / (1024 * 1024), 2)
            self._metrics.rss_delta_mb = round(delta_bytes / (1024 * 1024), 2)
            self._metrics.peak_rss_mb = round(peak_rss_bytes / (1024 * 1024), 2)

            # Success / failure outcome
            self._metrics.success = exc_type is None
            if exc_val is not None:
                self._metrics.error = str(exc_val)
                self._metrics.error_type = exc_type.__name__ if exc_type else "Error"
                self._metrics.error_message = str(exc_val)

            # Register with profiler if attached
            if self.profiler is not None:
                self.profiler.record_phase(self._metrics)

            # Emit structured telemetry event if auto_emit requested
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

            # Restore previous observability RunContext stage
            if self.update_context:
                try:
                    from src.observability.context import update_run_context

                    update_run_context(stage=self._prev_stage)
                except Exception:
                    pass
        except Exception as exc:
            logger.debug("PhaseTimer exit metric error on %s: %s", self.stage_name, exc)

        return False  # Never suppress exceptions from the wrapped block

    def __call__(self, func: F) -> F:
        """Allow PhaseTimer to be used directly as a decorator."""
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
    """Decorator factory to profile a function execution under a specific stage name."""
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            timer = PhaseTimer(
                stage_name=stage_name,
                profiler=profiler,
                metadata=metadata,
                enabled=enabled,
                auto_emit=auto_emit,
            )
            with timer:
                return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


# ---------------------------------------------------------------------------
# 5. PipelineProfiler Collector & Aggregator
# ---------------------------------------------------------------------------


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
        """Context manager factory linked to this profiler instance."""
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
        """Record completed phase metrics thread-safely."""
        with self._lock:
            # Sync correlation fields if not set on profiler
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
        """Record an unhandled pipeline error if no failing phase has been captured."""
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
                # Mark the last recorded phase as failed with this error
                last = self._phases[-1]
                last.success = False
                last.error = error_detail
                last.error_type = error_type or "PipelineError"
                last.error_message = error_detail

    def get_phase(self, stage_name: str | CanonicalStage) -> PhaseMetrics | None:
        """Lookup first matching stage metrics by exact name, canonical value, or alias."""
        target = normalize_stage_name(stage_name)
        with self._lock:
            for p in self._phases:
                if p.stage_name == target or normalize_stage_name(p.stage_name) == target:
                    return p
                # Also allow substring match if exact not found
                if str(stage_name).lower() in p.stage_name.lower():
                    return p
        return None

    def get_phases(self) -> list[PhaseMetrics]:
        """Return a shallow copy of all recorded phases."""
        with self._lock:
            return list(self._phases)

    def get_summary(self) -> ProfilingSummary:
        """Compute holistic pipeline profiling statistics."""
        with self._lock:
            phases = list(self._phases)

        completed_at = _utc_now_iso()
        total_duration = sum(p.duration_sec for p in phases)
        total_user_cpu = sum(p.cpu_user_sec for p in phases)
        total_sys_cpu = sum(p.cpu_system_sec for p in phases)
        total_cpu = total_user_cpu + total_sys_cpu
        overall_cpu_pct = round(
            (total_cpu / total_duration * 100.0) if total_duration > 0 else 0.0, 1
        )

        initial_rss_bytes = int(self._initial_rss_bytes)
        initial_rss_mb = round(initial_rss_bytes / (1024 * 1024), 2)
        final_rss_bytes = int(_read_vm_rss_bytes())
        final_rss_mb = round(final_rss_bytes / (1024 * 1024), 2)
        net_rss_delta_bytes = final_rss_bytes - initial_rss_bytes
        net_rss_delta_mb = round(net_rss_delta_bytes / (1024 * 1024), 2)
        peak_rss_bytes = max(
            [p.peak_rss_bytes for p in phases],
            default=_get_peak_rss_bytes(),
        )
        peak_rss_mb = max(
            [p.peak_rss_mb for p in phases],
            default=round(peak_rss_bytes / (1024 * 1024), 2),
        )

        success_count = sum(1 for p in phases if p.success)
        failed_count = sum(1 for p in phases if not p.success)

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
            successful_phases=success_count,
            failed_phases=failed_count,
            phase_breakdown=phases,
        )

    def format_table(self, color: bool = True) -> str:
        """Render a formatted ASCII table breakdown of all phases."""
        return self.get_summary().format_table(color=color)

    def to_dict(self) -> dict[str, Any]:
        """Convert full profiler state to dictionary."""
        return self.get_summary().to_dict()

    def to_json(self, path: str | Path | None = None, indent: int = 2) -> str:
        """Serialize profiler summary to JSON string and optionally save to file."""
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
        """Persist structured profiling telemetry into SQLite WAL and events.jsonl.

        Guarantees:
        - Emits PIPELINE_PROFILED event to system_events and events.jsonl.
        - Populates production_metrics without breaking on database lock or missing schema.
        - Never raises exceptions.
        """
        if not self.enabled:
            return True

        summary = self.get_summary()
        payload = summary.to_dict()

        # 1. Emit structured observability event
        try:
            from src.observability.events import emit_event

            emit_event(
                "PIPELINE_PROFILED",
                level="INFO" if summary.failed_phases == 0 else "WARNING",
                message=(
                    f"Pipeline run {self.run_id or 'N/A'} completed in "
                    f"{summary.total_duration_sec:.2f}s across {summary.phases_count} stages"
                ),
                details=payload,
                db_path=db_path,
                run_id=self.run_id,
                story_id=self.story_id,
                channel=self.channel,
                component="profiler",
            )
        except Exception as exc:
            logger.debug("Failed to emit PIPELINE_PROFILED event: %s", exc)

        # 2. Update production_metrics table if requested and IDs are present
        if record_in_production_metrics and self.run_id and self.story_id:
            try:
                from src.config import DEFAULT_DB_PATH
                from src.core.repository import QueueRepository

                tts_phase = self.get_phase(CanonicalStage.TTS_SYNTHESIS)
                render_phase = self.get_phase(CanonicalStage.VIDEO_RENDERING)

                tts_sec = tts_phase.duration_sec if tts_phase else None
                render_sec = (
                    render_phase.duration_sec if render_phase else summary.total_duration_sec
                )

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


# ---------------------------------------------------------------------------
# 6. Standalone Benchmarking Harness
# ---------------------------------------------------------------------------


def run_benchmark_cycle(
    channel: str = "moku",
    lane_id: str | None = None,
    iterations: int = 1,
    mock_mode: bool = True,
    mock: bool | None = None,
    stages: list[str] | None = None,
    db_path: str | None = None,
) -> list[ProfilingSummary] | ProfilingSummary:
    """Run benchmark cycles measuring latency, CPU, and RSS per stage.

    In mock mode (default), simulates realistic production workloads across all
    13 canonical stages without external API calls or GPU rendering costs.
    In real mode (mock_mode=False), delegates to run_pipeline_once.
    """
    if mock is not None:
        mock_mode = mock

    summaries: list[ProfilingSummary] = []
    target_stages = [normalize_stage_name(s) for s in stages] if stages else None

    for i in range(1, max(1, iterations) + 1):
        run_id = f"bench_run_{i:03d}_{int(time.time())}"
        story_id = f"bench_story_{i:03d}"
        profiler = PipelineProfiler(run_id=run_id, story_id=story_id, channel=channel)

        if mock_mode:
            # Simulate each of the 13 canonical production stages
            for stage in CANONICAL_STAGES:
                stage_str = stage.value
                if target_stages and stage_str not in target_stages:
                    continue

                with profiler.phase(stage):
                    if stage == CanonicalStage.CLAIM_LEASE:
                        time.sleep(0.005)
                    elif stage == CanonicalStage.INGEST_TRANSLATE:
                        # Simulate JSON/text curation
                        _ = [hash(f"story_word_{k}") for k in range(10_000)]
                        time.sleep(0.01)
                    elif stage == CanonicalStage.EDITORIAL_BARRIER:
                        # Simulate regex text compliance passes
                        text = "Sample horror story text for compliance checking " * 20
                        _ = [text.replace("horror", "misterio") for _ in range(500)]
                        time.sleep(0.005)
                    elif stage == CanonicalStage.MOOD_THEME:
                        time.sleep(0.005)
                    elif stage == CanonicalStage.TTS_SYNTHESIS:
                        # Simulate audio synthesis computation
                        _ = [sum(k * 0.5 for k in range(20_000))]
                        time.sleep(0.02)
                    elif stage == CanonicalStage.DURATION_ALIGNMENT:
                        time.sleep(0.005)
                    elif stage == CanonicalStage.SUBTITLE_GENERATION:
                        # Subtitle formatting
                        _ = [f"00:00:{s:02d},000 --> 00:00:{s+1:02d},000\nWord {s}" for s in range(50)]
                        time.sleep(0.005)
                    elif stage == CanonicalStage.LOOP_SCENE:
                        time.sleep(0.005)
                    elif stage == CanonicalStage.VIDEO_RENDERING:
                        # Post-#57: lavfi/stream-copy hot path — keep mock light (was 2MiB+30ms inflate).
                        _ = hash(b"lavfi_stream_copy_stub")
                        time.sleep(0.008)
                    elif stage == CanonicalStage.QA_GATING:
                        time.sleep(0.005)
                    elif stage == CanonicalStage.THUMBNAIL_METADATA:
                        # Simulate thumbnail image drawing
                        time.sleep(0.01)
                    elif stage == CanonicalStage.DEDUP_SIMHASH:
                        # Compute SimHash / SHA-256
                        _ = [hash(f"hash_sample_{k}") for k in range(5_000)]
                        time.sleep(0.005)
                    elif stage == CanonicalStage.BACKUP_PUBLISH:
                        time.sleep(0.005)

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
                # Reconstruct summary
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
