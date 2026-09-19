"""
src/mcp/tools.py - Backward-compatible facade delegating to src.mcp.tools package.
"""
from __future__ import annotations

from src.mcp.tools import (
    find_lane,
    register_tools,
    register_system_preflight_tool,
    register_list_lanes_tool,
    register_get_lane_info_tool,
    register_query_loop_catalog_tool,
    register_audit_loop_catalog_tool,
    register_run_pipeline_dry_run_tool,
    register_get_system_status_tool,
    register_manage_queue_tool,
    register_verify_integrity_tool,
)

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
