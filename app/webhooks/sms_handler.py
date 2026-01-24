# app/webhooks/sms_handler.py - SECURED with signature validation
"""SMS webhook handler - queuing only"""
import logging
from fastapi import APIRouter, Request, Response, Depends
from app.schemas.webhook_events import TwilioSMSWebhook
from app.tasks.conversation_tasks import process_sms_message
from app.webhooks.security import validate_twilio_signature_dependency

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/incoming", dependencies=[Depends(validate_twilio_signature_dependency)])
async def handle_incoming_sms(request: Request):
    """
    Handle incoming SMS webhook - queue processing immediately.

    🔒 SECURITY: Twilio signature is validated by the dependency.
    Only requests actually from Twilio will reach this handler.
    """
    try:
        # Parse webhook data
        form_data = await request.form()
        webhook_data = TwilioSMSWebhook(**form_data)

        # Get correlation ID from middleware
        correlation_id = getattr(request.state, "correlation_id", "unknown")

        # Queue the SMS processing task immediately
        task = process_sms_message.delay(
            message_sid=webhook_data.MessageSid,
            sender_phone=webhook_data.From,
            business_phone=webhook_data.To,
            message_body=webhook_data.Body,
            media_urls=[webhook_data.MediaUrl0] if webhook_data.MediaUrl0 else [],
            correlation_id=correlation_id
        )

        logger.info(
            f"Queued SMS processing for {webhook_data.MessageSid}, "
            f"Task ID: {task.id}"
        )

        # Return empty response immediately - worker will send reply
        return Response(status_code=200)

    except Exception as e:
        logger.error(f"Error handling SMS webhook: {str(e)}", exc_info=True)
        # Return 200 to prevent Twilio retries on our errors
        return Response(status_code=200)