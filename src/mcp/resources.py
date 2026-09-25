"""
src/mcp/resources.py - Resource Handlers for yt-auto MCP Server.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceNotFoundError

from src.api_health import check_all
from src.cli.handlers.status import cli_status
from src.config import BASE_DIR, DEFAULT_DB_PATH, SETTINGS, get_channel_settings
from src.core.lanes import DEFAULT_LANES_PATH
from src.mcp.sanitizer import sanitize_payload

logger = logging.getLogger("mcp.resources")


def register_resources(server: MCPServer) -> None:
    """Register all 3 canonical resources on the MCPServer instance."""

    # -------------------------------------------------------------------------
    # Resource 1: channels://{channel_name}/config
    # -------------------------------------------------------------------------
    @server.resource(
        "channels://{channel_name}/config",
        name="channel_config",
        description="Sanitized channel configuration profile (public_dict) without secret paths or credential exposure.",
        mime_type="application/json",
    )
    async def get_channel_config(channel_name: str) -> str:
        ch = str(channel_name).strip()
        # Security: reject path traversal and invalid characters
        if not re.match(r"^[a-zA-Z0-9_-]+$", ch):
            raise ResourceNotFoundError(f"Invalid channel identifier '{channel_name}'.")

        try:
            settings = get_channel_settings(ch.lower())
        except Exception as exc:
            valid_channels = list(SETTINGS.channels.keys())
            raise ResourceNotFoundError(
                f"Channel configuration '{channel_name}' not found. Available: {valid_channels}"
            ) from exc

        # Use canonical public_dict() which replaces secrets with presence booleans
        profile = settings.public_dict()
        clean = sanitize_payload(profile)
        return json.dumps(clean, indent=2, ensure_ascii=False)

    # -------------------------------------------------------------------------
    # Resource 2: lanes://catalog
    # -------------------------------------------------------------------------
    @server.resource(
        "lanes://catalog",
        name="lanes_catalog",
        description="Canonical production lane specifications and editorial configurations (config/lanes.json).",
        mime_type="application/json",
    )
    async def get_lanes_catalog() -> str:
        path = Path(DEFAULT_LANES_PATH)
        if not path.is_absolute():
            path = BASE_DIR / path

        if not path.is_file():
            raise ResourceNotFoundError(f"Lanes catalog configuration not found at {path}.")

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = json.load(f)
            clean = sanitize_payload(content)
            return json.dumps(clean, indent=2, ensure_ascii=False)
        except Exception as exc:
            logger.exception("Failed reading lanes catalog: %s", exc)
            raise ResourceNotFoundError(f"Failed to read lanes catalog: {exc}") from exc

    # -------------------------------------------------------------------------
    # Resource 3: system://health
    # -------------------------------------------------------------------------
    @server.resource(
        "system://health",
        name="system_health",
        description="Real-time system health metrics, storage headroom, queue depths, daemon heartbeat, and external API states.",
        mime_type="application/json",
    )
    async def get_system_health() -> str:
        try:
            from src.config import get_active_channel_key
            from src.observability.tube import TubeCollector

            st = cli_status(DEFAULT_DB_PATH)
            st["api_health"] = check_all(get_active_channel_key())

            collector = TubeCollector(DEFAULT_DB_PATH)
            stoppages = collector.sample_daemon_stoppages()
            db_health = collector.sample_database_health()
            cookie_health = collector.sample_cookie_health()
            mcp_health = collector.mcp_checker.evaluate_health()

            st["daemon_liveness_status"] = stoppages.daemon_liveness_status
            st["heartbeat_age_seconds"] = stoppages.heartbeat_age_seconds
            st["mcp_health"] = mcp_health.to_dict()
            st["cookie_health"] = cookie_health.to_dict()
            st["wal_status"] = db_health.wal_status

            clean = sanitize_payload(st)
            return json.dumps(clean, indent=2, ensure_ascii=False)
        except Exception as exc:
            logger.exception("Failed compiling system health resource: %s", exc)
            raise ResourceNotFoundError(f"Failed to compile system health: {exc}") from exc

    # -------------------------------------------------------------------------
    # Resource 4: system://tube
    # -------------------------------------------------------------------------
    @server.resource(
        "system://tube",
        name="system_tube",
        description="Comprehensive operational telemetry snapshot ('El Tubo') covering host resources, daemon stoppages, token burn, YouTube quotas, security incidents, and database health.",
        mime_type="application/json",
    )
    async def get_system_tube() -> str:
        try:
            from src.observability.tube import TubeCollector

            collector = TubeCollector(DEFAULT_DB_PATH)
            snapshot = collector.compile_snapshot()
            clean = sanitize_payload(snapshot.to_dict())
            return json.dumps(clean, indent=2, ensure_ascii=False)
        except Exception as exc:
            logger.exception("Failed compiling system tube resource: %s", exc)
            raise ResourceNotFoundError(f"Failed to compile system tube resource: {exc}") from exc

    # -------------------------------------------------------------------------
    # Resource 5: system://quotas
    # -------------------------------------------------------------------------
    @server.resource(
        "system://quotas",
        name="system_quotas",
        description="Multi-provider AI token burn rates, USD costs, and YouTube Data API v3 daily quota consumption.",
        mime_type="application/json",
    )
    async def get_system_quotas() -> str:
        try:
            from src.observability.quota import QuotaMonitor

            monitor = QuotaMonitor(DEFAULT_DB_PATH)
            burn = monitor.get_token_burn_summary().to_dict()
            yt = monitor.get_youtube_quota_metrics().to_dict()
            payload = {
                "token_burn": burn,
                "youtube_quotas": yt,
            }
            clean = sanitize_payload(payload)
            return json.dumps(clean, indent=2, ensure_ascii=False)
        except Exception as exc:
            logger.exception("Failed compiling system quotas resource: %s", exc)
            raise ResourceNotFoundError(f"Failed to compile system quotas resource: {exc}") from exc
