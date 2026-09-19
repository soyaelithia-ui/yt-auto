"""
src/mcp/tools/manage_queue.py - Canonical MCP tool for story queue management, review gating, and pause/resume.
"""
from __future__ import annotations

import logging
import os
from typing import Annotated, Any, Dict, Optional

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from src.config import DEFAULT_DB_PATH
from src.core.contracts import StoryRecord
from src.core.domain import canonical_channel
from src.core.repository import QueueRepository, connect
from src.mcp.sanitizer import sanitize_payload

logger = logging.getLogger("mcp.tools.manage_queue")


def _handle_list(target_db: str, channel: Optional[str], limit: int) -> Dict[str, Any]:
    stories = []
    if os.path.exists(target_db):
        with connect(target_db, read_only=True) as conn:
            query = "SELECT story_id, channel, title, status, created_at, updated_at, error_msg FROM stories"
            params = []
            if channel:
                ch_key = canonical_channel(channel).value
                query += " WHERE channel = ?"
                params.append(ch_key)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(max(0, limit))
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            for row in cursor.fetchall():
                stories.append(StoryRecord.from_row(row).to_dict())
    return sanitize_payload({
        "ok": True,
        "action": "list",
        "items": stories,
        "stories": stories,
        "count": len(stories),
    })


def _handle_pending_review(target_db: str, limit: int) -> Dict[str, Any]:
    pending = []
    if os.path.exists(target_db):
        with connect(target_db, read_only=True) as conn:
            query = (
                "SELECT story_id, channel, title, status, created_at, updated_at "
                "FROM stories WHERE status IN ('PENDING_REVIEW', 'READY_TO_PUBLISH') "
                "ORDER BY updated_at DESC LIMIT ?"
            )
            cursor = conn.cursor()
            cursor.execute(query, (max(0, limit),))
            for row in cursor.fetchall():
                pending.append(StoryRecord.from_row(row).to_dict())
    return sanitize_payload({
        "ok": True,
        "action": "pending_review",
        "items": pending,
        "pending_items": pending,
        "count": len(pending),
    })


def _handle_pause(target_db: str, channel: Optional[str], eff_reason: str) -> Dict[str, Any]:
    if not channel:
        raise ToolError("Parameter 'channel' is required for pause action.")
    ch_key = canonical_channel(channel)
    repo = QueueRepository(target_db)
    repo.initialize()
    repo.pause(ch_key, eff_reason)
    return sanitize_payload({
        "ok": True,
        "action": "pause",
        "channel": ch_key.value,
        "paused": True,
        "reason": eff_reason,
    })


def _handle_resume(target_db: str, channel: Optional[str]) -> Dict[str, Any]:
    if not channel:
        raise ToolError("Parameter 'channel' is required for resume action.")
    ch_key = canonical_channel(channel)
    repo = QueueRepository(target_db)
    repo.initialize()
    repo.resume(ch_key)
    return sanitize_payload({
        "ok": True,
        "action": "resume",
        "channel": ch_key.value,
        "paused": False,
    })


def _handle_sweep() -> Dict[str, Any]:
    from src.telegram import check_pending_approvals
    published = check_pending_approvals()
    return sanitize_payload({
        "ok": True,
        "action": "sweep",
        "published_count": len(published),
        "published": published,
    })


def register_manage_queue_tool(server: MCPServer) -> None:
    """Register manage_queue tool on the MCPServer instance."""

    @server.tool(
        name="manage_queue",
        description="Inspect story queue items, review pending candidate items, pause or resume channel production, or trigger auto-publish review sweeps.",
    )
    async def manage_queue(
        action: Annotated[
            str,
            Field(description="Queue management action ('list', 'pending_review', 'pause', 'resume', 'sweep')"),
        ],
        channel: Annotated[
            Optional[str],
            Field(description="Target channel for pause/resume or filtering ('moku', 'aelithia', 'scifi')"),
        ] = None,
        pause_reason: Annotated[
            Optional[str],
            Field(description="Reason string when pausing a channel"),
        ] = None,
        reason: Annotated[
            Optional[str],
            Field(description="Alias for pause_reason"),
        ] = None,
        limit: Annotated[
            int,
            Field(description="Maximum stories to return for listing actions"),
        ] = 25,
        db_path: Annotated[
            Optional[str],
            Field(description="Path to SQLite database file"),
        ] = None,
    ) -> Dict[str, Any]:
        target_db = db_path or DEFAULT_DB_PATH
        act = action.lower().strip()
        eff_reason = reason or pause_reason or "Paused via MCP"

        try:
            if act == "list":
                return _handle_list(target_db, channel, limit)
            elif act == "pending_review":
                return _handle_pending_review(target_db, limit)
            elif act == "pause":
                return _handle_pause(target_db, channel, eff_reason)
            elif act == "resume":
                return _handle_resume(target_db, channel)
            elif act == "sweep":
                return _handle_sweep()
            else:
                raise ToolError(
                    f"Unsupported queue action '{action}'. Allowed: 'list', 'pending_review', 'pause', 'resume', 'sweep'."
                )

        except ToolError:
            raise
        except Exception as exc:
            logger.exception("Queue management action '%s' failed: %s", action, exc)
            raise ToolError(f"manage_queue action '{action}' failed: {exc}") from exc
