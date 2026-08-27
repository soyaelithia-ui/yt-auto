"""Handler for 'lanes' CLI subcommand: inspect editorial lanes and scheduler states."""
from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from src.config import DEFAULT_DB_PATH
from src.core.domain import canonical_channel
from src.core.lanes import load_lanes, resolve_voice_for_lane
from src.core.repository import QueueRepository, connect

logger = logging.getLogger("cli.lanes")


def _format_timestamp(ts: int | float | None) -> str:
    if not ts or ts <= 0:
        return "Never"
    try:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%SZ")
    except Exception:
        return str(ts)


def handle_lanes(args: argparse.Namespace, parser: argparse.ArgumentParser | None = None) -> int:
    """Display configured production lanes and their real-time scheduler state."""
    db_path = getattr(args, "db_path", DEFAULT_DB_PATH)
    as_json = getattr(args, "json", False)
    channel_filter = getattr(args, "channel", "all") or "all"

    all_lanes = load_lanes()
    if channel_filter != "all":
        try:
            ch_key = canonical_channel(channel_filter).value
            lanes = [lane for lane in all_lanes if lane.channel.value == ch_key]
        except ValueError:
            lanes = [lane for lane in all_lanes if lane.channel.value == channel_filter]
    else:
        lanes = list(all_lanes)

    # Fetch scheduler state for each lane from DB
    repo = QueueRepository(db_path)
    now = int(time.time())
    lane_states: dict[str, dict[str, Any]] = {}
    try:
        with connect(db_path, read_only=True) as conn:
            rows = conn.execute("SELECT * FROM scheduler_lane_state").fetchall()
            for r in rows:
                lane_states[r["lane_id"]] = dict(r)
    except Exception:
        # If DB not initialized or table absent, continue gracefully
        pass

    results = []
    for lane in lanes:
        state = lane_states.get(lane.id) or {}
        voice = resolve_voice_for_lane(lane)
        paused = bool(state.get("paused", not lane.enabled))
        pause_reason = state.get("pause_reason") or ("Disabled in config" if not lane.enabled else None)
        next_due = state.get("next_due_at")
        last_fired = state.get("last_fired_at")
        
        info = {
            "lane_id": lane.id,
            "channel": lane.channel.value,
            "story_type": lane.story_type,
            "orientation": lane.orientation,
            "resolution": f"{lane.expected_resolution[0]}x{lane.expected_resolution[1]}",
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
            "paused": paused,
            "pause_reason": pause_reason,
            "last_fired_at": last_fired,
            "last_fired_at_formatted": _format_timestamp(last_fired),
            "next_due_at": next_due,
            "next_due_at_formatted": _format_timestamp(next_due),
            "consecutive_empty": state.get("consecutive_empty", 0),
            "last_run_id": state.get("last_run_id"),
        }
        results.append(info)

    if as_json:
        print(json.dumps({"lanes": results, "count": len(results)}, indent=2, ensure_ascii=False))
        return 0

    print("=" * 90)
    print("PRODUCTION LANES (yt-auto)")
    print("=" * 90)
    header = f"{'LANE ID':<20} {'CHANNEL':<10} {'ORIENTATION':<13} {'DURATION':<16} {'VOICE':<20} {'STATUS'}"
    print(header)
    print("-" * 90)

    for item in results:
        dur_str = f"{item['duration']['min_sec']}-{item['duration']['max_sec']}s ({item['duration']['target_sec']}s)"
        status_str = "PAUSED" if item["paused"] else "ACTIVE"
        if item["next_due_at"]:
            gap = item["next_due_at"] - now
            if gap <= 0:
                status_str += " (Due now)"
            else:
                status_str += f" (Due in {gap}s)"
        else:
            status_str += f" (Every {item['cadence_min_gap_seconds']}s)"
        
        voice_str = item["resolved_voice"]
        orient_str = f"{item['orientation']} ({item['resolution']})"
        row = f"{item['lane_id']:<20} {item['channel']:<10} {item['orientation']:<13} {dur_str:<16} {voice_str:<20} {status_str}"
        print(row)

    print("=" * 90)
    return 0
