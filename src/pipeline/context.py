"""Strongly-typed execution context for pipeline execution.

Backward-compatible facade delegating execution context contracts to src.core.contracts.pipeline.
"""

from __future__ import annotations

from src.core.contracts.pipeline import (
    ClaimedLeaseContext,
    PipelineContext,
    RunContext,
    _write_run_marker,
    active_heartbeat_scope,
)

__all__ = [
    "ClaimedLeaseContext",
    "PipelineContext",
    "RunContext",
    "_write_run_marker",
    "active_heartbeat_scope",
]
