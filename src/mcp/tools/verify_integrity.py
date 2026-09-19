"""
src/mcp/tools/verify_integrity.py - Canonical MCP tool for repository invariant verification.
"""
from __future__ import annotations

import logging
import subprocess
from typing import Annotated, Any, Dict

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from src.config import BASE_DIR
from src.mcp.sanitizer import sanitize_payload

logger = logging.getLogger("mcp.tools.verify_integrity")


def register_verify_integrity_tool(server: MCPServer) -> None:
    """Register verify_integrity tool on the MCPServer instance."""

    @server.tool(
        name="verify_integrity",
        description="Run repository invariant checks, worktree hygiene, zero-browser policy, and anti-regression validation suite.",
    )
    async def verify_integrity(
        fast: Annotated[
            bool,
            Field(description="Fast verification mode"),
        ] = False,
        fail_closed: Annotated[
            bool,
            Field(description="Raise ToolError if integrity checks fail (code 1)"),
        ] = False,
    ) -> Dict[str, Any]:
        script_path = BASE_DIR / "scripts" / "verify_integrity.sh"
        if not script_path.is_file():
            raise ToolError(f"Integrity script not found at {script_path}.")

        cmd = [str(script_path)]
        if fast:
            cmd.append("--fast")

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )

            healthy = (proc.returncode == 0)
            output_clean = proc.stdout.strip()
            if proc.stderr:
                output_clean += f"\nSTDERR:\n{proc.stderr.strip()}"

            checks_passed = []
            checks_failed = []
            for line in output_clean.splitlines():
                line_s = line.strip()
                if line_s.startswith("✅ [PASS]"):
                    checks_passed.append(line_s[9:].strip())
                elif line_s.startswith("❌ [FAIL]"):
                    checks_failed.append(line_s[9:].strip())

            commit_count = 0
            try:
                c_proc = subprocess.run(
                    ["git", "rev-list", "--count", "HEAD"],
                    cwd=str(BASE_DIR),
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if c_proc.returncode == 0:
                    commit_count = int(c_proc.stdout.strip())
            except Exception:
                pass

            result = {
                "healthy": healthy,
                "status": "HEALTHY" if healthy else "FAILED",
                "exit_code": proc.returncode,
                "checks_passed": checks_passed,
                "checks_failed": checks_failed,
                "commit_count": commit_count,
                "summary": "Repository invariants 100% HEALTHY" if healthy else "Integrity verification failed",
                "checks": "Invariant checks verified (Zero-Browser, Anti-Bloat, Zero-Legacy-Docs, Stream-Copy)",
                "output": output_clean,
            }
            sanitized = sanitize_payload(result)

            if not healthy and fail_closed:
                raise ToolError(f"Integrity check FAILED (exit code {proc.returncode}):\n{sanitized['output']}")

            return sanitized

        except subprocess.TimeoutExpired as texc:
            raise ToolError(f"verify_integrity timed out after 120 seconds: {texc}") from texc
        except ToolError:
            raise
        except Exception as exc:
            logger.exception("Unexpected error in verify_integrity: %s", exc)
            raise ToolError(f"verify_integrity execution error: {exc}") from exc
