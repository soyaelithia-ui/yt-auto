#!/usr/bin/env python3
"""
scripts/verify_mcp_sync.py - Automated MCP Server Parity & Drift Detection Gate

Single Source of Truth (SSOT) synchronization validator for yt-auto Model Context Protocol.
Enforces 100% bidirectional parity between:
1. Runtime MCPServer registrations via create_mcp_server() (tools, resources, prompts)
2. Canonical SSOT Specifications
3. Official Technical Documentation (docs/MCP.md)
4. Client Configuration Templates (mcp_config.json, .mcp.json.example)

Exit codes:
  0 - HEALTHY: 100% bidirectional parity verified, zero drift.
  1 - DRIFT / REGRESSION: Mismatches or invalid configurations detected.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# If not running in repo's .venv and .venv exists, transparently re-exec with .venv python
if __name__ == "__main__":
    _repo_venv_py = (Path(__file__).resolve().parent.parent / ".venv" / "bin" / "python3").resolve()
    if _repo_venv_py.is_file() and Path(sys.executable).resolve() != _repo_venv_py and os.environ.get("MCP_REEXEC") != "1":
        os.environ["MCP_REEXEC"] = "1"
        os.execv(str(_repo_venv_py), [str(_repo_venv_py)] + sys.argv)

import asyncio
import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple

# ==============================================================================
# Canonical Single Source of Truth (SSOT) Specifications
# ==============================================================================

CANONICAL_TOOLS: Set[str] = {
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

CANONICAL_RESOURCES: Set[str] = {
    "channels://{channel_name}/config",
    "lanes://catalog",
    "system://health",
}

CANONICAL_PROMPTS: Set[str] = {
    "preflight_diagnostics",
    "channel_incident_analysis",
    "video_qa_review",
}

CLIENT_CONFIG_FILES: List[str] = [
    "mcp_config.json",
    ".mcp.json.example",
]

# Table header and metadata tokens to ignore when parsing markdown tables
TABLE_HEADERS_TO_IGNORE: Set[str] = {
    "tool", "tools", "name", "tool_name", "parameter", "parameters",
    "args", "arguments", "description", "input", "output", "prompt",
    "prompts", "prompt_name", "resource", "resources", "resource_name",
    "type", "mime_type", "uri", "uri_pattern", "schema", "spec", "action",
    "herramienta", "propósito", "módulo", "origen", "flujo", "argumentos",
    "propósito principal", "módulo backing",
}


# ==============================================================================
# 1. Code Registration Inspector (MCPServer)
# ==============================================================================

def inspect_code_registrations(repo_root: Path) -> Tuple[bool, Dict[str, Any], List[str]]:
    """
    Imports create_mcp_server() from src.mcp.server and inspects
    all registered tools, resources, templates, and prompts.
    """
    errors: List[str] = []

    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    try:
        from src.mcp.server import create_mcp_server
    except ImportError as e:
        return False, {}, [f"Cannot import create_mcp_server from src.mcp.server: {e}"]
    except Exception as e:
        return False, {}, [f"Unexpected error loading src.mcp.server: {e}"]

    try:
        server = create_mcp_server()
    except Exception as e:
        return False, {}, [f"Failed to instantiate MCPServer via create_mcp_server(): {e}"]

    # Extract Tools
    registered_tools: Dict[str, Any] = {}
    try:
        tools_list = asyncio.run(server.list_tools())
        for tool in tools_list:
            registered_tools[tool.name] = tool
    except Exception as e:
        return False, {}, [f"Failed to list tools from MCPServer: {e}"]

    # Extract Resources (static and templates)
    registered_resources: Dict[str, Any] = {}
    try:
        resources_list = asyncio.run(server.list_resources())
        for res in resources_list:
            registered_resources[str(res.uri)] = res

        templates_list = asyncio.run(server.list_resource_templates())
        for tmpl in templates_list:
            registered_resources[str(tmpl.uri_template)] = tmpl
    except Exception as e:
        return False, {}, [f"Failed to list resources/templates from MCPServer: {e}"]

    # Extract Prompts
    registered_prompts: Dict[str, Any] = {}
    try:
        prompts_list = asyncio.run(server.list_prompts())
        for prm in prompts_list:
            registered_prompts[prm.name] = prm
    except Exception as e:
        return False, {}, [f"Failed to list prompts from MCPServer: {e}"]

    # Quality Check: Ensure descriptions are present
    for name, tool in registered_tools.items():
        if not getattr(tool, "description", None) or not tool.description.strip():
            errors.append(f"Tool '{name}' registered in code has empty or missing description.")

    for uri, res in registered_resources.items():
        if not getattr(res, "description", None) or not res.description.strip():
            errors.append(f"Resource '{uri}' registered in code has empty or missing description.")

    for name, prm in registered_prompts.items():
        if not getattr(prm, "description", None) or not prm.description.strip():
            errors.append(f"Prompt '{name}' registered in code has empty or missing description.")

    code_data = {
        "tools": registered_tools,
        "resources": registered_resources,
        "prompts": registered_prompts,
    }
    return len(errors) == 0, code_data, errors


# ==============================================================================
# 2. Documentation Parser (docs/MCP.md)
# ==============================================================================

def parse_docs_mcp(docs_path: Path) -> Tuple[bool, Dict[str, Set[str]], List[str]]:
    """
    Parses docs/MCP.md and extracts documented tool names, resource URI patterns,
    and prompt names within their respective markdown sections.
    """
    if not docs_path.is_file():
        return False, {"tools": set(), "resources": set(), "prompts": set()}, [
            f"Documentation file missing: {docs_path}"
        ]

    content = docs_path.read_text(encoding="utf-8")
    sections: Dict[str, Set[str]] = {
        "tools": set(),
        "resources": set(),
        "prompts": set(),
    }
    errors: List[str] = []
    current_section: Optional[str] = None

    for line_num, raw_line in enumerate(content.splitlines(), 1):
        line = raw_line.strip()

        # Section Heading Detection (## Section)
        h_match = re.match(r"^##\s+(.*)", line)
        if h_match:
            title = h_match.group(1).lower()
            if "herramienta" in title or "tool" in title:
                current_section = "tools"
            elif "recurso" in title or "resource" in title:
                current_section = "resources"
            elif "prompt" in title:
                current_section = "prompts"
            else:
                current_section = None
            continue

        if not current_section:
            continue

        if current_section == "tools":
            # Subheading match: ### 3.1. `system_preflight` or ### `system_preflight`
            m_h = re.match(r"^###+\s*(?:\d+\.|\d+\.\d+\.?|\bTool\b\s*\d*:?)*\s*`([a-z][a-z0-9_]+)`", line)
            if m_h:
                sections["tools"].add(m_h.group(1))

            # Table row match: | 1 | `system_preflight` | ... |
            if line.startswith("|") and not line.startswith("|---"):
                for col in line.split("|"):
                    m_c = re.search(r"^`([a-z][a-z0-9_]+)`$", col.strip())
                    if m_c and m_c.group(1).lower() not in TABLE_HEADERS_TO_IGNORE:
                        sections["tools"].add(m_c.group(1))

        elif current_section == "resources":
            # Match URI patterns with custom MCP schemes: channels://, lanes://, system://
            uris = re.findall(r"`?((?:channels|lanes|system)://[a-z0-9_{}/]+)`?", line)
            for u in uris:
                sections["resources"].add(u)

        elif current_section == "prompts":
            # Subheading match: ### 5.1. `preflight_diagnostics` or ### `preflight_diagnostics`
            m_h = re.match(r"^###+\s*(?:\d+\.|\d+\.\d+\.?|\bPrompt\b\s*\d*:?)*\s*`([a-z][a-z0-9_]+)`", line)
            if m_h:
                sections["prompts"].add(m_h.group(1))

            # Table row match
            if line.startswith("|") and not line.startswith("|---"):
                for col in line.split("|"):
                    m_c = re.search(r"^`([a-z][a-z0-9_]+)`$", col.strip())
                    if m_c and m_c.group(1).lower() not in TABLE_HEADERS_TO_IGNORE:
                        sections["prompts"].add(m_c.group(1))

    return len(errors) == 0, sections, errors


# ==============================================================================
# 3. Client Configuration Validator (mcp_config.json, .mcp.json.example)
# ==============================================================================

def validate_client_configs(repo_root: Path) -> Tuple[bool, List[str]]:
    """
    Validates client configuration files ensuring:
    1. Valid JSON syntax.
    2. Proper server definition under 'mcpServers.yt-auto' or root.
    3. Command points to '.venv/bin/python3' (or 'python3' / '${workspaceFolder}/.venv/bin/python3').
    4. Args specify ['-m', 'src.mcp'].
    """
    errors: List[str] = []

    for filename in CLIENT_CONFIG_FILES:
        cfg_path = repo_root / filename
        if not cfg_path.is_file():
            errors.append(f"Client config file missing: {filename}")
            continue

        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception as e:
            errors.append(f"Client config '{filename}' contains invalid JSON: {e}")
            continue

        if not isinstance(data, dict):
            errors.append(f"Client config '{filename}' root is not a JSON object")
            continue

        server_conf = None
        if "mcpServers" in data and isinstance(data["mcpServers"], dict):
            server_conf = data["mcpServers"].get("yt-auto")
            if server_conf is None and len(data["mcpServers"]) == 1:
                server_conf = next(iter(data["mcpServers"].values()))
        elif "command" in data:
            server_conf = data

        if not server_conf or not isinstance(server_conf, dict):
            errors.append(
                f"Client config '{filename}' missing valid MCP server configuration "
                f"(expected 'mcpServers.yt-auto' or top-level 'command')"
            )
            continue

        cmd = server_conf.get("command", "")
        valid_cmds = {".venv/bin/python3", "python3", "${workspaceFolder}/.venv/bin/python3"}
        if cmd not in valid_cmds and not cmd.endswith("/.venv/bin/python3"):
            errors.append(
                f"Client config '{filename}': 'command' is '{cmd}', "
                f"expected '.venv/bin/python3' or 'python3'"
            )

        args = server_conf.get("args")
        if args != ["-m", "src.mcp"]:
            errors.append(
                f"Client config '{filename}': 'args' is {args}, "
                f"expected ['-m', 'src.mcp']"
            )

    return len(errors) == 0, errors


# ==============================================================================
# 4. Bidirectional Parity & Drift Verification Engine
# ==============================================================================

def verify_mcp_sync(repo_root: Path) -> Tuple[bool, List[str], List[str]]:
    """
    Executes full synchronization & drift detection audit across:
    Code <-> Canonical Spec <-> Documentation <-> Client Configs.
    Returns (success: bool, passed_checks: list[str], failure_messages: list[str]).
    """
    passed: List[str] = []
    failures: List[str] = []

    # Step 1: Inspect Code Registrations
    code_ok, code_data, code_errors = inspect_code_registrations(repo_root)
    if not code_ok:
        failures.extend(code_errors)
        return False, passed, failures

    server_tools = set(code_data["tools"].keys())
    server_resources = set(code_data["resources"].keys())
    server_prompts = set(code_data["prompts"].keys())

    # Step 2: Code vs Canonical Specification
    # Tools
    missing_tools_in_code = CANONICAL_TOOLS - server_tools
    extra_tools_in_code = server_tools - CANONICAL_TOOLS
    if missing_tools_in_code:
        failures.append(f"Code is missing canonical tools: {sorted(missing_tools_in_code)}")
    if extra_tools_in_code:
        failures.append(f"Code registers extra tools not in canonical spec: {sorted(extra_tools_in_code)}")
    if not missing_tools_in_code and not extra_tools_in_code:
        passed.append(f"Code registers all {len(CANONICAL_TOOLS)} canonical tools ({', '.join(sorted(CANONICAL_TOOLS))})")

    # Resources
    missing_res_in_code = CANONICAL_RESOURCES - server_resources
    extra_res_in_code = server_resources - CANONICAL_RESOURCES
    if missing_res_in_code:
        failures.append(f"Code is missing canonical resources: {sorted(missing_res_in_code)}")
    if extra_res_in_code:
        failures.append(f"Code registers extra resources not in canonical spec: {sorted(extra_res_in_code)}")
    if not missing_res_in_code and not extra_res_in_code:
        passed.append(f"Code registers all {len(CANONICAL_RESOURCES)} canonical resources ({', '.join(sorted(CANONICAL_RESOURCES))})")

    # Prompts
    missing_prompts_in_code = CANONICAL_PROMPTS - server_prompts
    extra_prompts_in_code = server_prompts - CANONICAL_PROMPTS
    if missing_prompts_in_code:
        failures.append(f"Code is missing canonical prompts: {sorted(missing_prompts_in_code)}")
    if extra_prompts_in_code:
        failures.append(f"Code registers extra prompts not in canonical spec: {sorted(extra_prompts_in_code)}")
    if not missing_prompts_in_code and not extra_prompts_in_code:
        passed.append(f"Code registers all {len(CANONICAL_PROMPTS)} canonical prompts ({', '.join(sorted(CANONICAL_PROMPTS))})")

    # Step 3: Parse Documentation (docs/MCP.md)
    docs_path = repo_root / "docs" / "MCP.md"
    docs_ok, doc_data, doc_errors = parse_docs_mcp(docs_path)
    if not docs_ok:
        failures.extend(doc_errors)
        return False, passed, failures

    doc_tools = doc_data["tools"]
    doc_resources = doc_data["resources"]
    doc_prompts = doc_data["prompts"]

    # Step 4: Bidirectional Tool Parity (Code <-> Documentation)
    tools_in_code_not_docs = server_tools - doc_tools
    tools_in_docs_not_code = doc_tools - server_tools
    if tools_in_code_not_docs:
        failures.append(f"Tool Drift: Registered in code but missing from docs/MCP.md: {sorted(tools_in_code_not_docs)}")
    if tools_in_docs_not_code:
        failures.append(f"Tool Drift: Documented in docs/MCP.md but not registered in code: {sorted(tools_in_docs_not_code)}")
    if not tools_in_code_not_docs and not tools_in_docs_not_code:
        passed.append(f"100% Tool Parity between code and docs/MCP.md ({len(server_tools)} tools)")

    # Step 5: Bidirectional Resource Parity (Code <-> Documentation)
    res_in_code_not_docs = server_resources - doc_resources
    res_in_docs_not_code = doc_resources - server_resources
    if res_in_code_not_docs:
        failures.append(f"Resource Drift: Registered in code but missing from docs/MCP.md: {sorted(res_in_code_not_docs)}")
    if res_in_docs_not_code:
        failures.append(f"Resource Drift: Documented in docs/MCP.md but not registered in code: {sorted(res_in_docs_not_code)}")
    if not res_in_code_not_docs and not res_in_docs_not_code:
        passed.append(f"100% Resource Parity between code and docs/MCP.md ({len(server_resources)} resources)")

    # Step 6: Bidirectional Prompt Parity (Code <-> Documentation)
    prompts_in_code_not_docs = server_prompts - doc_prompts
    prompts_in_docs_not_code = doc_prompts - server_prompts
    if prompts_in_code_not_docs:
        failures.append(f"Prompt Drift: Registered in code but missing from docs/MCP.md: {sorted(prompts_in_code_not_docs)}")
    if prompts_in_docs_not_code:
        failures.append(f"Prompt Drift: Documented in docs/MCP.md but not registered in code: {sorted(prompts_in_docs_not_code)}")
    if not prompts_in_code_not_docs and not prompts_in_docs_not_code:
        passed.append(f"100% Prompt Parity between code and docs/MCP.md ({len(server_prompts)} prompts)")

    # Step 7: Client Configurations
    configs_ok, config_errors = validate_client_configs(repo_root)
    if not configs_ok:
        failures.extend(config_errors)
    else:
        passed.append(f"Client configurations valid ({', '.join(CLIENT_CONFIG_FILES)})")

    return len(failures) == 0, passed, failures


# ==============================================================================
# CLI Entrypoint
# ==============================================================================

def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    print("======================================================================")
    print("🔍 [MCP SYNC] Verifying Parity & Drift Across Code, Docs & Configs")
    print("======================================================================")

    success, passed, failures = verify_mcp_sync(repo_root)

    for item in passed:
        print(f"✅ [PASS] {item}")

    if not success:
        print("\n❌ [FAIL] MCP DRIFT / PARITY REGRESSIONS DETECTED:")
        for err in failures:
            print(f"  🛑 {err}")
        print("======================================================================")
        print("🛑 [DRIFT DETECTED] MCP synchronization verification failed!")
        print("======================================================================")
        return 1

    print("======================================================================")
    print("🎉 [STATUS: HEALTHY] 100% bidirectional parity verified with zero drift.")
    print("======================================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
