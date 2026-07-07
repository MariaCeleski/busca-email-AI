"""Multi-server MCP client that aggregates tools from multiple MCP servers.

Uses JSON-RPC over stdio to communicate with each server subprocess.
No external dependencies — only stdlib asyncio, json, and subprocess.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MCPTool:
    """Represents a tool exposed by an MCP server."""

    name: str
    description: str
    input_schema: Dict[str, Any]
    server_name: str


@dataclass
class ServerConfig:
    """Configuration for a single MCP server."""

    transport: str
    command: str
    args: List[str] = field(default_factory=list)


@dataclass
class _ServerConnection:
    """Internal representation of a connected MCP server."""

    name: str
    config: ServerConfig
    process: Optional[asyncio.subprocess.Process] = None
    tools: List[MCPTool] = field(default_factory=list)
    request_id: int = 0


class MultiServerMCPClient:
    """Aggregates multiple MCP servers into a single client.

    Each server is spawned as a subprocess using stdio transport.
    Tools from all servers are merged and accessible via a unified interface.
    """

    def __init__(self, servers: Dict[str, Any]) -> None:
        """Initialize with server configurations.

        Args:
            servers: Dict mapping server names to their configs.
                Each config has: transport, command, args
        """
        self._server_configs: Dict[str, ServerConfig] = {}
        for name, config in servers.items():
            if isinstance(config, ServerConfig):
                self._server_configs[name] = config
            else:
                self._server_configs[name] = ServerConfig(
                    transport=config.get("transport", "stdio"),
                    command=config.get("command", "python"),
                    args=config.get("args", []),
                )
        self._connections: Dict[str, _ServerConnection] = {}
        self._connected = False

    @property
    def connected(self) -> bool:
        """Whether the client has active connections."""
        return self._connected

    @property
    def server_names(self) -> List[str]:
        """List of configured server names."""
        return list(self._server_configs.keys())

    async def connect(self) -> None:
        """Connect to all configured MCP servers.

        Spawns each server as a subprocess and performs the MCP
        initialize handshake followed by tools/list to discover tools.
        """
        for name, config in self._server_configs.items():
            try:
                connection = await self._connect_server(name, config)
                self._connections[name] = connection
                logger.info(
                    "Connected to MCP server '%s' with %d tools",
                    name,
                    len(connection.tools),
                )
            except Exception as exc:
                logger.error("Failed to connect to MCP server '%s': %s", name, exc)
                raise

        self._connected = True

    async def disconnect(self) -> None:
        """Disconnect from all servers gracefully.

        Sends terminate signal and waits for processes to exit.
        """
        for name, conn in self._connections.items():
            try:
                await self._disconnect_server(conn)
                logger.info("Disconnected from MCP server '%s'", name)
            except Exception as exc:
                logger.warning(
                    "Error disconnecting from MCP server '%s': %s", name, exc
                )

        self._connections.clear()
        self._connected = False

    async def get_tools(self) -> List[MCPTool]:
        """Get all available tools from all connected servers.

        Returns:
            Combined list of MCPTool objects from all servers.
        """
        all_tools: List[MCPTool] = []
        for conn in self._connections.values():
            all_tools.extend(conn.tools)
        return all_tools

    async def call_tool(
        self, server_name: str, tool_name: str, arguments: Dict[str, Any]
    ) -> Any:
        """Call a specific tool on a specific server.

        Args:
            server_name: Name of the server that owns the tool.
            tool_name: Name of the tool to invoke.
            arguments: Arguments to pass to the tool.

        Returns:
            The tool's result.

        Raises:
            ValueError: If server_name is not connected.
            RuntimeError: If the tool call fails.
        """
        if server_name not in self._connections:
            raise ValueError(
                f"Server '{server_name}' not connected. "
                f"Available: {list(self._connections.keys())}"
            )

        conn = self._connections[server_name]
        return await self._send_tool_call(conn, tool_name, arguments)

    async def __aenter__(self) -> MultiServerMCPClient:
        """Async context manager entry — connects all servers."""
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit — disconnects all servers."""
        await self.disconnect()

    # --- Private methods ---

    async def _connect_server(
        self, name: str, config: ServerConfig
    ) -> _ServerConnection:
        """Spawn a server subprocess and perform initialization handshake."""
        process = await asyncio.create_subprocess_exec(
            config.command,
            *config.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        conn = _ServerConnection(name=name, config=config, process=process)

        # Send initialize request
        init_response = await self._send_request(conn, "initialize", {})
        if init_response is None:
            raise RuntimeError(
                f"Server '{name}' did not respond to initialize request"
            )

        # Send tools/list to discover available tools
        tools_response = await self._send_request(conn, "tools/list", {})
        if tools_response and "tools" in tools_response:
            for tool_data in tools_response["tools"]:
                conn.tools.append(
                    MCPTool(
                        name=tool_data["name"],
                        description=tool_data.get("description", ""),
                        input_schema=tool_data.get("inputSchema", {}),
                        server_name=name,
                    )
                )

        return conn

    async def _disconnect_server(self, conn: _ServerConnection) -> None:
        """Terminate a server subprocess."""
        if conn.process is None:
            return

        if conn.process.returncode is None:
            # Process still running — terminate gracefully
            conn.process.terminate()
            try:
                await asyncio.wait_for(conn.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                conn.process.kill()
                await conn.process.wait()

    async def _send_request(
        self, conn: _ServerConnection, method: str, params: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Send a JSON-RPC request to a server and read the response.

        Args:
            conn: The server connection.
            method: The JSON-RPC method name.
            params: The method parameters.

        Returns:
            The result field from the JSON-RPC response, or None on error.
        """
        if conn.process is None or conn.process.stdin is None:
            raise RuntimeError(f"Server '{conn.name}' process not available")

        conn.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": conn.request_id,
            "method": method,
            "params": params,
        }

        request_line = json.dumps(request) + "\n"
        conn.process.stdin.write(request_line.encode("utf-8"))
        await conn.process.stdin.drain()

        # Read response line
        if conn.process.stdout is None:
            raise RuntimeError(f"Server '{conn.name}' stdout not available")

        response_line = await asyncio.wait_for(
            conn.process.stdout.readline(), timeout=30.0
        )

        if not response_line:
            raise RuntimeError(
                f"Server '{conn.name}' closed stdout unexpectedly"
            )

        response = json.loads(response_line.decode("utf-8"))

        if "error" in response:
            error = response["error"]
            raise RuntimeError(
                f"Server '{conn.name}' returned error: "
                f"{error.get('message', 'Unknown error')}"
            )

        return response.get("result")

    async def _send_tool_call(
        self, conn: _ServerConnection, tool_name: str, arguments: Dict[str, Any]
    ) -> Any:
        """Send a tools/call request to a server.

        Args:
            conn: The server connection.
            tool_name: Name of the tool to call.
            arguments: Tool arguments.

        Returns:
            The tool result content.
        """
        params = {"name": tool_name, "arguments": arguments}
        result = await self._send_request(conn, "tools/call", params)

        if result is None:
            raise RuntimeError(
                f"Tool '{tool_name}' on server '{conn.name}' returned no result"
            )

        # MCP tools/call returns content array
        content = result.get("content", [])
        if content and isinstance(content, list):
            # Return the first text content
            for item in content:
                if item.get("type") == "text":
                    text = item.get("text", "")
                    # Try to parse as JSON
                    try:
                        return json.loads(text)
                    except (json.JSONDecodeError, TypeError):
                        return text
            return content[0]

        return result
