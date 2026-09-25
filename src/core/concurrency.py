"""Centralized concurrency governance, thread limits, and render semaphores.

Enforces AGENTS.md Section 5 resource ceiling invariants:
- <= 2.0 CPU Cores
- <= 2.0 GiB Peak RAM
- Thread bounded FFmpeg subprocesses
- Global partition semaphores for short (N=2) and longform (N=1) renders
"""

from __future__ import annotations

import contextlib
import threading
from typing import Final, Iterator, Optional

# Resource hard target ceilings (AGENTS.md Section 5)
RESOURCE_CPU_CEILING_CORES: Final[float] = 2.0
RESOURCE_RAM_CEILING_GIB: Final[float] = 2.0

# FFmpeg thread bounds
FFMPEG_PROBE_THREADS: Final[int] = 2
FFMPEG_ENCODE_MAX_THREADS: Final[int] = 4

# Single Sources of Truth (SSOT) for global concurrency semaphores
_LONG_RENDER_SEMAPHORE: Final[threading.Semaphore] = threading.Semaphore(1)
_SHORT_RENDER_SEMAPHORE: Final[threading.Semaphore] = threading.Semaphore(2)
_SYNTHESIS_SEMAPHORE: Final[threading.Semaphore] = threading.Semaphore(2)


@contextlib.contextmanager
def acquire_render_guard(
    is_longform: bool,
    timeout: Optional[float] = None,
) -> Iterator[threading.Semaphore]:
    """Context manager to boundedly acquire and release render semaphores.

    Args:
        is_longform: True if acquiring longform render semaphore (N=1),
                     False if acquiring short render semaphore (N=2).
        timeout: Optional timeout in seconds to wait for acquisition.

    Yields:
        The acquired threading.Semaphore.

    Raises:
        TimeoutError: If acquisition fails within the specified timeout.
    """
    semaphore = _LONG_RENDER_SEMAPHORE if is_longform else _SHORT_RENDER_SEMAPHORE
    blocking = timeout is None or timeout > 0
    acquired = semaphore.acquire(
        blocking=blocking,
        timeout=-1 if timeout is None else timeout,
    )
    if not acquired:
        target_name = "longform" if is_longform else "short"
        raise TimeoutError(
            f"Timed out waiting {timeout}s for {target_name} render semaphore"
        )
    try:
        yield semaphore
    finally:
        semaphore.release()
