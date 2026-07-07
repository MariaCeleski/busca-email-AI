"""Unit tests for MultiServerMCPClient.

Tests cover:
- Connecting to multiple servers
- Aggregating tools from all servers
- Routing tool calls to the correct server
- Graceful disconnect
- Error handling when a server is unavailable
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp.client import MCPTool, MultiServerMCPClient, ServerConfig, _ServerConnection


# --- Helpers ---


def _make_server_configs() -> Dict[str, Dict[str, Any]]:
    """Create test server configurations."""
    return {
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


def _mock_process(tools: List[Dict[str, Any]]) -> MagicMock:
    """Create a mock subprocess that responds to MCP protocol messages."""
    process = MagicMock()
    process.returncode = None

    # Mock stdin
    stdin = MagicMock()
    stdin.write = MagicMock()
    stdin.drain = AsyncMock()
    process.stdin = stdin

    # Build response sequence: initialize response, then tools/list response
    init_response = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "test-server", "version": "1.0.0"},
        },
    }).encode("utf-8") + b"\n"

    tools_response = json.dumps({
        "jsonrpc": "2.0",
        "id": 2,
        "result": {"tools": tools},
    }).encode("utf-8") + b"\n"

    # Mock stdout with readline that returns responses in sequence
    stdout = MagicMock()
    stdout.readline = AsyncMock(side_effect=[init_response, tools_response])
    process.stdout = stdout

    # Mock stderr
    process.stderr = MagicMock()

    # Mock terminate and wait
    process.terminate = MagicMock()
    process.kill = MagicMock()
    process.wait = AsyncMock()

    return process


# --- Test Class ---


class TestMultiServerMCPClientInit:
    """Tests for MultiServerMCPClient initialization."""

    def test_init_with_dict_configs(self) -> None:
        """Test initialization with raw dict configurations."""
        configs = _make_server_configs()
        client = MultiServerMCPClient(configs)

        assert not client.connected
        assert set(client.server_names) == {"gmail", "agenda", "vector_search"}

    def test_init_with_server_config_objects(self) -> None:
        """Test initialization with ServerConfig dataclass instances."""
        configs = {
            "test_server": ServerConfig(
                transport="stdio",
                command="python",
                args=["test_server.py"],
            ),
        }
        client = MultiServerMCPClient(configs)

        assert "test_server" in client.server_names

    def test_init_empty_servers(self) -> None:
        """Test initialization with no servers configured."""
        client = MultiServerMCPClient({})
        assert client.server_names == []
        assert not client.connected


class TestMultiServerMCPClientConnect:
    """Tests for connecting to MCP servers."""

    @pytest.mark.asyncio
    async def test_connect_multiple_servers(self) -> None:
        """Test connecting to multiple servers spawns subprocesses."""
        gmail_tools = [
            {"name": "fetch_unread_emails", "description": "Fetch unread", "inputSchema": {}},
            {"name": "send_reply", "description": "Send reply", "inputSchema": {}},
        ]
        agenda_tools = [
            {"name": "get_pending_emails", "description": "Get pending", "inputSchema": {}},
        ]
        vector_tools = [
            {"name": "search_similar_emails", "description": "Search similar", "inputSchema": {}},
        ]

        processes = [
            _mock_process(gmail_tools),
            _mock_process(agenda_tools),
            _mock_process(vector_tools),
        ]

        configs = _make_server_configs()
        client = MultiServerMCPClient(configs)

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(side_effect=processes)):
            await client.connect()

        assert client.connected
        tools = await client.get_tools()
        assert len(tools) == 4  # 2 + 1 + 1

    @pytest.mark.asyncio
    async def test_connect_sends_initialize_and_tools_list(self) -> None:
        """Test that connect sends initialize and tools/list requests."""
        tools_def = [
            {"name": "test_tool", "description": "A test tool", "inputSchema": {"type": "object"}},
        ]
        process = _mock_process(tools_def)

        configs = {"test": {"transport": "stdio", "command": "python", "args": ["test.py"]}}
        client = MultiServerMCPClient(configs)

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)):
            await client.connect()

        # Verify stdin.write was called twice (initialize + tools/list)
        assert process.stdin.write.call_count == 2

        # Parse the requests
        first_call = process.stdin.write.call_args_list[0][0][0]
        first_request = json.loads(first_call.decode("utf-8"))
        assert first_request["method"] == "initialize"

        second_call = process.stdin.write.call_args_list[1][0][0]
        second_request = json.loads(second_call.decode("utf-8"))
        assert second_request["method"] == "tools/list"

    @pytest.mark.asyncio
    async def test_connect_failure_raises(self) -> None:
        """Test that a connection failure raises RuntimeError."""
        configs = {"bad": {"transport": "stdio", "command": "python", "args": ["bad.py"]}}
        client = MultiServerMCPClient(configs)

        with patch(
            "asyncio.create_subprocess_exec",
            new=AsyncMock(side_effect=OSError("Process failed")),
        ):
            with pytest.raises(OSError, match="Process failed"):
                await client.connect()

        assert not client.connected


class TestMultiServerMCPClientGetTools:
    """Tests for tool aggregation."""

    @pytest.mark.asyncio
    async def test_get_tools_aggregates_from_all_servers(self) -> None:
        """Test that get_tools returns tools from all connected servers."""
        gmail_tools = [
            {"name": "fetch_unread_emails", "description": "Fetch unread", "inputSchema": {}},
            {"name": "send_reply", "description": "Send reply", "inputSchema": {}},
            {"name": "mark_as_read", "description": "Mark read", "inputSchema": {}},
        ]
        agenda_tools = [
            {"name": "get_pending_emails", "description": "Get pending", "inputSchema": {}},
            {"name": "get_email_status", "description": "Get status", "inputSchema": {}},
            {"name": "schedule_processing", "description": "Schedule", "inputSchema": {}},
        ]
        vector_tools = [
            {"name": "search_similar_emails", "description": "Search", "inputSchema": {}},
            {"name": "store_email_embedding", "description": "Store", "inputSchema": {}},
        ]

        processes = [
            _mock_process(gmail_tools),
            _mock_process(agenda_tools),
            _mock_process(vector_tools),
        ]

        configs = _make_server_configs()
        client = MultiServerMCPClient(configs)

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(side_effect=processes)):
            await client.connect()

        tools = await client.get_tools()
        assert len(tools) == 8  # 3 + 3 + 2

        tool_names = {t.name for t in tools}
        assert "fetch_unread_emails" in tool_names
        assert "send_reply" in tool_names
        assert "mark_as_read" in tool_names
        assert "get_pending_emails" in tool_names
        assert "get_email_status" in tool_names
        assert "schedule_processing" in tool_names
        assert "search_similar_emails" in tool_names
        assert "store_email_embedding" in tool_names

    @pytest.mark.asyncio
    async def test_get_tools_preserves_server_name(self) -> None:
        """Test that each tool knows which server it belongs to."""
        gmail_tools = [
            {"name": "fetch_unread_emails", "description": "Fetch", "inputSchema": {}},
        ]
        process = _mock_process(gmail_tools)

        configs = {"gmail": {"transport": "stdio", "command": "python", "args": ["gmail.py"]}}
        client = MultiServerMCPClient(configs)

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)):
            await client.connect()

        tools = await client.get_tools()
        assert tools[0].server_name == "gmail"

    @pytest.mark.asyncio
    async def test_get_tools_empty_when_not_connected(self) -> None:
        """Test that get_tools returns empty list when no servers connected."""
        client = MultiServerMCPClient({})
        tools = await client.get_tools()
        assert tools == []


class TestMultiServerMCPClientCallTool:
    """Tests for tool call routing."""

    @pytest.mark.asyncio
    async def test_call_tool_routes_to_correct_server(self) -> None:
        """Test that call_tool sends request to the right server."""
        tools_def = [
            {"name": "fetch_unread_emails", "description": "Fetch", "inputSchema": {}},
        ]
        process = _mock_process(tools_def)

        # Add a third response for the tool call
        tool_call_response = json.dumps({
            "jsonrpc": "2.0",
            "id": 3,
            "result": {
                "content": [{"type": "text", "text": json.dumps({"emails": [], "count": 0})}],
            },
        }).encode("utf-8") + b"\n"

        process.stdout.readline = AsyncMock(
            side_effect=[
                # initialize response
                json.dumps({
                    "jsonrpc": "2.0", "id": 1,
                    "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "test", "version": "1.0.0"}},
                }).encode("utf-8") + b"\n",
                # tools/list response
                json.dumps({
                    "jsonrpc": "2.0", "id": 2, "result": {"tools": tools_def},
                }).encode("utf-8") + b"\n",
                # tools/call response
                tool_call_response,
            ]
        )

        configs = {"gmail": {"transport": "stdio", "command": "python", "args": ["gmail.py"]}}
        client = MultiServerMCPClient(configs)

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)):
            await client.connect()

        result = await client.call_tool("gmail", "fetch_unread_emails", {"max_results": 10})
        assert result == {"emails": [], "count": 0}

        # Verify the tools/call request was sent
        third_call = process.stdin.write.call_args_list[2][0][0]
        third_request = json.loads(third_call.decode("utf-8"))
        assert third_request["method"] == "tools/call"
        assert third_request["params"]["name"] == "fetch_unread_emails"
        assert third_request["params"]["arguments"] == {"max_results": 10}

    @pytest.mark.asyncio
    async def test_call_tool_unknown_server_raises(self) -> None:
        """Test that calling a tool on an unknown server raises ValueError."""
        client = MultiServerMCPClient({})
        client._connected = True

        with pytest.raises(ValueError, match="Server 'nonexistent' not connected"):
            await client.call_tool("nonexistent", "some_tool", {})

    @pytest.mark.asyncio
    async def test_call_tool_server_error_raises(self) -> None:
        """Test that a server error response raises RuntimeError."""
        tools_def = [
            {"name": "test_tool", "description": "Test", "inputSchema": {}},
        ]
        process = _mock_process(tools_def)

        # Add error response for tool call
        error_response = json.dumps({
            "jsonrpc": "2.0",
            "id": 3,
            "error": {"code": -32000, "message": "Tool execution failed"},
        }).encode("utf-8") + b"\n"

        process.stdout.readline = AsyncMock(
            side_effect=[
                json.dumps({
                    "jsonrpc": "2.0", "id": 1,
                    "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "test", "version": "1.0.0"}},
                }).encode("utf-8") + b"\n",
                json.dumps({
                    "jsonrpc": "2.0", "id": 2, "result": {"tools": tools_def},
                }).encode("utf-8") + b"\n",
                error_response,
            ]
        )

        configs = {"test": {"transport": "stdio", "command": "python", "args": ["test.py"]}}
        client = MultiServerMCPClient(configs)

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)):
            await client.connect()

        with pytest.raises(RuntimeError, match="Tool execution failed"):
            await client.call_tool("test", "test_tool", {})


class TestMultiServerMCPClientDisconnect:
    """Tests for graceful disconnect."""

    @pytest.mark.asyncio
    async def test_disconnect_terminates_all_processes(self) -> None:
        """Test that disconnect terminates all server subprocesses."""
        tools_def = [{"name": "t", "description": "t", "inputSchema": {}}]
        process1 = _mock_process(tools_def)
        process2 = _mock_process(tools_def)

        configs = {
            "server1": {"transport": "stdio", "command": "python", "args": ["s1.py"]},
            "server2": {"transport": "stdio", "command": "python", "args": ["s2.py"]},
        }
        client = MultiServerMCPClient(configs)

        with patch(
            "asyncio.create_subprocess_exec",
            new=AsyncMock(side_effect=[process1, process2]),
        ):
            await client.connect()

        assert client.connected

        await client.disconnect()

        assert not client.connected
        process1.terminate.assert_called_once()
        process2.terminate.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_handles_already_exited_process(self) -> None:
        """Test disconnect handles processes that already exited."""
        tools_def = [{"name": "t", "description": "t", "inputSchema": {}}]
        process = _mock_process(tools_def)
        # Process already exited
        process.returncode = 0

        configs = {"server": {"transport": "stdio", "command": "python", "args": ["s.py"]}}
        client = MultiServerMCPClient(configs)

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)):
            await client.connect()

        # Should not raise
        await client.disconnect()
        assert not client.connected
        # terminate should not be called since process already exited
        process.terminate.assert_not_called()

    @pytest.mark.asyncio
    async def test_disconnect_kills_on_timeout(self) -> None:
        """Test that disconnect kills process if terminate times out."""
        tools_def = [{"name": "t", "description": "t", "inputSchema": {}}]
        process = _mock_process(tools_def)
        # Make wait timeout
        process.wait = AsyncMock(side_effect=[asyncio.TimeoutError(), None])

        configs = {"server": {"transport": "stdio", "command": "python", "args": ["s.py"]}}
        client = MultiServerMCPClient(configs)

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)):
            await client.connect()

        await client.disconnect()
        process.kill.assert_called_once()


class TestMultiServerMCPClientContextManager:
    """Tests for async context manager usage."""

    @pytest.mark.asyncio
    async def test_context_manager_connects_and_disconnects(self) -> None:
        """Test using the client as an async context manager."""
        tools_def = [{"name": "t", "description": "t", "inputSchema": {}}]
        process = _mock_process(tools_def)

        configs = {"server": {"transport": "stdio", "command": "python", "args": ["s.py"]}}

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)):
            async with MultiServerMCPClient(configs) as client:
                assert client.connected
                tools = await client.get_tools()
                assert len(tools) == 1

        # After exiting context, should be disconnected
        assert not client.connected


class TestMultiServerMCPClientErrorHandling:
    """Tests for error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_server_unavailable_on_connect(self) -> None:
        """Test handling when a server process fails to start."""
        configs = {"bad": {"transport": "stdio", "command": "nonexistent_cmd", "args": []}}
        client = MultiServerMCPClient(configs)

        with patch(
            "asyncio.create_subprocess_exec",
            new=AsyncMock(side_effect=FileNotFoundError("Command not found")),
        ):
            with pytest.raises(FileNotFoundError):
                await client.connect()

    @pytest.mark.asyncio
    async def test_server_closes_stdout_during_init(self) -> None:
        """Test handling when server closes stdout during initialization."""
        process = MagicMock()
        process.returncode = None
        process.stdin = MagicMock()
        process.stdin.write = MagicMock()
        process.stdin.drain = AsyncMock()
        process.stdout = MagicMock()
        # Empty readline = closed stdout
        process.stdout.readline = AsyncMock(return_value=b"")
        process.stderr = MagicMock()
        process.terminate = MagicMock()
        process.kill = MagicMock()
        process.wait = AsyncMock()

        configs = {"bad": {"transport": "stdio", "command": "python", "args": ["bad.py"]}}
        client = MultiServerMCPClient(configs)

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)):
            with pytest.raises(RuntimeError, match="closed stdout unexpectedly"):
                await client.connect()

    @pytest.mark.asyncio
    async def test_tool_call_returns_plain_text(self) -> None:
        """Test handling tool result that is plain text (not JSON)."""
        tools_def = [{"name": "echo", "description": "Echo", "inputSchema": {}}]
        process = _mock_process(tools_def)

        # Add plain text response for tool call
        tool_response = json.dumps({
            "jsonrpc": "2.0",
            "id": 3,
            "result": {
                "content": [{"type": "text", "text": "Hello, world!"}],
            },
        }).encode("utf-8") + b"\n"

        process.stdout.readline = AsyncMock(
            side_effect=[
                json.dumps({
                    "jsonrpc": "2.0", "id": 1,
                    "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "test", "version": "1.0.0"}},
                }).encode("utf-8") + b"\n",
                json.dumps({
                    "jsonrpc": "2.0", "id": 2, "result": {"tools": tools_def},
                }).encode("utf-8") + b"\n",
                tool_response,
            ]
        )

        configs = {"test": {"transport": "stdio", "command": "python", "args": ["t.py"]}}
        client = MultiServerMCPClient(configs)

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)):
            await client.connect()

        result = await client.call_tool("test", "echo", {})
        assert result == "Hello, world!"


class TestMCPToolModel:
    """Tests for the MCPTool dataclass."""

    def test_mcp_tool_creation(self) -> None:
        """Test creating an MCPTool instance."""
        tool = MCPTool(
            name="fetch_unread_emails",
            description="Fetch unread emails from Gmail",
            input_schema={"type": "object", "properties": {}},
            server_name="gmail",
        )
        assert tool.name == "fetch_unread_emails"
        assert tool.server_name == "gmail"

    def test_mcp_tool_equality(self) -> None:
        """Test MCPTool equality comparison."""
        tool1 = MCPTool(name="t", description="d", input_schema={}, server_name="s")
        tool2 = MCPTool(name="t", description="d", input_schema={}, server_name="s")
        assert tool1 == tool2


class TestServerConfig:
    """Tests for ServerConfig dataclass."""

    def test_server_config_defaults(self) -> None:
        """Test ServerConfig default values."""
        config = ServerConfig(transport="stdio", command="python")
        assert config.args == []

    def test_server_config_with_args(self) -> None:
        """Test ServerConfig with custom args."""
        config = ServerConfig(
            transport="stdio",
            command="python",
            args=["-m", "server"],
        )
        assert config.args == ["-m", "server"]
