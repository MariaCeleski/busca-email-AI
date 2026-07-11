"""Access logging middleware.

Logs requester_id, endpoint, method, timestamp, and response_status
using AccessLogger. No body content is included in logs.

Validates: Requirements 10.4
"""

from __future__ import annotations

import hashlib
import logging
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.models.database import get_session_factory

logger = logging.getLogger(__name__)

# Paths that should not generate access log entries
_SKIP_LOGGING_PATHS = {"/docs", "/openapi.json", "/redoc", "/health"}


class AccessLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware that logs API access events without body content.

    Logs requester_id (from auth state, hashed API key, or 'anonymous'),
    endpoint, HTTP method, and response status code.

    No email body content or request/response bodies are ever logged.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Log the access event after processing the request."""
        response = await call_next(request)

        # Don't log health checks or docs
        if request.url.path in _SKIP_LOGGING_PATHS:
            return response

        # Determine requester ID — prefer value set by auth middleware
        requester_id = self._get_requester_id(request)
        endpoint = request.url.path
        method = request.method
        response_status = response.status_code

        # Log to the database asynchronously (best-effort)
        try:
            session_factory = get_session_factory()
            async with session_factory() as session:
                from src.security.access_logger import AccessLogger

                access_logger = AccessLogger(session)
                await access_logger.log_access(
                    requester_id=requester_id,
                    endpoint=endpoint,
                    method=method,
                    response_status=response_status,
                )
                await session.commit()
        except Exception as exc:
            # Access logging should never break request processing
            logger.warning("Failed to log access event: %s", exc)

        return response

    @staticmethod
    def _get_requester_id(request: Request) -> str:
        """Extract requester identity from the request.

        Priority:
        1. request.state.requester_id (set by AuthMiddleware)
        2. Hashed API key from X-API-Key header
        3. 'anonymous' fallback

        Args:
            request: The incoming HTTP request.

        Returns:
            A string identifying the requester (never contains body content).
        """
        # Check if auth middleware set a requester_id
        try:
            if hasattr(request.state, "requester_id"):
                return request.state.requester_id
        except Exception:
            pass

        # Fallback: hash the API key if present
        api_key = request.headers.get("X-API-Key", "")
        if api_key:
            return hashlib.sha256(api_key.encode()).hexdigest()[:16]

        return "anonymous"
