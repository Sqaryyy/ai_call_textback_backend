from pydantic import BaseModel
from typing import Optional, List

# ============================================================================
# Pydantic Schemas
# ============================================================================

class CallEventResponse(BaseModel):
    """Response schema for call event."""
    id: str
    business_id: str
    twilio_call_sid: str
    caller_phone: str
    business_phone: str
    call_status: str
    direction: str
    caller_location: dict
    caller_name: Optional[str]
    duration: Optional[str]
    recording_url: Optional[str]
    call_metadata: dict
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "business_id": "660e8400-e29b-41d4-a716-446655440001",
                "twilio_call_sid": "CA1234567890abcdef1234567890ab",
                "caller_phone": "+1234567890",
                "business_phone": "+0987654321",
                "call_status": "completed",
                "direction": "inbound",
                "caller_location": {"city": "New York", "state": "NY"},
                "caller_name": "John Doe",
                "duration": "120",
                "recording_url": "https://api.twilio.com/recording/RE123",
                "call_metadata": {"source": "twilio"},
                "created_at": "2025-10-19T12:00:00+00:00",
                "updated_at": "2025-10-19T12:05:00+00:00"
            }
        }


class CallEventListResponse(BaseModel):
    """Response schema for paginated call events list."""
    total: int
    page: int
    page_size: int
    pages: int
    items: List[CallEventResponse]


class CallEventStatsResponse(BaseModel):
    """Response schema for call event statistics."""
    total_calls: int
    inbound_calls: int
    outbound_calls: int
    completed_calls: int
    failed_calls: int
    total_duration_seconds: int
    avg_duration_seconds: float
    calls_with_recordings: int
    unique_businesses: int
    calls_last_24h: int
    calls_last_7d: int
    calls_last_30d: int

    class Config:
        json_schema_extra = {
            "example": {
                "total_calls": 1250,
                "inbound_calls": 800,
                "outbound_calls": 450,
                "completed_calls": 1100,
                "failed_calls": 150,
                "total_duration_seconds": 150000,
                "avg_duration_seconds": 120.5,
                "calls_with_recordings": 950,
                "unique_businesses": 45,
                "calls_last_24h": 50,
                "calls_last_7d": 300,
                "calls_last_30d": 1000
            }
        }


class CallEventsByBusinessResponse(BaseModel):
    """Response schema for call events grouped by business."""
    business_id: str
    total_calls: int
    inbound_calls: int
    outbound_calls: int
    completed_calls: int
    failed_calls: int
    total_duration_seconds: int
    last_call_at: str


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    details: Optional[dict] = None