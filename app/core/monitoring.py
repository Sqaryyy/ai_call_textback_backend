"""Health checks and monitoring endpoints"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import redis.asyncio as redis

from app.config.database import get_db
from app.config.redis import get_redis

health_router = APIRouter()


@health_router.get("/")
async def health_check():
    """Basic health check"""
    return {"status": "healthy", "service": "after-hours-api"}


@health_router.get("/detailed")
async def detailed_health_check(db: Session = Depends(get_db)):
    """Detailed health check with dependencies"""
    checks = {
        "api": "healthy",
        "database": "unknown",
        "redis": "unknown",
        "overall": "unknown"
    }

    # Check database
    try:
        db.execute("SELECT 1")
        checks["database"] = "healthy"
    except Exception as e:
        checks["database"] = f"unhealthy: {str(e)}"

    # Check Redis
    try:
        redis_client = await get_redis()
        await redis_client.ping()
        checks["redis"] = "healthy"
        await redis_client.close()
    except Exception as e:
        checks["redis"] = f"unhealthy: {str(e)}"

    # Overall status
    if all(status == "healthy" for status in checks.values() if status != "unknown"):
        checks["overall"] = "healthy"
    else:
        checks["overall"] = "degraded"

    return checks