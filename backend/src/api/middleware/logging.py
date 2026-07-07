"""Access logging middleware.

Logs requester_id, endpoint, method, and response_status using AccessLogger.
No body content is included in logs.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.models.database import get_session_factory

logger = logging.getLogger(__name__)


class AccessLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware that logs API access events without body content.

    Logs requester_id (hash of API key or 'anonymous'), endpoint,
    HTTP method, and response status code.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Log the access event after processing the request."""
        response = await call_next(request)

        # Don't log health checks or docs
        if request.url.path in {"/docs", "/openapi.json", "/redoc", "/health"}:
            return response

        # Determine requester ID from API key (hashed) or 'anonymous'
        api_key = request.headers.get("X-API-Key", "")
        if api_key:
            requester_id = hashlib.sha256(api_key.encode()).hexdigest()[:16]
        else:
            requester_id = "anonymous"

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
