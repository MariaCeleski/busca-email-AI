"""FastAPI application factory.

Creates and configures the FastAPI application with:
- CORS middleware
- Authentication middleware (API key + OAuth Bearer token)
- Access logging middleware
- Request validation error handler (422 with field-level errors)
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

    # --- Authentication Middleware (API key + OAuth token) ---
    from src.api.middleware.auth import AuthMiddleware

    app.add_middleware(AuthMiddleware)

    # --- Access Logging Middleware ---
    from src.api.middleware.logging import AccessLoggingMiddleware

    app.add_middleware(AccessLoggingMiddleware)

    # --- Request Validation Error Handler (422 with field-level errors) ---
    from src.api.middleware.validation import install_validation_error_handler

    install_validation_error_handler(app)

    # --- Routers ---
    from src.api.routers.auth import router as auth_router
    from src.api.routers.emails import router as emails_router
    from src.api.routers.fetch import router as fetch_router
    from src.api.routers.websocket import router as websocket_router

    app.include_router(auth_router)
    app.include_router(emails_router)
    app.include_router(fetch_router)
    app.include_router(websocket_router)

    # --- Health check ---
    @app.get("/health")
    async def health_check():
        return {"status": "healthy"}

    return app
