"""Unit tests for src/core/lifecycle.py process management and atexit reaper."""

import os
import signal
import subprocess
import threading
from unittest.mock import MagicMock, call, patch

import pytest

from src.core.lifecycle import (
    cleanup_subprocesses,
    get_tracked_pids,
    register_process,
    sweep_tracked_processes,
    unregister_process,
)


def test_register_and_unregister_pid():
    """Test explicit registering and unregistering of integer PIDs."""
    pid = 99999
    registered = register_process(pid)
    assert registered == pid
    assert pid in get_tracked_pids()

    unregister_process(pid)
    assert pid not in get_tracked_pids()


def test_register_and_unregister_popen_instance():
    """Test registering and unregistering subprocess.Popen objects."""
    mock_proc = MagicMock()
    mock_proc.pid = 88888

    registered = register_process(mock_proc)
    assert registered == 88888
    assert 88888 in get_tracked_pids()

    unregister_process(mock_proc)
    assert 88888 not in get_tracked_pids()


def test_thread_safe_pid_tracking():
    """Test concurrent registration and deregistration under multiple threads."""
    pids = list(range(10000, 10100))

    def worker(pid):
        register_process(pid)
        assert pid in get_tracked_pids()
        unregister_process(pid)

    threads = [threading.Thread(target=worker, args=(pid,)) for pid in pids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    tracked = get_tracked_pids()
    for pid in pids:
        assert pid not in tracked


def test_register_and_unregister_none_and_invalid():
    """Test register_process and unregister_process with None or invalid objects."""
    assert register_process(None) is None
    unregister_process(None)

    mock_none_pid = MagicMock()
    mock_none_pid.pid = None
    assert register_process(mock_none_pid) is None
    unregister_process(mock_none_pid)

    assert register_process("invalid") is None
    unregister_process("invalid")


def test_cleanup_subprocesses_normal_clean_exit():
    """Test cleanup_subprocesses on a cleanly exiting process."""
    mock_proc = MagicMock()
    mock_proc.pid = 77777
    mock_proc.poll.return_value = 0
    mock_proc.stdin = MagicMock()
    mock_proc.stdout = MagicMock()
    mock_proc.stderr = MagicMock()

    register_process(mock_proc)
    assert 77777 in get_tracked_pids()

    cleanup_subprocesses(mock_proc)

    # Pipes should be safely closed
    mock_proc.stdin.close.assert_called_once()
    mock_proc.stdout.close.assert_called_once()
    mock_proc.stderr.close.assert_called_once()

    # Process shouldn't need kill since poll() returned 0
    mock_proc.terminate.assert_not_called()
    mock_proc.kill.assert_not_called()
    mock_proc.wait.assert_called_once_with(timeout=1.0)

    # PID should be unregistered
    assert 77777 not in get_tracked_pids()


def test_cleanup_subprocesses_hanging_process_escalation():
    """Test cleanup_subprocesses terminating and escalating to kill on timeout."""
    mock_proc = MagicMock()
    mock_proc.pid = 66666
    # Initially running, then times out on terminate wait, then exits after kill
    mock_proc.poll.side_effect = [None, None]
    mock_proc.stdin = None
    mock_proc.stdout = None
    mock_proc.stderr = None
    mock_proc.wait.side_effect = [subprocess.TimeoutExpired(cmd="mock", timeout=0.1), 0]

    register_process(mock_proc)

    cleanup_subprocesses(mock_proc, timeout=0.1)

    mock_proc.terminate.assert_called_once()
    mock_proc.kill.assert_called_once()
    assert mock_proc.wait.call_args_list == [
        call(timeout=0.1),
        call(timeout=1.0),
    ]
    assert 66666 not in get_tracked_pids()


def test_cleanup_subprocesses_handles_none_and_exceptions():
    """Test cleanup_subprocesses safely suppresses broken pipes / missing procs."""
    mock_proc = MagicMock()
    mock_proc.pid = 55555
    mock_proc.poll.return_value = None
    mock_proc.stdin = MagicMock()
    mock_proc.stdin.close.side_effect = BrokenPipeError("Pipe broken")
    mock_proc.stdout = None
    mock_proc.stderr = None
    mock_proc.terminate.side_effect = ProcessLookupError("No such process")
    mock_proc.wait.side_effect = OSError("OS Error")

    register_process(mock_proc)

    # Should not raise exception
    cleanup_subprocesses(None, mock_proc, None)

    assert 55555 not in get_tracked_pids()


def test_sweep_tracked_processes_signals_active_pids():
    """Test atexit sweeper sends SIGTERM, checks liveness with kill(pid, 0), and SIGKILLs alive PIDs."""
    pids = [11111, 22222]
    for p in pids:
        register_process(p)

    with patch("os.kill") as mock_kill:
        sweep_tracked_processes()

        # Check SIGTERM, liveness probe 0, and SIGKILL were sent for each pid
        expected_calls = [
            call(11111, signal.SIGTERM),
            call(22222, signal.SIGTERM),
            call(11111, 0),
            call(11111, signal.SIGKILL),
            call(22222, 0),
            call(22222, signal.SIGKILL),
        ]
        mock_kill.assert_has_calls(expected_calls, any_order=True)

    # Clean up test state
    for p in pids:
        unregister_process(p)


def test_sweep_tracked_processes_ignores_dead_pids():
    """Test atexit sweeper handles ProcessLookupError gracefully when PID already dead."""
    register_process(33333)

    with patch("os.kill", side_effect=ProcessLookupError("Process does not exist")):
        # Should not raise
        sweep_tracked_processes()

    assert 33333 not in get_tracked_pids()


def test_sweep_tracked_processes_dead_on_second_pass():
    """Test atexit sweeper when SIGTERM succeeds but process dies before second pass kill(pid, 0)."""
    register_process(44444)

    def mock_kill_fn(pid, sig):
        if sig == signal.SIGTERM:
            return None
        if sig == 0:
            raise ProcessLookupError("Died after SIGTERM")
        raise RuntimeError("Should not be reached")

    with patch("os.kill", side_effect=mock_kill_fn):
        sweep_tracked_processes()

    assert 44444 not in get_tracked_pids()
