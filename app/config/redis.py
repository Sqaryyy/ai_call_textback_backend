# app/config/redis.py
"""Redis configuration and connection setup"""
import redis.asyncio as redis
from typing import Optional

from app.config.settings import get_settings

settings = get_settings()

# Redis connection pool
_redis_pool: Optional[redis.ConnectionPool] = None


def get_redis_pool() -> redis.ConnectionPool:
    """Get or create Redis connection pool"""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.ConnectionPool.from_url(
            settings.REDIS_URL,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            retry_on_timeout=True,
        )
    return _redis_pool


async def get_redis() -> redis.Redis:
    """Get Redis client from pool"""
    pool = get_redis_pool()
    return redis.Redis(connection_pool=pool)


# Redis key patterns for different data types
class RedisKeys:
    """Redis key patterns for consistent naming"""

    # Conversation state keys
    CONVERSATION_STATE = "conversation:{conversation_id}:state"
    CONVERSATION_MESSAGES = "conversation:{conversation_id}:messages"
    CONVERSATION_CONTEXT = "conversation:{conversation_id}:context"

    # Phone number to conversation mapping
    PHONE_TO_CONVERSATION = "phone:{phone}:conversation"

    # Business data caching
    BUSINESS_PROFILE = "business:{business_id}:profile"
    BUSINESS_HOURS = "business:{business_id}:hours"

    # Task tracking
    TASK_STATUS = "task:{task_id}:status"
    RETRY_COUNT = "task:{task_id}:retries"

    # Rate limiting
    RATE_LIMIT_SMS = "ratelimit:sms:{phone}:{minute}"
    RATE_LIMIT_CALLS = "ratelimit:calls:{phone}:{hour}"

    # Temporary data
    WEBHOOK_DEDUP = "webhook:{webhook_id}"
    OTP_CODES = "otp:{phone}"
