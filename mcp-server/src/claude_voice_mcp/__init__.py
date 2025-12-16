import asyncio
import sys
from .server import app

async def main():
    """Main entry point for MCP server."""
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

def run():
    """Synchronous wrapper for console script entry point."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nVoice MCP server stopped.", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error in Voice MCP: {e}", file=sys.stderr)
        sys.exit(1)
