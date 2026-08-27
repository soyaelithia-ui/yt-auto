"""Observability pipe: run correlation, event persistence and alerts.

Public API:
* :func:`context.set_run_context` / :func:`context.update_run_context` —
  attach ``run_id``/``channel``/``stage`` correlation to logs and events.
* :func:`events.emit_event` / :func:`events.emit_error` — best-effort
  persistence to ``system_events`` + ``logs/events.jsonl``.
* :func:`alerts.send_operational_alert` — deduped Telegram pop-ups.
"""

from src.observability.context import (
    RunContext,
    clear_run_context,
    get_run_context,
    set_run_context,
    update_run_context,
)
from src.observability.events import emit_error, emit_event

__all__ = [
    "RunContext",
    "clear_run_context",
    "emit_error",
    "emit_event",
    "get_run_context",
    "set_run_context",
    "update_run_context",
]
