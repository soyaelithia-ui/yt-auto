"""
src/mcp/tools/list_lanes.py - Canonical MCP tool for querying production lanes.
"""
from __future__ import annotations

import logging
import os
from typing import Annotated, Any, Dict, List, Optional

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from src.config import DEFAULT_DB_PATH
from src.core.domain import canonical_channel
from src.core.lanes import load_lanes, resolve_voice_for_lane
from src.core.repository import connect
from src.mcp.sanitizer import sanitize_payload

logger = logging.getLogger("mcp.tools.list_lanes")


def register_list_lanes_tool(server: MCPServer) -> None:
    """Register list_lanes tool on the MCPServer instance."""

    @server.tool(
        name="list_lanes",
        description="Query configured editorial production lanes, active scheduling states, cadence gaps, and resolved voice profiles.",
    )
    async def list_lanes(
        channel: Annotated[
            Optional[str],
            Field(description="Filter by channel ('moku', 'aelithia', 'scifi', or None for all)"),
        ] = None,
        include_paused: Annotated[
            bool,
            Field(description="Include paused or disabled lanes in listing"),
        ] = True,
        include_disabled: Annotated[
            bool,
            Field(description="Include paused or disabled lanes in listing"),
        ] = True,
    ) -> Dict[str, Any]:
        try:
            all_lanes = load_lanes(include_disabled=True)
            if channel and channel != "all":
                try:
                    target_ch = canonical_channel(channel).value
                    filtered_lanes = [l for l in all_lanes if l.channel.value == target_ch]
                except (ValueError, KeyError) as exc:
                    raise ToolError(f"Unknown channel filter '{channel}': {exc}") from exc
            else:
                filtered_lanes = list(all_lanes)

            lane_states: dict[str, dict[str, Any]] = {}
            if os.path.exists(DEFAULT_DB_PATH):
                try:
                    with connect(DEFAULT_DB_PATH, read_only=True) as conn:
                        rows = conn.execute("SELECT * FROM scheduler_lane_state").fetchall()
                        for r in rows:
                            lane_states[r["lane_id"]] = dict(r)
                except Exception as exc:
                    logger.debug("Failed reading scheduler_lane_state: %s", exc)

            results: List[Dict[str, Any]] = []
            for lane in filtered_lanes:
                state = lane_states.get(lane.id, {})
                paused = bool(state.get("paused", not lane.enabled))
                if not (include_paused and include_disabled) and paused:
                    continue

                voice = resolve_voice_for_lane(lane)
                results.append({
                    "id": lane.id,
                    "lane_id": lane.id,
                    "channel": lane.channel.value,
                    "story_type": lane.story_type,
                    "orientation": lane.orientation,
                    "resolution": f"{lane.expected_resolution[0]}x{lane.expected_resolution[1]}",
                    "duration_target_sec": lane.duration_target_sec,
                    "cadence_min_gap_seconds": lane.cadence_min_gap_seconds,
                    "visual_pipeline": lane.visual_pipeline,
                    "voice_profile": lane.voice_profile or lane.story_type,
                    "resolved_voice": voice,
                    "enabled": lane.enabled,
                    "paused": paused,
                    "pause_reason": state.get("pause_reason") or ("Disabled in config" if not lane.enabled else None),
                    "last_fired_at": state.get("last_fired_at"),
                    "next_due_at": state.get("next_due_at"),
                })

            return sanitize_payload({"lanes": results, "count": len(results)})

        except ToolError:
            raise
        except Exception as exc:
            logger.exception("Unexpected error in list_lanes: %s", exc)
            raise ToolError(f"list_lanes failed: {exc}") from exc
