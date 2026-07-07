"""Integration layer connecting MCP servers to the agent orchestrator.

Provides factory functions to create an MCP-enhanced orchestrator
with tools from all configured MCP servers.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from src.mcp.client import MCPTool, MultiServerMCPClient

logger = logging.getLogger(__name__)


# Default server configurations
DEFAULT_SERVER_CONFIGS: Dict[str, Dict[str, Any]] = {
    "gmail": {
        "transport": "stdio",
        "command": "python",
        "args": ["src/mcp/servers/gmail_server.py"],
    },
    "agenda": {
        "transport": "stdio",
        "command": "python",
        "args": ["src/mcp/servers/agenda_server.py"],
    },
    "vector_search": {
        "transport": "stdio",
        "command": "python",
        "args": ["src/mcp/servers/vector_search_server.py"],
    },
}


async def create_mcp_enhanced_orchestrator(
    server_configs: Dict[str, Dict[str, Any]] = None,
) -> Tuple[MultiServerMCPClient, List[MCPTool]]:
    """Create an orchestrator with MCP tools available to all agents.

    Spawns all configured MCP servers, connects to them, and aggregates
    their tools into a single list accessible by the orchestrator.

    Args:
        server_configs: Optional custom server configurations.
            Defaults to DEFAULT_SERVER_CONFIGS.

    Returns:
        Tuple of (client, tools) where client is the connected
        MultiServerMCPClient and tools is the full list of available tools.
    """
    configs = server_configs or DEFAULT_SERVER_CONFIGS

    client = MultiServerMCPClient(configs)
    await client.connect()

    tools = await client.get_tools()

    logger.info(
        "MCP-enhanced orchestrator created with %d tools from %d servers",
        len(tools),
        len(configs),
    )

    return client, tools


def get_tools_by_server(tools: List[MCPTool]) -> Dict[str, List[MCPTool]]:
    """Group tools by their server name.

    Args:
        tools: List of MCPTool objects.

    Returns:
        Dict mapping server names to lists of tools.
    """
    grouped: Dict[str, List[MCPTool]] = {}
    for tool in tools:
        grouped.setdefault(tool.server_name, []).append(tool)
    return grouped


def find_tool(tools: List[MCPTool], tool_name: str) -> MCPTool:
    """Find a tool by name across all servers.

    Args:
        tools: List of MCPTool objects.
        tool_name: The name of the tool to find.

    Returns:
        The matching MCPTool.

    Raises:
        ValueError: If the tool is not found.
    """
    for tool in tools:
        if tool.name == tool_name:
            return tool
    available = [t.name for t in tools]
    raise ValueError(
        f"Tool '{tool_name}' not found. Available tools: {available}"
    )
