# ===== app/schemas/webhook.py =====
from pydantic import BaseModel, HttpUrl, Field, field_validator
from typing import List, Optional, Any, Dict
from datetime import datetime
from uuid import UUID


class WebhookEndpointCreate(BaseModel):
    url: str
    description: Optional[str] = None
    enabled_events: List[str] = Field(default=["*"])

    @field_validator('url')
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate that URL is properly formatted"""
        if not v.startswith(('http://', 'https://')):
            raise ValueError('URL must start with http:// or https://')
        return v


class WebhookEndpointUpdate(BaseModel):
    url: Optional[str] = None
    description: Optional[str] = None
    enabled_events: Optional[List[str]] = None
    is_active: Optional[bool] = None

    @field_validator('url')
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate that URL is properly formatted"""
        if v and not v.startswith(('http://', 'https://')):
            raise ValueError('URL must start with http:// or https://')
        return v


class WebhookEndpointResponse(BaseModel):
    id: UUID
    business_id: UUID
    url: str
    description: Optional[str]
    enabled_events: List[str]
    secret: str  # Include so users can verify signatures
    is_active: bool
    consecutive_failures: int
    last_success_at: Optional[datetime]
    last_failure_at: Optional[datetime]
    last_failure_reason: Optional[str]
    auto_disabled_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WebhookEventResponse(BaseModel):
    id: UUID
    webhook_endpoint_id: UUID
    business_id: UUID
    event_type: str
    event_data: Dict[str, Any]
    status: str
    attempts: int
    max_attempts: int
    response_status_code: Optional[int]
    response_body: Optional[str]
    response_time_ms: Optional[int]
    error_message: Optional[str]
    last_attempt_at: Optional[datetime]
    next_retry_at: Optional[datetime]
    created_at: datetime
    delivered_at: Optional[datetime]
    failed_at: Optional[datetime]

    class Config:
        from_attributes = True


class WebhookTestResponse(BaseModel):
    success: bool
    status_code: Optional[int] = None
    response_time_ms: Optional[int] = None
    message: str