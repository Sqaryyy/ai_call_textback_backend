"""
Pydantic schemas for business team invite endpoints
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List


class CreateBusinessInviteRequest(BaseModel):
    """Request body for creating a business invite."""
    email: Optional[EmailStr] = Field(
        None,
        description="Specific email (optional, if None anyone can use the invite)"
    )
    role: str = Field(
        "member",
        description="Role to assign: owner or member"
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
                "email": "teammember@example.com",
                "role": "member",
                "max_uses": 1,
                "expires_in_days": 7
            }
        }


class BusinessInviteResponse(BaseModel):
    """Response with business invite details."""
    id: str
    token: str
    email: Optional[str]
    role: str
    business_id: str
    business_name: Optional[str]
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
                "email": "teammember@example.com",
                "role": "member",
                "business_id": "660e8400-e29b-41d4-a716-446655440001",
                "business_name": "Acme Corp",
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


class BusinessInviteStatsResponse(BaseModel):
    """Response with business invite statistics."""
    total_invites: int
    active_invites: int
    valid_invites: int
    used_invites: int
    expired_invites: int
    total_uses: int

    class Config:
        json_schema_extra = {
            "example": {
                "total_invites": 15,
                "active_invites": 10,
                "valid_invites": 8,
                "used_invites": 5,
                "expired_invites": 5,
                "total_uses": 7
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


class BusinessUserResponse(BaseModel):
    """Response with business user details."""
    id: str
    email: str
    full_name: Optional[str]
    role: str
    joined_at: str
    is_active: bool

    class Config:
        json_schema_extra = {
            "example": {
                "id": "770e8400-e29b-41d4-a716-446655440002",
                "email": "member@example.com",
                "full_name": "John Doe",
                "role": "member",
                "joined_at": "2025-10-15T12:00:00+00:00",
                "is_active": True
            }
        }


class BusinessUsersListResponse(BaseModel):
    """Response with list of business users."""
    business_id: str
    business_name: str
    total_users: int
    users: List[BusinessUserResponse]

    class Config:
        json_schema_extra = {
            "example": {
                "business_id": "660e8400-e29b-41d4-a716-446655440001",
                "business_name": "Acme Corp",
                "total_users": 3,
                "users": [
                    {
                        "id": "770e8400-e29b-41d4-a716-446655440002",
                        "email": "owner@example.com",
                        "full_name": "Jane Smith",
                        "role": "owner",
                        "joined_at": "2025-10-01T12:00:00+00:00",
                        "is_active": True
                    }
                ]
            }
        }