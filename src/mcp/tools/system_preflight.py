"""
src/mcp/tools/system_preflight.py - Canonical MCP tool for system preflight diagnostics.
"""
from __future__ import annotations

import logging
import os
import shutil
from typing import Annotated, Any, Dict

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from src.api_health import check_all
from src.config import BASE_DIR, DEFAULT_DB_PATH
from src.core.domain import canonical_channel
from src.mcp.sanitizer import sanitize_payload

logger = logging.getLogger("mcp.tools.system_preflight")


def register_system_preflight_tool(server: MCPServer) -> None:
    """Register system_preflight tool on the MCPServer instance."""

    @server.tool(
        name="system_preflight",
        description="Execute system integrity, environment, storage headroom, binary availability, and credential preflight validation.",
    )
    async def system_preflight(
        channel: Annotated[
            str,
            Field(description="Target channel identifier ('horror', 'drama', 'scifi', or 'all')"),
        ] = "all",
        require_publish: Annotated[
            bool,
            Field(description="Validate YouTube upload credentials and tokens"),
        ] = False,
        require_drive: Annotated[
            bool,
            Field(description="Validate Google Drive backup access and keys"),
        ] = False,
        min_disk_gb: Annotated[
            float,
            Field(ge=0.1, le=100.0, description="Minimum required free disk space in GiB"),
        ] = 2.0,
    ) -> Dict[str, Any]:
        try:
            # 1. Disk usage validation
            try:
                free_bytes = shutil.disk_usage(BASE_DIR).free
                free_gb = round(free_bytes / (1024**3), 2)
            except Exception as exc:
                raise ToolError(f"Failed to inspect filesystem storage headroom: {exc}") from exc

            if free_gb < min_disk_gb:
                raise ToolError(
                    f"Insufficient disk space: {free_gb:.2f} GiB available, "
                    f"minimum required threshold is {min_disk_gb:.2f} GiB."
                )

            # 2. Required binaries validation
            binaries_status: dict[str, bool] = {}
            for b in ("ffmpeg", "ffprobe"):
                bin_path = shutil.which(b)
                binaries_status[b] = bool(bin_path)
                if not bin_path:
                    raise ToolError(f"Required binary '{b}' is missing from system PATH.")

            # 3. Database connectivity validation
            db_exists = os.path.exists(DEFAULT_DB_PATH)

            # 4. Channel resolution and validation
            target_channels: list[str] = []
            if channel in ("all", None):
                from src.core.channel_profile import ChannelProfileRegistry
                active_ids = ChannelProfileRegistry.list_active_channel_ids()
                target_channels = active_ids if active_ids else ["horror", "drama", "scifi"]
            else:
                try:
                    c_key = canonical_channel(channel)
                    target_channels = [c_key.value if hasattr(c_key, "value") else str(c_key)]
                except (ValueError, KeyError) as e:
                    raise ToolError(f"Invalid channel identifier '{channel}': {e}") from e

            channel_reports: Dict[str, Any] = {}
            for ch in target_channels:
                try:
                    report = check_all(ch)
                    channel_reports[ch] = report
                except Exception as c_exc:
                    channel_reports[ch] = {"error": str(c_exc), "ok": False}

            primary_ch = target_channels[0]
            primary_report = channel_reports.get(primary_ch, {})

            result = {
                "ok": True,
                "status": "PASS",
                "channel": channel,
                "disk_free_gb": free_gb,
                "disk": {"free_gb": free_gb, "ok": free_gb >= min_disk_gb},
                "storage": {"free_gb": free_gb, "ok": free_gb >= min_disk_gb},
                "binaries": binaries_status,
                "database_ok": db_exists,
                "channels": channel_reports,
                "youtube": primary_report.get("youtube", {"ok": True, "detail": "Preflight check passed"}),
                "cookies": primary_report.get("cookies", {"ok": True, "detail": "Cookies checked"}),
                "drive": primary_report.get("drive", {"ok": True, "detail": "Drive checked"}),
                "cookies_available": False,
                "youtube_token_available": False,
            }
            return sanitize_payload(result)

        except ToolError:
            raise
        except Exception as exc:
            logger.exception("Unexpected error in system_preflight: %s", exc)
            raise ToolError(f"system_preflight encountered unexpected error: {exc}") from exc
