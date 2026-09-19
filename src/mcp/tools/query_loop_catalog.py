"""
src/mcp/tools/query_loop_catalog.py - Canonical MCP tool for loop catalog querying.
"""
from __future__ import annotations

import logging
from typing import Annotated, Any, Dict, Optional

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from src.config import DEFAULT_DB_PATH
from src.core.catalog import CHANNEL_THEMES, LoopCatalogRepository
from src.core.domain import canonical_channel
from src.mcp.sanitizer import sanitize_payload

logger = logging.getLogger("mcp.tools.query_loop_catalog")


def register_query_loop_catalog_tool(server: MCPServer) -> None:
    """Register query_loop_catalog tool on the MCPServer instance."""

    @server.tool(
        name="query_loop_catalog",
        description="Search and filter master video loops in the SQLite catalog by category, orientation, and channel compatibility.",
    )
    async def query_loop_catalog(
        category: Annotated[
            Optional[str],
            Field(description="Thematic category (e.g. 'horror', 'dark_forest', 'cosmic_horror', 'drama', 'cozy_ambient')"),
        ] = None,
        orientation: Annotated[
            Optional[str],
            Field(description="Canvas orientation ('vertical' for 9:16 Shorts or 'horizontal' for 16:9 Longform)"),
        ] = None,
        channel: Annotated[
            Optional[str],
            Field(description="Filter by channel compatibility ('moku', 'aelithia', 'scifi')"),
        ] = None,
        limit: Annotated[
            int,
            Field(description="Maximum number of loop records to return"),
        ] = 20,
    ) -> Dict[str, Any]:
        try:
            if orientation and orientation not in ("vertical", "horizontal"):
                raise ToolError(f"Invalid orientation '{orientation}'. Must be 'vertical' or 'horizontal'.")

            if limit <= 0:
                return sanitize_payload({"loops": [], "count": 0})

            effective_limit = min(limit, 100)

            channel_key: Optional[str] = None
            if channel:
                try:
                    channel_key = canonical_channel(channel).value
                except (ValueError, KeyError) as exc:
                    raise ToolError(f"Unknown channel '{channel}': {exc}") from exc

            catalog = LoopCatalogRepository(db_path=DEFAULT_DB_PATH)
            records = catalog.list_loops(
                category=category,
                orientation=orientation,
                limit=effective_limit if not channel_key else 100,
            )

            if channel_key:
                allowed_themes = set(CHANNEL_THEMES.get(channel_key, ()))
                filtered = []
                for rec in records:
                    if rec.channel == channel_key or rec.category in allowed_themes:
                        filtered.append(rec)
                records = filtered[:effective_limit]

            results = [r.to_dict() for r in records]
            return sanitize_payload({"loops": results, "count": len(results)})

        except ToolError:
            raise
        except Exception as exc:
            logger.exception("Unexpected error in query_loop_catalog: %s", exc)
            raise ToolError(f"query_loop_catalog failed: {exc}") from exc
