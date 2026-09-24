"""
src/core/profiling/metrics_sampler.py - System Resource & Clock Metrics Sampling.

Non-intrusive Linux /proc and POSIX resource sampling for instantaneous RSS,
peak RSS (high water mark), and process/child CPU times.
"""
from __future__ import annotations

import os
import resource
from datetime import datetime, timezone

__all__ = [
    "_get_cpu_times",
    "_get_peak_rss_bytes",
    "_read_vm_rss_bytes",
    "_sync_bytes_mb",
    "_utc_now_iso",
    "is_profiling_enabled",
]

_PROFILING_ENABLED_CACHED: bool = True
_PROFILING_ENV_SNAPSHOT: str | None = "__UNSET__"


def is_profiling_enabled() -> bool:
    """Check if profiling is enabled via environment variable (default: True). Fast cached."""
    global _PROFILING_ENABLED_CACHED, _PROFILING_ENV_SNAPSHOT
    env_val = os.environ.get("PROFILING_ENABLED", "true")
    if env_val != _PROFILING_ENV_SNAPSHOT:
        _PROFILING_ENV_SNAPSHOT = env_val
        _PROFILING_ENABLED_CACHED = env_val.strip().lower() not in (
            "0",
            "false",
            "no",
            "off",
            "disable",
            "disabled",
        )
    return _PROFILING_ENABLED_CACHED


def _utc_now_iso() -> str:
    """Return current UTC time formatted as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_vm_rss_bytes() -> int:
    """Read instantaneous Resident Set Size in bytes from /proc/self/status."""
    try:
        with open("/proc/self/status", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1]) * 1024
    except Exception:
        pass
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return int(usage.ru_maxrss * 1024)
    except Exception:
        return 0


def _get_peak_rss_bytes() -> int:
    """Read High Water Mark RSS in bytes from /proc/self/status, fallback to ru_maxrss."""
    try:
        with open("/proc/self/status", encoding="ascii") as handle:
            for line in handle:
                if line.startswith("VmHWM:"):
                    return int(line.split()[1]) * 1024
    except Exception:
        pass
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return int(usage.ru_maxrss * 1024)
    except Exception:
        return _read_vm_rss_bytes()


def _get_cpu_times() -> tuple[float, float, float, float]:
    """Return (user, system, children_user, children_system) CPU seconds."""
    try:
        t = os.times()
        return (t.user, t.system, t.children_user, t.children_system)
    except Exception:
        return (0.0, 0.0, 0.0, 0.0)


def _sync_bytes_mb(b: int | float | None, mb: float | None) -> tuple[int, float]:
    """Synchronize bytes integer and megabytes float representation."""
    if b:
        return int(b), float(mb or round(int(b) / (1024 * 1024), 2))
    if mb:
        return int(round(float(mb) * 1024 * 1024)), float(mb)
    return 0, 0.0
