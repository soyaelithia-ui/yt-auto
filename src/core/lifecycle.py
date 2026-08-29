"""Process lifecycle management and atexit orphan sweeping."""

import atexit
import contextlib
import logging
import os
import signal
import subprocess
import threading
import time
from typing import Any, Optional, Set, Union

logger = logging.getLogger(__name__)

_tracked_pids_lock = threading.Lock()
_tracked_pids: Set[int] = set()


def register_process(proc: Union[subprocess.Popen, int, Any]) -> Optional[int]:
    """Registers a child PID in the thread-safe tracker. Returns tracked PID or None if invalid."""
    if proc is None:
        return None
    if hasattr(proc, "pid") and not isinstance(proc, (int, float)):
        if proc.pid is None:
            return None
        pid = int(proc.pid)
    else:
        try:
            pid = int(proc)
        except (ValueError, TypeError):
            return None
    with _tracked_pids_lock:
        _tracked_pids.add(pid)
    return pid


def unregister_process(proc: Union[subprocess.Popen, int, Any]) -> None:
    """Removes a child PID from the tracker."""
    if proc is None:
        return
    if hasattr(proc, "pid") and not isinstance(proc, (int, float)):
        if proc.pid is None:
            return
        pid = int(proc.pid)
    else:
        try:
            pid = int(proc)
        except (ValueError, TypeError):
            return
    with _tracked_pids_lock:
        _tracked_pids.discard(pid)


def get_tracked_pids() -> Set[int]:
    """Returns a copy of currently tracked PIDs."""
    with _tracked_pids_lock:
        return set(_tracked_pids)


def cleanup_subprocesses(*procs: Optional[Any], timeout: float = 2.0) -> None:
    """Safely closes pipes, terminates/kills child processes, and unregisters them."""
    for proc in procs:
        if proc is None:
            continue

        # 1. Close standard streams to avoid pipe buffer deadlocks
        for stream_name in ("stdin", "stdout", "stderr"):
            stream = getattr(proc, stream_name, None)
            if stream is not None:
                with contextlib.suppress(Exception):
                    stream.close()

        # 2. Terminate or kill if still running
        try:
            poll_fn = getattr(proc, "poll", None)
            is_running = poll_fn() is None if callable(poll_fn) else False

            if is_running:
                terminate_fn = getattr(proc, "terminate", None)
                if callable(terminate_fn):
                    terminate_fn()
                wait_fn = getattr(proc, "wait", None)
                if callable(wait_fn):
                    try:
                        wait_fn(timeout=timeout)
                    except (subprocess.TimeoutExpired, Exception):
                        kill_fn = getattr(proc, "kill", None)
                        if callable(kill_fn):
                            kill_fn()
                        with contextlib.suppress(Exception):
                            wait_fn(timeout=1.0)
            else:
                wait_fn = getattr(proc, "wait", None)
                if callable(wait_fn):
                    with contextlib.suppress(Exception):
                        wait_fn(timeout=1.0)
        except Exception:
            with contextlib.suppress(Exception):
                kill_fn = getattr(proc, "kill", None)
                if callable(kill_fn):
                    kill_fn()
                wait_fn = getattr(proc, "wait", None)
                if callable(wait_fn):
                    wait_fn(timeout=1.0)
        finally:
            unregister_process(proc)


def sweep_tracked_processes() -> None:
    """atexit handler: sends SIGTERM followed by SIGKILL to remaining registered PIDs."""
    with _tracked_pids_lock:
        pids_to_sweep = list(_tracked_pids)

    if not pids_to_sweep:
        return

    logger.warning("Sweeping %d remaining tracked child process(es) at exit: %s", len(pids_to_sweep), pids_to_sweep)

    # First pass: SIGTERM
    for pid in pids_to_sweep:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            unregister_process(pid)

    # Brief grace window
    time.sleep(0.1)

    # Second pass: check liveness with os.kill(pid, 0) and SIGKILL if still alive
    for pid in pids_to_sweep:
        try:
            os.kill(pid, 0)
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        finally:
            unregister_process(pid)


# Register atexit handler automatically on module import
atexit.register(sweep_tracked_processes)
