"""
src/mcp/tools/get_system_status.py - Canonical MCP tool for system status inspection.
"""
from __future__ import annotations

import logging
from typing import Annotated, Any, Dict, Optional

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from src.api_health import check_all
from src.cli.handlers.status import cli_status
from src.config import DEFAULT_DB_PATH
from src.core.lock import ChannelLock, ChannelLockError
from src.mcp.sanitizer import sanitize_payload

logger = logging.getLogger("mcp.tools.get_system_status")


def register_get_system_status_tool(server: MCPServer) -> None:
    """Register get_system_status tool on the MCPServer instance."""

    @server.tool(
        name="get_system_status",
        description="Inspect overall yt-auto system health, queue depths, daemon status, active process locks, and recent failure logs.",
    )
    async def get_system_status(
        db_path: Annotated[
            Optional[str],
            Field(description="Path to SQLite database file (defaults to configured DEFAULT_DB_PATH)"),
        ] = None,
        include_api_health: Annotated[
            bool,
            Field(description="Include real-time external API health checks"),
        ] = True,
        include_locks: Annotated[
            bool,
            Field(description="Include channel lock state inspection"),
        ] = True,
        include_recent_errors: Annotated[
            bool,
            Field(description="Include recent failure logs"),
        ] = True,
        error_limit: Annotated[
            int,
            Field(description="Maximum error logs to include"),
        ] = 10,
    ) -> Dict[str, Any]:
        try:
            target_db = db_path or DEFAULT_DB_PATH
            st = cli_status(target_db)

            # Ensure queue counts are directly accessible under both keys
            st["queue_counts"] = st.get("queue", {})
            st["counts"] = st.get("queue", {})

            if include_api_health:
                from src.config import get_active_channel_key
                st["api_health"] = check_all(get_active_channel_key())

            if include_locks:
                from src.core.channel_profile import ChannelProfileRegistry
                lock_status: Dict[str, str] = {}
                channels_to_check = ["global"] + (ChannelProfileRegistry.list_active_channel_ids() or ["horror", "drama", "scifi"])
                for ch in channels_to_check:
                    chk = ChannelLock(ch)
                    try:
                        acquired = chk.acquire(timeout=0.0)
                        if acquired:
                            chk.release()
                            lock_status[ch] = "UNLOCKED"
                        else:
                            lock_status[ch] = "LOCKED"
                    except ChannelLockError:
                        lock_status[ch] = "LOCKED"
                    except Exception:
                        lock_status[ch] = "UNKNOWN"
                st["locks"] = lock_status

            return sanitize_payload(st)

        except ToolError:
            raise
        except Exception as exc:
            logger.exception("Unexpected error in get_system_status: %s", exc)
            raise ToolError(f"get_system_status failed: {exc}") from exc
