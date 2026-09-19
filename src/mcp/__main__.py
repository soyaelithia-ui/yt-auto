"""
CLI entry point for direct execution: python3 -m src.mcp
"""
import argparse
import asyncio
import sys

from src.mcp.server import create_mcp_server, run_sse_async, run_stdio_async


def main() -> int:
    parser = argparse.ArgumentParser(description="yt-auto MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport type (stdio or sse, default: stdio)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host for SSE transport")
    parser.add_argument("--port", type=int, default=8000, help="Port for SSE transport")
    args = parser.parse_args()

    server = create_mcp_server()
    if args.transport == "sse":
        asyncio.run(run_sse_async(server, host=args.host, port=args.port))
    else:
        asyncio.run(run_stdio_async(server))
    return 0


if __name__ == "__main__":
    sys.exit(main())
