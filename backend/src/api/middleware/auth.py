"""API authentication middleware.

Supports two authentication methods:
- API key via X-API-Key header
- OAuth Bearer token via Authorization header

Returns 401 for unauthenticated requests without processing.
Skips authentication for public paths (/docs, /openapi.json, /health, /api/v1/auth).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import get_settings

# Paths that do not require authentication
_PUBLIC_PATHS = {"/docs", "/openapi.json", "/redoc", "/health"}

# Path prefixes that do not require authentication
_PUBLIC_PATH_PREFIXES = ("/api/v1/auth",)


def _is_public_path(path: str) -> bool:
    """Check if a request path is public (no auth required).

    Args:
        path: The request URL path.

    Returns:
        True if the path does not require authentication.
    """
    if path in _PUBLIC_PATHS:
        return True
    for prefix in _PUBLIC_PATH_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


def _validate_api_key(api_key: str, configured_key: str) -> bool:
    """Validate an API key against the configured key.

    Args:
        api_key: The provided API key from the request header.
        configured_key: The configured valid API key from settings.

    Returns:
        True if the API key is valid.
    """
    if not configured_key:
        # No key configured — dev mode, allow all
        return True
    return api_key == configured_key


def _validate_oauth_token(token: str, secret_key: str, algorithm: str) -> dict | None:
    """Validate an OAuth Bearer token (JWT).

    Checks the token signature and expiry.

    Args:
        token: The JWT token string.
        secret_key: The secret key for signature verification.
        algorithm: The JWT algorithm (e.g., HS256).

    Returns:
        The decoded token payload if valid, None otherwise.
    """
    if not secret_key:
        return None

    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
    except JWTError:
        return None

    # Check expiry
    exp = payload.get("exp")
    if exp is not None:
        exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
        if exp_dt < datetime.now(timezone.utc):
            return None

    return payload


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware that authenticates requests via API key or OAuth token.

    Authentication flow:
    1. Skip auth for public paths (/docs, /openapi.json, /health, /api/v1/auth/*)
    2. Check X-API-Key header — validate against configured key
    3. Check Authorization: Bearer <token> — validate JWT signature and expiry
    4. Return 401 if neither method provides valid credentials

    The authenticated requester identity is stored in request.state.requester_id
    for downstream use (logging, authorization).
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Validate authentication before forwarding the request."""
        # Skip auth for CORS preflight requests (OPTIONS)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Skip auth for public/documentation endpoints
        if _is_public_path(request.url.path):
            return await call_next(request)

        # Skip auth for WebSocket upgrade requests (handled separately)
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)

        settings = get_settings()

        # --- Try API Key authentication ---
        api_key = request.headers.get("X-API-Key")
        if api_key:
            if _validate_api_key(api_key, settings.api_key):
                # Store requester identity for logging
                request.state.requester_id = f"apikey:{api_key[:8]}"
                return await call_next(request)
            else:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing API key"},
                )

        # --- Try OAuth Bearer token authentication ---
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]  # Strip "Bearer " prefix
            payload = _validate_oauth_token(
                token, settings.jwt_secret_key, settings.jwt_algorithm
            )
            if payload is not None:
                # Store requester identity from token payload
                requester_id = payload.get("sub", payload.get("user_id", "unknown"))
                request.state.requester_id = f"oauth:{requester_id}"
                return await call_next(request)
            else:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or expired OAuth token"},
                )

        # --- No valid credentials provided ---
        # If no API key is configured at all (dev mode), allow through
        if not settings.api_key and not settings.jwt_secret_key:
            request.state.requester_id = "anonymous"
            return await call_next(request)

        return JSONResponse(
            status_code=401,
            content={"detail": "Authentication required. Provide X-API-Key header or Authorization: Bearer <token>"},
        )


# Keep backward-compatible alias
APIKeyAuthMiddleware = AuthMiddleware
