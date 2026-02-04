"""MCP server entry point.

This module provides the main() function that starts an MCP server
using stdio transport, making Tether tools available to MCP clients.
"""

import asyncio
import sys

import structlog

logger = structlog.get_logger(__name__)


def main() -> None:
    """Main entry point for MCP server.

    Starts an MCP server using stdio transport, exposing Tether
    functionality as MCP tools.
    """
    logger.info("Starting MCP server")

    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
    except ImportError:
        print("ERROR: MCP SDK not installed. Install with: pip install mcp", file=sys.stderr)
        sys.exit(1)

    # Import tool functions
    from tether.mcp.tools import execute_tool, get_tool_definitions

    # Create MCP server
    server = Server("tether-agent")

    # Register tools
    tool_definitions = get_tool_definitions()

    for tool_def in tool_definitions:
        tool_name = tool_def["name"]

        # Create tool handler that calls execute_tool
        async def tool_handler(arguments: dict, name: str = tool_name):
            try:
                result = await execute_tool(name, arguments)
                return [{"type": "text", "text": str(result)}]
            except Exception as e:
                logger.exception("Tool execution failed", tool=name, error=str(e))
                return [{"type": "text", "text": f"Error: {e}"}]

        # Register with MCP server
        server.tool(
            name=tool_name,
            description=tool_def["description"],
            input_schema=tool_def["input_schema"],
        )(tool_handler)

    logger.info("Registered MCP tools", tool_count=len(tool_definitions))

    # Run server with stdio transport
    async def run():
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    asyncio.run(run())


if __name__ == "__main__":
    main()
