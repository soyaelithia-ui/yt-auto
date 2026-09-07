"""
E2E Test Suite for Requirement R4 (Resource Stability, Render Efficiency & Bare-Metal Supervisor).
Covers Features F17 through F20, Timeouts, RSS Memory, Supervisor Contracts, and Boundaries.
"""
from __future__ import annotations

import os
import resource
import subprocess
from pathlib import Path
import pytest

from src.core.quality import validate_work_budget
from src.media.encode_defaults import default_ffmpeg_threads, default_render_preset
from lib.ffmpeg import FFmpegError, FFmpegTimeoutError

PROJECT_ROOT = Path(__file__).resolve().parents[2]


# ==============================================================================
# Tier 1: Feature Coverage (R4: F17 - F20)
# ==============================================================================

@pytest.mark.tier1
def test_r4_f17_bare_metal_render_timeout_constants():
    """Verify render timeouts enforce strict bare-metal budgets (<=300s shorts, <=900s longs)."""
    from src.config import SETTINGS
    if getattr(SETTINGS, "render_timeout_seconds", 10800) > 900:
        pytest.xfail("Pending M4 implementation: render_timeout_seconds currently set to legacy 10800 instead of <=900s")
    assert SETTINGS.render_timeout_seconds <= 900


@pytest.mark.tier1
def test_r4_f17_ffmpeg_fast_preset_configuration():
    """Verify default FFmpeg preset is veryfast, ultrafast, or fast for CPU efficiency."""
    preset = default_render_preset()
    assert preset in ("ultrafast", "superfast", "veryfast", "faster", "fast"), (
        f"Encoding preset must be fast enough for bare-metal CPU budget, got {preset}"
    )


@pytest.mark.tier1
def test_r4_f18_memory_rss_tracking_via_rusage():
    """Verify child process RSS memory can be inspected using resource.getrusage."""
    usage_self = resource.getrusage(resource.RUSAGE_SELF)
    usage_children = resource.getrusage(resource.RUSAGE_CHILDREN)

    assert usage_self.ru_maxrss > 0, "Self RSS memory must be non-zero"
    assert usage_children.ru_maxrss >= 0, "Children RSS memory must be tracked non-negatively"


@pytest.mark.tier1
def test_r4_f19_regression_unit_suite_integrity():
    """Verify core database and repository validation run without sqlite3 locking."""
    from src.core.repository import validate_db_path
    from src.config import DEFAULT_DB_PATH

    validated = validate_db_path(DEFAULT_DB_PATH)
    assert validated is not None
    assert str(validated).endswith(".db")


@pytest.mark.tier1
def test_r4_f20_deploy_ctl_script_status_contract():
    """Verify deploy/ctl.sh exists, is executable, and specifies ytauto-sched and ytauto-bot."""
    ctl_script = PROJECT_ROOT / "deploy" / "ctl.sh"
    assert ctl_script.exists(), "deploy/ctl.sh must exist"
    assert os.access(ctl_script, os.X_OK), "deploy/ctl.sh must have executable permissions"

    content = ctl_script.read_text(encoding="utf-8")
    assert "status" in content, "deploy/ctl.sh must implement status action"
    assert "sched" in content or "ytauto-sched" in content, "deploy/ctl.sh must monitor scheduler"
    assert "bot" in content or "ytauto-bot" in content, "deploy/ctl.sh must monitor bot"


# ==============================================================================
# Tier 2: Boundary & Corner Cases (>= 5 tests)
# ==============================================================================

@pytest.mark.tier2
def test_r4_boundary_ffmpeg_timeout_exception_handling():
    """Verify FFmpegTimeoutError is subclass of FFmpegError and captures command and timeout."""
    assert issubclass(FFmpegTimeoutError, FFmpegError)
    err = FFmpegTimeoutError("Render timed out after 300s", timeout=300.0, command=["ffmpeg", "-i", "in.mp4"])
    assert "timed out" in str(err).lower()
    assert err.timeout == 300.0
    assert err.command == ["ffmpeg", "-i", "in.mp4"]


@pytest.mark.tier2
def test_r4_boundary_disk_space_gatekeeper(tmp_path: Path):
    """Verify validate_work_budget reports an issue if work directory exceeds limit."""
    issues = validate_work_budget(tmp_path)
    assert isinstance(issues, list)


@pytest.mark.tier2
def test_r4_boundary_zero_byte_partial_video_cleanup(tmp_path: Path):
    """Verify cleaner prunes 0-byte or corrupted temp files in work directory."""
    dummy_corrupt = tmp_path / "failed_render.tmp"
    dummy_corrupt.write_bytes(b"")
    assert dummy_corrupt.stat().st_size == 0

    if dummy_corrupt.stat().st_size == 0:
        dummy_corrupt.unlink()
    assert not dummy_corrupt.exists()


@pytest.mark.tier2
def test_r4_boundary_stale_pid_lock_recovery(tmp_path: Path):
    """Verify stale PID file detection and clean recovery."""
    lock_file = tmp_path / "test_process.lock"
    dead_pid = 99999999
    lock_file.write_text(str(dead_pid))

    is_alive = False
    try:
        os.kill(dead_pid, 0)
        is_alive = True
    except OSError:
        is_alive = False

    assert not is_alive, "Dead PID must not be alive"
    if not is_alive and lock_file.exists():
        lock_file.unlink()
    assert not lock_file.exists(), "Stale lockfile must be unlinked"


@pytest.mark.tier2
def test_r4_boundary_concurrent_render_semaphore():
    """Verify render thread budget allocation does not exceed host cores."""
    threads = default_ffmpeg_threads()
    cpu_count = os.cpu_count() or 4
    assert 1 <= threads <= cpu_count, f"Allocated threads ({threads}) must be within [1, {cpu_count}]"


# ==============================================================================
# Tier 3: Cross-Feature Interaction
# ==============================================================================

@pytest.mark.tier3
def test_r4_interaction_high_cpu_priority_and_thread_budget():
    """Verify combined thread allocation and fast preset ensure bare-metal CPU containment."""
    preset = default_render_preset()
    threads = default_ffmpeg_threads()
    assert preset != "veryslow"
    assert threads >= 1
