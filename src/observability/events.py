"""Best-effort observability event emitter.

``emit_event`` persists a structured event to the ``system_events`` table
(migration 004) and mirrors it as one JSON line in ``logs/events.jsonl``.

Design guarantees:
* Never raises — telemetry failures must never break the pipeline. On any
  error it falls back to standard logging.
* Lazy imports keep module import cheap and avoid import cycles with
  :mod:`src.config` / :mod:`src.core.repository`.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_JSONL_LOCK = threading.Lock()


def _events_log_path() -> Path:
    from src.config import BASE_DIR

    return Path(os.environ.get("YT_EVENTS_LOG_PATH") or (BASE_DIR / "logs" / "events.jsonl"))


def _default_db_path() -> str:
    from src.config import DEFAULT_DB_PATH

    return str(DEFAULT_DB_PATH)


def _utc_ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _rotate_jsonl_if_needed(path: "Path") -> None:
    """Size-based rotation: events.jsonl -> events.jsonl.1 -> ... (keep N).

    Mirrors the main logger's rotation scheme with stdlib-only machinery.
    Never raises: emission must survive any filesystem hiccup.
    """
    try:
        try:
            max_bytes = int(os.environ.get("YT_EVENTS_LOG_MAX_BYTES", str(20 * 1024 * 1024)))
        except ValueError:
            max_bytes = 20 * 1024 * 1024
        try:
            backups = max(1, int(os.environ.get("YT_EVENTS_LOG_BACKUPS", "3")))
        except ValueError:
            backups = 3
        if not path.exists() or path.stat().st_size < max_bytes:
            return
        # Shift .N-1 -> .N ... .1 -> .2, then current -> .1
        for idx in range(backups - 1, 0, -1):
            src = path.with_suffix(path.suffix + f".{idx}")
            dst = path.with_suffix(path.suffix + f".{idx + 1}")
            if src.exists():
                os.replace(src, dst)
        os.replace(path, path.with_suffix(path.suffix + ".1"))
    except OSError:
        pass


def _append_jsonl(record: dict[str, Any]) -> None:
    path = _events_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, default=str)
    with _JSONL_LOCK:
        _rotate_jsonl_if_needed(path)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def emit_event(
    event_type: str,
    *,
    level: str = "INFO",
    message: str | None = None,
    error_code: str | None = None,
    details: dict[str, Any] | None = None,
    db_path: str | None = None,
    run_id: str | None = None,
    story_id: str | None = None,
    channel: str | None = None,
    component: str | None = None,
    stage: str | None = None,
) -> bool:
    """Record one observability event; returns True when fully persisted.

    Correlation fields default to the active :class:`RunContext` when not
    provided explicitly, so callers inside a pipeline turn only need to pass
    what is specific to the event.
    """
    from src.observability.context import get_run_context

    context = get_run_context()
    record: dict[str, Any] = {
        "ts": _utc_ts(),
        "level": str(level).upper(),
        "event_type": event_type,
        "run_id": run_id or context.run_id,
        "story_id": story_id or context.story_id,
        "channel": channel or context.channel,
        "component": component or context.component,
        "stage": stage or context.stage,
        "error_code": error_code,
        "message": message,
        "details": details or {},
    }
    try:
        from src.core.repository import QueueRepository

        QueueRepository(db_path or _default_db_path()).record_system_event(
            event_type,
            level=record["level"],
            run_id=record["run_id"],
            story_id=record["story_id"],
            channel=record["channel"],
            component=record["component"],
            stage=record["stage"],
            error_code=record["error_code"],
            message=record["message"],
            details=record["details"],
        )
    except Exception:  # telemetry must never break the pipeline
        logger.debug("system_events insert failed", exc_info=True)
        persisted = False
    else:
        persisted = True

    try:
        record["persisted"] = persisted
        _append_jsonl(record)
    except Exception:
        logger.debug("events.jsonl mirror failed", exc_info=True)

    return persisted


def emit_error(
    event_type: str,
    exc: BaseException,
    *,
    component: str | None = None,
    stage: str | None = None,
    db_path: str | None = None,
) -> bool:
    """Emit an ERROR event enriched with ``format_error_diagnostics`` payload."""
    from src.core.errors import format_error_diagnostics

    diagnostics = format_error_diagnostics(exc)
    code = getattr(exc, "code", None) or getattr(exc, "component", None)
    return emit_event(
        event_type,
        level="ERROR",
        message=str(exc),
        error_code=str(code) if code else type(exc).__name__,
        details={"diagnostics": diagnostics},
        db_path=db_path,
        component=component,
        stage=stage,
    )
