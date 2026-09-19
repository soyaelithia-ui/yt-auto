"""
src/mcp/tools/audit_loop_catalog.py - Canonical MCP tool for auditing physical loop assets and database consistency.
"""
from __future__ import annotations

import json
import logging
from typing import Annotated, Any, Dict

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from src.config import BASE_DIR, DEFAULT_DB_PATH
from src.core.catalog import LoopCatalogRepository
from src.mcp.sanitizer import sanitize_payload

logger = logging.getLogger("mcp.tools.audit_loop_catalog")


def register_audit_loop_catalog_tool(server: MCPServer) -> None:
    """Register audit_loop_catalog tool on the MCPServer instance."""

    @server.tool(
        name="audit_loop_catalog",
        description="Audit physical video loop MP4 assets against database catalog records, detect missing/corrupt files, and verify bank_manifest.json metrics.",
    )
    async def audit_loop_catalog(
        cleanup: Annotated[
            bool,
            Field(description="Automatically unregister missing or broken video loop records from SQLite"),
        ] = False,
        auto_fix: Annotated[
            bool,
            Field(description="Alias for cleanup: remove missing records from database"),
        ] = False,
        verify_manifest_metrics: Annotated[
            bool,
            Field(description="Verify precomputed visual quality metrics in bank_manifest.json"),
        ] = True,
    ) -> Dict[str, Any]:
        try:
            do_fix = cleanup or auto_fix
            catalog = LoopCatalogRepository(db_path=DEFAULT_DB_PATH)
            catalog_report = catalog.audit_and_cleanup(auto_remove_missing=do_fix)

            manifest_report: Dict[str, Any] = {"manifest_present": False, "verified": False, "errors": []}
            manifest_path = BASE_DIR / "assets" / "loops" / "bank_manifest.json"

            if verify_manifest_metrics and manifest_path.is_file():
                manifest_report["manifest_present"] = True
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        manifest_data = json.load(f)

                    master_loops = manifest_data.get("master_loops", [])
                    checked = 0
                    errors = []

                    for loop in master_loops:
                        checked += 1
                        fname = loop.get("filename", "")
                        rel_path = loop.get("file_path", "")
                        phys_path = BASE_DIR / rel_path

                        if not phys_path.is_file():
                            errors.append(f"Master loop '{fname}' missing at path '{rel_path}'")
                            continue

                        black_sec = float(loop.get("longest_black_seconds", 0.0))
                        if black_sec > 2.0:
                            errors.append(f"Master loop '{fname}' exceeds black threshold: {black_sec}s > 2.0s")

                        lum = loop.get("perceptual_luminance", {})
                        if not lum.get("passed", False):
                            errors.append(f"Master loop '{fname}' failed perceptual luminance certification")

                    manifest_report["master_loops_checked"] = checked
                    manifest_report["errors"] = errors
                    manifest_report["verified"] = (len(errors) == 0)

                except Exception as m_exc:
                    manifest_report["errors"].append(f"Error parsing bank_manifest.json: {m_exc}")

            healthy = (catalog_report.get("missing", 0) == 0 and catalog_report.get("corrupted", 0) == 0)
            if manifest_report["manifest_present"] and not manifest_report["verified"]:
                healthy = False

            total_records = catalog_report.get("total", catalog_report.get("total_records", 0))
            verified_count = catalog_report.get("verified", total_records - catalog_report.get("missing", 0))

            return sanitize_payload({
                "healthy": healthy,
                "status": "HEALTHY" if healthy else "NEEDS_CLEANUP",
                "total": total_records,
                "total_records": total_records,
                "verified_count": verified_count,
                "catalog_audit": catalog_report,
                "manifest_audit": manifest_report,
            })

        except ToolError:
            raise
        except Exception as exc:
            logger.exception("Unexpected error in audit_loop_catalog: %s", exc)
            raise ToolError(f"audit_loop_catalog failed: {exc}") from exc
