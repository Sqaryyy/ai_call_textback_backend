# ============================================================================
# FILE: app/config/sentry_config.py
# Sentry error tracking - catches all exceptions automatically
# ============================================================================
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.redis import RedisIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
import logging

from app.config.settings import get_settings

settings = get_settings()


def init_sentry():
    """
    Initialize Sentry for error tracking.

    Free tier: 5,000 errors/month
    Only runs when SENTRY_DSN is set in environment
    """
    if not settings.SENTRY_DSN:
        logging.info("Sentry disabled (no SENTRY_DSN)")
        return

    environment = "development" if settings.DEBUG else "production"

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=environment,

        # Integrations - auto-capture errors from these
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
            CeleryIntegration(monitor_beat_tasks=True),
            RedisIntegration(),
            LoggingIntegration(
                level=logging.INFO,
                event_level=logging.ERROR
            ),
        ],

        # Performance monitoring (only sample 10% in production to save quota)
        traces_sample_rate=1.0 if settings.DEBUG else 0.1,

        # Error sampling (capture all errors)
        sample_rate=1.0,

        # Attach user context automatically
        send_default_pii=False,  # Don't send PII (emails, IPs, etc.)

        # Release tracking (optional - for tracking deployments)
        release=settings.APP_VERSION if hasattr(settings, 'APP_VERSION') else None,

        # Custom tags for filtering
        before_send=_before_send_hook,
    )

    logging.info(f"✅ Sentry initialized - Environment: {environment}")


def _before_send_hook(event, hint):
    """
    Modify events before sending to Sentry.
    Use this to add custom context or filter events.
    """
    # Add custom tags
    event.setdefault("tags", {})
    event["tags"]["service"] = "afterhours-api"

    # Don't send certain errors (e.g., 404s, validation errors)
    if "exc_info" in hint:
        exc_type, exc_value, tb = hint["exc_info"]

        # Ignore HTTPException 404s (not really errors)
        if exc_type.__name__ == "HTTPException":
            if hasattr(exc_value, "status_code") and exc_value.status_code == 404:
                return None

    return event


def capture_exception_with_context(error: Exception, context: dict = None):
    """
    Manually capture an exception with custom context.

    Usage:
        try:
            risky_operation()
        except Exception as e:
            capture_exception_with_context(e, {
                "user_id": user.id,
                "business_id": business.id,
                "action": "booking_appointment"
            })
            raise
    """
    # New API - use isolation_scope instead of push_scope
    with sentry_sdk.isolation_scope() as scope:
        if context:
            for key, value in context.items():
                scope.set_context(key, value)
        sentry_sdk.capture_exception(error)