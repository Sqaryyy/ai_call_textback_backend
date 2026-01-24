# ============================================================================
# FILE: app/api/middleware/alert_middleware.py (NEW)
# Middleware to catch and alert on critical failures
# ============================================================================
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR, HTTP_403_FORBIDDEN
from app.config.email_config import email_service
from app.utils.logger import get_logger
import time

logger = get_logger(__name__)


class CriticalFailureAlertMiddleware(BaseHTTPMiddleware):
    """
    Alert on critical failures:
    - 500 errors (server crashes)
    - 403 errors on admin endpoints (permission issues)
    - Slow requests (>10 seconds)
    """

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        try:
            response: Response = await call_next(request)
            duration = time.time() - start_time

            # Alert on slow requests (>10 seconds)
            if duration > 10.0:
                await self._alert_slow_request(request, duration)

            # Alert on permission errors on admin endpoints
            if response.status_code == HTTP_403_FORBIDDEN and "/admin/" in request.url.path:
                await self._alert_permission_failure(request)

            # Alert on 500 errors
            if response.status_code == HTTP_500_INTERNAL_SERVER_ERROR:
                await self._alert_server_error(request, response)

            return response

        except Exception as e:
            # Alert on unhandled exceptions
            await self._alert_unhandled_exception(request, e)
            raise

    async def _alert_slow_request(self, request: Request, duration: float):
        """Alert on slow requests"""
        logger.warning(f"Slow request detected: {request.method} {request.url.path} - {duration:.2f}s")

        await email_service.send_alert(
            subject=f"Slow Request: {request.url.path}",
            body=f"""
Slow request detected (>{duration:.2f}s)

Endpoint: {request.method} {request.url.path}
Duration: {duration:.2f} seconds
Threshold: 10 seconds

This may indicate:
- Database performance issues
- External API slowness
- Resource constraints

Check server metrics and logs.
""",
            severity="warning"
        )

    async def _alert_permission_failure(self, request: Request):
        """Alert on admin permission failures"""
        logger.warning(f"Permission denied on admin endpoint: {request.url.path}")

        await email_service.send_alert(
            subject=f"Permission Denied: Admin Endpoint",
            body=f"""
Permission denied on admin endpoint

Endpoint: {request.method} {request.url.path}
User: {getattr(request.state, 'user_id', 'unknown')}

Possible causes:
- User role misconfiguration
- Token validation failure
- Authorization logic bug

Review access control immediately.
""",
            severity="warning"
        )

    async def _alert_server_error(self, request: Request, response: Response):
        """Alert on 500 errors"""
        logger.error(f"500 error: {request.method} {request.url.path}")

        # Sentry will catch the actual exception
        # This is just an email notification
        await email_service.send_alert(
            subject=f"Server Error: {request.url.path}",
            body=f"""
500 Internal Server Error

Endpoint: {request.method} {request.url.path}

Check Sentry for full stack trace.
Check application logs for details.
""",
            severity="critical"
        )

    async def _alert_unhandled_exception(self, request: Request, error: Exception):
        """Alert on unhandled exceptions"""
        logger.error(f"Unhandled exception: {request.method} {request.url.path} - {error}")

        await email_service.send_alert(
            subject=f"Unhandled Exception: {type(error).__name__}",
            body=f"""
Unhandled exception in request

Endpoint: {request.method} {request.url.path}
Error: {type(error).__name__}: {str(error)}

Check Sentry for full stack trace.
""",
            severity="critical"
        )