"""
src/mcp/server.py - MCPServer Factory and Transport Runners for yt-auto.
"""
from __future__ import annotations

import logging
import sys
from typing import Optional

from mcp.server.mcpserver import MCPServer
from starlette.applications import Starlette

from src.mcp.prompts import register_prompts
from src.mcp.resources import register_resources
from src.mcp.tools import register_tools

logger = logging.getLogger("mcp.server")

SERVER_NAME = "yt-auto"
SERVER_VERSION = "2.2.0"
SERVER_INSTRUCTIONS = (
    "Production Model Context Protocol (MCP) server for the yt-auto automation platform. "
    "Provides tools for system preflight, lane queries, video loop catalog audits, dry runs, "
    "and queue management. All operations enforce fail-closed security, resource limits "
    "(<= 2 cores, <= 2 GB RAM), and zero credential leaks."
)


def create_mcp_server() -> MCPServer:
    """Create and configure canonical yt-auto MCPServer instance."""
    server = MCPServer(
        name=SERVER_NAME,
        version=SERVER_VERSION,
        instructions=SERVER_INSTRUCTIONS,
    )

    register_tools(server)
    register_resources(server)
    register_prompts(server)

    return server


async def run_stdio_async(server: Optional[MCPServer] = None) -> None:
    """
    Run server using primary stdio transport.
    The SDK's run_stdio_async automatically performs OS file descriptor diversion
    (diverting fd 1 to stderr) to safeguard JSON-RPC stream integrity.
    """
    if server is None:
        server = create_mcp_server()

    # Route any stray root logging handlers to stderr
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    await server.run_stdio_async()


async def run_sse_async(
    server: Optional[MCPServer] = None,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """Run server using modular SSE transport."""
    if server is None:
        server = create_mcp_server()

    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    await server.run_sse_async(host=host, port=port)


def get_sse_app(server: Optional[MCPServer] = None) -> Starlette:
    """Export Starlette ASGI application for modular SSE deployment."""
    if server is None:
        server = create_mcp_server()
    return server.sse_app()
