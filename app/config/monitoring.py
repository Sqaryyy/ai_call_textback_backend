# ============================================================================
# FILE: app/config/monitoring.py (UPDATED)
# Enhanced health checks with Celery queue monitoring
# ============================================================================
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone
from typing import Dict, Any

from app.config.database import get_db
from app.config.redis import get_redis
from app.config.celery_config import celery_app
from app.config.email_config import email_service
from app.utils.logger import get_logger

health_router = APIRouter()
logger = get_logger(__name__)


async def check_celery_workers() -> Dict[str, Any]:
    """Check if Celery workers are running and responsive"""
    try:
        # Inspect active workers
        inspect = celery_app.control.inspect()
        
        # Get active workers (timeout after 2 seconds)
        active_workers = inspect.active(timeout=2.0)
        stats = inspect.stats(timeout=2.0)
        
        if not active_workers:
            return {
                "status": "unhealthy",
                "error": "No active workers found",
                "workers": 0
            }
        
        worker_count = len(active_workers)
        
        return {
            "status": "healthy",
            "workers": worker_count,
            "worker_names": list(active_workers.keys())
        }
        
    except Exception as e:
        logger.error(f"Celery health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "workers": 0
        }


async def check_queue_lengths() -> Dict[str, Any]:
    """Check Celery queue depths"""
    try:
        redis_client = await get_redis()
        
        queues = ["conversations", "calls", "appointments", "maintenance", "emails"]
        queue_lengths = {}
        total_pending = 0
        
        for queue_name in queues:
            # Celery uses 'celery' as default queue prefix in Redis
            redis_key = f"celery:queue:{queue_name}"
            length = await redis_client.llen(redis_key)
            queue_lengths[queue_name] = length
            total_pending += length
        
        await redis_client.close()
        
        # Alert if any queue has >50 tasks (configurable threshold)
        status = "healthy"
        alerts = []
        
        for queue, length in queue_lengths.items():
            if length > 50:
                status = "warning"
                alerts.append(f"{queue}: {length} tasks")
        
        return {
            "status": status,
            "total_pending": total_pending,
            "queues": queue_lengths,
            "alerts": alerts
        }
        
    except Exception as e:
        logger.error(f"Queue check failed: {e}")
        return {
            "status": "unknown",
            "error": str(e)
        }


@health_router.get("/")
async def health_check(db: Session = Depends(get_db)):
    """
    Basic health check for load balancers.
    Returns 200 if healthy, 503 if unhealthy.
    """
    try:
        db.execute(text("SELECT 1"))
        return JSONResponse(
            content={
                "status": "healthy",
                "service": "after-hours-api",
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            status_code=200
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            content={
                "status": "unhealthy",
                "service": "after-hours-api",
                "error": "database_unavailable",
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            status_code=503
        )


@health_router.get("/detailed")
async def detailed_health_check(db: Session = Depends(get_db)):
    """
    Detailed health check with all dependencies.
    
    Checks:
    - API (always healthy if this runs)
    - Database connectivity
    - Redis connectivity
    - Celery workers
    - Queue depths
    """
    checks = {
        "api": "healthy",
        "database": "unknown",
        "redis": "unknown",
        "celery_workers": "unknown",
        "queues": "unknown",
        "overall": "unknown",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    # Check database
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "healthy"
    except Exception as e:
        checks["database"] = f"unhealthy: {str(e)}"
        logger.error(f"Database health check failed: {e}")
    
    # Check Redis
    try:
        redis_client = await get_redis()
        await redis_client.ping()
        checks["redis"] = "healthy"
        await redis_client.close()
    except Exception as e:
        checks["redis"] = f"unhealthy: {str(e)}"
        logger.error(f"Redis health check failed: {e}")
    
    # Check Celery workers
    worker_check = await check_celery_workers()
    checks["celery_workers"] = worker_check
    
    # Check queue lengths
    queue_check = await check_queue_lengths()
    checks["queues"] = queue_check
    
    # Determine overall status
    critical_checks = [
        checks["database"] == "healthy",
        checks["redis"] == "healthy",
        worker_check.get("status") == "healthy"
    ]
    
    if all(critical_checks):
        if queue_check.get("status") == "warning":
            checks["overall"] = "degraded"
            status_code = 200  # Still operational
        else:
            checks["overall"] = "healthy"
            status_code = 200
    else:
        checks["overall"] = "unhealthy"
        status_code = 503
        
        # Send alert email for critical failures
        await _send_health_alert(checks)
    
    return JSONResponse(content=checks, status_code=status_code)


async def _send_health_alert(checks: Dict[str, Any]):
    """Send email alert when health check fails"""
    failures = []
    
    if "unhealthy" in str(checks.get("database")):
        failures.append(f"❌ Database: {checks['database']}")
    if "unhealthy" in str(checks.get("redis")):
        failures.append(f"❌ Redis: {checks['redis']}")
    if checks.get("celery_workers", {}).get("status") == "unhealthy":
        failures.append(f"❌ Celery Workers: {checks['celery_workers'].get('error')}")
    
    if not failures:
        return
    
    body = f"""
Critical Health Check Failure - After Hours Service

Time: {checks['timestamp']}

Failures:
{chr(10).join(failures)}

Action Required: Check server immediately

Full Status:
{chr(10).join(f"{k}: {v}" for k, v in checks.items())}
"""
    
    await email_service.send_alert(
        subject="CRITICAL: Service Health Check Failed",
        body=body,
        severity="critical"
    )
