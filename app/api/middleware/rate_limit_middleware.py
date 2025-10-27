# ===== app/api/middleware/rate_limit_middleware.py =====
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
import time


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Global rate limiting middleware.
    Works in conjunction with per-key rate limits in APIKeyService.

    This adds an extra layer of protection against abuse.
    """

    def __init__(self, app, requests_per_second: int = 10):
        super().__init__(app)
        self.requests_per_second = requests_per_second
        self.request_times = {}  # In production, use Redis

    async def dispatch(self, request: Request, call_next):
        # Only apply to API routes
        if not request.url.path.startswith("/api/v1/"):
            return await call_next(request)

        # Get API key from request state (set by auth dependency)
        api_key = getattr(request.state, "api_key", None)

        if api_key:
            key_id = str(api_key.id)
            current_time = time.time()

            # Simple sliding window (in production, use Redis)
            if key_id not in self.request_times:
                self.request_times[key_id] = []

            # Remove old timestamps (older than 1 second)
            self.request_times[key_id] = [
                t for t in self.request_times[key_id]
                if current_time - t < 1.0
            ]

            # Check if rate limit exceeded
            if len(self.request_times[key_id]) >= self.requests_per_second:
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Rate limit exceeded. Too many requests per second.",
                        "retry_after": 1
                    },
                    headers={"Retry-After": "1"}
                )

            # Add current request timestamp
            self.request_times[key_id].append(current_time)

        return await call_next(request)
