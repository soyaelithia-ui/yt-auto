"""Run-scoped context propagation for the observability pipe.

A single ``ContextVar`` carries ``{run_id, story_id, channel, component,
stage}`` for every thread/coroutine involved in a pipeline turn. The logging
filter in :mod:`src.log` reads it to annotate log records, so
existing call sites gain correlation without any signature changes.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True)
class RunContext:
    """Correlation identifiers attached to logs and observability events."""

    run_id: str | None = None
    story_id: str | None = None
    channel: str | None = None
    component: str | None = None
    stage: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def with_updates(self, **changes: Any) -> "RunContext":
        payload = {k: v for k, v in changes.items() if k != "extra"}
        extra = {**self.extra, **(changes.get("extra") or {})}
        return replace(self, extra=extra, **payload)


_CONTEXT: contextvars.ContextVar[RunContext | None] = contextvars.ContextVar(
    "yt_auto_run_context", default=None
)


def get_run_context() -> RunContext:
    """Return the active context (never ``None``; empty when unset)."""
    return _CONTEXT.get() or RunContext()


def set_run_context(**fields: Any) -> RunContext:
    """Set (replacing) the active run context and return it."""
    context = RunContext(**fields)
    _CONTEXT.set(context)
    return context


def update_run_context(**fields: Any) -> RunContext:
    """Merge fields into the active run context and return the new one."""
    context = get_run_context().with_updates(**fields)
    _CONTEXT.set(context)
    return context


def clear_run_context() -> None:
    """Reset the context (used between turns / in test teardown)."""
    _CONTEXT.set(None)
