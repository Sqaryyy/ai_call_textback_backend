# ===== app/config/validator.py =====
import sys
import logging
from app.config.settings import get_settings

logger = logging.getLogger(__name__)


def validate_production_config():
    """
    Validate that all required production settings are configured.
    Called during startup to fail fast if misconfigured.
    """
    settings = get_settings()

    if not settings.DEBUG:
        errors = []
        warnings = []

        # Check SECRET_KEY
        if settings.SECRET_KEY == "change-this-in-production":
            errors.append("SECRET_KEY is still set to default value")

        if len(settings.SECRET_KEY) < 32:
            errors.append("SECRET_KEY is too short (minimum 32 characters)")

        # Check JWT_SECRET_KEY
        if "change-this" in settings.JWT_SECRET_KEY.lower():
            errors.append("JWT_SECRET_KEY is still set to default value")

        if len(settings.JWT_SECRET_KEY) < 32:
            errors.append("JWT_SECRET_KEY is too short (minimum 32 characters)")

        # Check database
        if "localhost" in settings.DATABASE_URL or "127.0.0.1" in settings.DATABASE_URL:
            errors.append("DATABASE_URL points to localhost in production")

        if "user:password" in settings.DATABASE_URL:
            errors.append("DATABASE_URL is still using default credentials")

        # Check Redis
        if "localhost" in settings.REDIS_URL or "127.0.0.1" in settings.REDIS_URL:
            errors.append("REDIS_URL points to localhost in production")

        # Check CORS
        if not settings.ALLOWED_ORIGINS:
            errors.append("ALLOWED_ORIGINS is empty")

        if any("localhost" in origin or "127.0.0.1" in origin for origin in settings.ALLOWED_ORIGINS):
            warnings.append("ALLOWED_ORIGINS contains localhost URLs in production")

        # Check Twilio (required for webhooks)
        if not settings.TWILIO_ACCOUNT_SID:
            errors.append("TWILIO_ACCOUNT_SID is required for webhook validation")
        else:
            # Validate format
            if not settings.TWILIO_ACCOUNT_SID.startswith('AC'):
                errors.append("TWILIO_ACCOUNT_SID has invalid format (should start with 'AC')")
            if len(settings.TWILIO_ACCOUNT_SID) != 34:
                errors.append(f"TWILIO_ACCOUNT_SID has invalid length: {len(settings.TWILIO_ACCOUNT_SID)}")

        if not settings.TWILIO_AUTH_TOKEN:
            errors.append("TWILIO_AUTH_TOKEN is REQUIRED for webhook signature validation (CRITICAL SECURITY)")
        else:
            if len(settings.TWILIO_AUTH_TOKEN) != 32:
                warnings.append(f"TWILIO_AUTH_TOKEN has unexpected length: {len(settings.TWILIO_AUTH_TOKEN)}")

        # Check OpenAI (required for AI features)
        if not settings.OPENAI_API_KEY:
            warnings.append("OPENAI_API_KEY is not set")

        # Check calendar encryption (if using calendar features)
        if not settings.CALENDAR_ENCRYPTION_KEY:
            warnings.append("CALENDAR_ENCRYPTION_KEY is not set")

        # Check email settings (if sending emails)
        if settings.EMAIL_PASSWORD == "ytwk sigq ssyn nnmi":
            warnings.append("EMAIL_PASSWORD appears to be a placeholder/default value")

        # If there are errors, log them and exit
        if errors:
            logger.error("=" * 80)
            logger.error("❌ PRODUCTION CONFIGURATION ERRORS - CANNOT START:")
            logger.error("=" * 80)
            for error in errors:
                logger.error(f"  ❌ {error}")
            logger.error("=" * 80)
            logger.error("Fix these errors before deploying to production!")
            logger.error("=" * 80)
            sys.exit(1)

        # Log warnings (non-fatal)
        if warnings:
            logger.warning("=" * 80)
            logger.warning("⚠️  PRODUCTION CONFIGURATION WARNINGS:")
            logger.warning("=" * 80)
            for warning in warnings:
                logger.warning(f"  ⚠️  {warning}")
            logger.warning("=" * 80)

        if not errors:
            logger.info("✅ Production configuration validated successfully")

    else:
        logger.info("⚠️  Running in DEBUG mode - skipping strict validation")


async def validate_required_services():
    """
    Check that required external services are reachable.
    Called during startup (ASYNC VERSION).
    """
    settings = get_settings()
    warnings = []

    # Check database connection
    try:
        from app.config.database import engine
        from sqlalchemy import text

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("✅ Database connection successful")
    except Exception as e:
        warnings.append(f"Database connection failed: {e}")

    # Check Redis connection (FIXED: Now properly async)
    try:
        from app.config.redis import get_redis

        redis = await get_redis()
        await redis.ping()
        logger.info("✅ Redis connection successful")
    except Exception as e:
        warnings.append(f"Redis connection failed: {e}")

    # Log warnings but don't fail (services might not be ready yet in dev)
    if warnings:
        if not settings.DEBUG:
            logger.error("=" * 80)
            logger.error("❌ CRITICAL SERVICE FAILURES IN PRODUCTION:")
            for warning in warnings:
                logger.error(f"  ❌ {warning}")
            logger.error("=" * 80)
            sys.exit(1)
        else:
            logger.warning("=" * 80)
            logger.warning("⚠️  SERVICE CONNECTION WARNINGS (dev mode):")
            for warning in warnings:
                logger.warning(f"  ⚠️  {warning}")
            logger.warning("=" * 80)