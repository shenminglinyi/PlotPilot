"""Unified error handling middleware for FastAPI applications."""
import logging
from typing import Any, Dict, List

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ..responses import ErrorResponse

logger = logging.getLogger("plotpilot.interfaces.api.middleware.error_handler")


# Starlette/FastAPI 版本兼容：新版常量名为 HTTP_422_UNPROCESSABLE_CONTENT
try:
    HTTP_422_STATUS = status.HTTP_422_UNPROCESSABLE_CONTENT
except AttributeError:
    HTTP_422_STATUS = 422  # 固定数值，永远不会弃用


# Status code to error code mapping
STATUS_CODE_MAP: Dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
    status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
    status.HTTP_403_FORBIDDEN: "FORBIDDEN",
    status.HTTP_404_NOT_FOUND: "NOT_FOUND",
    status.HTTP_409_CONFLICT: "CONFLICT",
    HTTP_422_STATUS: "UNPROCESSABLE_ENTITY",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "INTERNAL_ERROR",
}


async def http_exception_handler(request: Request, exc) -> JSONResponse:
    """Handle HTTPException instances.

    Args:
        request: The incoming request
        exc: The HTTPException to handle

    Returns:
        JSONResponse with unified error format
    """
    status_code = exc.status_code
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)

    # Map status code to error code, use generic if not found
    error_code = STATUS_CODE_MAP.get(status_code, "HTTP_ERROR")

    # Log the error at appropriate level
    if status_code >= 500:
        logger.error(f"HTTP {status_code} - {detail}")
    elif status_code >= 400:
        logger.warning(f"HTTP {status_code} - {detail}")
    else:
        logger.info(f"HTTP {status_code} - {detail}")

    error_response = ErrorResponse(
        message=detail,
        code=error_code
    )

    return JSONResponse(
        status_code=status_code,
        content=error_response.model_dump()
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle pydantic RequestValidationError instances.

    Args:
        request: The incoming request
        exc: The RequestValidationError to handle

    Returns:
        JSONResponse with unified error format and field validation details
    """
    # Format validation errors
    field_errors: List[Dict[str, Any]] = []

    for error in exc.errors():
        field_errors.append({
            "field": ".".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"]
        })

    error_response = ErrorResponse(
        message="Validation failed",
        code="UNPROCESSABLE_ENTITY",
        details=field_errors
    )

    logger.warning(f"Validation error: {len(field_errors)} field(s)")
    for field_error in field_errors:
        logger.debug(f"  - {field_error['field']}: {field_error['message']}")

    return JSONResponse(
        status_code=HTTP_422_STATUS,
        content=error_response.model_dump()
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle generic exceptions.

    Args:
        request: The incoming request
        exc: The Exception to handle

    Returns:
        JSONResponse with unified error format
    """
    error_message = str(exc) if exc else "An unexpected error occurred"

    # Log the error at error level
    logger.exception(f"Unhandled exception: {error_message}")

    error_response = ErrorResponse(
        message=error_message,
        code="INTERNAL_ERROR"
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response.model_dump()
    )


def add_error_handlers(app: FastAPI) -> None:
    """Add unified error handlers to FastAPI application.

    Args:
        app: FastAPI application instance
    """
    from fastapi import HTTPException

    # Register exception handlers - order matters!
    # More specific handlers should be registered first
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)

    logger.info("Unified error handlers registered")
