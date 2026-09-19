"""
src/mcp/tools - Modular Canonical Tools Package for yt-auto MCP Server.
"""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from src.mcp.tools.audit_loop_catalog import register_audit_loop_catalog_tool
from src.mcp.tools.common import find_lane
from src.mcp.tools.get_lane_info import register_get_lane_info_tool
from src.mcp.tools.get_system_status import register_get_system_status_tool
from src.mcp.tools.list_lanes import register_list_lanes_tool
from src.mcp.tools.manage_queue import register_manage_queue_tool
from src.mcp.tools.query_loop_catalog import register_query_loop_catalog_tool
from src.mcp.tools.run_pipeline_dry_run import register_run_pipeline_dry_run_tool
from src.mcp.tools.system_preflight import register_system_preflight_tool
from src.mcp.tools.verify_integrity import register_verify_integrity_tool


def register_tools(server: MCPServer) -> None:
    """Register all 9 canonical tools on the MCPServer instance."""
    register_system_preflight_tool(server)
    register_list_lanes_tool(server)
    register_get_lane_info_tool(server)
    register_query_loop_catalog_tool(server)
    register_audit_loop_catalog_tool(server)
    register_run_pipeline_dry_run_tool(server)
    register_get_system_status_tool(server)
    register_manage_queue_tool(server)
    register_verify_integrity_tool(server)


__all__ = [
    "find_lane",
    "register_tools",
    "register_system_preflight_tool",
    "register_list_lanes_tool",
    "register_get_lane_info_tool",
    "register_query_loop_catalog_tool",
    "register_audit_loop_catalog_tool",
    "register_run_pipeline_dry_run_tool",
    "register_get_system_status_tool",
    "register_manage_queue_tool",
    "register_verify_integrity_tool",
]
