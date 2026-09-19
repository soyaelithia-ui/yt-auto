"""
src/mcp/tools/common.py - Shared helpers and utilities for canonical MCP tools.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Optional

from src.core.lanes import LaneProfile, load_lanes


def find_lane(lane_id: str) -> Optional[LaneProfile]:
    """Lookup a lane by ID (including disabled lanes and aliases)."""
    wanted = str(lane_id or "").strip()
    target_id = wanted
    if wanted == "scifi-chronicles-shorts":
        target_id = "scifi-singularity-shorts"

    for lane in load_lanes(include_disabled=True):
        if lane.id == target_id:
            if wanted == "scifi-chronicles-shorts":
                return replace(lane, id="scifi-chronicles-shorts")
            return lane
    return None
