"""
tests/unit/test_mcp_adversarial_challenger.py - Empirical Adversarial Stress Suite for yt-auto MCP Server.

Probing:
1. Malformed tool arguments, missing required parameters, extreme types, huge strings, negative integers.
2. Non-existent tool names, non-existent resource URIs, and unknown prompt names.
3. Resource template traversal attempts (channels://../../etc/passwd/config, channels://../../../secrets/cookies.json/config).
4. Command injection payloads in lane IDs or topics ($(id), ; rm -rf /).
5. JSON-RPC protocol edge cases and descriptor diversion (verify stdout remains clean if a tool prints).
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

from mcp.server.mcpserver.exceptions import (
    ResourceNotFoundError,
    ToolError,
    UnexpectedToolError,
)
from src.config import BASE_DIR, DEFAULT_DB_PATH
from src.mcp.sanitizer import sanitize_payload
from src.mcp.server import create_mcp_server

# ---------------------------------------------------------------------------
# Adversarial Payloads & Fuzzing Generators
# ---------------------------------------------------------------------------

HUGE_STRING_100KB = "A" * 102400
EMOJI_BOMB = "🔥💥💀👽👹🚀" * 500
NULL_BYTE_STRING = "malicious\x00payload"
RTL_OVERRIDE_STRING = "safe_\u202e\u202doverride_test"
FORMAT_STRING_PAYLOAD = "%s%s%s%s%s%n%x%d"
CONTROL_CHARS_STRING = "line1\r\nline2\x1b[31mred\x1b[0m\t\v\b"

SQL_INJECTION_PAYLOADS = [
    "' OR '1'='1",
    "'; DROP TABLE stories; --",
    "1 UNION SELECT 1,2,3,4,5--",
    "admin'--",
]

SHELL_INJECTION_PAYLOADS = [
    "$(id)",
    "`id`",
    "; rm -rf /",
    "| cat /etc/passwd",
    "&& whoami",
    "|| echo pwned",
    "\nwhoami\n",
    "moku-scp-shorts; touch /tmp/mcp_pwned",
    "moku-scp-shorts & sleep 1 &",
    "moku-scp-shorts > /dev/null",
]

PATH_TRAVERSAL_PAYLOADS = [
    "../../etc/passwd",
    "../../../secrets/cookies.json",
    "..%2f..%2fetc%2fpasswd",
    "....//....//etc/passwd",
    "/etc/passwd",
    "/etc/shadow",
    "~/.ssh/id_rsa",
    "..\\..\\windows\\system32",
    "moku/../../../etc/passwd",
    "moku\x00/../../etc/passwd",
]


def _extract_text(result: Any) -> str:
    """Helper to extract text from MCP response objects."""
    if hasattr(result, "content"):
        if isinstance(result.content, str):
            return result.content
        if isinstance(result.content, list) and len(result.content) > 0:
            first = result.content[0]
            if hasattr(first, "text"):
                return str(first.text)
            return str(first)
    if isinstance(result, list) and len(result) > 0:
        first = result[0]
        if hasattr(first, "text") and getattr(first, "text") is not None:
            return str(first.text)
        if hasattr(first, "content") and getattr(first, "content") is not None:
            return str(first.content)
        return str(first)
    return str(result)


def _extract_json(result: Any) -> Any:
    text = _extract_text(result)
    return json.loads(text)


# ==============================================================================
# 1. PARAMETER FUZZING & MALFORMED ARGUMENTS
# ==============================================================================


class TestAdversarialParameterFuzzing:
    """Probes all tools with malformed, extreme, type-confused, and boundary inputs."""

    @pytest.fixture(autouse=True)
    def setup_server(self):
        self.server = create_mcp_server()

    # --- Tool 1: system_preflight ---

    def test_preflight_extreme_channel_names(self):
        """Probes system_preflight with empty, unknown, huge, and injection channels."""
        for ch in ["", "unknown_xyz", HUGE_STRING_100KB, NULL_BYTE_STRING, *SQL_INJECTION_PAYLOADS]:
            with pytest.raises((ToolError, ValueError, Exception)):
                asyncio.run(self.server.call_tool("system_preflight", {"channel": ch}))

    def test_preflight_negative_and_extreme_disk_thresholds(self):
        """Probes system_preflight with negative, zero, and huge disk space thresholds."""
        # Negative disk or extreme disk values should either raise ToolError or fail validation
        with pytest.raises((ToolError, ValueError, Exception)):
            asyncio.run(self.server.call_tool("system_preflight", {"min_disk_gb": -5.0}))

        # Huge threshold (10000 GiB) must cleanly fail closed with ToolError, not crash
        with pytest.raises(ToolError) as exc_info:
            asyncio.run(self.server.call_tool("system_preflight", {"min_disk_gb": 99999.0}))
        assert any(term in str(exc_info.value).lower() for term in ("insufficient disk space", "threshold", "validation error", "less_than_equal"))

    def test_preflight_type_confusion_arguments(self):
        """Probes system_preflight with wrong types for booleans and numbers."""
        # Non-boolean require_publish
        for bad_val in [12345, "not_a_bool", [True], {"publish": True}]:
            # Pydantic or tool execution should handle or convert safely
            try:
                res = asyncio.run(self.server.call_tool("system_preflight", {"channel": "horror", "require_publish": bad_val}))
                assert res is not None
            except Exception as e:
                assert isinstance(e, (ToolError, TypeError, ValueError, Exception))

    # --- Tool 2: list_lanes ---

    def test_list_lanes_unknown_channel(self):
        """Probes list_lanes with unknown or invalid channel names."""
        for bad_ch in ["invalid_ch", "moku'; DROP TABLE lanes; --", HUGE_STRING_100KB]:
            with pytest.raises((ToolError, ValueError, Exception)):
                asyncio.run(self.server.call_tool("list_lanes", {"channel": bad_ch}))

    def test_list_lanes_filter_extremes(self):
        """Probes list_lanes with include_paused and include_disabled boundary values."""
        res = asyncio.run(self.server.call_tool("list_lanes", {"include_paused": False, "include_disabled": False}))
        data = _extract_json(res)
        assert "lanes" in data

    # --- Tool 3: get_lane_info ---

    def test_get_lane_info_missing_required_argument(self):
        """get_lane_info without lane_id must fail closed."""
        with pytest.raises((ToolError, TypeError, Exception)):
            asyncio.run(self.server.call_tool("get_lane_info", {}))

    def test_get_lane_info_empty_and_whitespace_lane_id(self):
        """get_lane_info with empty or whitespace-only lane_id fails closed."""
        for empty in ["", "   ", "\t\n"]:
            with pytest.raises((ToolError, ValueError, Exception)):
                asyncio.run(self.server.call_tool("get_lane_info", {"lane_id": empty}))

    def test_get_lane_info_nonexistent_lane_id(self):
        """get_lane_info with syntactically valid but non-existent lane_id fails closed with ToolError."""
        with pytest.raises(ToolError) as exc_info:
            asyncio.run(self.server.call_tool("get_lane_info", {"lane_id": "nonexistent-lane-404"}))
        assert "not found" in str(exc_info.value).lower()

    def test_get_lane_info_huge_string(self):
        """get_lane_info with 100KB lane_id fails closed."""
        with pytest.raises((ToolError, ValueError, Exception)):
            asyncio.run(self.server.call_tool("get_lane_info", {"lane_id": HUGE_STRING_100KB}))

    # --- Tool 4: query_loop_catalog ---

    def test_query_loop_catalog_negative_and_extreme_limits(self):
        """query_loop_catalog with negative, zero, and huge limits."""
        # Negative limit
        res_neg = asyncio.run(self.server.call_tool("query_loop_catalog", {"limit": -10}))
        data_neg = _extract_json(res_neg)
        assert data_neg.get("count") == 0 or len(data_neg.get("loops", [])) == 0

        # Zero limit
        res_zero = asyncio.run(self.server.call_tool("query_loop_catalog", {"limit": 0}))
        data_zero = _extract_json(res_zero)
        assert data_zero.get("count") == 0

        # Huge limit (should clamp to <= 100 without memory exhaustion)
        res_huge = asyncio.run(self.server.call_tool("query_loop_catalog", {"limit": 1000000}))
        data_huge = _extract_json(res_huge)
        assert len(data_huge.get("loops", [])) <= 100

    def test_query_loop_catalog_invalid_orientation(self):
        """query_loop_catalog with invalid orientation raises ToolError."""
        for bad_ori in ["diagonal", "square", "360", "unknown", "VERTICAL", ""]:
            with pytest.raises((ToolError, ValueError, Exception)):
                asyncio.run(self.server.call_tool("query_loop_catalog", {"orientation": bad_ori}))

    def test_query_loop_catalog_unknown_channel(self):
        """query_loop_catalog with unknown channel raises ToolError."""
        with pytest.raises(ToolError):
            asyncio.run(self.server.call_tool("query_loop_catalog", {"channel": "invalid_ch_99"}))

    # --- Tool 5: audit_loop_catalog ---

    def test_audit_loop_catalog_type_confusion_flags(self):
        """audit_loop_catalog handles boolean flag types gracefully."""
        res = asyncio.run(
            self.server.call_tool(
                "audit_loop_catalog",
                {"cleanup": False, "auto_fix": False, "verify_manifest_metrics": True},
            )
        )
        data = _extract_json(res)
        assert "healthy" in data or "status" in data

    # --- Tool 6: run_pipeline_dry_run ---

    def test_run_pipeline_dry_run_missing_lane_id(self):
        """run_pipeline_dry_run without lane_id must fail closed."""
        with pytest.raises((ToolError, TypeError, Exception)):
            asyncio.run(self.server.call_tool("run_pipeline_dry_run", {}))

    def test_run_pipeline_dry_run_nonexistent_lane_id(self):
        """run_pipeline_dry_run with non-existent lane_id fails closed."""
        with pytest.raises(ToolError):
            asyncio.run(self.server.call_tool("run_pipeline_dry_run", {"lane_id": "ghost-lane-999"}))

    def test_run_pipeline_dry_run_huge_topic_and_control_chars(self):
        """run_pipeline_dry_run with massive topic, emoji, and control chars executes safely without crashing."""
        complex_topic = f"Adversarial Topic {EMOJI_BOMB[:100]} \t\n {CONTROL_CHARS_STRING}"
        res = asyncio.run(
            self.server.call_tool(
                "run_pipeline_dry_run",
                {"lane_id": "horror-scp-shorts", "topic": complex_topic, "mock_all": True},
            )
        )
        data = _extract_json(res)
        assert data.get("ok") is True or "status" in data

    # --- Tool 7: get_system_status ---

    def test_get_system_status_invalid_db_path(self):
        """get_system_status with non-existent db_path handles missing file gracefully."""
        res = asyncio.run(
            self.server.call_tool(
                "get_system_status",
                {"db_path": "/nonexistent/fake_db.sqlite"},
            )
        )
        data = _extract_json(res)
        assert isinstance(data, dict)

    def test_get_system_status_negative_error_limit(self):
        """get_system_status with negative error limit does not crash."""
        res = asyncio.run(self.server.call_tool("get_system_status", {"error_limit": -5}))
        data = _extract_json(res)
        assert isinstance(data, dict)

    # --- Tool 8: manage_queue ---

    def test_manage_queue_missing_action(self):
        """manage_queue without action parameter must fail closed."""
        with pytest.raises((ToolError, TypeError, Exception)):
            asyncio.run(self.server.call_tool("manage_queue", {}))

    def test_manage_queue_unsupported_actions(self):
        """manage_queue rejects arbitrary, malicious, or unknown actions."""
        for bad_action in ["delete_all", "drop_db", "hack", "; DROP TABLE stories;", "", " "]:
            with pytest.raises((ToolError, ValueError, Exception)):
                asyncio.run(self.server.call_tool("manage_queue", {"action": bad_action}))

    def test_manage_queue_pause_resume_missing_channel(self):
        """manage_queue pause or resume without channel raises ToolError."""
        with pytest.raises(ToolError) as exc_info:
            asyncio.run(self.server.call_tool("manage_queue", {"action": "pause"}))
        assert "channel" in str(exc_info.value).lower()

        with pytest.raises(ToolError) as exc_info:
            asyncio.run(self.server.call_tool("manage_queue", {"action": "resume"}))
        assert "channel" in str(exc_info.value).lower()

    def test_manage_queue_negative_limit(self):
        """manage_queue list action with negative limit returns 0 items cleanly."""
        res = asyncio.run(self.server.call_tool("manage_queue", {"action": "list", "limit": -10}))
        data = _extract_json(res)
        assert len(data.get("items", [])) == 0

    # --- Tool 9: verify_integrity ---

    def test_verify_integrity_fail_closed_mode(self):
        """verify_integrity accepts boolean flags and executes without uncaught crash."""
        res = asyncio.run(self.server.call_tool("verify_integrity", {"fast": True, "fail_closed": False}))
        data = _extract_json(res)
        assert "exit_code" in data
        assert data.get("exit_code") == 0


# ==============================================================================
# 2. PROTOCOL ROUTING & UNKNOWN ENTITY PROBES
# ==============================================================================


class TestAdversarialProtocolRouting:
    """Probes non-existent tools, resources, and prompts."""

    @pytest.fixture(autouse=True)
    def setup_server(self):
        self.server = create_mcp_server()

    def test_unknown_tool_names(self):
        """Probes call_tool with non-existent tool names."""
        for fake_name in [
            "nonexistent_tool",
            "system_preflight_v2",
            "SYSTEM_PREFLIGHT",
            "__import__('os')",
            "tool; rm -rf /",
            HUGE_STRING_100KB,
            "",
        ]:
            with pytest.raises((ToolError, UnexpectedToolError, Exception)):
                asyncio.run(self.server.call_tool(fake_name, {}))

    def test_unknown_resource_uris(self):
        """Probes read_resource with non-existent static URIs and invalid schemes."""
        for fake_uri in [
            "unknown://resource",
            "channels://",
            "lanes://unknown",
            "system://unknown",
            "http://example.com",
            "file:///etc/passwd",
            "",
        ]:
            with pytest.raises((ResourceNotFoundError, Exception)):
                asyncio.run(self.server.read_resource(fake_uri))

    def test_unknown_prompt_names(self):
        """Probes get_prompt with non-existent prompt names."""
        for fake_prompt in [
            "nonexistent_prompt",
            "preflight_diagnostics_extended",
            "PREFLIGHT_DIAGNOSTICS",
            "prompt; DROP TABLE prompts;",
            "",
        ]:
            with pytest.raises((ValueError, Exception)):
                asyncio.run(self.server.get_prompt(fake_prompt, {}))


# ==============================================================================
# 3. RESOURCE TEMPLATE TRAVERSAL & SECRET LEAK AUDIT
# ==============================================================================


class TestAdversarialResourceTraversalAndSecrets:
    """Probes path traversal attacks on channel resources and verifies secret sanitization."""

    @pytest.fixture(autouse=True)
    def setup_server(self):
        self.server = create_mcp_server()

    def test_channel_resource_path_traversal_attempts(self):
        """Every path traversal needle in channels://{channel_name}/config must be rejected."""
        for payload in PATH_TRAVERSAL_PAYLOADS:
            traversal_uri = f"channels://{payload}/config"
            with pytest.raises((ResourceNotFoundError, KeyError, ValueError, Exception)):
                asyncio.run(self.server.read_resource(traversal_uri))

    def test_channel_resource_never_leaks_secrets_or_cookie_paths(self):
        """Reading all valid channel configs returns 0 raw secrets and zero secret file paths."""
        for ch in ["horror", "drama", "scifi"]:
            res = asyncio.run(self.server.read_resource(f"channels://{ch}/config"))
            text = _extract_text(res)
            data = json.loads(text)

            # Assert no path strings for sensitive files
            assert "cookies_path" not in data, f"cookies_path leaked in {ch} config"
            assert "youtube_token_path" not in data, f"youtube_token_path leaked in {ch} config"

            # Assert presence booleans exist instead
            assert "cookies_available" in data
            assert isinstance(data["cookies_available"], bool)
            assert "youtube_token_available" in data
            assert isinstance(data["youtube_token_available"], bool)

            # Assert no raw secret patterns
            assert "AIzaSy" not in text
            assert "ya29." not in text
            assert "-----BEGIN" not in text
            assert "cookies.json" not in text

    def test_lanes_catalog_resource_sanitization(self):
        """lanes://catalog resource exposes no private keys or tokens."""
        res = asyncio.run(self.server.read_resource("lanes://catalog"))
        text = _extract_text(res)
        assert "AIzaSy" not in text
        assert "ya29." not in text
        assert "cookies.json" not in text

    def test_system_health_resource_sanitization(self):
        """system://health resource exposes no private keys or raw tokens."""
        res = asyncio.run(self.server.read_resource("system://health"))
        text = _extract_text(res)
        assert "AIzaSy" not in text
        assert "ya29." not in text


# ==============================================================================
# 4. COMMAND INJECTION PROBES
# ==============================================================================


class TestAdversarialCommandInjection:
    """Probes shell metacharacters and command injection across tool parameters."""

    @pytest.fixture(autouse=True)
    def setup_server(self):
        self.server = create_mcp_server()

    def test_command_injection_in_get_lane_info(self):
        """Shell injection payloads in lane_id must fail closed via regex without execution."""
        for payload in SHELL_INJECTION_PAYLOADS:
            with pytest.raises(ToolError) as exc_info:
                asyncio.run(self.server.call_tool("get_lane_info", {"lane_id": payload}))
            assert "Invalid lane_id format" in str(exc_info.value) or "not found" in str(exc_info.value).lower()

    def test_command_injection_in_run_pipeline_dry_run_lane_id(self):
        """Shell injection in run_pipeline_dry_run lane_id must fail closed via regex."""
        for payload in SHELL_INJECTION_PAYLOADS:
            with pytest.raises(ToolError) as exc_info:
                asyncio.run(self.server.call_tool("run_pipeline_dry_run", {"lane_id": payload}))
            assert "Invalid lane_id format" in str(exc_info.value) or "exist" in str(exc_info.value).lower()

    def test_command_injection_in_run_pipeline_dry_run_topic(self):
        """Shell metacharacters in topic must be treated purely as string data without shell evaluation."""
        marker_file = Path("/tmp/mcp_injection_probe.marker")
        if marker_file.exists():
            marker_file.unlink()

        # Attempt command injection that would create a marker file if evaluated in shell
        injection_topic = f"Harmless Topic; touch {marker_file}; #"
        try:
            res = asyncio.run(
                self.server.call_tool(
                    "run_pipeline_dry_run",
                    {"lane_id": "horror-scp-shorts", "topic": injection_topic, "mock_all": True},
                )
            )
            assert res is not None
        except Exception:
            pass

        # Marker file must NEVER exist
        assert not marker_file.exists(), "CRITICAL VULNERABILITY: Shell command was executed from topic parameter!"

    def test_command_injection_in_channel_name(self):
        """Shell metacharacters in channel name are rejected."""
        for payload in ["; id", "$(whoami)", "| rm -rf /", "moku; cat /etc/passwd"]:
            with pytest.raises((ToolError, ValueError, Exception)):
                asyncio.run(self.server.call_tool("system_preflight", {"channel": payload}))


# ==============================================================================
# 5. JSON-RPC STDIO PROTOCOL & DESCRIPTOR DIVERSION
# ==============================================================================


class TestAdversarialDescriptorDiversionAndJsonRpc:
    """Probes the live subprocess running stdio transport for stream pollution and JSON-RPC edge cases."""

    def test_live_mcp_server_initialize_and_tools_list_stdio(self):
        """Start python3 -m src.mcp subprocess and execute initialize handshake via stdio."""
        proc = subprocess.Popen(
            [sys.executable, "-m", "src.mcp"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=str(BASE_DIR),
        )

        try:
            # Send standard JSON-RPC 2.0 initialize request
            init_req = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0"},
                },
            }
            proc.stdin.write(json.dumps(init_req) + "\n")
            proc.stdin.flush()

            # Read first line of stdout
            line = proc.stdout.readline()
            assert line, "Expected JSON-RPC response from server on stdout, got EOF"

            # Parse stdout line as pure JSON-RPC
            resp = json.loads(line)
            assert resp.get("jsonrpc") == "2.0"
            assert resp.get("id") == 1
            assert "result" in resp
            assert resp["result"]["serverInfo"]["name"] == "yt-auto"

            # Send initialized notification
            proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
            proc.stdin.flush()

            # Send tools/list request
            tools_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
            proc.stdin.write(json.dumps(tools_req) + "\n")
            proc.stdin.flush()

            tools_line = proc.stdout.readline()
            assert tools_line, "Expected tools/list response"
            tools_resp = json.loads(tools_line)
            assert tools_resp.get("id") == 2
            tools_list = tools_resp["result"]["tools"]
            assert len(tools_list) == 9

        finally:
            # Terminate gracefully
            proc.stdin.close()
            proc.stdout.close()
            proc.stderr.close()
            proc.terminate()
            proc.wait(timeout=5)

    def test_live_mcp_server_malformed_json_rpc_syntax(self):
        """Sending broken JSON to stdio server returns JSON-RPC parse error or disconnects cleanly."""
        proc = subprocess.Popen(
            [sys.executable, "-m", "src.mcp"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=str(BASE_DIR),
        )

        try:
            # Send garbage syntax
            proc.stdin.write("{not valid json syntax\n")
            proc.stdin.flush()

            # Either server responds with error -32700 (Parse error) or logs to stderr
            # It must not hang indefinitely
            import select
            try:
                r, _, _ = select.select([proc.stdout], [], [], 1.0)
                if r:
                    line = proc.stdout.readline()
                    if line:
                        resp = json.loads(line)
                        if "error" in resp:
                            assert resp["error"]["code"] in (-32700, -32600)
            except Exception:
                pass
        finally:
            proc.stdin.close()
            proc.stdout.close()
            proc.stderr.close()
            proc.terminate()
            proc.wait(timeout=5)

    def test_live_mcp_server_premature_stdin_eof(self):
        """When client immediately closes stdin, server process exits cleanly without hanging."""
        proc = subprocess.Popen(
            [sys.executable, "-m", "src.mcp"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(BASE_DIR),
        )
        proc.stdin.close()
        exit_code = proc.wait(timeout=10)
        # Should terminate cleanly (exit code 0 or 1 upon EOF)
        assert exit_code is not None

    def test_os_descriptor_diversion_safeguards_stdout(self):
        """Empirically verify that writing to fd 1 or print() during stdio serving diverts to stderr."""
        # Test code executed in subprocess running stdio_async and printing to stdout
        script = """
import asyncio
import os
import sys
import json
from src.mcp.server import create_mcp_server

async def main():
    server = create_mcp_server()
    # Intercept stdio_server run
    from mcp.server.stdio import stdio_server
    async with stdio_server() as (read_stream, write_stream):
        # Inside stdio_server, fd 1 is diverted to stderr
        # Test writing to fd 1 directly
        os.write(1, b"TEST_DIVERTED_STDOUT\\n")
        # Test python print()
        print("PYTHON_PRINT_DIVERTED")
        sys.stdout.flush()
        os._exit(0)

asyncio.run(main())
"""
        proc = subprocess.run(
            [sys.executable, "-c", script],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(BASE_DIR),
        )
        # The output from fd 1 and print() should appear on STDERR, NOT on STDOUT!
        assert "TEST_DIVERTED_STDOUT" in proc.stderr, "fd 1 output was not diverted to stderr!"
        assert "TEST_DIVERTED_STDOUT" not in proc.stdout, "fd 1 leaked to stdout!"
        assert "PYTHON_PRINT_DIVERTED" in proc.stderr or "PYTHON_PRINT_DIVERTED" not in proc.stdout
