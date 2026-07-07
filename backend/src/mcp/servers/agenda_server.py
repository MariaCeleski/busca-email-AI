"""MCP server for email processing agenda management.

Exposes agenda/scheduling operations as MCP tools via JSON-RPC over stdio.
Tools:
    - get_pending_emails: Lists emails pending processing
    - get_email_status: Gets processing status of an email
    - schedule_processing: Schedules an email for processing

This server is spawned as a subprocess by the MultiServerMCPClient.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List


# --- In-memory agenda store (process-local) ---
# In production this would use the ProcessedEmailRepository via DB session.

_agenda: Dict[str, Dict[str, Any]] = {}


# --- Tool Definitions ---

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "get_pending_emails",
        "description": "List emails that are pending processing in the agenda.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of pending emails to return (default 20).",
                    "default": 20,
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_email_status",
        "description": "Get the current processing status of a specific email.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "email_id": {
                    "type": "string",
                    "description": "The email ID to check status for.",
                },
            },
            "required": ["email_id"],
        },
    },
    {
        "name": "schedule_processing",
        "description": "Schedule an email for processing in the pipeline.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "email_id": {
                    "type": "string",
                    "description": "The email ID to schedule.",
                },
                "priority": {
                    "type": "string",
                    "description": "Processing priority: high, medium, low.",
                    "enum": ["high", "medium", "low"],
                    "default": "medium",
                },
                "metadata": {
                    "type": "object",
                    "description": "Optional metadata about the email.",
                },
            },
            "required": ["email_id"],
        },
    },
]


# --- Tool Handlers ---


async def handle_get_pending_emails(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """List emails with 'pending' status from the agenda.

    Args:
        arguments: Tool arguments with optional limit.

    Returns:
        Dict with list of pending emails.
    """
    limit = arguments.get("limit", 20)
    pending = [
        entry for entry in _agenda.values() if entry["status"] == "pending"
    ]
    # Sort by scheduled time
    pending.sort(key=lambda x: x.get("scheduled_at", ""))
    pending = pending[:limit]

    return {
        "pending_emails": pending,
        "count": len(pending),
    }


async def handle_get_email_status(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Get the processing status of a specific email.

    Args:
        arguments: Tool arguments with email_id.

    Returns:
        Dict with email status information.
    """
    email_id = arguments["email_id"]
    entry = _agenda.get(email_id)

    if entry is None:
        return {
            "email_id": email_id,
            "status": "not_found",
            "message": f"No agenda entry found for email_id: {email_id}",
        }

    return {
        "email_id": email_id,
        "status": entry["status"],
        "priority": entry.get("priority", "medium"),
        "scheduled_at": entry.get("scheduled_at"),
        "metadata": entry.get("metadata", {}),
    }


async def handle_schedule_processing(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Schedule an email for processing.

    Args:
        arguments: Tool arguments with email_id, priority, and metadata.

    Returns:
        Dict with scheduling confirmation.
    """
    email_id = arguments["email_id"]
    priority = arguments.get("priority", "medium")
    metadata = arguments.get("metadata", {})

    now = datetime.now(timezone.utc).isoformat()

    _agenda[email_id] = {
        "email_id": email_id,
        "status": "pending",
        "priority": priority,
        "scheduled_at": now,
        "metadata": metadata,
    }

    return {
        "success": True,
        "email_id": email_id,
        "status": "pending",
        "priority": priority,
        "scheduled_at": now,
    }


TOOL_HANDLERS = {
    "get_pending_emails": handle_get_pending_emails,
    "get_email_status": handle_get_email_status,
    "schedule_processing": handle_schedule_processing,
}


# --- JSON-RPC Server Loop ---


def make_response(request_id: Any, result: Any) -> str:
    """Create a JSON-RPC success response."""
    return json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result})


def make_error(request_id: Any, code: int, message: str) -> str:
    """Create a JSON-RPC error response."""
    return json.dumps(
        {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
    )


async def handle_request(request: Dict[str, Any]) -> str:
    """Handle a single JSON-RPC request.

    Args:
        request: Parsed JSON-RPC request.

    Returns:
        JSON-RPC response string.
    """
    request_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params", {})

    if method == "initialize":
        return make_response(request_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "agenda-mcp-server", "version": "1.0.0"},
        })

    elif method == "tools/list":
        return make_response(request_id, {"tools": TOOLS})

    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        handler = TOOL_HANDLERS.get(tool_name)
        if handler is None:
            return make_error(request_id, -32601, f"Unknown tool: {tool_name}")

        try:
            result = await handler(arguments)
            return make_response(request_id, {
                "content": [{"type": "text", "text": json.dumps(result)}],
            })
        except Exception as exc:
            return make_error(request_id, -32000, str(exc))

    else:
        return make_error(request_id, -32601, f"Unknown method: {method}")


async def main() -> None:
    """Main server loop — reads JSON-RPC from stdin, writes responses to stdout."""
    import asyncio

    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        line = await reader.readline()
        if not line:
            break

        try:
            request = json.loads(line.decode("utf-8"))
        except json.JSONDecodeError:
            continue

        response = await handle_request(request)
        sys.stdout.write(response + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
