# ===== app/api/middleware/rate_limit_middleware.py =====
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
import time
import logging

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Global rate limiting middleware.
    Works in conjunction with per-key rate limits in APIKeyService.

    Uses Redis in production, falls back to in-memory for development.
    """

    def __init__(self, app, requests_per_second: int = 10):
        super().__init__(app)
        self.requests_per_second = requests_per_second
        self.request_times = {}  # Fallback for when Redis is unavailable
        self.use_redis = True  # Try Redis first

    async def dispatch(self, request: Request, call_next):
        # Only apply to API routes
        if not request.url.path.startswith("/api/v1/"):
            return await call_next(request)

        # Get API key from request state (set by auth dependency)
        api_key = getattr(request.state, "api_key", None)

        if api_key:
            key_id = str(api_key.id)
            current_time = time.time()

            if self.use_redis:
                # Use Redis for distributed rate limiting
                allowed = await self._check_rate_limit_redis(key_id, current_time)
                if not allowed:
                    return self._rate_limit_response()
            else:
                # Fallback to in-memory
                if not self._check_rate_limit_memory(key_id, current_time):
                    return self._rate_limit_response()

        return await call_next(request)

    async def _check_rate_limit_redis(self, key_id: str, current_time: float) -> bool:
        """Check rate limit using Redis (production)"""
        try:
            from app.config.redis import get_redis

            redis_client = await get_redis()
            redis_key = f"ratelimit:api_key:{key_id}:{int(current_time)}"

            # Use Redis sorted set for sliding window
            # Remove old entries (older than 1 second)
            await redis_client.zremrangebyscore(redis_key, 0, current_time - 1.0)

            # Count requests in the last second
            request_count = await redis_client.zcard(redis_key)

            if request_count >= self.requests_per_second:
                await redis_client.close()
                return False

            # Add current request
            await redis_client.zadd(redis_key, {str(current_time): current_time})

            # Set expiration (cleanup after 2 seconds)
            await redis_client.expire(redis_key, 2)

            await redis_client.close()
            return True

        except Exception as e:
            logger.warning(f"Redis rate limit error, falling back to in-memory: {e}")
            self.use_redis = False  # Fall back to in-memory for this instance
            return self._check_rate_limit_memory(key_id, current_time)

    def _check_rate_limit_memory(self, key_id: str, current_time: float) -> bool:
        """Check rate limit using in-memory storage (development fallback)"""
        if key_id not in self.request_times:
            self.request_times[key_id] = []

        # Remove old timestamps (older than 1 second)
        self.request_times[key_id] = [
            t for t in self.request_times[key_id]
            if current_time - t < 1.0
        ]

        # Check if rate limit exceeded
        if len(self.request_times[key_id]) >= self.requests_per_second:
            return False

        # Add current request timestamp
        self.request_times[key_id].append(current_time)

        # Cleanup old keys periodically (prevent memory leak)
        if len(self.request_times) > 10000:
            keys_to_remove = list(self.request_times.keys())[:2000]
            for k in keys_to_remove:
                del self.request_times[k]

        return True

    def _rate_limit_response(self) -> JSONResponse:
        """Return rate limit exceeded response"""
        return JSONResponse(
            status_code=429,
            content={
                "detail": "Rate limit exceeded. Too many requests per second.",
                "retry_after": 1
            },
            headers={"Retry-After": "1"}
        )