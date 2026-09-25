"""Contracts and configurations governing autonomous multi-lane daemon orchestration."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Optional, Set, TypedDict

from src.core.concurrency import (
    FFMPEG_ENCODE_MAX_THREADS,
    FFMPEG_PROBE_THREADS,
    RESOURCE_CPU_CEILING_CORES,
    RESOURCE_RAM_CEILING_GIB,
    _LONG_RENDER_SEMAPHORE,
    _SHORT_RENDER_SEMAPHORE,
)


@dataclass(frozen=True, slots=True)
class LaneDaemonConfig:
    """Configuration parameters governing multi-lane daemon execution."""

    db_path: str
    interval_seconds: int = 60
    max_picks: Optional[int] = None
    lanes_filter: Optional[Set[str]] = None
    max_parallel: int = 3
    generate_only: bool = False
    max_ticks: Optional[int] = None
    apply_offsets: bool = True
    enable_sweeps: bool = True


@dataclass(frozen=True, slots=True)
class ConcurrencyPolicy:
    """System-wide concurrency bounds adhering to AGENTS.md Section 5."""

    max_parallel_lanes: int = 3
    short_render_semaphore: threading.Semaphore = field(
        default_factory=lambda: _SHORT_RENDER_SEMAPHORE
    )
    long_render_semaphore: threading.Semaphore = field(
        default_factory=lambda: _LONG_RENDER_SEMAPHORE
    )
    ffmpeg_probe_threads: int = FFMPEG_PROBE_THREADS
    ffmpeg_encode_max_threads: int = FFMPEG_ENCODE_MAX_THREADS
    cpu_cores_hard_ceiling: float = RESOURCE_CPU_CEILING_CORES
    ram_gib_hard_ceiling: float = RESOURCE_RAM_CEILING_GIB


class TurnResult(TypedDict, total=False):
    """Result of an individual lane execution turn."""

    status: str
    lane: Optional[str]
    channel: str
    error: Optional[str]
    error_code: Optional[str]
    run_id: Optional[str]
    work_dir: Optional[str]
