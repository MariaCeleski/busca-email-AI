"""API key authentication middleware.

Validates X-API-Key header against the configured API key.
Returns 401 for unauthenticated requests without processing.
"""

from __future__ import annotations

from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import get_settings

# Paths that do not require authentication
_PUBLIC_PATHS = {"/docs", "/openapi.json", "/redoc", "/health"}


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Middleware that checks X-API-Key header against settings.api_key.

    Returns 401 JSON response for requests missing or providing
    an invalid API key. Skips authentication for public paths.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Validate the API key before forwarding the request."""
        # Skip auth for public/documentation endpoints
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        # Skip auth for WebSocket upgrade requests (handled separately)
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)

        settings = get_settings()
        api_key = request.headers.get("X-API-Key")

        if not settings.api_key:
            # If no API key is configured, allow all requests (dev mode)
            return await call_next(request)

        if not api_key or api_key != settings.api_key:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key"},
            )

        return await call_next(request)
