"""Integration tests for synthetic offline multi-lane daemon orchestration.

Validates end-to-end multi-lane dispatch, atomic WAL leasing, render semaphores,
cadence progression, and total network/browser isolation adhering to AGENTS.md Section 5.
"""

from __future__ import annotations

import os
import re
import socket
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from src.core.concurrency import (
    _LONG_RENDER_SEMAPHORE,
    _SHORT_RENDER_SEMAPHORE,
    acquire_render_guard,
)
from src.core.contracts.daemon import LaneDaemonConfig
from src.core.domain import CanonicalChannel
from src.core.repository import QueueRepository, connect, migrate_database
from src.orchestrator.scheduler import LaneDaemonOrchestrator


@pytest.fixture
def integration_db(tmp_path: pytest.TempPathFactory) -> str:
    db_file = str(tmp_path / "integration_queue.db")
    migrate_database(db_file)
    return db_file


def _seed_story_for_lane(db_path: str, story_id: str, lane_id: str, channel: str) -> None:
    repo = QueueRepository(db_path)
    assert repo.enqueue(
        story_id,
        f"Synthetic Title {story_id}",
        "Synthetic script content long enough for validation. " * 5,
        f"https://synthetic.local/{story_id}",
        channel,
        lane_id=lane_id,
    )


def test_synthetic_offline_multi_lane_turn_concurrent_execution(
    integration_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test full multi-lane turn across all 4 production lanes with leasing and cadence advance."""
    lanes = [
        ("horror-scp-shorts", "horror"),
        ("horror-horror-long", "horror"),
        ("drama-aita-long", "drama"),
        ("drama-drama-shorts", "drama"),
    ]
    # Seed stories for 3 lanes; leave the 4th lane empty to test adaptive backoff
    for lane_id, ch in lanes[:3]:
        _seed_story_for_lane(integration_db, f"story-{lane_id}-1", lane_id, ch)
        _seed_story_for_lane(integration_db, f"story-{lane_id}-2", lane_id, ch)

    observed_owners: list[str] = []

    def mock_pipeline_run(**kwargs):
        # Inspect active lease for the lane in database
        lane_id = kwargs.get("lane_id")
        with connect(integration_db, read_only=True) as conn:
            row = conn.execute(
                "SELECT owner FROM lane_leases WHERE lane_id = ?", (lane_id,)
            ).fetchone()
            if row:
                observed_owners.append(row["owner"])
        return {"status": "COMPLETED", "lane": lane_id, "channel": kwargs.get("channel")}

    monkeypatch.setattr("src.pipeline.run_pipeline_once", mock_pipeline_run)

    config = LaneDaemonConfig(
        db_path=integration_db,
        max_parallel=4,
        interval_seconds=1,
        max_ticks=1,
        apply_offsets=False,
        enable_sweeps=False,
    )
    orchestrator = LaneDaemonOrchestrator(config)

    start_time = time.monotonic()
    results = orchestrator.run_loop()
    duration = time.monotonic() - start_time

    # Must complete cleanly and quickly
    assert duration <= 5.0
    assert len(results) == 4

    # Verify atomic lane lease acquisition owner signatures: lane-{lane_id}:{hostname}:{pid}:{thread_id}
    owner_pattern = re.compile(r"^lane-[^:]+:[^:]+:\d+:\d+$")
    assert len(observed_owners) >= 1
    for owner in observed_owners:
        assert owner_pattern.match(owner) is not None

    # Verify pure-forward cadence advancement on completed lanes
    repo = QueueRepository(integration_db)
    for lane_id, _ in lanes[:3]:
        state = repo.get_lane_state(lane_id)
        assert state is not None
        assert state["consecutive_empty"] == 0
        assert state["last_run_id"] is not None

    # Verify adaptive empty backoff on empty lane (drama-drama-shorts)
    empty_state = repo.get_lane_state(lanes[3][0])
    assert empty_state is not None
    assert empty_state["consecutive_empty"] >= 1
    assert empty_state["last_run_id"] is None


def test_multi_lane_turn_enforces_render_semaphores() -> None:
    """Verify _LONG_RENDER_SEMAPHORE serializes longform while _SHORT_RENDER permits 2 concurrent."""
    assert _SHORT_RENDER_SEMAPHORE._value == 2
    assert _LONG_RENDER_SEMAPHORE._value == 1

    # Acquire longform render guard: blocks second longform caller
    with acquire_render_guard(is_longform=True):
        assert _LONG_RENDER_SEMAPHORE._value == 0
        # Second acquire should fail immediately non-blocking
        assert _LONG_RENDER_SEMAPHORE.acquire(blocking=False) is False

        # Meanwhile, short render semaphore is completely independent and permits 2 callers
        with acquire_render_guard(is_longform=False):
            assert _SHORT_RENDER_SEMAPHORE._value == 1
            with acquire_render_guard(is_longform=False):
                assert _SHORT_RENDER_SEMAPHORE._value == 0
                assert _SHORT_RENDER_SEMAPHORE.acquire(blocking=False) is False

    # After exit, semaphores are restored
    assert _LONG_RENDER_SEMAPHORE._value == 1
    assert _SHORT_RENDER_SEMAPHORE._value == 2


def test_multi_lane_turn_offline_network_and_browser_isolation(
    integration_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify zero external network calls and zero browser imports during execution."""
    # Disallow network socket connect
    def forbid_network_connect(*args, **kwargs):
        raise ConnectionRefusedError("Offline isolation violated: unexpected external network call")

    monkeypatch.setattr(socket.socket, "connect", forbid_network_connect)

    config = LaneDaemonConfig(
        db_path=integration_db,
        max_ticks=1,
        interval_seconds=1,
        enable_sweeps=False,
    )
    orchestrator = LaneDaemonOrchestrator(config)

    # Tick execution should make zero external socket connections
    results = orchestrator.run_loop()
    assert isinstance(results, list)

    # Zero playwright or chromium in scheduler
    import src.orchestrator.scheduler as sched_mod
    src_content = open(sched_mod.__file__, "r", encoding="utf-8").read()
    assert "playwright" not in src_content.lower()
    assert "chromium" not in src_content.lower()
