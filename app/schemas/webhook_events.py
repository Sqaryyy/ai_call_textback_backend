from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal
from datetime import datetime


class TwilioCallWebhook(BaseModel):
    """Twilio incoming call webhook payload"""
    CallSid: str = Field(..., description="Unique call identifier")
    AccountSid: str = Field(..., description="Twilio account ID")
    From: str = Field(..., description="Caller phone number")
    To: str = Field(..., description="Called phone number (your Twilio number)")
    CallStatus: Literal["ringing", "in-progress", "completed", "busy", "failed", "no-answer", "canceled"] = Field(..., description="Current call status")
    Direction: Literal["inbound", "outbound"] = Field(..., description="Call direction")
    FromCity: Optional[str] = Field(None, description="Caller's city")
    FromState: Optional[str] = Field(None, description="Caller's state")
    FromCountry: Optional[str] = Field(None, description="Caller's country")
    CallerName: Optional[str] = Field(None, description="Caller ID name if available")

    @field_validator("From", "To")
    @classmethod
    def validate_phone_number(cls, v: str) -> str:
        if not v.startswith("+"):
            raise ValueError("Phone number must include country code")
        return v


class TwilioSMSWebhook(BaseModel):
    """Twilio incoming SMS webhook payload"""
    MessageSid: str = Field(..., description="Unique message identifier")
    AccountSid: str = Field(..., description="Twilio account ID")
    From: str = Field(..., description="Sender phone number")
    To: str = Field(..., description="Recipient phone number (your Twilio number)")
    Body: str = Field(..., description="SMS message content")
    NumMedia: int = Field(0, description="Number of media attachments")
    MediaUrl0: Optional[str] = Field(None, description="First media attachment URL")
    MediaContentType0: Optional[str] = Field(None, description="First media content type")
    FromCity: Optional[str] = Field(None, description="Sender's city")
    FromState: Optional[str] = Field(None, description="Sender's state")
    FromCountry: Optional[str] = Field(None, description="Sender's country")
    Timestamp: Optional[datetime] = Field(None, description="Message timestamp")

    @field_validator("From", "To")
    @classmethod
    def validate_phone_number(cls, v: str) -> str:
        if not v.startswith("+"):
            raise ValueError("Phone number must include country code")
        return v


class TwilioStatusCallback(BaseModel):
    """Twilio SMS delivery status callback"""
    MessageSid: str = Field(..., description="Message identifier")
    MessageStatus: Literal["received", "sending", "sent", "failed", "delivered", "undelivered"] = Field(..., description="Message delivery status")
    To: str = Field(..., description="Recipient phone number")
    From: str = Field(..., description="Sender phone number")
    AccountSid: str = Field(..., description="Twilio account ID")
    ErrorCode: Optional[str] = Field(None, description="Error code if failed")
    ErrorMessage: Optional[str] = Field(None, description="Error description")
    Timestamp: Optional[datetime] = Field(None, description="Status update timestamp")