#!/usr/bin/env python3
"""Thin supervisor for hosts without cron/systemd.

Since production moved to config-driven lanes (config/lanes.json), ALL cadence
decisions live inside ``main.py daemon`` (LaneScheduler + per-lane leases).
This process no longer schedules anything: it just keeps exactly one daemon
child alive, restarting it only when it dies (crash/OOM), and forwards SIGTERM.

The old wall-clock grid (%5 shorts / {17,47} longform) is gone on purpose:
firing by wall clock raced the queue and double-scheduled against in-flight
renders. Per-lane ``min_gap_seconds`` ceilings are the single source of truth.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
PY = str(PROJECT / ".venv" / "bin" / "python")
LOG_DIR = PROJECT / "logs"
MAX_LOG_BYTES = 50 * 1024 * 1024
PID_FILE = PROJECT / "logs" / "tmux_scheduler.pid"
LOCK_FILE = PROJECT / "logs" / "tmux_scheduler.lock"

DAEMON_ARGS = ["daemon", "--interval", "60"]
RESTART_DELAY_SECONDS = 15


def acquire_singleton() -> int | None:
    """Exclusive instance guard: returns pid of the live owner, or None if we won.

    Uses fcntl.flock on a lockfile (auto-released by the kernel if the holder
    dies) plus a best-effort PID file for operator visibility. A second
    invocation can never start a duplicate scheduler.
    """
    import fcntl

    LOCK_FILE.parent.mkdir(exist_ok=True)
    handle = open(LOCK_FILE, "w")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        try:
            existing = PID_FILE.read_text().strip()
        except OSError:
            existing = "?"
        handle.close()
        return int(existing) if existing.isdigit() else -1
    # We hold the lock for the process lifetime (handle stays open).
    globals()["_SINGLETON_HANDLE"] = handle
    PID_FILE.write_text(f"{os.getpid()}\n")
    return None


_SHUTDOWN = False


def _on_signal(signum, _frame):
    global _SHUTDOWN
    _SHUTDOWN = True


def _rotate_if_needed(path: Path) -> None:
    try:
        if path.exists() and path.stat().st_size > MAX_LOG_BYTES:
            path.replace(path.with_suffix(path.suffix + ".old"))
    except OSError:
        pass


def _stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def main() -> int:
    owner = acquire_singleton()
    if owner is not None:
        print(
            f"[tmux-supervisor] another instance already running (pid={owner}); exiting.",
            flush=True,
        )
        return 0
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    LOG_DIR.mkdir(exist_ok=True)

    log_path = LOG_DIR / "daemon.log"
    print(f"[tmux-supervisor] started pid={os.getpid()} project={PROJECT}", flush=True)
    while not _SHUTDOWN:
        _rotate_if_needed(log_path)
        log_fh = open(log_path, "ab", buffering=0)
        log_fh.write(f"\n===== [{_stamp()}] launching daemon =====\n".encode())
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        env.setdefault("FFMPEG_THREADS", "2")
        env.setdefault("YT_PROFILE", "prod")
        env["ENABLE_TELEGRAM_CALLBACK_POLLING"] = "0"
        child = subprocess.Popen(
            [PY, str(PROJECT / "main.py"), *DAEMON_ARGS],
            cwd=str(PROJECT),
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
        log_fh.close()
        print(f"[{_stamp()}] daemon launched pid={child.pid}", flush=True)
        while not _SHUTDOWN and child.poll() is None:
            time.sleep(1)
        try:
            child.terminate()
            child.wait(timeout=10)
        except Exception:
            try:
                child.kill()
            except Exception:
                pass
        code = child.returncode
        if _SHUTDOWN:
            print(f"[{_stamp()}] shutdown requested; daemon exit={code}", flush=True)
            break
        print(f"[{_stamp()}] daemon exited code={code}; restarting in {RESTART_DELAY_SECONDS}s", flush=True)
        deadline = time.monotonic() + RESTART_DELAY_SECONDS
        while not _SHUTDOWN and time.monotonic() < deadline:
            time.sleep(0.5)
    print("[tmux-supervisor] shutdown complete", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
