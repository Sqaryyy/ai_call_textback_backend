# ===== app/schemas/api_key.py =====
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from uuid import UUID
from datetime import datetime


class APIKeyCreate(BaseModel):
    """Schema for creating a new API key"""
    name: str = Field(..., min_length=1, max_length=100, description="Name for the API key")
    description: Optional[str] = Field(None, max_length=500, description="Optional description")
    scopes: List[str] = Field(default=["*"], description="List of permission scopes")
    expires_in_days: Optional[int] = Field(None, gt=0, description="Number of days until expiration")
    rate_limit: Optional[int] = Field(1000, gt=0, description="Requests per hour limit")
    allowed_ips: Optional[List[str]] = Field(default=[], description="IP addresses allowed to use this key")

    @validator('name')
    def name_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Name cannot be empty')
        return v.strip()


class APIKeyUpdate(BaseModel):
    """Schema for updating an API key"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    scopes: Optional[List[str]] = None
    is_active: Optional[bool] = None
    rate_limit: Optional[int] = Field(None, gt=0)
    allowed_ips: Optional[List[str]] = None


class APIKeyResponse(BaseModel):
    """Schema for API key responses (without secret)"""
    id: UUID
    business_id: UUID
    key_prefix: str
    name: str
    description: Optional[str]
    scopes: List[str]
    is_active: bool
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    usage_count: int
    rate_limit: int
    allowed_ips: List[str]
    created_at: datetime
    updated_at: datetime
    revoked_at: Optional[datetime]
    revoked_reason: Optional[str]

    class Config:
        from_attributes = True


class APIKeyWithSecretResponse(APIKeyResponse):
    """Schema for API key with secret (only returned on creation/rotation)"""
    secret: str = Field(..., description="Full API key - only shown once!")

    class Config:
        from_attributes = True