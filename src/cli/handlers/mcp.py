"""
src/cli/handlers/mcp.py - CLI Handler for `main.py mcp` subcommand.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

logger = logging.getLogger("cli.mcp")


def handle_mcp(args: argparse.Namespace, parser: argparse.ArgumentParser | None = None) -> int:
    """Start the Model Context Protocol (MCP) server."""
    from src.mcp.server import create_mcp_server, run_sse_async, run_stdio_async

    transport = getattr(args, "transport", "stdio") or "stdio"
    host = getattr(args, "host", "127.0.0.1") or "127.0.0.1"
    port = getattr(args, "port", 8000) or 8000

    server = create_mcp_server()

    if transport == "sse":
        print(f"Starting yt-auto MCP Server (SSE) on http://{host}:{port}...", file=sys.stderr)
        asyncio.run(run_sse_async(server, host=host, port=port))
    else:
        # stdio transport logs to stderr
        asyncio.run(run_stdio_async(server))

    return 0
