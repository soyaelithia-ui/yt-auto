"""Strongly-typed data contracts and slotted models for yt-auto core and pipeline."""

from __future__ import annotations

from src.core.contracts.pipeline import (
    ClaimedLeaseContext,
    PipelineContext,
    RunContext,
    _write_run_marker,
    active_heartbeat_scope,
)
from src.core.contracts.render import RenderSpec
from src.core.contracts.review import ReviewContract
from src.core.contracts.story import StoryRecord

__all__ = [
    "ClaimedLeaseContext",
    "PipelineContext",
    "RenderSpec",
    "ReviewContract",
    "RunContext",
    "StoryRecord",
    "_write_run_marker",
    "active_heartbeat_scope",
]
