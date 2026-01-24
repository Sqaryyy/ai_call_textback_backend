# app/webhooks/security.py
"""Twilio webhook signature validation"""
import logging
from fastapi import Request, HTTPException, status
from twilio.request_validator import RequestValidator
from app.config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def validate_twilio_signature(request: Request) -> bool:
    """
    Validate that the request actually came from Twilio.

    Twilio signs all webhook requests with your auth token.
    This prevents attackers from spoofing webhooks.

    Returns True if valid, raises HTTPException if invalid.
    """

    # Skip validation in DEBUG mode (for local testing)
    if settings.DEBUG:
        logger.warning("⚠️  Skipping Twilio signature validation (DEBUG mode)")
        return True

    # Get the signature from headers
    signature = request.headers.get("X-Twilio-Signature", "")

    if not signature:
        logger.error("❌ Missing X-Twilio-Signature header")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing Twilio signature"
        )

    # Get the full URL (including query params if any)
    url = str(request.url)

    # Get form data as dict
    form_data = await request.form()
    params = dict(form_data)

    # Validate signature
    validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
    is_valid = validator.validate(url, params, signature)

    if not is_valid:
        logger.error(
            f"❌ Invalid Twilio signature! "
            f"URL: {url}, "
            f"Signature: {signature[:20]}..."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Twilio signature"
        )

    logger.info(f"✅ Twilio signature validated for {url}")
    return True


async def validate_twilio_signature_dependency(request: Request):
    """
    FastAPI dependency for Twilio signature validation.

    Usage:
        @router.post("/incoming", dependencies=[Depends(validate_twilio_signature_dependency)])
        async def handle_webhook(request: Request):
            ...
    """
    await validate_twilio_signature(request)
    return True