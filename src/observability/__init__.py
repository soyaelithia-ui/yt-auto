"""Observability pipe: run correlation, event persistence, alerts, and El Tubo hub.

Public API:
* :func:`context.set_run_context` / :func:`context.update_run_context` —
  attach ``run_id``/``channel``/``stage`` correlation to logs and events.
* :func:`events.emit_event` / :func:`events.emit_error` — best-effort
  persistence to ``system_events`` + ``logs/events.jsonl``.
* :func:`alerts.send_operational_alert` — deduped Telegram pop-ups.
* :class:`tube.TubeCollector` — centralized telemetry snapshot compiler.
* :class:`quota.QuotaMonitor` — multi-provider and YouTube quota tracker.
* :class:`mcp_health.MCPHealthChecker` — MCP server and SSOT parity inspector.
"""

from typing import Any

from src.observability.alerts import send_operational_alert
from src.observability.context import (
    RunContext,
    clear_run_context,
    get_run_context,
    set_run_context,
    update_run_context,
)
from src.observability.events import emit_error, emit_event

__all__ = [
    "AssetRejectionSummary",
    "CookieIncidentMetrics",
    "DaemonStoppageMetrics",
    "DatabaseHealthMetrics",
    "HostResourceMetrics",
    "MCPHealthChecker",
    "MCPHealthMetrics",
    "PromptLeakMetrics",
    "QuotaMonitor",
    "RunContext",
    "TokenBurnSummary",
    "TubeCollector",
    "TubeSnapshot",
    "YouTubeQuotaMetrics",
    "clear_run_context",
    "emit_error",
    "emit_event",
    "get_run_context",
    "send_operational_alert",
    "set_run_context",
    "update_run_context",
]


def __getattr__(name: str) -> Any:
    if name in (
        "TubeCollector",
        "TubeSnapshot",
        "HostResourceMetrics",
        "DaemonStoppageMetrics",
        "TokenBurnSummary",
        "CookieIncidentMetrics",
        "PromptLeakMetrics",
        "DatabaseHealthMetrics",
        "AssetRejectionSummary",
    ):
        import src.observability.tube as _tube

        return getattr(_tube, name)

    if name in ("QuotaMonitor", "YouTubeQuotaMetrics"):
        import src.observability.quota as _quota

        return getattr(_quota, name)

    if name in ("MCPHealthChecker", "MCPHealthMetrics"):
        import src.observability.mcp_health as _mcp_health

        return getattr(_mcp_health, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
