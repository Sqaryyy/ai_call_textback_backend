# app/services/twilio/sms_service.py
"""SMS sending service with retry logic"""
import logging
import uuid
from twilio.rest import Client
from twilio.base.exceptions import TwilioException
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models.message import Message

logger = logging.getLogger(__name__)
settings = get_settings()


class SMSService:
    def __init__(self):
        self.client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

    def send_sms(self, to_phone: str, from_phone: str, message_body: str,
                 conversation_id: str, correlation_id: str, db: Session) -> dict:
        """Send SMS and log to database"""
        try:
            # Send via Twilio
            twilio_message = self.client.messages.create(
                body=message_body,
                from_=from_phone,
                to=to_phone
            )

            # Log successful message
            message = Message(
                id=uuid.uuid4(),
                conversation_id=uuid.UUID(conversation_id) if isinstance(conversation_id, str) else conversation_id,  # ✅ Convert to UUID
                sender_phone=from_phone,
                recipient_phone=to_phone,
                role="assistant",
                content=message_body,
                message_status="sent",
                is_inbound=False,
                message_metadata={
                    "correlation_id": correlation_id,
                    "twilio_status": twilio_message.status,
                    "twilio_sid": twilio_message.sid  # ✅ Store the actual Twilio SID
                }
            )
            db.add(message)
            db.commit()  # ✅ ADDED: Commit the message
            db.refresh(message)  # ✅ ADDED: Refresh to get timestamps

            logger.info(f"SMS sent successfully to {to_phone}: {twilio_message.sid}")
            return {"success": True, "message_sid": twilio_message.sid}

        except TwilioException as e:
            logger.error(f"Twilio error sending SMS to {to_phone}: {str(e)}")

            # Log failed message
            message = Message(
                id=uuid.uuid4(),
                conversation_id=uuid.UUID(conversation_id) if isinstance(conversation_id, str) else conversation_id,  # ✅ Convert to UUID
                sender_phone=from_phone,
                recipient_phone=to_phone,
                role="assistant",
                content=message_body,
                message_status="failed",
                is_inbound=False,
                error_message=str(e),
                message_metadata={"correlation_id": correlation_id}
            )
            db.add(message)
            db.commit()  # ✅ ADDED: Commit even failed messages
            db.refresh(message)  # ✅ ADDED: Refresh to get timestamps

            return {"success": False, "error": str(e)}


# Create service instance
sms_service = SMSService()