from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID


# ============================================================================
# Request/Response Models
# ============================================================================

class AppointmentCreate(BaseModel):
    business_id: UUID = Field(..., description="Business ID for this appointment")
    conversation_id: UUID = Field(..., description="Associated conversation ID")
    customer_phone: str = Field(..., description="Customer phone number")
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    service_type: str = Field(..., description="Type of service")
    appointment_datetime: datetime = Field(..., description="Appointment date and time")
    duration_minutes: int = Field(30, description="Duration in minutes")
    notes: Optional[str] = None
    status: str = Field("scheduled", description="scheduled, confirmed, cancelled, completed, no_show")
    booking_source: str = Field("manual", description="sms, web, api, manual")
    calendar_integration_id: Optional[UUID] = None


class AppointmentUpdate(BaseModel):
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    service_type: Optional[str] = None
    appointment_datetime: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    cancellation_reason: Optional[str] = None
    external_event_id: Optional[str] = None
    external_event_url: Optional[str] = None
    sync_status: Optional[str] = None


class AppointmentResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    business_id: UUID
    calendar_integration_id: Optional[UUID]
    customer_phone: str
    customer_name: Optional[str]
    customer_email: Optional[str]
    service_type: str
    appointment_datetime: datetime
    duration_minutes: int
    notes: Optional[str]
    status: str
    booking_source: str
    external_event_id: Optional[str]
    external_event_url: Optional[str]
    sync_status: str
    sync_attempts: int
    last_sync_error: Optional[str]
    last_synced_at: Optional[datetime]
    reminder_sent_at: Optional[datetime]
    confirmation_sent_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    cancelled_at: Optional[datetime]
    cancellation_reason: Optional[str]

    class Config:
        from_attributes = True


class AppointmentListResponse(BaseModel):
    """Response schema for paginated appointments list."""
    total: int
    page: int
    page_size: int
    pages: int
    items: List[AppointmentResponse]


class AppointmentStatsResponse(BaseModel):
    """Response schema for appointment statistics."""
    total_appointments: int
    scheduled_appointments: int
    confirmed_appointments: int
    cancelled_appointments: int
    completed_appointments: int
    no_show_appointments: int
    appointments_by_status: dict
    appointments_by_source: dict
    unique_businesses: int
    unique_customers: int
    avg_duration_minutes: float
    appointments_last_24h: int
    appointments_last_7d: int
    appointments_last_30d: int
    upcoming_appointments: int


class AppointmentsByBusinessResponse(BaseModel):
    """Response schema for appointments grouped by business."""
    business_id: str
    total_appointments: int
    scheduled_appointments: int
    confirmed_appointments: int
    cancelled_appointments: int
    completed_appointments: int
    last_appointment_at: Optional[str]


class CancelAppointmentRequest(BaseModel):
    cancellation_reason: Optional[str] = Field(None, description="Reason for cancellation")


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    details: Optional[dict] = None

