from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date as date_type,time
from uuid import UUID

# ============================================================================
# Request/Response Models - Availability Rules
# ============================================================================

class AvailabilityRuleCreate(BaseModel):
    business_id: UUID = Field(..., description="Business ID for this rule")
    day_of_week: int = Field(..., ge=0, le=6, description="0=Monday, 6=Sunday")
    start_time: time = Field(..., description="Start time (HH:MM:SS)")
    end_time: time = Field(..., description="End time (HH:MM:SS)")
    slot_duration_minutes: int = Field(30, ge=5, le=240, description="Duration of each slot")
    buffer_time_minutes: int = Field(0, ge=0, le=60, description="Buffer between appointments")
    is_active: bool = Field(True, description="Whether this rule is active")


class AvailabilityRuleUpdate(BaseModel):
    day_of_week: Optional[int] = Field(None, ge=0, le=6)
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    slot_duration_minutes: Optional[int] = Field(None, ge=5, le=240)
    buffer_time_minutes: Optional[int] = Field(None, ge=0, le=60)
    is_active: Optional[bool] = None


class AvailabilityRuleResponse(BaseModel):
    id: UUID
    business_id: UUID
    day_of_week: int
    start_time: time
    end_time: time
    slot_duration_minutes: int
    buffer_time_minutes: int
    is_active: bool

    class Config:
        from_attributes = True


class AvailabilityRuleListResponse(BaseModel):
    """Response schema for paginated availability rules list."""
    total: int
    page: int
    page_size: int
    pages: int
    items: List[AvailabilityRuleResponse]


class AvailabilityRuleStatsResponse(BaseModel):
    """Response schema for availability rule statistics."""
    total_rules: int
    active_rules: int
    inactive_rules: int
    rules_by_day: dict
    unique_businesses: int
    avg_slot_duration_minutes: float
    avg_buffer_time_minutes: float


# ============================================================================
# Request/Response Models - Availability Overrides
# ============================================================================

class AvailabilityOverrideCreate(BaseModel):
    business_id: UUID = Field(..., description="Business ID for this override")
    date: date_type = Field(..., description="Date for the override")
    is_available: bool = Field(..., description="Whether business is available on this date")
    start_time: Optional[time] = Field(None, description="Start time if different from normal")
    end_time: Optional[time] = Field(None, description="End time if different from normal")
    reason: Optional[str] = Field(None, description="Reason for override (e.g., Holiday, Vacation)")


class AvailabilityOverrideUpdate(BaseModel):
    date: Optional[date_type] = None
    is_available: Optional[bool] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    reason: Optional[str] = None


class AvailabilityOverrideResponse(BaseModel):
    id: UUID
    business_id: UUID
    date: date_type
    is_available: bool
    start_time: Optional[time]
    end_time: Optional[time]
    reason: Optional[str]

    class Config:
        from_attributes = True


class AvailabilityOverrideListResponse(BaseModel):
    """Response schema for paginated availability overrides list."""
    total: int
    page: int
    page_size: int
    pages: int
    items: List[AvailabilityOverrideResponse]


class AvailabilityOverrideStatsResponse(BaseModel):
    """Response schema for availability override statistics."""
    total_overrides: int
    available_overrides: int
    unavailable_overrides: int
    unique_businesses: int
    overrides_last_30d: int
    overrides_next_30d: int


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    details: Optional[dict] = None
