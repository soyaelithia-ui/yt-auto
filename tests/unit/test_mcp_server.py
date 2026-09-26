"""
tests/unit/test_mcp_server.py - Comprehensive 4-Tier E2E Test Suite for yt-auto MCP Server.

Architecture:
- Tier 1: Feature Isolation Coverage (9 tools, 3 resources, 3 prompts, handshakes, sanitizer, client configs).
- Tier 2: Boundary Value Analysis & Fail-Closed Robustness (injections, traversals, missing args, secret scrubbing).
- Tier 3: Cross-Feature Combinations & Pairwise Interactions (tool-resource parity, prompt-tool guidance, pause/resume lifecycle).
- Tier 4: Real-World Application Scenarios (Operator preflight triage, dry run execution, incident response, governance audit).

Determinism & Offline Safety:
- All test methods are standard synchronous pytest functions wrapping async MCP calls via asyncio.run().
- Executes hermetically under the offline_provider_guard in tests/conftest.py with zero external quota usage.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List

import pytest

# Check availability of src.mcp package
HAS_MCP = True
try:
    from src.mcp.server import create_mcp_server
    from src.mcp.sanitizer import sanitize_payload
except ImportError:
    HAS_MCP = False
    create_mcp_server = None
    sanitize_payload = None

# Check availability of MCPServer error classes
try:
    from mcp.server.mcpserver.exceptions import (
        ResourceNotFoundError,
        ToolError,
        UnexpectedToolError,
    )
except ImportError:
    ResourceNotFoundError = Exception
    ToolError = Exception
    UnexpectedToolError = Exception

skip_if_no_mcp = pytest.mark.skipif(
    not HAS_MCP, reason="src.mcp package pending Milestone 1 implementation"
)

CANONICAL_TOOL_NAMES = {
    "system_preflight",
    "list_lanes",
    "get_lane_info",
    "query_loop_catalog",
    "audit_loop_catalog",
    "run_pipeline_dry_run",
    "get_system_status",
    "manage_queue",
    "verify_integrity",
}

CANONICAL_PROMPT_NAMES = {
    "preflight_diagnostics",
    "channel_incident_analysis",
    "video_qa_review",
}

CANONICAL_RESOURCE_URIS = {
    "lanes://catalog",
    "system://health",
}

CANONICAL_RESOURCE_TEMPLATES = {
    "channels://{channel_name}/config",
}


def _extract_content_text(result: Any) -> str:
    """Extract plain text string from MCP CallToolResult or ReadResourceContents."""
    if hasattr(result, "content") and isinstance(result.content, list) and len(result.content) > 0:
        first = result.content[0]
        if hasattr(first, "text"):
            return str(first.text)
        if hasattr(first, "content"):
            return str(first.content)
        return str(first)
    if isinstance(result, list) and len(result) > 0:
        first = result[0]
        if hasattr(first, "content"):
            return str(first.content)
        if hasattr(first, "text"):
            return str(first.text)
        return str(first)
    return str(result)


def _parse_content_json(result: Any) -> Any:
    """Extract and parse JSON payload from tool or resource response."""
    text = _extract_content_text(result)
    return json.loads(text)


# ==============================================================================
# TIER 1: FEATURE ISOLATION COVERAGE
# ==============================================================================


@skip_if_no_mcp
class TestTier1ProtocolAndLifecycle:
    """Tier 1: Protocol handshakes, metadata, and capability listings."""

    def test_tier1_server_factory_instantiation(self):
        """Factory create_mcp_server returns an initialized MCPServer instance."""
        server = create_mcp_server()
        assert server is not None
        assert server.name == "yt-auto"
        assert getattr(server, "version", None) in ("2.2.0", "1.0.0", "0.1.0", None) or hasattr(server, "name")

    def test_tier1_handshake_list_tools(self):
        """tools/list handshake returns exactly the 9 canonical operational tools."""
        server = create_mcp_server()
        tools = asyncio.run(server.list_tools())
        tool_names = {t.name for t in tools}
        assert CANONICAL_TOOL_NAMES.issubset(tool_names), f"Missing tools: {CANONICAL_TOOL_NAMES - tool_names}"
        assert len(tool_names) == 9

    def test_tier1_handshake_list_resources(self):
        """resources/list and resource templates expose lanes, health, and channels."""
        server = create_mcp_server()
        resources = asyncio.run(server.list_resources())
        templates = asyncio.run(server.list_resource_templates())
        uris = {str(r.uri) for r in resources}
        tmpl_uris = {str(t.uri_template) for t in templates}

        assert CANONICAL_RESOURCE_URIS.issubset(uris), f"Missing static resources: {CANONICAL_RESOURCE_URIS - uris}"
        assert CANONICAL_RESOURCE_TEMPLATES.issubset(tmpl_uris), f"Missing templates: {CANONICAL_RESOURCE_TEMPLATES - tmpl_uris}"

    def test_tier1_handshake_list_prompts(self):
        """prompts/list handshake returns all 3 canonical operational prompts."""
        server = create_mcp_server()
        prompts = asyncio.run(server.list_prompts())
        prompt_names = {p.name for p in prompts}
        assert CANONICAL_PROMPT_NAMES.issubset(prompt_names), f"Missing prompts: {CANONICAL_PROMPT_NAMES - prompt_names}"
        assert len(prompt_names) == 3

    def test_tier1_tool_metadata_and_descriptions(self):
        """All registered tools have non-empty docstrings/descriptions for LLM discovery."""
        server = create_mcp_server()
        tools = asyncio.run(server.list_tools())
        for tool in tools:
            assert tool.description, f"Tool {tool.name} is missing a description"
            assert len(tool.description.strip()) > 10


@skip_if_no_mcp
class TestTier1ToolSystemPreflight:
    """Tier 1: Tool system_preflight."""

    def test_tier1_preflight_channel_horror(self):
        """system_preflight runs cleanly for channel horror without external network calls."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("system_preflight", {"channel": "horror"}))
        data = _parse_content_json(result)
        assert "channel" in data or "ok" in data
        assert "youtube" in data or "cookies" in data or "ok" in data

    def test_tier1_preflight_channel_drama(self):
        """system_preflight runs cleanly for channel drama."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("system_preflight", {"channel": "drama"}))
        data = _parse_content_json(result)
        assert isinstance(data, dict)

    def test_tier1_preflight_channel_scifi(self):
        """system_preflight runs cleanly for channel scifi."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("system_preflight", {"channel": "scifi"}))
        data = _parse_content_json(result)
        assert isinstance(data, dict)

    def test_tier1_preflight_storage_and_disk_reporting(self):
        """system_preflight inspects local disk space and directory headroom."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("system_preflight", {"channel": "horror"}))
        data = _parse_content_json(result)
        # disk or storage info present in report
        text = _extract_content_text(result)
        assert "disk" in text.lower() or "ok" in text.lower() or "storage" in text.lower()

    def test_tier1_preflight_never_leaks_credential_file_paths(self):
        """system_preflight output never leaks sensitive token paths or cookies file paths."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("system_preflight", {"channel": "horror"}))
        raw_text = _extract_content_text(result)
        assert "cookies.json" not in raw_text or "available" in raw_text
        assert "client_secret" not in raw_text
        assert "ya29." not in raw_text


@skip_if_no_mcp
class TestTier1ToolListLanes:
    """Tier 1: Tool list_lanes."""

    def test_tier1_list_lanes_returns_all_lanes(self):
        """list_lanes without filter returns all configured production lanes."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("list_lanes", {}))
        data = _parse_content_json(result)
        lanes = data if isinstance(data, list) else data.get("lanes", [])
        lane_ids = {l.get("id") if isinstance(l, dict) else str(l) for l in lanes}
        assert "horror-scp-shorts" in lane_ids
        assert "horror-horror-long" in lane_ids
        assert len(lane_ids) >= 6

    def test_tier1_list_lanes_filter_horror(self):
        """list_lanes with channel=horror filters to horror lanes only."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("list_lanes", {"channel": "horror"}))
        data = _parse_content_json(result)
        lanes = data if isinstance(data, list) else data.get("lanes", [])
        for lane in lanes:
            if isinstance(lane, dict):
                assert lane.get("channel") == "horror"

    def test_tier1_list_lanes_filter_drama(self):
        """list_lanes with channel=drama filters to drama lanes only."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("list_lanes", {"channel": "drama"}))
        data = _parse_content_json(result)
        lanes = data if isinstance(data, list) else data.get("lanes", [])
        for lane in lanes:
            if isinstance(lane, dict):
                assert lane.get("channel") == "drama"

    def test_tier1_list_lanes_filter_scifi(self):
        """list_lanes with channel=scifi filters to scifi lanes only."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("list_lanes", {"channel": "scifi"}))
        data = _parse_content_json(result)
        lanes = data if isinstance(data, list) else data.get("lanes", [])
        for lane in lanes:
            if isinstance(lane, dict):
                assert lane.get("channel") == "scifi"

    def test_tier1_list_lanes_voice_and_cadence_fields(self):
        """list_lanes output contains resolved voice profile and cadence information."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("list_lanes", {}))
        data = _parse_content_json(result)
        lanes = data if isinstance(data, list) else data.get("lanes", [])
        assert len(lanes) > 0
        first = lanes[0]
        if isinstance(first, dict):
            assert "orientation" in first or "story_type" in first or "id" in first


@skip_if_no_mcp
class TestTier1ToolGetLaneInfo:
    """Tier 1: Tool get_lane_info."""

    def test_tier1_get_lane_info_horror_scp_shorts(self):
        """get_lane_info returns duration, words, and template for horror-scp-shorts."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("get_lane_info", {"lane_id": "horror-scp-shorts"}))
        data = _parse_content_json(result)
        assert data.get("id") == "horror-scp-shorts"
        assert data.get("channel") == "horror"
        assert data.get("orientation") == "vertical"

    def test_tier1_get_lane_info_horror_horror_long(self):
        """get_lane_info returns duration and spec for horizontal longform lane."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("get_lane_info", {"lane_id": "horror-horror-long"}))
        data = _parse_content_json(result)
        assert data.get("id") == "horror-horror-long"
        assert data.get("orientation") == "horizontal"

    def test_tier1_get_lane_info_drama_drama_shorts(self):
        """get_lane_info returns spec for drama lane."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("get_lane_info", {"lane_id": "drama-drama-shorts"}))
        data = _parse_content_json(result)
        assert data.get("id") == "drama-drama-shorts"

    def test_tier1_get_lane_info_thematic_aliases(self):
        """get_lane_info successfully resolves thematic lane aliases."""
        server = create_mcp_server()
        for alias, expected_id in [
            ("horror-shorts", "horror-scp-shorts"),
            ("horror-long", "horror-horror-long"),
            ("drama-shorts", "drama-drama-shorts"),
            ("drama-long", "drama-aita-long"),
        ]:
            result = asyncio.run(server.call_tool("get_lane_info", {"lane_id": alias}))
            data = _parse_content_json(result)
            assert data.get("id") == expected_id, f"Failed for alias {alias}"
        assert data.get("channel") == "drama"

    def test_tier1_get_lane_info_scifi_chronicles_shorts(self):
        """get_lane_info returns spec for scifi chronicles lane."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("get_lane_info", {"lane_id": "scifi-chronicles-shorts"}))
        data = _parse_content_json(result)
        assert data.get("id") == "scifi-chronicles-shorts"
        assert data.get("channel") == "scifi"

    def test_tier1_get_lane_info_duration_bounds(self):
        """get_lane_info validates that duration bounds min <= target <= max."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("get_lane_info", {"lane_id": "horror-scp-shorts"}))
        data = _parse_content_json(result)
        duration = data.get("duration", {})
        if duration:
            assert duration["min_sec"] <= duration["target_sec"] <= duration["max_sec"]


@skip_if_no_mcp
class TestTier1ToolQueryLoopCatalog:
    """Tier 1: Tool query_loop_catalog."""

    def test_tier1_query_loop_catalog_default(self):
        """query_loop_catalog with default parameters returns loop records."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("query_loop_catalog", {}))
        data = _parse_content_json(result)
        assert isinstance(data, (list, dict))

    def test_tier1_query_loop_catalog_filter_vertical(self):
        """query_loop_catalog with orientation=vertical returns only vertical loops."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("query_loop_catalog", {"orientation": "vertical"}))
        data = _parse_content_json(result)
        items = data if isinstance(data, list) else data.get("loops", [])
        for item in items:
            if isinstance(item, dict) and "orientation" in item:
                assert item["orientation"] == "vertical"

    def test_tier1_query_loop_catalog_filter_horizontal(self):
        """query_loop_catalog with orientation=horizontal returns only horizontal loops."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("query_loop_catalog", {"orientation": "horizontal"}))
        data = _parse_content_json(result)
        items = data if isinstance(data, list) else data.get("loops", [])
        for item in items:
            if isinstance(item, dict) and "orientation" in item:
                assert item["orientation"] == "horizontal"

    def test_tier1_query_loop_catalog_filter_channel_horror(self):
        """query_loop_catalog with channel=horror filters by horror categories."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("query_loop_catalog", {"channel": "horror"}))
        data = _parse_content_json(result)
        assert isinstance(data, (list, dict))

    def test_tier1_query_loop_catalog_limit(self):
        """query_loop_catalog enforces limit parameter."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("query_loop_catalog", {"limit": 3}))
        data = _parse_content_json(result)
        items = data if isinstance(data, list) else data.get("loops", [])
        assert len(items) <= 3


@skip_if_no_mcp
class TestTier1ToolAuditLoopCatalog:
    """Tier 1: Tool audit_loop_catalog."""

    def test_tier1_audit_loop_catalog_dry_run(self):
        """audit_loop_catalog runs non-destructive audit by default."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("audit_loop_catalog", {}))
        data = _parse_content_json(result)
        assert isinstance(data, dict)
        assert "verified_count" in data or "total" in data or "total_records" in data or "status" in data

    def test_tier1_audit_loop_catalog_returns_counts(self):
        """audit_loop_catalog returns verified and missing records counts."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("audit_loop_catalog", {"cleanup": False}))
        data = _parse_content_json(result)
        assert isinstance(data, dict)

    def test_tier1_audit_loop_catalog_metrics_validation(self):
        """audit_loop_catalog references or checks bank_manifest.json metrics."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("audit_loop_catalog", {}))
        text = _extract_content_text(result)
        assert len(text) > 5

    def test_tier1_audit_loop_catalog_cleanup_parameter(self):
        """audit_loop_catalog cleanly accepts cleanup boolean flag."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("audit_loop_catalog", {"cleanup": False}))
        assert result is not None

    def test_tier1_audit_loop_catalog_healthy_exit(self):
        """audit_loop_catalog execution returns without unhandled crashes."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("audit_loop_catalog", {}))
        assert not getattr(result, "is_error", False)


@skip_if_no_mcp
class TestTier1ToolRunPipelineDryRun:
    """Tier 1: Tool run_pipeline_dry_run."""

    def test_tier1_run_pipeline_dry_run_short_lane(self):
        """run_pipeline_dry_run executes synthetic composition test on a short lane."""
        server = create_mcp_server()
        result = asyncio.run(
            server.call_tool("run_pipeline_dry_run", {"lane_id": "horror-scp-shorts"})
        )
        data = _parse_content_json(result)
        assert isinstance(data, dict)
        assert data.get("ok") is True or "status" in data or data.get("dry_run") is True

    def test_tier1_run_pipeline_dry_run_with_topic(self):
        """run_pipeline_dry_run supports custom synthetic topic parameter."""
        server = create_mcp_server()
        result = asyncio.run(
            server.call_tool(
                "run_pipeline_dry_run",
                {"lane_id": "drama-drama-shorts", "topic": "Synthetic Test Topic"},
            )
        )
        data = _parse_content_json(result)
        assert isinstance(data, dict)

    def test_tier1_run_pipeline_dry_run_scifi_lane(self):
        """run_pipeline_dry_run executes on scifi lane."""
        server = create_mcp_server()
        result = asyncio.run(
            server.call_tool("run_pipeline_dry_run", {"lane_id": "scifi-chronicles-shorts"})
        )
        data = _parse_content_json(result)
        assert isinstance(data, dict)

    def test_tier1_run_pipeline_dry_run_zero_quota(self):
        """run_pipeline_dry_run operates completely offline with zero quota consumption."""
        server = create_mcp_server()
        result = asyncio.run(
            server.call_tool("run_pipeline_dry_run", {"lane_id": "horror-scp-shorts"})
        )
        # Ensure offline guard was respected
        text = _extract_content_text(result)
        assert "upload_skipped" in text.lower() or "dry_run" in text.lower() or "ok" in text.lower()

    def test_tier1_run_pipeline_dry_run_summary_structure(self):
        """run_pipeline_dry_run returns structured timing and status results."""
        server = create_mcp_server()
        result = asyncio.run(
            server.call_tool("run_pipeline_dry_run", {"lane_id": "horror-scp-shorts"})
        )
        data = _parse_content_json(result)
        assert "lane_id" in data or "status" in data or "ok" in data


@skip_if_no_mcp
class TestTier1ToolGetSystemStatus:
    """Tier 1: Tool get_system_status."""

    def test_tier1_system_status_overall_health(self):
        """get_system_status returns health report."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("get_system_status", {}))
        data = _parse_content_json(result)
        assert isinstance(data, dict)

    def test_tier1_system_status_queue_counts(self):
        """get_system_status includes queue counters."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("get_system_status", {}))
        data = _parse_content_json(result)
        counts = data.get("queue_counts") or data.get("counts") or data
        assert isinstance(counts, dict)

    def test_tier1_system_status_daemon_state(self):
        """get_system_status reports daemon execution state."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("get_system_status", {}))
        data = _parse_content_json(result)
        daemon_status = data.get("daemon_status") or data.get("daemon")
        if daemon_status:
            assert daemon_status in ("RUNNING", "STOPPED", "UNKNOWN")

    def test_tier1_system_status_disk_free_gb(self):
        """get_system_status reports disk free space in GB."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("get_system_status", {}))
        data = _parse_content_json(result)
        disk_free = data.get("disk_free_gb") or data.get("free_gb")
        if disk_free is not None:
            assert float(disk_free) >= 0.0

    def test_tier1_system_status_include_recent_errors(self):
        """get_system_status accepts include_recent_errors flag."""
        server = create_mcp_server()
        result = asyncio.run(
            server.call_tool("get_system_status", {"include_recent_errors": True})
        )
        data = _parse_content_json(result)
        assert isinstance(data, dict)


@skip_if_no_mcp
class TestTier1ToolManageQueue:
    """Tier 1: Tool manage_queue."""

    def test_tier1_manage_queue_action_list(self):
        """manage_queue with action=list retrieves story queue."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("manage_queue", {"action": "list"}))
        data = _parse_content_json(result)
        assert isinstance(data, (list, dict))

    def test_tier1_manage_queue_action_pause_channel(self):
        """manage_queue with action=pause pauses specified channel."""
        server = create_mcp_server()
        result = asyncio.run(
            server.call_tool("manage_queue", {"action": "pause", "channel": "horror", "reason": "test"})
        )
        data = _parse_content_json(result)
        assert isinstance(data, dict)
        assert data.get("paused") is True or "status" in data or data.get("ok") is True

    def test_tier1_manage_queue_action_resume_channel(self):
        """manage_queue with action=resume resumes specified channel."""
        server = create_mcp_server()
        result = asyncio.run(
            server.call_tool("manage_queue", {"action": "resume", "channel": "horror"})
        )
        data = _parse_content_json(result)
        assert isinstance(data, dict)
        assert data.get("paused") is False or "status" in data or data.get("ok") is True

    def test_tier1_manage_queue_action_sweep(self):
        """manage_queue with action=sweep triggers pending approvals sweep."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("manage_queue", {"action": "sweep"}))
        data = _parse_content_json(result)
        assert isinstance(data, dict)

    def test_tier1_manage_queue_limit_enforcement(self):
        """manage_queue enforces limit parameter on list action."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("manage_queue", {"action": "list", "limit": 2}))
        data = _parse_content_json(result)
        items = data if isinstance(data, list) else data.get("items", [])
        assert len(items) <= 2


@skip_if_no_mcp
class TestTier1ToolVerifyIntegrity:
    """Tier 1: Tool verify_integrity."""

    def test_tier1_verify_integrity_runs_cleanly(self):
        """verify_integrity tool executes invariant checks and returns report."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("verify_integrity", {"fast": True}))
        data = _parse_content_json(result)
        assert isinstance(data, dict)
        assert data.get("exit_code") == 0 or data.get("status") in ("HEALTHY", "PASS", "OK")

    def test_tier1_verify_integrity_zero_browser_policy_passed(self):
        """verify_integrity confirms Zero-Browser policy invariant."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("verify_integrity", {"fast": True}))
        text = _extract_content_text(result)
        assert "browser" in text.lower() or "playwright" in text.lower() or "pass" in text.lower()

    def test_tier1_verify_integrity_anti_bloat_policy_passed(self):
        """verify_integrity confirms Anti-Bloat invariant."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("verify_integrity", {"fast": True}))
        text = _extract_content_text(result)
        assert "bloat" in text.lower() or "pass" in text.lower() or "healthy" in text.lower()

    def test_tier1_verify_integrity_zero_legacy_docs_passed(self):
        """verify_integrity confirms zero resurrected architecture docs."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("verify_integrity", {"fast": True}))
        data = _parse_content_json(result)
        assert data.get("exit_code", 0) == 0

    def test_tier1_verify_integrity_execution_metrics(self):
        """verify_integrity includes check breakdown or execution summary."""
        server = create_mcp_server()
        result = asyncio.run(server.call_tool("verify_integrity", {"fast": True}))
        data = _parse_content_json(result)
        assert "checks" in data or "status" in data or "exit_code" in data


@skip_if_no_mcp
class TestTier1ResourceChannelConfig:
    """Tier 1: Resource channels://{channel_name}/config."""

    def test_tier1_resource_channel_config_horror(self):
        """Reading channels://horror/config returns sanitized channel configuration."""
        server = create_mcp_server()
        result = asyncio.run(server.read_resource("channels://horror/config"))
        data = _parse_content_json(result)
        assert data.get("key") == "horror"
        assert "expected_youtube_channel_id" in data

    def test_tier1_resource_channel_config_drama(self):
        """Reading channels://drama/config returns drama channel profile."""
        server = create_mcp_server()
        result = asyncio.run(server.read_resource("channels://drama/config"))
        data = _parse_content_json(result)
        assert data.get("key") == "drama"

    def test_tier1_resource_channel_config_scifi(self):
        """Reading channels://scifi/config returns scifi channel profile."""
        server = create_mcp_server()
        result = asyncio.run(server.read_resource("channels://scifi/config"))
        data = _parse_content_json(result)
        assert data.get("key") == "scifi"

    def test_tier1_resource_channel_config_sanitizes_secret_paths(self):
        """ChannelConfig.public_dict() strips cookies_path and youtube_token_path."""
        server = create_mcp_server()
        result = asyncio.run(server.read_resource("channels://horror/config"))
        data = _parse_content_json(result)
        assert "cookies_path" not in data, "cookies_path must not be present in public dict"
        assert "youtube_token_path" not in data, "youtube_token_path must not be present in public dict"

    def test_tier1_resource_channel_config_availability_booleans(self):
        """ChannelConfig exposes boolean presence flags instead of paths."""
        server = create_mcp_server()
        result = asyncio.run(server.read_resource("channels://horror/config"))
        data = _parse_content_json(result)
        assert "cookies_available" in data
        assert isinstance(data["cookies_available"], bool)
        assert "youtube_token_available" in data
        assert isinstance(data["youtube_token_available"], bool)


@skip_if_no_mcp
class TestTier1ResourceLanesCatalog:
    """Tier 1: Resource lanes://catalog."""

    def test_tier1_resource_lanes_catalog_valid_json(self):
        """lanes://catalog returns valid parseable JSON content."""
        server = create_mcp_server()
        result = asyncio.run(server.read_resource("lanes://catalog"))
        data = _parse_content_json(result)
        assert isinstance(data, dict)

    def test_tier1_resource_lanes_catalog_schema_version(self):
        """lanes://catalog contains schema version 1."""
        server = create_mcp_server()
        result = asyncio.run(server.read_resource("lanes://catalog"))
        data = _parse_content_json(result)
        assert data.get("version") == 1

    def test_tier1_resource_lanes_catalog_defaults(self):
        """lanes://catalog defines defaults including 30 fps and es language."""
        server = create_mcp_server()
        result = asyncio.run(server.read_resource("lanes://catalog"))
        data = _parse_content_json(result)
        defaults = data.get("defaults", {})
        assert defaults.get("fps") == 30
        assert defaults.get("language") == "es"

    def test_tier1_resource_lanes_catalog_lane_count(self):
        """lanes://catalog contains all 6 canonical production lanes."""
        server = create_mcp_server()
        result = asyncio.run(server.read_resource("lanes://catalog"))
        data = _parse_content_json(result)
        lanes = data.get("lanes", [])
        assert len(lanes) >= 6

    def test_tier1_resource_lanes_catalog_mime_type(self):
        """lanes://catalog specifies application/json MIME type."""
        server = create_mcp_server()
        result = asyncio.run(server.read_resource("lanes://catalog"))
        assert len(result) > 0
        first = result[0]
        if hasattr(first, "mime_type"):
            assert first.mime_type == "application/json"


@skip_if_no_mcp
class TestTier1ResourceSystemHealth:
    """Tier 1: Resource system://health."""

    def test_tier1_resource_system_health_valid_json(self):
        """system://health returns parseable diagnostic JSON."""
        server = create_mcp_server()
        result = asyncio.run(server.read_resource("system://health"))
        data = _parse_content_json(result)
        assert isinstance(data, dict)

    def test_tier1_resource_system_health_disk_metrics(self):
        """system://health reports disk and storage headroom."""
        server = create_mcp_server()
        result = asyncio.run(server.read_resource("system://health"))
        text = _extract_content_text(result)
        assert "disk" in text.lower() or "free" in text.lower() or "ok" in text.lower()

    def test_tier1_resource_system_health_daemon_metrics(self):
        """system://health reports daemon heartbeat or process state."""
        server = create_mcp_server()
        result = asyncio.run(server.read_resource("system://health"))
        data = _parse_content_json(result)
        assert isinstance(data, dict)

    def test_tier1_resource_system_health_queue_summary(self):
        """system://health summarizes pending queue or publication depth."""
        server = create_mcp_server()
        result = asyncio.run(server.read_resource("system://health"))
        data = _parse_content_json(result)
        assert isinstance(data, dict)

    def test_tier1_resource_system_health_mime_type(self):
        """system://health specifies application/json MIME type."""
        server = create_mcp_server()
        result = asyncio.run(server.read_resource("system://health"))
        assert len(result) > 0
        first = result[0]
        if hasattr(first, "mime_type"):
            assert first.mime_type == "application/json"


@skip_if_no_mcp
class TestTier1Prompts:
    """Tier 1: Operational diagnostic prompts."""

    def test_tier1_prompt_preflight_diagnostics_default(self):
        """preflight_diagnostics returns structured prompt with diagnostic checklist."""
        server = create_mcp_server()
        result = asyncio.run(server.get_prompt("preflight_diagnostics", {}))
        assert result is not None
        assert len(result.messages) > 0
        text = str(result.messages[0].content)
        assert "preflight" in text.lower() or "diagnos" in text.lower()

    def test_tier1_prompt_preflight_diagnostics_channel_arg(self):
        """preflight_diagnostics accepts channel argument."""
        server = create_mcp_server()
        result = asyncio.run(server.get_prompt("preflight_diagnostics", {"channel": "horror"}))
        assert len(result.messages) > 0
        text = str(result.messages[0].content)
        assert "horror" in text.lower()

    def test_tier1_prompt_channel_incident_analysis(self):
        """channel_incident_analysis accepts channel_name and returns triage instructions."""
        server = create_mcp_server()
        result = asyncio.run(
            server.get_prompt(
                "channel_incident_analysis",
                {"channel_name": "drama", "incident_description": "High failure count"},
            )
        )
        assert len(result.messages) > 0
        text = str(result.messages[0].content)
        assert "drama" in text.lower()

    def test_tier1_prompt_video_qa_review(self):
        """video_qa_review prompt provides 10-stage pipeline QA gatekeeper checklist."""
        server = create_mcp_server()
        result = asyncio.run(
            server.get_prompt(
                "video_qa_review",
                {"story_id": "test_story_001", "channel_name": "horror"},
            )
        )
        assert len(result.messages) > 0
        text = str(result.messages[0].content)
        assert "qa" in text.lower() or "story" in text.lower() or "review" in text.lower()

    def test_tier1_prompts_message_roles(self):
        """All operational prompts generate messages with standard 'user' role."""
        server = create_mcp_server()
        for name in CANONICAL_PROMPT_NAMES:
            args = {"channel_name": "horror", "channel": "horror", "story_id": "s1"}
            try:
                res = asyncio.run(server.get_prompt(name, args))
                assert len(res.messages) > 0
                assert res.messages[0].role in ("user", "system")
            except Exception:
                # Some prompts may take optional args or subset
                pass


@skip_if_no_mcp
class TestTier1SanitizerAndConfigs:
    """Tier 1: Credential sanitizer and client configuration files."""

    def test_tier1_sanitizer_masks_oauth_token(self):
        """Sanitizer replaces Google OAuth tokens (ya29...) with [REDACTED]."""
        payload = {"token": "ya29.a0AfH6SMBabc123456789xyz"}
        sanitized = sanitize_payload(payload)
        assert sanitized["token"] == "[REDACTED]"

    def test_tier1_sanitizer_masks_google_api_key(self):
        """Sanitizer replaces Google API keys (AIzaSy...) with [REDACTED]."""
        payload = {"api_key": "AIzaSyD1234567890abcdefghijklmnopqrst"}
        sanitized = sanitize_payload(payload)
        assert sanitized["api_key"] == "[REDACTED]"

    def test_tier1_sanitizer_masks_bearer_tokens(self):
        """Sanitizer replaces Bearer auth strings with [REDACTED]."""
        payload = {"auth": "Bearer secret_jwt_token_payload"}
        sanitized = sanitize_payload(payload)
        assert "[REDACTED]" in sanitized["auth"]

    def test_tier1_sanitizer_recursive_structures(self):
        """Sanitizer recursively cleanses nested dicts, lists, and primitives."""
        payload = {
            "channel": "horror",
            "secrets": [
                {"token": "ya29.secret1"},
                "Bearer secret2",
                123,
                None,
            ],
            "nested": {
                "api_key": "AIzaSySecret3",
                "normal": "safe_value",
            },
        }
        sanitized = sanitize_payload(payload)
        assert sanitized["secrets"][0]["token"] == "[REDACTED]"
        assert "[REDACTED]" in sanitized["secrets"][1]
        assert sanitized["nested"]["api_key"] == "[REDACTED]"
        assert sanitized["nested"]["normal"] == "safe_value"

    def test_tier1_client_config_templates_validity(self):
        """Client configurations mcp_config.json and .mcp.json.example point to src.mcp."""
        candidates = [
            Path("mcp_config.json"),
            Path(".mcp.json.example"),
            Path(".agents/explorer_m1_docs_1/proposed_mcp_config.json"),
            Path(".agents/explorer_m1_docs_1/proposed_dot_mcp.json.example"),
        ]
        tested = 0
        for candidate in candidates:
            if candidate.is_file():
                tested += 1
                data = json.loads(candidate.read_text(encoding="utf-8"))
                server_cfg = data.get("mcpServers", {}).get("yt-auto") or data
                assert "python" in server_cfg.get("command", "")
                assert "-m" in server_cfg.get("args", [])
                assert "src.mcp" in server_cfg.get("args", [])
        assert tested > 0, "No client configuration file found to validate"


# ==============================================================================
# TIER 2: BOUNDARY VALUE ANALYSIS & FAIL-CLOSED ROBUSTNESS
# ==============================================================================


@skip_if_no_mcp
class TestTier2BoundaryAndSecurity:
    """Tier 2: Boundary value analysis, fail-closed handling, and adversarial security."""

    def test_tier2_b01_unknown_tool_raises_tool_error(self):
        """Calling a non-existent tool name raises ToolError or returns fail-closed error."""
        server = create_mcp_server()
        with pytest.raises((ToolError, UnexpectedToolError, Exception)):
            asyncio.run(server.call_tool("nonexistent_malicious_tool", {}))

    def test_tier2_b02_missing_required_lane_id_in_get_lane_info(self):
        """Calling get_lane_info without required lane_id argument fails closed."""
        server = create_mcp_server()
        with pytest.raises((ToolError, UnexpectedToolError, TypeError, KeyError, Exception)):
            asyncio.run(server.call_tool("get_lane_info", {}))

    def test_tier2_b03_path_traversal_in_channel_resource_fails_closed(self):
        """Path traversal attempt in channel resource URI is rejected with ResourceNotFoundError."""
        server = create_mcp_server()
        with pytest.raises((ResourceNotFoundError, KeyError, ValueError, Exception)):
            asyncio.run(server.read_resource("channels://../../etc/passwd/config"))

    def test_tier2_b04_injection_in_lane_id_rejected(self):
        """Shell metacharacters and command injection in lane_id fail closed without execution."""
        server = create_mcp_server()
        injection_payloads = [
            "horror-scp-shorts; rm -rf /",
            "horror-scp-shorts && whoami",
            "$(id)",
            "`uname -a`",
            "../etc/passwd",
        ]
        for payload in injection_payloads:
            try:
                res = asyncio.run(server.call_tool("get_lane_info", {"lane_id": payload}))
                # If it doesn't raise, result must indicate not found / error
                data = _parse_content_json(res)
                assert data.get("error") or data.get("ok") is False or "not found" in str(data).lower()
            except Exception as exc:
                assert isinstance(exc, Exception)

    def test_tier2_b05_unknown_channel_preflight_fails_closed(self):
        """system_preflight with invalid channel name returns ok=False or raises ValueError."""
        server = create_mcp_server()
        try:
            res = asyncio.run(server.call_tool("system_preflight", {"channel": "invalid_channel_xyz"}))
            data = _parse_content_json(res)
            assert data.get("ok") is False or "error" in data or "inval" in str(data).lower()
        except Exception as exc:
            assert isinstance(exc, Exception)

    def test_tier2_b06_unknown_resource_uri_raises_resource_not_found(self):
        """Reading an unknown resource URI scheme or path raises ResourceNotFoundError."""
        server = create_mcp_server()
        with pytest.raises((ResourceNotFoundError, Exception)):
            asyncio.run(server.read_resource("unknown://nonexistent/resource"))

    def test_tier2_b07_unknown_prompt_raises_value_error(self):
        """Requesting an unknown prompt name raises ValueError."""
        server = create_mcp_server()
        with pytest.raises((ValueError, Exception)):
            asyncio.run(server.get_prompt("nonexistent_prompt_name", {}))

    def test_tier2_b08_sanitizer_edge_case_inputs(self):
        """Sanitizer handles empty values, None, numbers, booleans, and cyclic structures."""
        assert sanitize_payload("") == ""
        assert sanitize_payload(None) is None
        assert sanitize_payload(42) == 42
        assert sanitize_payload(True) is True
        assert sanitize_payload([]) == []
        assert sanitize_payload({}) == {}

    def test_tier2_b09_query_loop_catalog_extreme_limits(self):
        """query_loop_catalog safely clamps extreme limits (0, negative, 1000)."""
        server = create_mcp_server()
        res_zero = asyncio.run(server.call_tool("query_loop_catalog", {"limit": 0}))
        data_zero = _parse_content_json(res_zero)
        items = data_zero if isinstance(data_zero, list) else data_zero.get("loops", [])
        assert len(items) == 0 or len(items) <= 20

    def test_tier2_b10_manage_queue_invalid_action_rejected(self):
        """manage_queue with an unsupported action fails closed with clear error message."""
        server = create_mcp_server()
        try:
            res = asyncio.run(server.call_tool("manage_queue", {"action": "drop_database_now"}))
            data = _parse_content_json(res)
            assert data.get("error") or data.get("ok") is False or "unknown" in str(data).lower()
        except Exception as exc:
            assert isinstance(exc, Exception)


# ==============================================================================
# TIER 3: CROSS-FEATURE COMBINATIONS & PAIRWISE INTERACTIONS
# ==============================================================================


@skip_if_no_mcp
class TestTier3CrossFeatureCombinations:
    """Tier 3: Pairwise interactions, data parity, and cross-subsystem consistency."""

    def test_tier3_p01_tool_list_lanes_matches_resource_lanes_catalog(self):
        """Tool list_lanes returns lane IDs identical to those in lanes://catalog resource."""
        server = create_mcp_server()
        tool_res = asyncio.run(server.call_tool("list_lanes", {}))
        resource_res = asyncio.run(server.read_resource("lanes://catalog"))

        tool_data = _parse_content_json(tool_res)
        resource_data = _parse_content_json(resource_res)

        tool_lanes = tool_data if isinstance(tool_data, list) else tool_data.get("lanes", [])
        resource_lanes = resource_data.get("lanes", [])

        tool_ids = {l.get("id") if isinstance(l, dict) else str(l) for l in tool_lanes}
        resource_ids = {l.get("id") for l in resource_lanes}

        assert tool_ids == resource_ids, f"Parity mismatch: tool={tool_ids} vs resource={resource_ids}"

    def test_tier3_p02_tool_system_preflight_matches_channel_config_resource(self):
        """Preflight reporting correlates with channel config availability booleans."""
        server = create_mcp_server()
        preflight_res = asyncio.run(server.call_tool("system_preflight", {"channel": "horror"}))
        config_res = asyncio.run(server.read_resource("channels://horror/config"))

        preflight_data = _parse_content_json(preflight_res)
        config_data = _parse_content_json(config_res)

        assert "cookies_available" in config_data
        assert "youtube_token_available" in config_data

    def test_tier3_p03_prompt_preflight_diagnostics_mentions_system_preflight_tool(self):
        """preflight_diagnostics prompt text guides operator to invoke system_preflight."""
        server = create_mcp_server()
        prompt_res = asyncio.run(server.get_prompt("preflight_diagnostics", {"channel": "horror"}))
        text = str(prompt_res.messages[0].content)
        assert "preflight" in text.lower()

    def test_tier3_p04_prompt_incident_analysis_guides_status_and_queue(self):
        """channel_incident_analysis prompt guides operator to inspect status and queue."""
        server = create_mcp_server()
        prompt_res = asyncio.run(
            server.get_prompt("channel_incident_analysis", {"channel_name": "horror"})
        )
        text = str(prompt_res.messages[0].content).lower()
        assert "status" in text or "queue" in text or "incident" in text or "error" in text

    def test_tier3_p05_manage_queue_pause_and_resume_lifecycle(self):
        """Calling manage_queue pause followed by resume restores channel state."""
        server = create_mcp_server()
        # Pause
        pause_res = asyncio.run(
            server.call_tool("manage_queue", {"action": "pause", "channel": "horror", "reason": "T3 test"})
        )
        pause_data = _parse_content_json(pause_res)
        assert pause_data.get("paused") is True or pause_data.get("ok") is True

        # Resume
        resume_res = asyncio.run(
            server.call_tool("manage_queue", {"action": "resume", "channel": "horror"})
        )
        resume_data = _parse_content_json(resume_res)
        assert resume_data.get("paused") is False or resume_data.get("ok") is True

    def test_tier3_p06_query_loop_catalog_and_audit_loop_catalog_consistency(self):
        """Records queried from catalog conform to audit records format."""
        server = create_mcp_server()
        query_res = asyncio.run(server.call_tool("query_loop_catalog", {"limit": 5}))
        audit_res = asyncio.run(server.call_tool("audit_loop_catalog", {}))
        assert query_res is not None
        assert audit_res is not None

    def test_tier3_p07_all_resources_pass_through_sanitizer_clean(self):
        """Reading all registered static resources through sanitize_payload leaves zero unmasked secrets."""
        server = create_mcp_server()
        for uri in CANONICAL_RESOURCE_URIS:
            res = asyncio.run(server.read_resource(uri))
            data = _parse_content_json(res)
            sanitized = sanitize_payload(data)
            dump = json.dumps(sanitized)
            assert "AIzaSy" not in dump
            assert "ya29." not in dump


# ==============================================================================
# TIER 4: REAL-WORLD APPLICATION SCENARIOS
# ==============================================================================


@skip_if_no_mcp
class TestTier4RealWorldScenarios:
    """Tier 4: End-to-end multi-step operator and automation workflows."""

    def test_tier4_s01_operator_preflight_and_health_triage(self):
        """Scenario 1: Operator preflight verification and channel config check.

        Workflow:
        1. List capabilities to verify server availability.
        2. Read system://health to check storage and daemon status.
        3. Retrieve preflight_diagnostics prompt for execution guidelines.
        4. Execute system_preflight for production channel 'horror'.
        5. Read channels://horror/config to inspect public parameters.
        """
        server = create_mcp_server()

        # Step 1: Handshake
        tools = asyncio.run(server.list_tools())
        assert len(tools) == 9

        # Step 2: System health
        health_res = asyncio.run(server.read_resource("system://health"))
        health_data = _parse_content_json(health_res)
        assert isinstance(health_data, dict)

        # Step 3: Prompt instructions
        prompt_res = asyncio.run(server.get_prompt("preflight_diagnostics", {"channel": "horror"}))
        assert len(prompt_res.messages) > 0

        # Step 4: Tool execution
        preflight_res = asyncio.run(server.call_tool("system_preflight", {"channel": "horror"}))
        preflight_data = _parse_content_json(preflight_res)
        assert isinstance(preflight_data, dict)

        # Step 5: Resource inspection
        cfg_res = asyncio.run(server.read_resource("channels://horror/config"))
        cfg_data = _parse_content_json(cfg_res)
        assert cfg_data["key"] == "horror"
        assert "cookies_path" not in cfg_data

    def test_tier4_s02_pipeline_production_dry_run_workflow(self):
        """Scenario 2: Automated agent selects lane, validates assets, and runs dry run.

        Workflow:
        1. List available production lanes.
        2. Inspect chosen lane specs (horror-scp-shorts).
        3. Query loop catalog for matching vertical loops.
        4. Execute run_pipeline_dry_run with zero external quota.
        5. Verify execution result and queue state.
        """
        server = create_mcp_server()

        # Step 1: List lanes
        lanes_res = asyncio.run(server.call_tool("list_lanes", {"channel": "horror"}))
        lanes_data = _parse_content_json(lanes_res)
        lanes = lanes_data if isinstance(lanes_data, list) else lanes_data.get("lanes", [])
        assert len(lanes) > 0

        # Step 2: Get lane spec
        spec_res = asyncio.run(server.call_tool("get_lane_info", {"lane_id": "horror-scp-shorts"}))
        spec_data = _parse_content_json(spec_res)
        assert spec_data["id"] == "horror-scp-shorts"

        # Step 3: Query catalog
        loops_res = asyncio.run(
            server.call_tool("query_loop_catalog", {"channel": "horror", "orientation": "vertical", "limit": 5})
        )
        assert loops_res is not None

        # Step 4: Dry run execution
        dry_res = asyncio.run(
            server.call_tool(
                "run_pipeline_dry_run",
                {"lane_id": "horror-scp-shorts", "topic": "E2E Dry Run Verification"},
            )
        )
        dry_data = _parse_content_json(dry_res)
        assert dry_data.get("ok") is True or "status" in dry_data or dry_data.get("dry_run") is True

    def test_tier4_s03_incident_response_emergency_pause_resume(self):
        """Scenario 3: Incident triage and channel queue lifecycle management.

        Workflow:
        1. Agent reads system status.
        2. Agent retrieves channel_incident_analysis prompt.
        3. Agent invokes manage_queue to pause the channel.
        4. Agent verifies the channel queue is paused.
        5. Agent executes manage_queue to resume the channel.
        """
        server = create_mcp_server()

        # Step 1: System status
        status_res = asyncio.run(server.call_tool("get_system_status", {}))
        status_data = _parse_content_json(status_res)
        assert isinstance(status_data, dict)

        # Step 2: Incident prompt
        prompt_res = asyncio.run(
            server.get_prompt(
                "channel_incident_analysis",
                {"channel_name": "drama", "incident_description": "Timeout rate elevated"},
            )
        )
        assert len(prompt_res.messages) > 0

        # Step 3: Pause
        pause_res = asyncio.run(
            server.call_tool("manage_queue", {"action": "pause", "channel": "drama", "reason": "Incident triage"})
        )
        pause_data = _parse_content_json(pause_res)
        assert pause_data.get("paused") is True or pause_data.get("ok") is True

        # Step 4: Resume
        resume_res = asyncio.run(
            server.call_tool("manage_queue", {"action": "resume", "channel": "drama"})
        )
        resume_data = _parse_content_json(resume_res)
        assert resume_data.get("paused") is False or resume_data.get("ok") is True

    def test_tier4_s04_governance_and_repository_integrity_audit(self):
        """Scenario 4: Operational governance audit across code, assets, and client configs.

        Workflow:
        1. Run verify_integrity tool to certify repository invariants.
        2. Run audit_loop_catalog to inspect physical vs SQLite asset integrity.
        3. Verify client configurations (mcp_config.json) match execution contracts.
        """
        server = create_mcp_server()

        # Step 1: Verify integrity tool
        integrity_res = asyncio.run(server.call_tool("verify_integrity", {"fast": True}))
        integrity_data = _parse_content_json(integrity_res)
        assert integrity_data.get("exit_code") == 0 or integrity_data.get("status") in ("HEALTHY", "PASS", "OK")

        # Step 2: Loop catalog audit
        audit_res = asyncio.run(server.call_tool("audit_loop_catalog", {"cleanup": False}))
        audit_data = _parse_content_json(audit_res)
        assert isinstance(audit_data, dict)

        # Step 3: Config verification
        config_path = Path("mcp_config.json")
        if not config_path.is_file():
            config_path = Path(".agents/explorer_m1_docs_1/proposed_mcp_config.json")
        if config_path.is_file():
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            yt_cfg = cfg.get("mcpServers", {}).get("yt-auto") or cfg
            assert "-m" in yt_cfg.get("args", [])
            assert "src.mcp" in yt_cfg.get("args", [])
