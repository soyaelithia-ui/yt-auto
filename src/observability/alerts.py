"""Operational Telegram alerts with per-subject dedupe.

Used for "the system stopped, here is why" pop-ups: daemon crash recovery,
resource-guard pauses and channel circuit-breaker trips. Alerts are
best-effort (never raise), skipped entirely in test environments, and the
same subject is not repeated within ``YT_ALERT_DEDUPE_SECONDS``.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_LAST_SENT: dict[str, float] = {}


def _dedupe_seconds() -> int:
    raw = os.environ.get("YT_ALERT_DEDUPE_SECONDS", "600")
    try:
        return max(0, int(raw))
    except ValueError:
        return 600


def _subject_key(subject: str) -> str:
    return hashlib.sha256(subject.encode("utf-8")).hexdigest()[:16]


def _should_send(key: str, now: float, interval: int) -> bool:
    with _LOCK:
        last = _LAST_SENT.get(key)
        if last is not None and (now - last) < interval:
            return False
        _LAST_SENT[key] = now
        # keep memory bounded
        if len(_LAST_SENT) > 128:
            for stale in sorted(_LAST_SENT, key=_LAST_SENT.get)[:64]:
                _LAST_SENT.pop(stale, None)
        return True


def send_operational_alert(
    subject: str,
    body: str,
    *,
    photo_path: str | None = None,
    min_interval_seconds: int | None = None,
    force: bool = False,
) -> bool:
    """Send a Telegram operational alert; returns True when sent.

    Dedupe is keyed on ``subject``. Pass ``force=True`` to bypass it
    (e.g. manual CLI diagnostics). If ``photo_path`` is provided and valid,
    it delivers the screenshot with the alert caption.
    """
    from src.config import is_test_environment

    if is_test_environment():
        logger.info("[alert suppressed:test] %s — %s (photo: %s)", subject, body, photo_path)
        return False

    interval = (
        max(0, int(min_interval_seconds))
        if min_interval_seconds is not None
        else _dedupe_seconds()
    )
    key = _subject_key(subject)
    if not force and not _should_send(key, time.time(), interval):
        logger.debug("alert deduped: %s", subject)
        return False

    text = f"⚠️ {subject}\n\n{body}"
    try:
        from src.telegram.notifier import TelegramNotifier

        notifier = TelegramNotifier()
        if photo_path and os.path.isfile(photo_path):
            result = notifier.send_photo(photo_path, caption=text[:1024])
            if not bool(getattr(result, "success", getattr(result, "ok", True))):
                result = notifier.send_message(text[:3900])
        else:
            result = notifier.send_message(text[:3900])
        ok = bool(getattr(result, "success", getattr(result, "ok", True)))
    except Exception:
        logger.warning("operational alert delivery failed", exc_info=True)
        return False
    if not ok:
        logger.warning("operational alert rejected by Telegram: %s", subject)
    return ok
