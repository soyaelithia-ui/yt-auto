"""src/mcp/tools/get_tube_status.py - Canonical MCP tool for comprehensive pipeline telemetry.

Exposes host CPU/RAM headroom, daemon heartbeat, active worker locks,
multi-provider token burn, YouTube Data API quotas, security incidents,
and SQLite database health ('El Tubo').
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Dict, Optional

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from src.config import DEFAULT_DB_PATH
from src.mcp.sanitizer import sanitize_payload
from src.observability.events import emit_event
from src.observability.tube import TubeCollector

logger = logging.getLogger("mcp.tools.get_tube_status")


def register_get_tube_status_tool(server: MCPServer) -> None:
    """Register get_tube_status tool on the MCPServer instance."""

    @server.tool(
        name="get_tube_status",
        description="Comprehensive operational telemetry hub inspecting host resources, multi-provider token burn, YouTube quota limits, stoppages, and incidents.",
    )
    async def get_tube_status(
        channel: Annotated[
            Optional[str],
            Field(description="Filter telemetry to a specific canonical channel (horror, drama, scifi)"),
        ] = None,
        window_hours: Annotated[
            int,
            Field(description="Observation window in hours for token burn and incident queries"),
        ] = 24,
        include_incidents: Annotated[
            bool,
            Field(description="Whether to include recent operational incidents"),
        ] = True,
        include_burn: Annotated[
            bool,
            Field(description="Whether to include multi-provider token burn and USD calculations"),
        ] = True,
        db_path: Annotated[
            Optional[str],
            Field(description="Path to SQLite database file (defaults to configured DEFAULT_DB_PATH)"),
        ] = None,
    ) -> Dict[str, Any]:
        target_db = db_path or DEFAULT_DB_PATH
        ch_filter = channel if channel not in ("all", "") else None
        hours = max(1, int(window_hours))

        try:
            collector = TubeCollector(db_path=target_db)
            snapshot = collector.compile_snapshot(channel=ch_filter, window_hours=hours)
            payload = snapshot.to_dict()

            if not include_incidents:
                payload["recent_incidents"] = []

            if not include_burn:
                payload["token_burn"] = {}

            return sanitize_payload(payload)

        except ToolError:
            raise
        except Exception as exc:
            logger.exception("Unexpected error in get_tube_status: %s", exc)
            try:
                emit_event(
                    "mcp_tool_failure",
                    level="ERROR",
                    message=f"MCP tool get_tube_status execution failed: {exc}",
                    details={
                        "tool": "get_tube_status",
                        "channel": channel,
                        "error": str(exc),
                    },
                    component="mcp",
                )
            except Exception:
                pass
            raise ToolError(f"get_tube_status failed: {exc}") from exc
