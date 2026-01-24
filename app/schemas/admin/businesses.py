from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from uuid import UUID


# ============================================================================
# Request/Response Models - Business
# ============================================================================

class BusinessProfileUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    business_type: Optional[str] = Field(None, max_length=100)
    timezone: Optional[str] = Field(None, max_length=50)
    business_profile: Optional[dict] = Field(None, description="Personality, tone, general info")
    contact_info: Optional[dict] = Field(None, description="Contact information")
    ai_instructions: Optional[str] = Field(None, description="Additional AI behavior instructions")
    booking_settings: Optional[dict] = Field(None, description="Booking configuration")
    is_active: Optional[bool] = None


class BusinessResponse(BaseModel):
    id: UUID
    name: str
    phone_number: Optional[str] = None  # Can be null
    business_type: Optional[str] = None  # Might be null
    business_profile: Optional[dict] = {}  # Default to empty dict
    contact_info: Optional[dict] = {}  # Default to empty dict
    timezone: str
    webhook_urls: Optional[dict] = {}  # Default to empty dict
    booking_settings: Optional[dict] = {}  # Default to empty dict
    onboarding_status: Optional[dict] = {}  # Default to empty dict
    ai_instructions: Optional[str] = ""  # Default to empty string
    created_at: str
    updated_at: str
    is_active: bool

    class Config:
        from_attributes = True


class BusinessListResponse(BaseModel):
    """Response schema for paginated business list."""
    total: int
    page: int
    page_size: int
    pages: int
    items: List[BusinessResponse]


class BusinessStatsResponse(BaseModel):
    """Response schema for business statistics."""
    business_id: str
    business_name: str
    services_count: int
    documents_count: int
    availability_rules_count: int
    availability_overrides_count: int
    business_hours_configured: bool
    onboarding_complete: bool
    timezone: str
    is_active: bool


class PlatformBusinessStatsResponse(BaseModel):
    """Response schema for platform-wide business statistics."""
    total_businesses: int
    active_businesses: int
    inactive_businesses: int
    businesses_by_type: dict
    businesses_with_hours_configured: int
    businesses_onboarded: int
    businesses_last_24h: int
    businesses_last_7d: int
    businesses_last_30d: int


# ============================================================================
# Request/Response Models - Business Hours
# ============================================================================

class BusinessHoursCreate(BaseModel):
    business_id: UUID = Field(..., description="Business ID for these hours")
    day_of_week: int = Field(..., ge=0, le=6, description="0=Monday, 6=Sunday")
    open_time: str = Field(..., pattern=r'^([01]\d|2[0-3]):([0-5]\d)$', description="HH:MM format")
    close_time: str = Field(..., pattern=r'^([01]\d|2[0-3]):([0-5]\d)$', description="HH:MM format")
    is_closed: bool = Field(False, description="Whether business is closed this day")

    @field_validator('close_time')
    @classmethod
    def validate_time_range(cls, v, info):
        open_time = info.data.get('open_time')
        if open_time and v <= open_time:
            raise ValueError('close_time must be after open_time')
        return v


class BusinessHoursUpdate(BaseModel):
    open_time: Optional[str] = Field(None, pattern=r'^([01]\d|2[0-3]):([0-5]\d)$')
    close_time: Optional[str] = Field(None, pattern=r'^([01]\d|2[0-3]):([0-5]\d)$')
    is_closed: Optional[bool] = None


class BusinessHoursResponse(BaseModel):
    id: int
    business_id: UUID
    day_of_week: int
    open_time: str
    close_time: str
    is_closed: bool

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    details: Optional[dict] = None
