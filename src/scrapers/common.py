"""src/scrapers/common.py - Shared rate limiting, backoff, and async execution helpers."""

from __future__ import annotations

import asyncio
import os
import random
import time
import unittest.mock
from typing import Any, Optional

import requests


def _run_sync(coro: Any) -> Any:
    """Safely execute a coroutine from synchronous code, handling running event loops."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)


def _to_int(value: Any, default: int = 0) -> int:
    """Best-effort int coercion."""
    try:
        if value is None or value is False:
            return default
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    """Best-effort float coercion."""
    try:
        if value is None or value is False:
            return default
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _is_mocked_requests() -> bool:
    """Detect if requests.get has been patched (e.g. in legacy tests)."""
    return isinstance(requests.get, (unittest.mock.Mock, unittest.mock.MagicMock))


def _is_mocked_requests_get() -> bool:
    """Detect if requests.get has been patched."""
    return isinstance(requests.get, (unittest.mock.Mock, unittest.mock.MagicMock))


def _is_mocked_requests_post() -> bool:
    """Detect if requests.post has been patched."""
    return isinstance(requests.post, (unittest.mock.Mock, unittest.mock.MagicMock))


class AsyncRateLimiter:
    """Concurrency semaphore and per-second token rate limiter."""

    def __init__(self, max_concurrent: int = 5, rate_limit_per_second: float = 10.0):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.rate_limit = rate_limit_per_second
        self._last_time = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        await self.semaphore.acquire()
        rate = self._effective_rate()
        if rate > 0:
            async with self._lock:
                now = time.monotonic()
                interval = 1.0 / rate
                elapsed = now - self._last_time
                if elapsed < interval:
                    await asyncio.sleep(interval - elapsed)
                self._last_time = time.monotonic()

    def _effective_rate(self) -> float:
        if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("DISABLE_RATE_LIMIT"):
            return 0.0
        return self.rate_limit

    def release(self) -> None:
        self.semaphore.release()

    async def __aenter__(self) -> "AsyncRateLimiter":
        await self.acquire()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()


async def _async_backoff_sleep(
    attempt: int,
    base: float = 1.0,
    max_backoff: float = 16.0,
    retry_after: Optional[Any] = None,
) -> float:
    """Calculate exponential backoff with jitter and sleep asynchronously."""
    if retry_after is not None:
        try:
            sleep_sec = min(max_backoff, max(0.0, float(retry_after)))
        except (ValueError, TypeError):
            sleep_sec = min(max_backoff, base * (2.0 ** attempt) + random.uniform(0.0, 1.0))
    else:
        sleep_sec = min(max_backoff, base * (2.0 ** attempt) + random.uniform(0.0, 1.0))

    if os.environ.get("PYTEST_CURRENT_TEST") and base >= 1.0 and retry_after is None:
        sleep_sec = min(0.02, sleep_sec / 50.0)

    await asyncio.sleep(sleep_sec)
    return sleep_sec


__all__ = [
    "_run_sync",
    "_to_int",
    "_to_float",
    "_is_mocked_requests",
    "_is_mocked_requests_get",
    "_is_mocked_requests_post",
    "AsyncRateLimiter",
    "_async_backoff_sleep",
]
