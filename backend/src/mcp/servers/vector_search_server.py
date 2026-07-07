"""MCP server for semantic search via vector embeddings.

Exposes vector store operations as MCP tools via JSON-RPC over stdio.
Tools:
    - search_similar_emails: Searches for similar emails by semantic similarity
    - store_email_embedding: Stores a new email embedding

This server is spawned as a subprocess by the MultiServerMCPClient.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List


# --- Tool Definitions ---

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "search_similar_emails",
        "description": "Search for emails similar to a given query text using semantic similarity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query_text": {
                    "type": "string",
                    "description": "Text to find similar emails for.",
                },
                "k": {
                    "type": "integer",
                    "description": "Number of results to return (default 5).",
                    "default": 5,
                },
                "sender_filter": {
                    "type": "string",
                    "description": "Optional filter by sender email.",
                },
                "category_filter": {
                    "type": "string",
                    "description": "Optional filter by email category.",
                },
            },
            "required": ["query_text"],
        },
    },
    {
        "name": "store_email_embedding",
        "description": "Generate and store an embedding for an email in the vector store.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "email_id": {
                    "type": "string",
                    "description": "Unique identifier for the email.",
                },
                "text": {
                    "type": "string",
                    "description": "Email text content to embed.",
                },
                "sender": {
                    "type": "string",
                    "description": "Email sender address.",
                },
                "timestamp": {
                    "type": "string",
                    "description": "Email timestamp in ISO format.",
                },
                "category": {
                    "type": "string",
                    "description": "Email category (e.g., urgent, personal, newsletter).",
                },
                "provider_message_id": {
                    "type": "string",
                    "description": "Provider-specific message ID.",
                },
                "thread_id": {
                    "type": "string",
                    "description": "Optional thread ID.",
                },
            },
            "required": ["email_id", "text", "sender", "timestamp", "category", "provider_message_id"],
        },
    },
]


# --- Tool Handlers ---


async def handle_search_similar_emails(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Search for similar emails using VectorStoreService.

    Args:
        arguments: Tool arguments with query_text, k, and optional filters.

    Returns:
        Dict with search results.
    """
    from src.services.vector_store import VectorStoreService
    from src.models.vector_store import MetadataFilter
    from src.models.enums import EmailCategory

    query_text = arguments["query_text"]
    k = arguments.get("k", 5)

    # Build filters
    filters = None
    sender_filter = arguments.get("sender_filter")
    category_filter = arguments.get("category_filter")

    if sender_filter or category_filter:
        category_enum = None
        if category_filter:
            try:
                category_enum = EmailCategory(category_filter)
            except ValueError:
                pass

        filters = MetadataFilter(
            sender=sender_filter,
            category=category_enum,
        )

    service = VectorStoreService()
    results = service.search_similar(query_text=query_text, k=k, filters=filters)

    return {
        "results": [
            {
                "email_id": r.email_id,
                "similarity_score": r.similarity_score,
                "text_snippet": r.text_snippet,
                "sender": r.metadata.sender,
                "category": r.metadata.category.value,
                "timestamp": r.metadata.timestamp.isoformat(),
            }
            for r in results
        ],
        "count": len(results),
    }


async def handle_store_email_embedding(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Store an email embedding using VectorStoreService.

    Args:
        arguments: Tool arguments with email data.

    Returns:
        Dict with storage confirmation.
    """
    from src.services.vector_store import VectorStoreService
    from src.models.vector_store import EmailMetadata
    from src.models.enums import EmailCategory
    from datetime import datetime

    email_id = arguments["email_id"]
    text = arguments["text"]

    # Parse category
    try:
        category = EmailCategory(arguments["category"])
    except ValueError:
        category = EmailCategory.NEWSLETTER  # Default fallback

    # Parse timestamp
    try:
        timestamp = datetime.fromisoformat(arguments["timestamp"])
    except (ValueError, TypeError):
        from datetime import timezone
        timestamp = datetime.now(timezone.utc)

    metadata = EmailMetadata(
        email_id=email_id,
        sender=arguments["sender"],
        timestamp=timestamp,
        category=category,
        provider_message_id=arguments["provider_message_id"],
        thread_id=arguments.get("thread_id"),
    )

    service = VectorStoreService()
    record_id = service.store_embedding(
        email_id=email_id,
        text=text,
        metadata=metadata,
    )

    return {
        "success": True,
        "record_id": record_id,
        "email_id": email_id,
    }


TOOL_HANDLERS = {
    "search_similar_emails": handle_search_similar_emails,
    "store_email_embedding": handle_store_email_embedding,
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
            "serverInfo": {"name": "vector-search-mcp-server", "version": "1.0.0"},
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
