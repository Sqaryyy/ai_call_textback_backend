# app/webhooks/call_handler.py - SECURED with signature validation
"""Incoming call webhook handler - queuing only"""
import logging
from fastapi import APIRouter, Request, Response, Depends
from app.schemas.webhook_events import TwilioCallWebhook
from app.tasks.call_tasks import process_incoming_call
from app.webhooks.security import validate_twilio_signature_dependency

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/incoming", dependencies=[Depends(validate_twilio_signature_dependency)])
async def handle_incoming_call(request: Request):
    """
    Handle incoming call webhook - queue processing immediately.

    🔒 SECURITY: Twilio signature is validated by the dependency.
    Only requests actually from Twilio will reach this handler.
    """
    print("=" * 80)
    print("🔥 WEBHOOK HIT - START")
    print("=" * 80)

    try:
        # Parse webhook data
        form_data = await request.form()
        form_dict = dict(form_data)

        print(f"📥 RAW WEBHOOK DATA: {form_dict}")
        print(f"📊 Number of fields: {len(form_dict)}")

        # Skip if empty (test requests)
        if not form_dict or not form_dict.get('CallSid'):
            print("⚠️  SKIPPING: Empty webhook data or no CallSid")
            return Response(status_code=200)

        print(f"✅ CallSid found: {form_dict.get('CallSid')}")

        # Remove Timestamp field to avoid parsing errors
        if 'Timestamp' in form_dict:
            print("🗑️  Removing Timestamp field")
            del form_dict['Timestamp']

        print("📋 Parsing webhook data into TwilioCallWebhook schema...")
        webhook_data = TwilioCallWebhook(**form_dict)
        print(f"✅ Webhook data parsed successfully")
        print(f"   CallSid: {webhook_data.CallSid}")
        print(f"   From: {webhook_data.From}")
        print(f"   To: {webhook_data.To}")
        print(f"   Status: {webhook_data.CallStatus}")

        # Get correlation ID from middleware
        correlation_id = getattr(request.state, "correlation_id", "unknown")
        print(f"🔗 Correlation ID: {correlation_id}")

        # Queue the call processing task immediately
        print("📤 Queuing Celery task: process_incoming_call...")
        task = process_incoming_call.delay(
            call_sid=webhook_data.CallSid,
            caller_phone=webhook_data.From,
            business_phone=webhook_data.To,
            call_status=webhook_data.CallStatus,
            caller_location={
                "city": webhook_data.FromCity,
                "state": webhook_data.FromState,
                "country": webhook_data.FromCountry,
            },
            correlation_id=correlation_id
        )
        print(f"✅ Task queued successfully! Task ID: {task.id}")

        print("📞 Returning TwiML response to Twilio...")
        print("=" * 80)
        print("🔥 WEBHOOK HIT - END (SUCCESS)")
        print("=" * 80)

        # Return TwiML to end the call immediately
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><Response><Say>Thank you for calling. We will send you a text message shortly to help with your request.</Say><Hangup/></Response>',
            media_type="application/xml"
        )

    except Exception as e:
        print("=" * 80)
        print(f"❌ ERROR in webhook handler: {str(e)}")
        print(f"❌ Error type: {type(e).__name__}")
        import traceback
        print(f"❌ Traceback:\n{traceback.format_exc()}")
        print("=" * 80)
        logger.error(f"Error handling call webhook: {str(e)}")
        # Always return 200 to Twilio to prevent retries on our errors
        return Response(status_code=200)