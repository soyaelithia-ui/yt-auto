"""
src/mcp/tools/common.py - Shared helpers and utilities for canonical MCP tools.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Optional

from src.core.lanes import LANE_ALIASES, LaneProfile, load_lanes


def find_lane(lane_id: str) -> Optional[LaneProfile]:
    """Lookup a lane by ID (including disabled lanes and aliases)."""
    wanted = str(lane_id or "").strip()
    wanted_lower = wanted.lower()
    target_id = LANE_ALIASES.get(wanted_lower, wanted_lower)

    for lane in load_lanes(include_disabled=True):
        lane_id_lower = lane.id.lower()
        if lane_id_lower in (wanted_lower, target_id):
            if wanted_lower == "scifi-chronicles-shorts":
                return replace(lane, id="scifi-chronicles-shorts")
            return lane
    return None
