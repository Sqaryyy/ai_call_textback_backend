from __future__ import annotations
# app/schemas/task_payloads.py
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List, Literal
from datetime import datetime, timezone

class ProcessCallPayload(BaseModel):
    """Payload for processing incoming calls"""
    call_sid: str = Field(..., description="Twilio call SID")
    caller_phone: str = Field(..., description="Caller's phone number")
    business_phone: str = Field(..., description="Called business number")
    call_status: str = Field(..., description="Call status")
    caller_location: Optional[Dict[str, str]] = Field(None, description="Caller location info")
    correlation_id: str = Field(..., description="Request correlation ID")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ProcessSMSPayload(BaseModel):
    """Payload for processing SMS messages"""
    message_sid: str = Field(..., description="Twilio message SID")
    sender_phone: str = Field(..., description="Sender's phone number")
    business_phone: str = Field(..., description="Business phone number")
    message_body: str = Field(..., description="SMS content")
    media_urls: List[str] = Field(default_factory=list, description="Media attachment URLs")
    conversation_id: Optional[str] = Field(None, description="Existing conversation ID")
    correlation_id: str = Field(..., description="Request correlation ID")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SendSMSPayload(BaseModel):
    """Payload for sending SMS messages"""
    to_phone: str = Field(..., description="Recipient phone number")
    from_phone: str = Field(..., description="Sender phone number (Twilio number)")
    message_body: str = Field(..., description="SMS content")
    conversation_id: Optional[str] = Field(None, description="Conversation ID")
    correlation_id: str = Field(..., description="Request correlation ID")
    priority: Literal["high", "medium", "low"] = Field("medium", description="Task priority")
    retry_count: int = Field(0, description="Current retry attempt")

class BookAppointmentPayload(BaseModel):
    """Payload for booking appointments"""
    conversation_id: str = Field(..., description="Conversation ID")
    customer_phone: str = Field(..., description="Customer phone number")
    business_id: str = Field(..., description="Business identifier")
    appointment_details: Dict[str, Any] = Field(..., description="Appointment information")
    preferred_datetime: Optional[datetime] = Field(None, description="Customer's preferred time")
    correlation_id: str = Field(..., description="Request correlation ID")

class CleanupPayload(BaseModel):
    """Payload for cleanup tasks"""
    cleanup_type: str = Field(..., description="Type of cleanup to perform")
    older_than_hours: int = Field(24, description="Clean items older than X hours")
    batch_size: int = Field(100, description="Cleanup batch size")
    dry_run: bool = Field(False, description="Preview cleanup without executing")