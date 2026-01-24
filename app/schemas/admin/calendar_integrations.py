from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from datetime import datetime
# ============================================================================
# Request/Response Models
# ============================================================================

class CalendarIntegrationCreate(BaseModel):
    business_id: UUID = Field(..., description="Business ID for the integration")
    provider: str = Field(..., description="google, calendly, outlook, cal.com")
    is_active: bool = Field(True, description="Whether integration is active")
    is_primary: bool = Field(False, description="Primary calendar for the business")
    sync_direction: str = Field("bidirectional", description="read_only, write_only, bidirectional")
    auto_sync_enabled: bool = Field(True, description="Enable automatic sync")
    provider_config: Optional[dict] = Field(None, description="Provider-specific configuration")


class CalendarIntegrationUpdate(BaseModel):
    is_active: Optional[bool] = None
    is_primary: Optional[bool] = None
    sync_direction: Optional[str] = Field(None, description="read_only, write_only, bidirectional")
    auto_sync_enabled: Optional[bool] = None
    provider_config: Optional[dict] = None
    last_sync_status: Optional[str] = Field(None, description="success, failed, partial")


class CalendarIntegrationResponse(BaseModel):
    id: UUID
    business_id: UUID
    provider: str
    is_active: bool
    is_primary: bool
    sync_direction: str
    auto_sync_enabled: bool
    provider_config: Optional[dict]
    last_sync_at: Optional[datetime]
    last_sync_status: Optional[str]
    token_expires_at: Optional[datetime]
    has_valid_token: bool = Field(description="Whether access token exists and hasn't expired")
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class CalendarIntegrationListResponse(BaseModel):
    """Response schema for paginated calendar integrations list."""
    total: int
    page: int
    page_size: int
    pages: int
    items: List[CalendarIntegrationResponse]


class CalendarSyncRequest(BaseModel):
    force_full_sync: bool = Field(False, description="Force a full sync instead of incremental")


class CalendarSyncResponse(BaseModel):
    integration_id: UUID
    sync_status: str
    events_synced: int
    errors: List[str]
    sync_started_at: datetime
    sync_completed_at: Optional[datetime]


class CalendarIntegrationStatsResponse(BaseModel):
    """Response schema for calendar integration statistics."""
    total_integrations: int
    active_integrations: int
    inactive_integrations: int
    integrations_by_provider: dict
    integrations_with_valid_tokens: int
    integrations_last_24h: int
    integrations_last_7d: int
    integrations_last_30d: int
    unique_businesses: int


class CalendarIntegrationsByBusinessResponse(BaseModel):
    """Response schema for calendar integrations grouped by business."""
    business_id: str
    total_integrations: int
    active_integrations: int
    integrations_by_provider: dict
    valid_tokens: int
    primary_calendar_provider: Optional[str]
    last_sync_at: Optional[str]


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    details: Optional[dict] = None
