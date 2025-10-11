# app/core/middleware.py
"""Custom middleware for request handling"""
import uuid
import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


async def correlation_id_middleware(request: Request, call_next):
    """Add correlation ID to all requests for tracing"""
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    request.state.correlation_id = correlation_id

    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response


async def request_logging_middleware(request: Request, call_next):
    """Log all incoming requests"""
    start_time = time.time()
    correlation_id = getattr(request.state, "correlation_id", "unknown")

    logger.info(
        f"Request started",
        extra={
            "correlation_id": correlation_id,
            "method": request.method,
            "url": str(request.url),
            "client": request.client.host if request.client else "unknown",
        }
    )

    response = await call_next(request)

    duration = time.time() - start_time
    logger.info(
        f"Request completed",
        extra={
            "correlation_id": correlation_id,
            "method": request.method,
            "url": str(request.url),
            "status_code": response.status_code,
            "duration_ms": round(duration * 1000, 2),
        }
    )

    return response
