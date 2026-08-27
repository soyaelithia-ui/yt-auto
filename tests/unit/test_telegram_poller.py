"""Robustness tests for the Telegram update poller."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.telegram import callbacks as cb


class FakeBot:
    """Records routing calls; can raise per update-id or on get_updates."""

    def __init__(self, batches):
        self.initial_batches = len(batches)
        self.batches = list(batches)
        self.calls: list[int | None] = []
        self.polls = 0
        self.routed: dict[str, list[int]] = {"ctl": [], "review": [], "msg": []}
        self.crash_ids: set[int] = set()

    def get_updates(self, offset=None, timeout=25):
        self.polls += 1
        self.calls.append(offset)
        if not self.batches:
            return []
        batch = self.batches.pop(0)
        if isinstance(batch, Exception):
            raise batch
        return batch

    def handle_control_callback(self, update):
        self._route("ctl", update)

    def handle_callback_query(self, update):
        self._route("review", update)

    def handle_text_command(self, update):
        self._route("msg", update)

    def _route(self, key: str, update: dict):
        uid = update["update_id"]
        if uid in self.crash_ids:
            raise RuntimeError("handler boom")
        self.routed[key].append(uid)


def _upd(uid: int) -> dict:
    return {"update_id": uid}


def _cbq_update(uid: int, data: str) -> dict:
    return {"update_id": uid, "callback_query": {"id": "c", "data": data}}


def _msg_update(uid: int) -> dict:
    return {"update_id": uid, "message": {"text": "/menu"}}


def test_routes_ctl_review_and_message(bot=None):
    fb = FakeBot(
        [
            [_cbq_update(1, "ctl:menu"), _cbq_update(2, "approve:j1")],
            [_msg_update(3)],
        ]
    )
    cb.poll_callbacks(fb, lambda: fb.polls >= 2)
    assert fb.routed["ctl"] == [1]
    assert fb.routed["review"] == [2]
    assert fb.routed["msg"] == [3]


def test_handler_crash_skips_poison_but_keeps_batch():
    fb = FakeBot([[_msg_update(1), _msg_update(2), _msg_update(3)], []])
    fb.crash_ids = {2}
    cb.poll_callbacks(fb, lambda: fb.polls >= 2)
    # Poisoned id=2 skipped; neighbors still processed.
    assert fb.routed["msg"] == [1, 3]


def test_offset_advances_past_crashing_update():
    fb = FakeBot([[_upd(7), _upd(8)], []])
    fb.crash_ids = {8}

    class StopAfterTwoPolls:
        def __init__(self, target_fb):
            self.fb = target_fb

        def __call__(self):
            return self.fb.polls >= 2

    cb.poll_callbacks(fb, StopAfterTwoPolls(fb))
    # Second poll requested offset=9 (past the crashing update), not stuck at 8.
    assert fb.calls == [None, 9]


def test_backoff_on_failures_then_recovery(monkeypatch):
    monkeypatch.setattr(cb, "_BACKOFF_BASE_SECONDS", 0.001)
    error = RuntimeError("network down")
    fb = FakeBot([error, error, []])

    heartbeat = cb.poll_callbacks(fb, lambda: fb.polls >= 3)

    assert fb.polls == 3
    assert heartbeat.seconds_since_success() < 5.0


def test_heartbeat_touched_on_success():
    fb = FakeBot([[_upd(1)]])
    hb = cb.poll_callbacks(fb, lambda: fb.polls >= 1)
    assert hb.seconds_since_success() < 5.0


def test_stop_requested_during_backoff_exits_quickly(monkeypatch):
    monkeypatch.setattr(cb, "_BACKOFF_BASE_SECONDS", 60)  # would sleep long
    fb = FakeBot([RuntimeError("down")])

    polls = {"n": 0}

    def should_stop() -> bool:
        # Stop becomes true right after the first failed attempt.
        return polls["n"] >= 1

    original_get = fb.get_updates

    def counting_get(offset=None, timeout=25):
        polls["n"] += 1
        return original_get(offset=offset, timeout=timeout)

    fb.get_updates = counting_get  # type: ignore[method-assign]
    cb.poll_callbacks(fb, should_stop)
    assert fb.polls == 1  # no second attempt after stop during backoff
