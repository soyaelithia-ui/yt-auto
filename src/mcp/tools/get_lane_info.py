"""
src/mcp/tools/get_lane_info.py - Canonical MCP tool for detailed production lane specification.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Annotated, Any, Dict

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from src.config import DEFAULT_DB_PATH
from src.core.contracts import RenderSpec
from src.core.lanes import load_lanes, resolve_voice_for_lane
from src.core.repository import connect
from src.mcp.sanitizer import sanitize_payload
from src.mcp.tools.common import find_lane

logger = logging.getLogger("mcp.tools.get_lane_info")


def register_get_lane_info_tool(server: MCPServer) -> None:
    """Register get_lane_info tool on the MCPServer instance."""

    @server.tool(
        name="get_lane_info",
        description="Retrieve in-depth specification, cadence, duration gates, word budget, visual pipeline, and sources for a single production lane.",
    )
    async def get_lane_info(
        lane_id: Annotated[
            str,
            Field(description="Unique lane identifier (e.g. 'moku-scp-shorts', 'moku-horror-long', 'aelithia-aita-long')"),
        ],
    ) -> Dict[str, Any]:
        # Security: validate lane_id format to prevent injection attacks
        if not lane_id or not re.match(r"^[a-zA-Z0-9_-]+$", lane_id):
            raise ToolError(f"Invalid lane_id format: '{lane_id}'.")

        try:
            lane = find_lane(lane_id)
            if lane is None:
                available = [l.id for l in load_lanes(include_disabled=True)]
                raise ToolError(f"Lane '{lane_id}' not found. Available lanes: {available}")

            state: dict[str, Any] = {}
            if os.path.exists(DEFAULT_DB_PATH):
                try:
                    with connect(DEFAULT_DB_PATH, read_only=True) as conn:
                        row = conn.execute(
                            "SELECT * FROM scheduler_lane_state WHERE lane_id = ?",
                            (lane.id,),
                        ).fetchone()
                        if row:
                            state = dict(row)
                except Exception as exc:
                    logger.debug("Failed reading state for lane '%s': %s", lane_id, exc)

            voice = resolve_voice_for_lane(lane)
            info = {
                "id": lane.id,
                "lane_id": lane.id,
                "channel": lane.channel.value,
                "story_type": lane.story_type,
                "orientation": lane.orientation,
                "resolution": [lane.expected_resolution[0], lane.expected_resolution[1]],
                "duration": {
                    "min_sec": lane.duration_min_sec,
                    "target_sec": lane.duration_target_sec,
                    "max_sec": lane.duration_max_sec,
                },
                "words": {
                    "min": lane.words_min,
                    "max": lane.words_max,
                    "recondense_max": lane.words_recondense_max,
                },
                "cadence_min_gap_seconds": lane.cadence_min_gap_seconds,
                "visual_pipeline": lane.visual_pipeline,
                "voice_profile": lane.voice_profile or lane.story_type,
                "resolved_voice": voice,
                "enabled": lane.enabled,
                "paused": bool(state.get("paused", not lane.enabled)),
                "pause_reason": state.get("pause_reason") or ("Disabled in config" if not lane.enabled else None),
                "last_fired_at": state.get("last_fired_at"),
                "next_due_at": state.get("next_due_at"),
                "consecutive_empty": state.get("consecutive_empty", 0),
                "sources": lane.sources,
                "background_audio": lane.background_audio,
            }
            render_threads = 4 if ("long" in lane.id.lower() or lane.orientation == "horizontal") else 2
            render_spec = RenderSpec(
                orientation=lane.orientation,
                duration_sec=float(lane.duration_target_sec),
                category=lane.story_type,
                threads=render_threads,
                fps=lane.fps,
                width=lane.expected_resolution[0],
                height=lane.expected_resolution[1],
            )
            render_spec.validate()
            info["render_spec"] = render_spec.to_dict()
            return sanitize_payload(info)

        except ToolError:
            raise
        except Exception as exc:
            logger.exception("Unexpected error in get_lane_info: %s", exc)
            raise ToolError(f"get_lane_info failed: {exc}") from exc
