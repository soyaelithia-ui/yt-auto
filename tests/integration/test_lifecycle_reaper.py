"""Integration test verifying end-to-end atexit orphan process reaping."""

import os
import signal
import subprocess
import sys
import time

import pytest


def test_atexit_sweeper_reaps_orphaned_subprocesses():
    """Spawn an isolated python process that registers child processes and terminates abruptly.
    Verify child processes are terminated by the atexit hook and not orphaned in the OS.
    """
    # Child script to execute in a separate python process
    child_script = """
import subprocess
import time
import sys
from src.core.lifecycle import register_process

# Spawn 2 long-running sleep processes
p1 = subprocess.Popen(["sleep", "60"])
p2 = subprocess.Popen(["sleep", "60"])

register_process(p1)
register_process(p2)

# Print PIDs to stdout so the parent test can inspect them
print(f"{p1.pid},{p2.pid}", flush=True)

# Normal exit which triggers atexit
sys.exit(0)
"""

    run_proc = subprocess.Popen(
        [sys.executable, "-c", child_script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    stdout, stderr = run_proc.communicate(timeout=5.0)
    assert run_proc.returncode == 0, f"Child script failed: {stderr}"

    pid1_str, pid2_str = stdout.strip().split(",")
    pid1 = int(pid1_str)
    pid2 = int(pid2_str)

    # Give a tiny grace window for OS signal delivery
    time.sleep(0.3)

    # Check if pid1 and pid2 are still alive
    def is_pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False

    assert not is_pid_alive(pid1), f"Child process {pid1} was orphaned and still running"
    assert not is_pid_alive(pid2), f"Child process {pid2} was orphaned and still running"
