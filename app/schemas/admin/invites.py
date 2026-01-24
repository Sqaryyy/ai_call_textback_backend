from pydantic import BaseModel, Field, EmailStr
from typing import Optional

# ============================================================================
# Pydantic Schemas
# ============================================================================

class CreatePlatformInviteRequest(BaseModel):
    """Request body for creating a platform invite."""
    email: Optional[EmailStr] = Field(
        None,
        description="Specific email (optional, if None anyone can use the invite)"
    )
    max_uses: int = Field(
        1,
        ge=1,
        le=100,
        description="Maximum number of times the invite can be used"
    )
    expires_in_days: Optional[int] = Field(
        7,
        ge=1,
        le=365,
        description="Days until expiration (null = never expires)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "email": "newowner@example.com",
                "max_uses": 1,
                "expires_in_days": 7
            }
        }


class PlatformInviteResponse(BaseModel):
    """Response with platform invite details."""
    id: str
    token: str
    email: Optional[str]
    role: str
    max_uses: int
    used_count: int
    is_active: bool
    is_valid: bool
    expires_at: Optional[str]
    created_at: str
    used_at: Optional[str]
    invite_url: str

    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "token": "abc123xyz789def456ghi012",
                "email": "newowner@example.com",
                "role": "owner",
                "max_uses": 1,
                "used_count": 0,
                "is_active": True,
                "is_valid": True,
                "expires_at": "2025-10-26T12:00:00+00:00",
                "created_at": "2025-10-19T12:00:00+00:00",
                "used_at": None,
                "invite_url": "http://localhost:3000/register?invite=abc123xyz789def456ghi012"
            }
        }


class PlatformInviteStatsResponse(BaseModel):
    """Response with platform invite statistics."""
    total_invites: int
    active_invites: int
    valid_invites: int
    used_invites: int
    expired_invites: int
    total_uses: int

    class Config:
        json_schema_extra = {
            "example": {
                "total_invites": 25,
                "active_invites": 18,
                "valid_invites": 15,
                "used_invites": 10,
                "expired_invites": 7,
                "total_uses": 12
            }
        }


class ExtendInviteRequest(BaseModel):
    """Request body for extending invite expiration."""
    additional_days: int = Field(
        ...,
        ge=1,
        le=365,
        description="Number of days to add to expiration"
    )


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    details: Optional[dict] = None
