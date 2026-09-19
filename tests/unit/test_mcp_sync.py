"""
tests/unit/test_mcp_sync.py - Unit tests for MCP server synchronization & drift verification gate.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from scripts.verify_mcp_sync import (
    CANONICAL_TOOLS,
    CANONICAL_RESOURCES,
    CANONICAL_PROMPTS,
    CLIENT_CONFIG_FILES,
    parse_docs_mcp,
    validate_client_configs,
    verify_mcp_sync,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class TestDocsParsing:
    def test_parse_docs_mcp_canonical(self):
        docs_path = REPO_ROOT / "docs" / "MCP.md"
        if not docs_path.is_file():
            pytest.skip("docs/MCP.md not yet written")
        ok, sections, errors = parse_docs_mcp(docs_path)
        assert ok, f"Errors parsing docs/MCP.md: {errors}"
        assert sections["tools"] == CANONICAL_TOOLS
        assert sections["resources"] == CANONICAL_RESOURCES
        assert sections["prompts"] == CANONICAL_PROMPTS

    def test_parse_missing_docs_fails_cleanly(self, tmp_path):
        ok, sections, errors = parse_docs_mcp(tmp_path / "nonexistent.md")
        assert not ok
        assert any("Documentation file missing" in e for e in errors)


class TestClientConfigValidation:
    def test_validate_production_configs(self):
        for f in CLIENT_CONFIG_FILES:
            if not (REPO_ROOT / f).is_file():
                pytest.skip(f"{f} not yet written")
        ok, errors = validate_client_configs(REPO_ROOT)
        assert ok, f"Validation errors on client configs: {errors}"

    def test_detects_missing_config_files(self, tmp_path):
        ok, errors = validate_client_configs(tmp_path)
        assert not ok
        assert len(errors) == len(CLIENT_CONFIG_FILES)

    def test_detects_invalid_json(self, tmp_path):
        (tmp_path / "mcp_config.json").write_text("{ corrupt json")
        (tmp_path / ".mcp.json.example").write_text("{}")
        ok, errors = validate_client_configs(tmp_path)
        assert not ok
        assert any("invalid JSON" in e for e in errors)

    def test_detects_invalid_command_or_args(self, tmp_path):
        bad_config = {
            "mcpServers": {
                "yt-auto": {
                    "command": "node",
                    "args": ["server.js"]
                }
            }
        }
        (tmp_path / "mcp_config.json").write_text(json.dumps(bad_config))
        (tmp_path / ".mcp.json.example").write_text(json.dumps(bad_config))
        ok, errors = validate_client_configs(tmp_path)
        assert not ok
        assert any("command" in e for e in errors)
        assert any("args" in e for e in errors)


class TestDriftVerificationEngine:
    def test_full_parity_positive(self, tmp_path):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        # Create minimal valid doc
        doc_content = """# MCP Manual
## Herramientas
| 1 | `system_preflight` |
| 2 | `list_lanes` |
| 3 | `get_lane_info` |
| 4 | `query_loop_catalog` |
| 5 | `audit_loop_catalog` |
| 6 | `run_pipeline_dry_run` |
| 7 | `get_system_status` |
| 8 | `manage_queue` |
| 9 | `verify_integrity` |

## Recursos
`channels://{channel_name}/config`
`lanes://catalog`
`system://health`

## Prompts
| 1 | `preflight_diagnostics` |
| 2 | `channel_incident_analysis` |
| 3 | `video_qa_review` |
"""
        (docs_dir / "MCP.md").write_text(doc_content)

        cfg = {
            "mcpServers": {
                "yt-auto": {
                    "command": ".venv/bin/python3",
                    "args": ["-m", "src.mcp"]
                }
            }
        }
        (tmp_path / "mcp_config.json").write_text(json.dumps(cfg))
        (tmp_path / ".mcp.json.example").write_text(json.dumps(cfg))

        mock_code_data = {
            "tools": {t: MagicMock(description=f"Desc for {t}") for t in CANONICAL_TOOLS},
            "resources": {r: MagicMock(description=f"Desc for {r}") for r in CANONICAL_RESOURCES},
            "prompts": {p: MagicMock(description=f"Desc for {p}") for p in CANONICAL_PROMPTS},
        }

        with patch("scripts.verify_mcp_sync.inspect_code_registrations", return_value=(True, mock_code_data, [])):
            success, passed, failures = verify_mcp_sync(tmp_path)
            assert success, f"Expected success but got failures: {failures}"
            assert len(failures) == 0

    def test_drift_when_tool_missing_in_docs(self, tmp_path):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        # Doc missing verify_integrity
        doc_content = """# MCP Manual
## Herramientas
| 1 | `system_preflight` |
## Recursos
`channels://{channel_name}/config`
`lanes://catalog`
`system://health`
## Prompts
| 1 | `preflight_diagnostics` |
| 2 | `channel_incident_analysis` |
| 3 | `video_qa_review` |
"""
        (docs_dir / "MCP.md").write_text(doc_content)
        cfg = {"mcpServers": {"yt-auto": {"command": ".venv/bin/python3", "args": ["-m", "src.mcp"]}}}
        (tmp_path / "mcp_config.json").write_text(json.dumps(cfg))
        (tmp_path / ".mcp.json.example").write_text(json.dumps(cfg))

        mock_code_data = {
            "tools": {t: MagicMock(description=f"Desc for {t}") for t in CANONICAL_TOOLS},
            "resources": {r: MagicMock(description=f"Desc for {r}") for r in CANONICAL_RESOURCES},
            "prompts": {p: MagicMock(description=f"Desc for {p}") for p in CANONICAL_PROMPTS},
        }

        with patch("scripts.verify_mcp_sync.inspect_code_registrations", return_value=(True, mock_code_data, [])):
            success, passed, failures = verify_mcp_sync(tmp_path)
            assert not success
            assert any("Tool Drift: Registered in code but missing from docs/MCP.md" in f for f in failures)


class TestIntegrityScriptIntegration:
    def test_verify_integrity_script_contains_check_9(self):
        script_text = (REPO_ROOT / "scripts" / "verify_integrity.sh").read_text(encoding="utf-8")
        assert "scripts/verify_mcp_sync.py" in script_text
        assert "Check #9" in script_text or "9. Verify MCP Server" in script_text
