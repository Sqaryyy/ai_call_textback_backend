"""
FastAPI application for handling Twilio webhooks
WITH MONITORING AND ALERTING
"""

from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.api.middleware.error_handlers import (
    http_exception_handler,
    validation_exception_handler,
    general_exception_handler
)

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from contextlib import asynccontextmanager

from app.config.settings import get_settings
from app.config.monitoring import health_router
from app.webhooks.router import webhook_router
from app.api.v1.router import api_v1_router
from app.utils.my_logging import setup_logging
from app.utils.logger import get_logger
from app.api.middleware.request_size_middleware import RequestSizeLimitMiddleware
from app.api.middleware.security_headerrs_middleware import SecurityHeadersMiddleware
from app.api.middleware.request_middleware import CorrelationIDMiddleware, RequestLoggingMiddleware
from app.api.middleware.logging_middleware import APIRequestLoggingMiddleware
from app.api.middleware.rate_limit_middleware import RateLimitMiddleware
from app.api.middleware.ip_whitelist_middleware import IPWhitelistMiddleware

# ===== NEW IMPORTS FOR MONITORING =====
from app.config.sentry_config import init_sentry
from app.api.middleware.alert_middleware import CriticalFailureAlertMiddleware
# ======================================

from app.config.validator import validate_production_config, validate_required_services
import signal
import asyncio

settings = get_settings()
logger = get_logger(__name__)

# ===== INITIALIZE SENTRY AT MODULE LEVEL (ONCE) =====
init_sentry()
logger.info("✅ Monitoring initialized (Sentry + Email Alerts)")
# ====================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events with graceful shutdown"""

    # ========== STARTUP ==========
    setup_logging()

    # Validate configuration FIRST (fail fast if misconfigured)
    validate_production_config()
    await validate_required_services()

    logger.info("After-Hours Service API starting up...")
    logger.info("Webhook endpoints ready at /webhooks/")
    logger.info("Admin API available at /api/v1/")
    logger.info("Health check at /health")

    # ===== NEW: Log monitoring status =====
    if settings.SENTRY_DSN:
        logger.info("📊 Sentry error tracking: ENABLED")
    else:
        logger.warning("📊 Sentry error tracking: DISABLED (no SENTRY_DSN)")

    if settings.RESEND_API_KEY:
        logger.info(f"📧 Email alerts: ENABLED → {settings.ALERT_EMAIL_TO}")
    else:
        logger.warning("📧 Email alerts: DISABLED (no RESEND_API_KEY)")
    # ======================================

    # Log all registered routes
    logger.info("=" * 80)
    logger.info("REGISTERED ROUTES:")
    logger.info("=" * 80)

    routes_list = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in route.methods:
                routes_list.append((method, route.path, route.name, route.tags))

    routes_list.sort(key=lambda x: (x[1], x[0]))

    from collections import defaultdict
    routes_by_tag = defaultdict(list)

    for method, path, name, tags in routes_list:
        tag = tags[0] if tags else "other"
        routes_by_tag[tag].append((method, path, name))

    for tag, routes in sorted(routes_by_tag.items()):
        logger.info(f"\n[{tag.upper()}]")
        for method, path, name in routes:
            logger.info(f"  {method:8} {path:50} ({name})")

    logger.info("=" * 80)
    logger.info(f"Total routes registered: {len(routes_list)}")
    logger.info("=" * 80)

    yield

    # ========== SHUTDOWN ==========
    logger.info("Starting graceful shutdown...")

    # Give ongoing requests time to complete (max 10 seconds)
    logger.info("Waiting for ongoing requests to complete (max 10s)...")
    await asyncio.sleep(10)

    # Close database connections
    try:
        from app.config.database import engine
        engine.dispose()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Error closing database: {e}")

    # Close Redis connections
    try:
        from app.config.redis import get_redis
        redis_client = await get_redis()
        await redis_client.close()
        logger.info("Redis connections closed")
    except Exception as e:
        logger.warning(f"Redis cleanup: {e}")

    logger.info("Graceful shutdown complete")


def create_app() -> FastAPI:
    """Create and configure FastAPI application"""

    app = FastAPI(
        title="After-Hours Service API",
        description="Queue-based AI customer service with appointment booking",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
    )

    # Exception handlers
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)

    # ===== MIDDLEWARE ORDER (CRITICAL) =====
    # 1. Request size limit (reject large uploads early)
    app.add_middleware(RequestSizeLimitMiddleware, max_upload_size=10 * 1024 * 1024)

    # 2. Correlation ID (first, so all requests have an ID)
    app.add_middleware(CorrelationIDMiddleware)

    # 3. Request logging (logs with correlation ID)
    app.add_middleware(RequestLoggingMiddleware)

    # 4. ===== NEW: Alert middleware (catches critical failures) =====
    app.add_middleware(CriticalFailureAlertMiddleware)
    # ================================================================

    # 5. Security headers
    app.add_middleware(SecurityHeadersMiddleware)

    # 6. API-specific middleware
    app.add_middleware(APIRequestLoggingMiddleware)
    app.add_middleware(RateLimitMiddleware, requests_per_second=10)
    app.add_middleware(IPWhitelistMiddleware)

    # 7. CORS (last, so it wraps all responses)
    ALLOWED_HEADERS = [
        "Authorization",
        "Content-Type",
        "X-Request-ID",
        "X-Correlation-ID",
        "Accept",
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "PUT", "OPTIONS"],
        allow_headers=ALLOWED_HEADERS,
        expose_headers=["X-Correlation-ID", "X-Request-ID"],
        max_age=3600,
    )

    # Include routers
    app.include_router(webhook_router, prefix="/webhooks", tags=["webhooks"])
    app.include_router(health_router, prefix="/health", tags=["monitoring"])
    app.include_router(api_v1_router, prefix="/api/v1", tags=["api"])

    @app.get("/")
    async def root():
        return {
            "service": "After-Hours Service API",
            "version": "0.1.0",
            "status": "running",
            "monitoring": {
                "sentry": bool(settings.SENTRY_DSN),
                "email_alerts": bool(settings.RESEND_API_KEY)
            },
            "endpoints": {
                "webhooks": "/webhooks/",
                "health": "/health",
                "health_detailed": "/health/detailed",
                "docs": "/docs" if settings.DEBUG else "disabled"
            }
        }

    return app


app = create_app()


@app.get("/debug/routes", tags=["debug"], include_in_schema=False)
async def list_all_routes():
    """List all registered routes (only available in DEBUG mode)"""
    if not settings.DEBUG:
        raise HTTPException(status_code=404, detail="Not found")

    routes = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            routes.append({
                "path": route.path,
                "name": route.name,
                "methods": list(route.methods),
                "tags": route.tags
            })
    return {
        "total": len(routes),
        "routes": sorted(routes, key=lambda x: x["path"])
    }


# ===== NEW: Test endpoint for monitoring (remove after testing) =====
@app.get("/test/sentry", tags=["debug"], include_in_schema=False)
async def test_sentry():
    """Test Sentry error tracking - REMOVE IN PRODUCTION"""
    if not settings.DEBUG:
        raise HTTPException(status_code=404, detail="Not found")

    # This will trigger an error that Sentry will catch
    1 / 0


@app.get("/test/email-alert", tags=["debug"], include_in_schema=False)
async def test_email_alert():
    """Test email alerts - REMOVE IN PRODUCTION"""
    if not settings.DEBUG:
        raise HTTPException(status_code=404, detail="Not found")

    from app.config.email_config import email_service

    await email_service.send_alert(
        subject="Test Alert from After-Hours Service",
        body="If you received this, email alerts are working correctly!",
        severity="info"
    )

    return {"message": "Alert sent! Check your email."}
# ====================================================================


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info"
    )