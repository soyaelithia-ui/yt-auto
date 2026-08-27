"""Telegram callback long-poller for the human review gate.

Robustness contract (owner directive: bot must be robust):
- One poisoned update can never wedge the loop: the offset advances before
  dispatch, and handler crashes are contained per update.
- Network/API failures back off exponentially (capped) instead of hammering;
  repeated failures escalate to ERROR level, recovery is logged.
- A heartbeat exposes seconds since the last successful poll for future
  healthcheck/liveness wiring.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Optional

from src.log import get_logger
from review.telegram_bot import TelegramReviewBot

logger = get_logger("telegram.callbacks")

_BACKOFF_BASE_SECONDS = 0.5
_MAX_BACKOFF_SECONDS = 30.0


class PollerHeartbeat:
    """Thread-safe monotonic marker of the last successful poll cycle."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_ok = time.monotonic()

    def touch(self) -> None:
        with self._lock:
            self._last_ok = time.monotonic()

    def seconds_since_success(self) -> float:
        with self._lock:
            return time.monotonic() - self._last_ok


def _route_update(bot: TelegramReviewBot, update: dict[str, Any]) -> None:
    """Dispatch one update; never raises so a bad payload cannot stall the loop."""
    try:
        callback_query = update.get("callback_query")
        if isinstance(callback_query, dict):
            data = str(callback_query.get("data") or "")
            if data.startswith("ctl:"):
                bot.handle_control_callback(update)
            else:
                bot.handle_callback_query(update)
        elif isinstance(update.get("message"), dict):
            bot.handle_text_command(update)
    except Exception:
        logger.exception("Update handler crashed; update skipped")


def _sleep_interruptible(seconds: float, should_stop: Callable[[], bool]) -> None:
    deadline = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < deadline:
        if should_stop():
            return
        time.sleep(min(0.5, max(0.05, deadline - time.monotonic())))


def poll_callbacks(
    bot: TelegramReviewBot,
    should_stop: Callable[[], bool],
    poll_timeout: int = 25,
) -> PollerHeartbeat:
    """Consume updates until the daemon requests shutdown.

    Returns a :class:`PollerHeartbeat` so callers (or a future healthcheck)
    can detect a silently stalled poller.
    """
    offset: Optional[int] = None
    consecutive_failures = 0
    heartbeat = PollerHeartbeat()

    while not should_stop():
        try:
            updates = bot.get_updates(offset=offset, timeout=poll_timeout)
        except Exception as exc:
            consecutive_failures += 1
            delay = min(
                _MAX_BACKOFF_SECONDS,
                _BACKOFF_BASE_SECONDS * (2 ** min(consecutive_failures, 6)),
            )
            log = logger.error if consecutive_failures >= 3 else logger.warning
            log(
                "Telegram polling failed (%d consecutive): %s; retrying in %.1fs",
                consecutive_failures,
                exc,
                delay,
            )
            _sleep_interruptible(delay, should_stop)
            continue

        if consecutive_failures >= 3:
            logger.info(
                "Telegram polling recovered after %d consecutive failures",
                consecutive_failures,
            )
        consecutive_failures = 0
        heartbeat.touch()

        for update in updates:
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                # Advance BEFORE dispatch: a crashing handler must never pin
                # the poller to the same poisoned update forever.
                offset = update_id + 1
            _route_update(bot, update)
            if should_stop():
                break
    return heartbeat
