"""
src/mcp/tools/run_pipeline_dry_run.py - Canonical MCP tool for offline zero-quota synthetic dry runs.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Annotated, Any, Dict, Optional

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from src.config import DEFAULT_DB_PATH
from src.core.contracts import RenderSpec
from src.core.lock import ChannelLock, ChannelLockError
from src.mcp.sanitizer import sanitize_payload
from src.mcp.tools.common import find_lane

from contextlib import contextmanager

logger = logging.getLogger("mcp.tools.run_pipeline_dry_run")


@contextmanager
def _mock_pipeline_env(enabled: bool):
    if not enabled:
        yield
        return
    orig_env = {}
    for k in ("TEST_MODE", "MOCK_DRIVE_UPLOAD", "MOCK_YOUTUBE_UPLOAD"):
        orig_env[k] = os.environ.get(k)
        os.environ[k] = "1"
    try:
        yield
    finally:
        for k, v in orig_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _build_dry_run_render_spec(lane: Any) -> RenderSpec:
    spec = RenderSpec(
        orientation=lane.orientation,
        duration_sec=float(lane.duration_target_sec),
        category=lane.story_type,
        threads=2,
        fps=lane.fps,
        width=lane.expected_resolution[0],
        height=lane.expected_resolution[1],
        stream_copy=True,
    )
    spec.validate()
    return spec


def register_run_pipeline_dry_run_tool(server: MCPServer) -> None:
    """Register run_pipeline_dry_run tool on the MCPServer instance."""

    @server.tool(
        name="run_pipeline_dry_run",
        description="Execute fast synthetic test composition (--lane <lane> -t) with zero external API quota usage and stream-copy rendering.",
    )
    async def run_pipeline_dry_run(
        lane_id: Annotated[
            str,
            Field(description="Target production lane identifier (e.g. 'horror-scp-shorts', 'horror-long', 'drama-shorts')"),
        ],
        topic: Annotated[
            Optional[str],
            Field(description="Optional custom topic for synthetic generation"),
        ] = None,
        story_id: Annotated[
            Optional[str],
            Field(description="Optional story ID to target (if None, synthetic test story is executed)"),
        ] = None,
        channel: Annotated[
            Optional[str],
            Field(description="Optional channel override"),
        ] = None,
        mock_all: Annotated[
            bool,
            Field(description="Enforce synthetic zero-quota offline mode (mock TTS, mock LLM, mock YouTube)"),
        ] = True,
    ) -> Dict[str, Any]:
        # Validate lane_id
        if not lane_id or not re.match(r"^[a-zA-Z0-9_-]+$", lane_id):
            raise ToolError(f"Invalid lane_id format: '{lane_id}'.")

        lane = find_lane(lane_id)
        if lane is None:
            raise ToolError(f"Lane '{lane_id}' does not exist in configuration.")

        ch_name = channel or lane.channel.value
        actual_lane_id = lane.id
        if actual_lane_id == "scifi-chronicles-shorts":
            actual_lane_id = "scifi-singularity-shorts"

        lock = ChannelLock(ch_name, timeout=5.0)

        try:
            lock.acquire()
        except ChannelLockError as lock_err:
            raise ToolError(
                f"Cannot execute dry run for lane '{lane_id}': Channel [{ch_name}] lock is currently held ({lock_err})."
            ) from lock_err

        try:
            with _mock_pipeline_env(mock_all):
                from src.orchestrator.pipeline import PipelineOrchestrator

                orch = PipelineOrchestrator(db_path=DEFAULT_DB_PATH)
                effective_topic = topic or f"Test Dry Run {lane.story_type} {lane.id}"

                res = orch.run_channel(
                    channel=ch_name,
                    topic=effective_topic,
                    story_id=story_id,
                    lane_id=actual_lane_id,
                    dry_run=True,
                    skip_lock=True,
                )

                dry_render_spec = _build_dry_run_render_spec(lane)
                return sanitize_payload({
                    "ok": True,
                    "status": res.status,
                    "dry_run": True,
                    "upload_skipped": True,
                    "lane_id": lane_id,
                    "channel": ch_name,
                    "story_id": res.story_id,
                    "work_dir": res.work_dir,
                    "video_file": None,
                    "render_spec": dry_render_spec.to_dict(),
                    "facts": {"dry_run": True, "offline": True, "quota_used": 0},
                })

        except ToolError:
            raise
        except Exception as exc:
            logger.exception("Dry run execution crashed for lane '%s': %s", lane_id, exc)
            raise ToolError(f"Pipeline dry run failed for lane '{lane_id}': {exc}") from exc
        finally:
            lock.release()
