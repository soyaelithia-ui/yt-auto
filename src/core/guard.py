"""In-process resource guard: disk pre-flight, memory ceiling, failure breaker.

Complements the hard container limits (docker-compose ``mem_limit``/``cpus``)
by acting *before* an OOM kill can destroy a run:

* :func:`ensure_disk_available` — pre-run disk check with one automatic
  cleaner pass; callers decide to pause/skip when still below threshold.
* :class:`MemoryWatchdog` / :func:`memory_checkpoint` — cheap ``/proc``
  samples of self+children RSS against a soft ceiling (default 80% of the
  cgroup limit); sustained breach raises :class:`ResourceLimitError` so the
  run aborts orderly preserving artifacts instead of being OOM-killed.
* :class:`ConsecutiveFailureBreaker` — trips after N failed turns on a
  channel so the daemon pauses it instead of burning quota/compute in a loop.

Stdlib only (no psutil). All thresholds are env-tunable with safe defaults.
"""

from __future__ import annotations

import os
import resource
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from src.core.errors import PipelineError


class ResourceLimitError(PipelineError):
    """Raised when a soft resource ceiling is exceeded mid-run."""

    def __init__(
        self,
        message: str,
        *,
        resource_kind: str = "memory",
        observed_bytes: int | None = None,
        limit_bytes: int | None = None,
        details: dict | None = None,
    ) -> None:
        merged = {"resource": resource_kind}
        if observed_bytes is not None:
            merged["observed_bytes"] = observed_bytes
        if limit_bytes is not None:
            merged["limit_bytes"] = limit_bytes
        merged.update(details or {})
        super().__init__(
            message,
            component="resource_guard",
            retryable=True,
            details=merged,
        )
        self.resource_kind = resource_kind
        self.observed_bytes = observed_bytes
        self.limit_bytes = limit_bytes


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Disk guard
# ---------------------------------------------------------------------------


def free_disk_bytes(path: str | os.PathLike) -> int:
    """Free bytes available on the volume holding ``path`` (0 on error)."""
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return 0


@dataclass
class DiskPreflight:
    ok: bool
    min_free_bytes: int
    checked: dict[str, int] = field(default_factory=dict)
    cleaned_bytes: int = 0

    @property
    def tightest_path(self) -> str | None:
        if not self.checked:
            return None
        return min(self.checked, key=self.checked.get)


def _guard_paths() -> list[Path]:
    from src.config import BASE_DIR

    configured = os.environ.get("YT_GUARD_PATHS", "")
    if configured.strip():
        return [Path(p) for p in configured.split(os.pathsep) if p.strip()]
    candidates = [BASE_DIR / "data", BASE_DIR / "work", BASE_DIR / "logs"]
    return [p for p in candidates if not p.exists() or p.is_dir()]


def ensure_disk_available(
    paths: Iterable[str | os.PathLike] | None = None,
    *,
    min_free_gb: float | None = None,
    auto_clean: bool = True,
) -> DiskPreflight:
    """Verify free disk space; optionally run one cleaner pass and re-check.

    Never raises. The caller decides whether a failed check should pause the
    channel / skip the turn.
    """
    targets = [Path(p) for p in paths] if paths is not None else _guard_paths()
    threshold = (
        min_free_gb * (1024**3)
        if min_free_gb is not None
        else _env_float("YT_MIN_FREE_DISK_GB", 5.0) * (1024**3)
    )

    checked = {str(p): free_disk_bytes(p) for p in targets}
    if not checked or all(free >= threshold for free in checked.values()):
        return DiskPreflight(
            ok=True,
            min_free_bytes=int(threshold),
            checked=checked,
        )

    cleaned_bytes = 0
    if auto_clean:
        try:
            from src.cleaner import clean_system_cache

            report = clean_system_cache(dry_run=False)
            cleaned_bytes = int(report.get("freed_bytes", 0))
        except Exception:  # cleaner must never crash the guard
            cleaned_bytes = 0
        checked = {str(p): free_disk_bytes(p) for p in targets}

    ok = bool(checked) and all(free >= threshold for free in checked.values())
    return DiskPreflight(
        ok=ok,
        min_free_bytes=int(threshold),
        checked=checked,
        cleaned_bytes=cleaned_bytes,
    )


# ---------------------------------------------------------------------------
# Memory ceiling
# ---------------------------------------------------------------------------

_PROC_SELF_STATUS = "/proc/self/status"
_CGROUP_V2_LIMIT = "/sys/fs/cgroup/memory.max"
_CGROUP_V1_LIMIT = "/sys/fs/cgroup/memory/memory.limit_in_bytes"


def read_vm_rss_bytes(status_path: str = _PROC_SELF_STATUS) -> int:
    """Current process RSS in bytes from ``/proc/self/status`` (0 on error)."""
    try:
        with open(status_path, encoding="ascii") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    # value is expressed in kB
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return 0
    return 0


def children_peak_rss_bytes() -> int:
    """Peak RSS of reaped child processes (FFmpeg et al.) via getrusage."""
    try:
        return int(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss) * 1024
    except Exception:
        return 0


def observed_memory_bytes(
    *,
    self_rss: int | None = None,
    children_rss: int | None = None,
) -> int:
    """Best-effort footprint estimate: own RSS + peak child RSS."""
    own = read_vm_rss_bytes() if self_rss is None else self_rss
    kids = children_peak_rss_bytes() if children_rss is None else children_rss
    return max(own, 0) + max(kids, 0)


def cgroup_memory_limit_bytes() -> int | None:
    """Effective cgroup memory limit, or None when unlimited/unknown."""
    for path in (_CGROUP_V2_LIMIT, _CGROUP_V1_LIMIT):
        try:
            raw = Path(path).read_text(encoding="ascii").strip()
        except OSError:
            continue
        if not raw or raw == "max":
            continue
        try:
            value = int(raw)
        except ValueError:
            continue
        # kernel reports ~unlimited as a huge number; ignore those
        if 0 < value < (1 << 55):
            return value
    return None


_SOFT_RATIO = 0.80


def resolve_soft_limit_bytes(*, explicit: float | None = None) -> int | None:
    """Soft ceiling resolution: arg > env > 80% of cgroup > disabled(None)."""
    if explicit is not None:
        return max(0, int(explicit))
    env_value = os.environ.get("YT_MAX_RSS_GB", "").strip()
    if env_value:
        try:
            return max(0, int(float(env_value) * (1024**3)))
        except ValueError:
            pass
    limit = cgroup_memory_limit_bytes()
    if limit:
        return int(limit * _SOFT_RATIO)
    return None


class MemoryWatchdog:
    """Synchronous checkpoint sampler; raises after sustained breaches.

    A single sample above the ceiling does NOT abort (transient spikes);
    ``required_breaches`` consecutive breaches do.
    """

    def __init__(
        self,
        *,
        soft_limit_bytes: int | float | None = None,
        required_breaches: int = 2,
        observer: Callable[[], int] | None = None,
    ) -> None:
        self.soft_limit_bytes = resolve_soft_limit_bytes(explicit=soft_limit_bytes)
        self.required_breaches = max(1, int(required_breaches))
        self._observer = observer
        self._breaches = 0
        self.last_observed = 0
        self.disabled = self.soft_limit_bytes is None or self.soft_limit_bytes <= 0

    def _sample(self) -> int:
        return self._observer() if self._observer else observed_memory_bytes()

    def checkpoint(self, stage: str = "checkpoint") -> dict:
        """Take one sample; raise ResourceLimitError when sustained."""
        info: dict = {"stage": stage, "disabled": True}
        if self.disabled:
            return info
        observed = self._sample()
        self.last_observed = observed
        info.update(disabled=False, observed_bytes=observed, limit_bytes=self.soft_limit_bytes)
        if observed > int(self.soft_limit_bytes):
            self._breaches += 1
            info["breaches"] = self._breaches
            if self._breaches >= self.required_breaches:
                raise ResourceLimitError(
                    f"Memoria {observed / (1024**3):.2f} GB supera el techo "
                    f"{self.soft_limit_bytes / (1024**3):.2f} GB en '{stage}'",
                    resource_kind="memory",
                    observed_bytes=observed,
                    limit_bytes=int(self.soft_limit_bytes),
                )
        else:
            self._breaches = 0
            info["breaches"] = 0
        return info


_MODULE_WATCHDOG: MemoryWatchdog | None = None


def memory_checkpoint(stage: str = "checkpoint") -> dict:
    """Module-level checkpoint used by pipeline stages (cheap no-op when disabled)."""
    global _MODULE_WATCHDOG
    if _MODULE_WATCHDOG is None:
        _MODULE_WATCHDOG = MemoryWatchdog()
    return _MODULE_WATCHDOG.checkpoint(stage)


def reset_module_watchdog() -> None:
    """Test isolation hook: force re-resolution of limits on next checkpoint."""
    global _MODULE_WATCHDOG
    _MODULE_WATCHDOG = None


# ---------------------------------------------------------------------------
# Consecutive-failure circuit breaker
# ---------------------------------------------------------------------------


class ConsecutiveFailureBreaker:
    """Counts consecutive failed turns per channel; trips at threshold.

    Pure counting logic: when :meth:`record_failure` returns True the caller
    (daemon) pauses the channel and alerts. Thread-safe across concurrent lanes.
    """

    def __init__(self, threshold: int | None = None) -> None:
        self.threshold = (
            threshold
            if threshold is not None
            else _env_int("YT_MAX_CONSECUTIVE_FAILURES", 3)
        )
        self.counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def record_success(self, channel: str) -> None:
        with self._lock:
            self.counts[channel] = 0

    def record_failure(self, channel: str) -> bool:
        """Register a failure; True exactly when the breaker trips."""
        with self._lock:
            count = self.counts.get(channel, 0) + 1
            self.counts[channel] = count
            return self.threshold > 0 and count >= self.threshold

    def reset(self, channel: str | None = None) -> None:
        with self._lock:
            if channel is None:
                self.counts.clear()
            else:
                self.counts.pop(channel, None)
