"""MCP server that wraps Gmail functionality.

Exposes Gmail operations as MCP tools via JSON-RPC over stdio.
Tools:
    - fetch_unread_emails: Fetches unread emails from Gmail
    - send_reply: Sends an email reply
    - mark_as_read: Marks an email as read

This server is spawned as a subprocess by the MultiServerMCPClient.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List


# --- Tool Definitions ---

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "fetch_unread_emails",
        "description": "Fetch unread emails from the connected Gmail account.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of emails to fetch (default 50).",
                    "default": 50,
                },
            },
            "required": [],
        },
    },
    {
        "name": "send_reply",
        "description": "Send a reply to an email via Gmail.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "to_address": {
                    "type": "string",
                    "description": "Recipient email address.",
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject line.",
                },
                "body": {
                    "type": "string",
                    "description": "Email body text.",
                },
                "thread_id": {
                    "type": "string",
                    "description": "Gmail thread ID to reply to (optional).",
                },
                "in_reply_to": {
                    "type": "string",
                    "description": "Message-ID header to reply to (optional).",
                },
            },
            "required": ["to_address", "subject", "body"],
        },
    },
    {
        "name": "mark_as_read",
        "description": "Mark a specific email as read in Gmail.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "string",
                    "description": "The Gmail message ID to mark as read.",
                },
            },
            "required": ["message_id"],
        },
    },
]


# --- Tool Handlers ---


async def handle_fetch_unread_emails(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch unread emails using the GmailClient.

    Args:
        arguments: Tool arguments with optional max_results.

    Returns:
        Dict with list of email data.
    """
    # Late import to allow subprocess isolation
    from src.providers.gmail import GmailClient
    from src.config import get_settings

    settings = get_settings()
    # In production, tokens would come from secure storage
    # For the MCP server pattern, we expect environment variables
    import os

    access_token = os.environ.get("GMAIL_ACCESS_TOKEN", "")
    refresh_token = os.environ.get("GMAIL_REFRESH_TOKEN", "")

    client = GmailClient(access_token=access_token, refresh_token=refresh_token)
    emails = await client.fetch_unread()

    max_results = arguments.get("max_results", 50)
    emails = emails[:max_results]

    return {
        "emails": [
            {
                "id": email.provider_message_id,
                "sender": email.sender,
                "subject": email.subject,
                "body": email.body[:500],  # Truncate for tool response
                "timestamp": email.timestamp.isoformat(),
                "thread_id": email.thread_id,
            }
            for email in emails
        ],
        "count": len(emails),
    }


async def handle_send_reply(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Send a reply using the GmailClient.

    Args:
        arguments: Tool arguments with to_address, subject, body, etc.

    Returns:
        Dict with send result.
    """
    from src.providers.gmail import GmailClient
    from src.models.auth import ApprovedReply

    import os

    access_token = os.environ.get("GMAIL_ACCESS_TOKEN", "")
    refresh_token = os.environ.get("GMAIL_REFRESH_TOKEN", "")

    client = GmailClient(access_token=access_token, refresh_token=refresh_token)

    reply = ApprovedReply(
        to_address=arguments["to_address"],
        subject=arguments["subject"],
        body=arguments["body"],
        thread_id=arguments.get("thread_id"),
        in_reply_to=arguments.get("in_reply_to"),
    )

    result = await client.send_reply(reply)
    return {
        "success": result.success,
        "message_id": result.provider_message_id if result.success else None,
        "error": result.error if not result.success else None,
    }


async def handle_mark_as_read(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Mark an email as read by removing the UNREAD label.

    Args:
        arguments: Tool arguments with message_id.

    Returns:
        Dict with operation result.
    """
    import os
    import httpx

    access_token = os.environ.get("GMAIL_ACCESS_TOKEN", "")
    message_id = arguments["message_id"]

    gmail_api_base = "https://gmail.googleapis.com/gmail/v1/users/me"
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient() as http_client:
        response = await http_client.post(
            f"{gmail_api_base}/messages/{message_id}/modify",
            headers=headers,
            json={"removeLabelIds": ["UNREAD"]},
        )

    if response.status_code == 200:
        return {"success": True, "message_id": message_id}
    else:
        return {
            "success": False,
            "error": f"HTTP {response.status_code}: {response.text}",
        }


TOOL_HANDLERS = {
    "fetch_unread_emails": handle_fetch_unread_emails,
    "send_reply": handle_send_reply,
    "mark_as_read": handle_mark_as_read,
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
            "serverInfo": {"name": "gmail-mcp-server", "version": "1.0.0"},
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
