# app/webhooks/sms_handler.py
"""SMS webhook handler - queuing only"""
import logging
from fastapi import APIRouter, Request, HTTPException, Response
from app.schemas.webhook_events import TwilioSMSWebhook
from app.tasks.conversation_tasks import process_sms_message

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/incoming")
async def handle_incoming_sms(request: Request):
    """Handle incoming SMS webhook - queue processing immediately"""
    try:
        # Parse webhook data
        form_data = await request.form()
        webhook_data = TwilioSMSWebhook(**form_data)

        # Get correlation ID from middleware
        correlation_id = getattr(request.state, "correlation_id", "unknown")

        # Queue the SMS processing task immediately
        process_sms_message.delay(
            message_sid=webhook_data.MessageSid,
            sender_phone=webhook_data.From,
            business_phone=webhook_data.To,
            message_body=webhook_data.Body,
            media_urls=[webhook_data.MediaUrl0] if webhook_data.MediaUrl0 else [],
            correlation_id=correlation_id
        )

        logger.info(f"Queued SMS processing for {webhook_data.MessageSid}")

        # Return empty response immediately - worker will send reply
        return Response(status_code=200)

    except Exception as e:
        logger.error(f"Error handling SMS webhook: {str(e)}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")
