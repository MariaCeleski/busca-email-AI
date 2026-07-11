"""Request validation error handler.

Ensures that Pydantic validation errors return 422 responses with
field-level error messages indicating which fields failed and why.

FastAPI handles this natively via Pydantic, but this module provides
a custom exception handler for consistent error formatting.

Validates: Requirements 8.5
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def install_validation_error_handler(app: FastAPI) -> None:
    """Install a custom validation error handler on the FastAPI app.

    Formats Pydantic validation errors as 422 responses with field-level
    detail including the field location, message, and error type.

    Args:
        app: The FastAPI application to add the handler to.
    """

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Return 422 with field-level error details.

        Each error includes:
        - loc: The field location (e.g., ["body", "email_id"])
        - msg: Human-readable error message
        - type: The Pydantic error type identifier
        """
        errors = []
        for error in exc.errors():
            errors.append(
                {
                    "loc": list(error.get("loc", [])),
                    "msg": error.get("msg", "Validation error"),
                    "type": error.get("type", "value_error"),
                }
            )

        return JSONResponse(
            status_code=422,
            content={
                "detail": "Request validation failed",
                "errors": errors,
            },
        )
