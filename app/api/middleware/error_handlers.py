# ===== app/api/middleware/error_handlers.py =====
import logging
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions with correlation ID"""
    correlation_id = getattr(request.state, "correlation_id", "unknown")

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "correlation_id": correlation_id,
        }
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors with better formatting"""
    correlation_id = getattr(request.state, "correlation_id", "unknown")

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Validation error",
            "errors": exc.errors(),
            "correlation_id": correlation_id,
        }
    )


async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected errors safely"""
    correlation_id = getattr(request.state, "correlation_id", "unknown")

    # Log the error with full details
    logger.error(
        f"Unhandled exception: {str(exc)}",
        exc_info=True,
        extra={
            "correlation_id": correlation_id,
            "method": request.method,
            "url": str(request.url),
        }
    )

    # Don't expose internal error details to users
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error",
            "correlation_id": correlation_id,
        }
    )