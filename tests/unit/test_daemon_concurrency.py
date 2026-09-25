"""Unit tests for daemon concurrency semaphores and contracts."""

from __future__ import annotations

import dataclasses
import threading
from typing import get_type_hints

import pytest

from src.core.concurrency import (
    FFMPEG_ENCODE_MAX_THREADS,
    FFMPEG_PROBE_THREADS,
    RESOURCE_CPU_CEILING_CORES,
    RESOURCE_RAM_CEILING_GIB,
    _LONG_RENDER_SEMAPHORE,
    _SHORT_RENDER_SEMAPHORE,
    acquire_render_guard,
)
from src.core.contracts.daemon import (
    ConcurrencyPolicy,
    LaneDaemonConfig,
    TurnResult,
)


def test_concurrency_policy_defaults() -> None:
    """Validate ConcurrencyPolicy default values and resource ceilings."""
    policy = ConcurrencyPolicy()
    assert policy.max_parallel_lanes == 3
    assert policy.short_render_semaphore is _SHORT_RENDER_SEMAPHORE
    assert policy.long_render_semaphore is _LONG_RENDER_SEMAPHORE
    assert policy.ffmpeg_probe_threads == 2
    assert policy.ffmpeg_encode_max_threads == 4
    assert policy.cpu_cores_hard_ceiling == 2.0
    assert policy.ram_gib_hard_ceiling == 2.0
    assert FFMPEG_PROBE_THREADS == 2
    assert FFMPEG_ENCODE_MAX_THREADS == 4
    assert RESOURCE_CPU_CEILING_CORES == 2.0
    assert RESOURCE_RAM_CEILING_GIB == 2.0


def test_render_semaphore_isolation() -> None:
    """Validate short (cap=2) and long (cap=1) semaphores operate independently."""
    # Ensure starting in clean state
    assert _SHORT_RENDER_SEMAPHORE._value == 2
    assert _LONG_RENDER_SEMAPHORE._value == 1

    # Acquire long semaphore
    acquired_long = _LONG_RENDER_SEMAPHORE.acquire(blocking=False)
    assert acquired_long is True
    try:
        assert _LONG_RENDER_SEMAPHORE._value == 0
        # Short semaphore must be completely unaffected
        assert _SHORT_RENDER_SEMAPHORE._value == 2
    finally:
        _LONG_RENDER_SEMAPHORE.release()

    assert _LONG_RENDER_SEMAPHORE._value == 1
    assert _SHORT_RENDER_SEMAPHORE._value == 2


def test_long_render_semaphore_blocks_second_caller() -> None:
    """Acquiring _LONG_RENDER_SEMAPHORE blocks subsequent callers."""
    assert _LONG_RENDER_SEMAPHORE.acquire(blocking=False) is True
    try:
        # Second acquire should fail immediately non-blocking
        assert _LONG_RENDER_SEMAPHORE.acquire(blocking=False) is False
    finally:
        _LONG_RENDER_SEMAPHORE.release()

    assert _LONG_RENDER_SEMAPHORE._value == 1


def test_short_render_semaphore_allows_two_blocks_third() -> None:
    """_SHORT_RENDER_SEMAPHORE allows two concurrent acquisitions and blocks third."""
    assert _SHORT_RENDER_SEMAPHORE.acquire(blocking=False) is True
    assert _SHORT_RENDER_SEMAPHORE.acquire(blocking=False) is True
    try:
        assert _SHORT_RENDER_SEMAPHORE.acquire(blocking=False) is False
    finally:
        _SHORT_RENDER_SEMAPHORE.release()
        _SHORT_RENDER_SEMAPHORE.release()

    assert _SHORT_RENDER_SEMAPHORE._value == 2


def test_lane_daemon_config_contract_validation() -> None:
    """Verify LaneDaemonConfig dataclass slots, immutability, and defaults."""
    config = LaneDaemonConfig(db_path="data/test.db")
    assert config.db_path == "data/test.db"
    assert config.interval_seconds == 60
    assert config.max_picks is None
    assert config.lanes_filter is None
    assert config.max_parallel == 3
    assert config.generate_only is False
    assert config.max_ticks is None
    assert config.apply_offsets is True
    assert config.enable_sweeps is True

    # Immutability check
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        config.interval_seconds = 30  # type: ignore[misc]

    # Slots check
    assert hasattr(config, "__slots__")


def test_turn_result_typed_dict_keys() -> None:
    """Verify TurnResult TypedDict annotations and instantiability."""
    annotations = get_type_hints(TurnResult)
    expected_keys = {
        "status",
        "lane",
        "channel",
        "error",
        "error_code",
        "run_id",
        "work_dir",
    }
    assert expected_keys.issubset(set(annotations.keys()))

    sample: TurnResult = {
        "status": "COMPLETED",
        "lane": "horror-scp-shorts",
        "channel": "horror",
        "run_id": "run-123",
        "work_dir": "/tmp/work",
    }
    assert sample["status"] == "COMPLETED"
    assert sample["lane"] == "horror-scp-shorts"


def test_acquire_render_guard_context_manager() -> None:
    """Verify acquire_render_guard properly manages token lifecycle."""
    # Test short semaphore guard
    initial_short = _SHORT_RENDER_SEMAPHORE._value
    with acquire_render_guard(is_longform=False):
        assert _SHORT_RENDER_SEMAPHORE._value == initial_short - 1
    assert _SHORT_RENDER_SEMAPHORE._value == initial_short

    # Test long semaphore guard
    initial_long = _LONG_RENDER_SEMAPHORE._value
    with acquire_render_guard(is_longform=True):
        assert _LONG_RENDER_SEMAPHORE._value == initial_long - 1
    assert _LONG_RENDER_SEMAPHORE._value == initial_long

    # Test exception release safety
    with pytest.raises(RuntimeError):
        with acquire_render_guard(is_longform=False):
            assert _SHORT_RENDER_SEMAPHORE._value == initial_short - 1
            raise RuntimeError("Simulation error")
    assert _SHORT_RENDER_SEMAPHORE._value == initial_short

    # Test timeout error when semaphore unavailable
    assert _LONG_RENDER_SEMAPHORE.acquire(blocking=False) is True
    try:
        with pytest.raises(TimeoutError):
            with acquire_render_guard(is_longform=True, timeout=0.01):
                pass
    finally:
        _LONG_RENDER_SEMAPHORE.release()
