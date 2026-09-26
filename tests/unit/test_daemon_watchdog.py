"""Watchdog: deterministic turn timeouts that do not block the daemon loop."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from src.daemon import (
    _await_future_responsive,
    _collect_futures_responsive,
)
from src.core.scheduler import LanePick
from src.core.domain import CanonicalChannel


def test_await_future_returns_result_without_timeout():
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(lambda: {"status": "OK"})
        result, timed_out = _await_future_responsive(
            future,
            timeout=2.0,
            database=":memory:",
            tick=0.05,
            touch_heartbeat=False,
        )
    assert timed_out is False
    assert result == {"status": "OK"}


def test_await_future_times_out_without_waiting_for_hang():
    stop = threading.Event()

    def hang():
        stop.wait(5)
        return "done"

    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(hang)
        started = time.monotonic()
        result, timed_out = _await_future_responsive(
            future,
            timeout=0.2,
            database=":memory:",
            tick=0.05,
            touch_heartbeat=False,
        )
        elapsed = time.monotonic() - started
    finally:
        stop.set()
        pool.shutdown(wait=True)

    assert timed_out is True
    assert result is None
    assert elapsed < 1.5


def test_collect_futures_records_timeout_for_pending_lane():
    stop = threading.Event()
    pick = LanePick(
        lane_id="horror-scp-shorts",
        channel=CanonicalChannel.HORROR,
        fired_at=0,
        next_due_at=1,
    )

    def hang():
        stop.wait(5)
        return {"status": "PUBLISHED", "lane": pick.lane_id}

    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(hang)
        started = time.monotonic()
        results = _collect_futures_responsive(
            {future: pick},
            timeout=0.2,
            database=":memory:",
            tick=0.05,
            touch_heartbeat=False,
        )
        elapsed = time.monotonic() - started
    finally:
        stop.set()
        pool.shutdown(wait=True)

    assert elapsed < 1.5
    assert results[0]["status"] == "RETRYABLE_FAILED"
    assert results[0]["error_code"] == "timeout"
    assert results[0]["lane"] == "horror-scp-shorts"


def test_timeout_terminates_descendant_ffmpeg_outside_tests(monkeypatch):
    stop = threading.Event()
    pick = LanePick(
        lane_id="horror-scp-shorts",
        channel=CanonicalChannel.HORROR,
        fired_at=0,
        next_due_at=1,
    )
    calls: list[dict] = []

    def hang():
        stop.wait(5)
        return {"status": "PUBLISHED"}

    monkeypatch.setattr("src.config.is_test_environment", lambda: False)
    monkeypatch.setattr("src.daemon.reap_zombies", lambda: 0)
    monkeypatch.setattr(
        "src.core.process_watch.terminate_hung_ffmpeg",
        lambda **kwargs: calls.append(kwargs) or {"signaled": [1], "killed": []},
    )

    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(hang)
        results = _collect_futures_responsive(
            {future: pick},
            timeout=0.2,
            database=":memory:",
            tick=0.05,
            touch_heartbeat=False,
        )
    finally:
        stop.set()
        pool.shutdown(wait=True)

    assert results[0]["error_code"] == "timeout"
    assert calls
    assert calls[0]["max_age_seconds"] == 0
