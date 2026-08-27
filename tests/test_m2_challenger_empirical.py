"""
Empirical test harness created by Challenger M2-2 (teamwork_preview_challenger)
to stress-test Milestone M2 P0 fixes and uncover edge cases.
"""
import os
import sys
import time
import signal
import pytest
import subprocess
import socket
import urllib.request
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import main
from lib.audio import _ffmpeg_run, apply_sidechain_ducking, FFmpegExecutionError
import src.youtube.auth as auth_yt


def _get_pgrep_pids(pattern: str) -> set:
    try:
        out = subprocess.check_output(["pgrep", "-f", pattern], text=True, stderr=subprocess.DEVNULL)
        return set(out.strip().split())
    except subprocess.CalledProcessError:
        return set()


def test_ffmpeg_run_timeout_returns_124():
    """Verify _ffmpeg_run returns returncode 124 on timeout when check=False."""
    res = _ffmpeg_run(["sleep", "5"], check=False, timeout=0.2)
    assert res.returncode == 124
    assert res.stderr == "TimeoutExpired"


def test_ffmpeg_run_timeout_raises_exception():
    """Verify _ffmpeg_run raises FFmpegExecutionError on timeout when check=True."""
    with pytest.raises(FFmpegExecutionError) as exc_info:
        _ffmpeg_run(["sleep", "5"], check=True, timeout=0.2)
    assert exc_info.value.returncode == 124
    assert "timed out" in str(exc_info.value)


def test_process_group_orphan_leakage_on_subprocess_timeout():
    """
    Empirical Stress Test: Does standard subprocess.run with timeout=... and start_new_session=True
    kill child processes in the process group, or leave orphan processes running?
    """
    marker = "m2_challenger_sleep_marker_9999"
    # Spawn python process which spawns child process 'sleep 120' in the process group and waits on it
    script = f"import subprocess, time; p = subprocess.Popen(['sleep', '120', '{marker}']); p.wait()"
    cmd = [sys.executable, "-c", script]
    
    pids_before = _get_pgrep_pids(marker)

    start = time.time()
    try:
        subprocess.run(cmd, timeout=0.5, start_new_session=True, capture_output=True)
    except subprocess.TimeoutExpired:
        pass
    elapsed = time.time() - start
    assert elapsed < 3.0, f"Subprocess timeout took too long: {elapsed}s"

    time.sleep(0.3)
    pids_after = _get_pgrep_pids(marker)
    orphans = pids_after - pids_before

    # Clean up orphan process if found
    for orphan in orphans:
        try:
            os.kill(int(orphan), signal.SIGKILL)
        except OSError:
            pass

    print(f"\n[EMPIRICAL TEST] Orphan child processes remaining after timeout: {orphans}")
    # Python stdlib subprocess.run(..., timeout=..., start_new_session=True) DOES NOT KILL CHILD PROCESSES IN THE PROCESS GROUP!
    # It only sends SIGKILL to the main process PID (self.kill()).
    assert len(orphans) == 0, f"FLAW CONFIRMED: Subprocess timeout leaked {len(orphans)} orphan process(es) in process group: {orphans}"


def test_main_lock_release_signal_handler():
    """Verify acquire_lock and signal handler lock release."""
    channel = "test_m2_chan"
    base_lock = main.LOCK_FILE_PATH
    expected_lock_file = f"{base_lock}.{channel}"

    if os.path.exists(expected_lock_file):
        try:
            os.unlink(expected_lock_file)
        except OSError:
            pass

    main.acquire_lock(channel)
    assert os.path.exists(expected_lock_file), f"Lock file {expected_lock_file} should exist"

    # Simulate signal handler invocation (WP5: canonical handler in lock.py)
    from src.core.lock import _handle_signal as _lock_handle_signal

    try:
        _lock_handle_signal(signal.SIGINT, None)
    except SystemExit:
        pass

    assert not os.path.exists(expected_lock_file), f"Lock file {expected_lock_file} should have been unlinked by signal handler"


def test_main_lock_release_channel_mismatch_bug():
    """
    Empirical Stress Test: What happens when acquire_lock('moku') is called (e.g. in test-telegram),
    and main()'s finally block executes release_lock('all')?
    """
    lock_moku = f"{main.LOCK_FILE_PATH}.moku"
    if os.path.exists(lock_moku):
        try:
            os.unlink(lock_moku)
        except OSError:
            pass

    # Step 1: acquire lock for 'moku'
    main.acquire_lock("moku")
    assert os.path.exists(lock_moku), "lock file .moku should exist"

    # Step 2: call release_lock("all") as main.py's finally block does when args.channel == "all"
    main.release_lock("all")

    # Step 3: check if lock file .moku was unlinked or orphaned
    moku_exists = os.path.exists(lock_moku)
    
    # Cleanup if orphaned
    if moku_exists:
        try:
            os.unlink(lock_moku)
        except OSError:
            pass

    print(f"\n[EMPIRICAL TEST] Is .moku lock file orphaned when release_lock('all') is called? {moku_exists}")
    # Assert whether the lock file remained orphaned
    assert not moku_exists, "BUG CONFIRMED: release_lock('all') failed to unlink /tmp/youtube_automation.lock.moku because target_channel did not match _active_lock_channel"


def test_http_timeout_in_exchange_code():
    """Verify timeout handling when OAuth endpoint drops/stalls connection."""
    import unittest.mock as mock
    with mock.patch.object(auth_yt, "CLIENT_ID", "test_client_id"), \
         mock.patch.object(auth_yt, "CLIENT_SECRET", "test_client_secret"), \
         mock.patch("src.youtube.auth.create_oauth_flow") as mock_flow_factory:
        mock_flow = mock.MagicMock()
        mock_flow.fetch_token.side_effect = TimeoutError("timed out")
        mock_flow_factory.return_value = mock_flow
        with pytest.raises((TimeoutError, Exception)) as exc_info:
            auth_yt.exchange_code("fake_code", token_path="/tmp/fake_token.json")

    assert "timed out" in str(exc_info.value)


def test_sidechain_ducking_ffmpeg_execution(tmp_path):
    """Verify FFmpeg sidechain ducking filter compiles and runs without syntax error."""
    narr_path = str(tmp_path / "narr.wav")
    music_path = str(tmp_path / "music.wav")
    out_path = str(tmp_path / "out.wav")

    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", narr_path], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=1", music_path], check=True, capture_output=True)

    result = apply_sidechain_ducking(
        narration_path=narr_path,
        music_path=music_path,
        output_path=out_path,
        ducking_db=-18.0,
    )
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 0
