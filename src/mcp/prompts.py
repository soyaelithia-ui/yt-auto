"""
src/mcp/prompts.py - Standard Operational Prompts for yt-auto MCP Server.
"""
from __future__ import annotations

from typing import List

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.prompts.base import Message, UserMessage


def register_prompts(server: MCPServer) -> None:
    """Register standardized operational prompt workflows."""

    # -------------------------------------------------------------------------
    # Prompt 1: preflight_diagnostics
    # -------------------------------------------------------------------------
    @server.prompt(
        name="preflight_diagnostics",
        description="Standardized operational workflow for checking system readiness, credentials, storage, and API connectivity.",
    )
    async def preflight_diagnostics(
        channel: str = "moku",
        require_publish: bool = True,
        channel_name: str = "",
    ) -> List[Message]:
        target_channel = channel_name or channel or "moku"
        text = (
            f"You are conducting a strict preflight diagnostic review for yt-auto (channel='{target_channel}').\n\n"
            f"Follow this operational checklist:\n"
            f"1. Run tool `system_preflight(channel='{target_channel}', require_publish={require_publish})`.\n"
            f"2. Inspect resource `system://health` to verify disk space (>= 2 GiB free) and daemon heartbeat.\n"
            f"3. Verify that YouTube tokens and Google Drive access are validated.\n"
            f"4. Confirm that FFmpeg and ffprobe binaries are present.\n"
            f"5. Issue a definitive GO or NO-GO decision with remedial steps if NO-GO."
        )
        return [UserMessage(content=text)]

    # -------------------------------------------------------------------------
    # Prompt 2: channel_incident_analysis
    # -------------------------------------------------------------------------
    @server.prompt(
        name="channel_incident_analysis",
        description="Guided triage workflow for channel failures, error spikes, and paused lanes.",
    )
    async def channel_incident_analysis(
        channel_name: str = "moku",
        incident_description: str = "",
        channel: str = "",
        error_context: str = "",
    ) -> List[Message]:
        target_channel = channel or channel_name or "moku"
        context = incident_description or error_context or "Unspecified failure report"
        text = (
            f"Analyze a channel incident on yt-auto for channel '{target_channel}'.\n"
            f"Context: {context}\n\n"
            f"Execution Steps:\n"
            f"1. Query `get_system_status()` to inspect recent failure logs and active locks.\n"
            f"2. Read `channels://{target_channel}/config` to inspect active voice and design settings.\n"
            f"3. Run `manage_queue(action='list', channel='{target_channel}')` to identify failed stories and error messages.\n"
            f"4. Check whether the lane is paused or if a rate-limit / token expiry occurred.\n"
            f"5. Propose a targeted remediation plan."
        )
        return [UserMessage(content=text)]

    # -------------------------------------------------------------------------
    # Prompt 3: video_qa_review
    # -------------------------------------------------------------------------
    @server.prompt(
        name="video_qa_review",
        description="In-depth QA review checklist against the 10-stage pipeline gatekeeper.",
    )
    async def video_qa_review(
        story_id: str,
        lane_id: str = "",
        channel_name: str = "moku",
        channel: str = "",
    ) -> List[Message]:
        target_channel = channel or channel_name or "moku"
        text = (
            f"Perform an exhaustive Quality Assurance audit for produced story '{story_id}' "
            f"(channel='{target_channel}', lane='{lane_id or 'auto'}').\n\n"
            f"Verify compliance against the 10 QA Gates:\n"
            f"- Gate 1: Story & metadata validation (title, script, tags).\n"
            f"- Gate 2: Audio loudness (EBU R128 integrated -14.0 LUFS, true peak <= -1.0 dBFS).\n"
            f"- Gate 3: Visual loop compatibility from `query_loop_catalog`.\n"
            f"- Gate 4: Zero black frames exceeding 2.0s duration.\n"
            f"- Gate 5: Perceptual luminance check passed (no underexposed flat planes).\n"
            f"- Gate 6: Resolution matches lane specification (1080x1920 or 1920x1080).\n"
            f"- Gate 7: Video composition executed via Stream-Copy (-c:v copy) without re-encoding.\n"
            f"- Gate 8: Thumbnail rendered at required aspect ratio.\n"
            f"- Gate 9: Zero Playwright/browser traces in media pipelines.\n"
            f"- Gate 10: Run `audit_loop_catalog()` if loop assets were modified."
        )
        return [UserMessage(content=text)]
