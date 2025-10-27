# ===== app/api/middleware/logging_middleware.py =====
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from app.services.api_key.api_key_service import APIKeyService
from app.config.database import get_db
import time

class APIRequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log all API requests for authenticated endpoints.
    Tracks per-endpoint usage, response times, and errors.
    """

    async def dispatch(self, request: Request, call_next):
        # Only log API routes (skip health checks, internal routes)
        if not request.url.path.startswith("/api/v1/"):
            return await call_next(request)

        start_time = time.time()

        # Process the request
        response = await call_next(request)

        # Calculate response time
        response_time_ms = int((time.time() - start_time) * 1000)

        # Log if API key was used
        api_key = getattr(request.state, "api_key", None)

        if api_key:
            # Get database session
            async for db in get_db():
                service = APIKeyService(db)

                # Extract query params
                query_params = dict(request.query_params) if request.query_params else None

                # Log the request
                await service.log_request(
                    api_key=api_key,
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    response_time_ms=response_time_ms,
                    query_params=query_params,
                    ip_address=request.client.host if request.client else None,
                    user_agent=request.headers.get("user-agent"),
                    error_message=None  # Could extract from response if needed
                )
                break

        return response
