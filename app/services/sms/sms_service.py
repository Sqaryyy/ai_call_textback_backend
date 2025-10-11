# ============================================================================
# app/services/sms/message_service.py
# ============================================================================
"""Service for SMS operations"""
import os

from twilio.rest import Client
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class SMSService:
    """Handles SMS sending operations"""

    def __init__(self):
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.client = Client(account_sid, auth_token) if account_sid else None

    def send_sms(
        self,
        to_phone: str,
        from_phone: str,
        message_body: str
    ) -> Optional[str]:
        """Send SMS message via Twilio"""
        if not self.client:
            logger.error("Twilio client not initialized")
            return None

        try:
            message = self.client.messages.create(
                to=to_phone,
                from_=from_phone,
                body=message_body
            )
            return message.sid
        except Exception as e:
            logger.error(f"Error sending SMS: {str(e)}")
            return None
