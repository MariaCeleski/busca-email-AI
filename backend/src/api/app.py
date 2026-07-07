"""FastAPI application factory.

Creates and configures the FastAPI application with:
- CORS middleware
- API key authentication middleware
- Access logging middleware
- All API routers
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import get_settings


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI app instance with all middleware and routers.
    """
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
    )

    # --- CORS Middleware ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Authentication Middleware ---
    from src.api.middleware.auth import APIKeyAuthMiddleware

    app.add_middleware(APIKeyAuthMiddleware)

    # --- Access Logging Middleware ---
    from src.api.middleware.logging import AccessLoggingMiddleware

    app.add_middleware(AccessLoggingMiddleware)

    # --- Routers ---
    from src.api.routers.emails import router as emails_router
    from src.api.routers.fetch import router as fetch_router
    from src.api.routers.websocket import router as websocket_router

    app.include_router(emails_router)
    app.include_router(fetch_router)
    app.include_router(websocket_router)

    # --- Health check ---
    @app.get("/health")
    async def health_check():
        return {"status": "healthy"}

    return app
