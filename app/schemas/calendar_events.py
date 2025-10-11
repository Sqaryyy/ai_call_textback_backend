# app/schemas/calendar_events.py
from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from enum import Enum


class CalendarProvider(str, Enum):
    GOOGLE = "google"
    OUTLOOK = "outlook"
    CALENDLY = "calendly"


class AppointmentStatus(str, Enum):
    TENTATIVE = "tentative"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class TimeSlot(BaseModel):
    """Available time slot"""
    start_time: datetime = Field(..., description="Slot start time")
    end_time: datetime = Field(..., description="Slot end time")
    available: bool = Field(True, description="Whether slot is available")
    calendar_provider: CalendarProvider = Field(..., description="Calendar system")

    @field_validator("end_time")
    @classmethod
    def end_after_start(cls, v: datetime, info) -> datetime:
        start_time = info.data.get("start_time")
        if start_time and v <= start_time:
            raise ValueError("End time must be after start time")
        return v


class AvailabilityResponse(BaseModel):
    """Calendar availability response"""
    business_id: str = Field(..., description="Business identifier")
    requested_date: str = Field(..., description="Requested date")
    available_slots: List[TimeSlot] = Field(default_factory=list)
    next_available: Optional[datetime] = Field(None, description="Next available slot if requested date is full")
    timezone: str = Field("UTC", description="Timezone for all times")


class AppointmentRequest(BaseModel):
    """Appointment booking request"""
    business_id: str = Field(..., description="Business identifier")
    customer_phone: str = Field(..., description="Customer phone number")
    customer_name: str = Field(..., description="Customer name")
    customer_email: Optional[str] = Field(None, description="Customer email")
    service_type: str = Field(..., description="Requested service")
    appointment_datetime: datetime = Field(..., description="Requested appointment time")
    duration_minutes: int = Field(60, description="Appointment duration")
    notes: str = Field("", description="Additional notes")
    calendar_provider: CalendarProvider = Field(CalendarProvider.GOOGLE)


class AppointmentResponse(BaseModel):
    """Appointment booking response"""
    appointment_id: str = Field(..., description="Created appointment ID")
    status: AppointmentStatus = Field(..., description="Appointment status")
    confirmation_number: Optional[str] = Field(None, description="Confirmation number")
    calendar_event_id: Optional[str] = Field(None, description="Calendar system event ID")
    booking_url: Optional[str] = Field(None, description="Online booking URL if available")
    success: bool = Field(..., description="Whether booking was successful")
    message: str = Field(..., description="Booking result message")


class CalendarCredentials(BaseModel):
    """Calendar integration credentials"""
    provider: CalendarProvider = Field(..., description="Calendar provider")
    credentials: Dict[str, Any] = Field(..., description="Provider-specific credentials")
    calendar_id: Optional[str] = Field(None, description="Specific calendar ID")
    timezone: str = Field("UTC", description="Calendar timezone")


class BusinessHours(BaseModel):
    """Business operating hours"""
    day_of_week: int = Field(..., description="Day of week (0=Monday, 6=Sunday)", ge=0, le=6)
    open_time: str = Field(..., description="Opening time (HH:MM)")
    close_time: str = Field(..., description="Closing time (HH:MM)")
    is_closed: bool = Field(False, description="Whether business is closed this day")

    @field_validator("open_time")
    @classmethod
    def validate_open_time(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%H:%M")
        except ValueError:
            raise ValueError("Time must be in HH:MM format")
        return v

    @field_validator("close_time")
    @classmethod
    def validate_close_time(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%H:%M")
        except ValueError:
            raise ValueError("Time must be in HH:MM format")
        return v


class BusinessProfile(BaseModel):
    """Complete business profile"""
    id: str = Field(..., description="Business identifier")
    name: str = Field(..., description="Business name")
    phone_number: str = Field(..., description="Business phone number")
    business_type: str = Field(..., description="Type of business")
    services: List[str] = Field(default_factory=list, description="Available services")
    operating_hours: List[BusinessHours] = Field(default_factory=list)
    timezone: str = Field("UTC", description="Business timezone")
    calendar_integration: Optional[CalendarCredentials] = Field(None)
    booking_settings: Dict[str, Any] = Field(default_factory=dict, description="Booking configuration")
    contact_info: Dict[str, str] = Field(default_factory=dict, description="Contact information")
    ai_instructions: str = Field("", description="Custom AI behavior instructions")
    webhook_urls: Dict[str, str] = Field(default_factory=dict, description="Custom webhook endpoints")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = Field(True, description="Whether business profile is active")


# Common validation schemas
class PhoneNumberValidator(BaseModel):
    """Phone number validation helper"""
    phone: str = Field(..., description="Phone number to validate")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not v.startswith("+"):
            raise ValueError("Phone number must start with +")
        if not v[1:].isdigit():
            raise ValueError("Phone number must contain only digits after +")
        if len(v) < 8 or len(v) > 16:
            raise ValueError("Phone number must be between 8-16 characters")
        return v


class CorrelationIdMixin(BaseModel):
    """Mixin for adding correlation ID tracking"""
    correlation_id: str = Field(..., description="Request correlation ID for tracking")


class TimestampMixin(BaseModel):
    """Mixin for adding timestamp fields"""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
