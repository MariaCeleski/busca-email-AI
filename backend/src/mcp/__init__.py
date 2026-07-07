"""MCP (Model Context Protocol) multi-server client package.

Provides a unified interface to aggregate tools from multiple MCP servers,
making them available to the agent orchestrator.
"""

from __future__ import annotations

from src.mcp.client import MultiServerMCPClient

__all__ = ["MultiServerMCPClient"]
