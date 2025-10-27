"""
Pydantic schemas for Business model validation and serialization
"""
from pydantic import BaseModel, Field, validator, field_validator
from typing import Optional, Dict, List, Any
from datetime import datetime
from uuid import UUID


# ============================================================================
# Request Schemas (for incoming data)
# ============================================================================

class ServiceCatalogItem(BaseModel):
    """Schema for a single service in the catalog"""
    description: Optional[str] = None
    price: Optional[str] = None  # Can be "Free" or a number as string
    duration: Optional[int] = Field(None, ge=0, description="Duration in minutes")

    @field_validator('price')
    @classmethod
    def validate_price(cls, v):
        if v is None:
            return v
        if isinstance(v, (int, float)):
            return str(v)
        if v.lower() == 'free':
            return 'Free'
        # Try to parse as number
        try:
            float(v.replace('$', '').replace(',', ''))
            return v
        except ValueError:
            raise ValueError('Price must be a number, "Free", or a valid price string')


class BusinessProfileSchema(BaseModel):
    """Schema for business_profile JSON field"""
    description: Optional[str] = None
    areas_served: Optional[List[str]] = Field(default_factory=list)
    specialties: Optional[List[str]] = Field(default_factory=list)

    class Config:
        extra = "allow"  # Allow additional fields


class ContactInfoSchema(BaseModel):
    """Schema for contact_info JSON field"""
    address: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    office_phone: Optional[str] = None
    emergency_line: Optional[str] = None

    class Config:
        extra = "allow"


class BookingSettingsSchema(BaseModel):
    """Schema for booking_settings JSON field"""
    enabled: Optional[bool] = True
    require_deposit: Optional[bool] = False
    deposit_amount: Optional[float] = Field(None, ge=0)
    cancellation_hours: Optional[int] = Field(None, ge=0)

    class Config:
        extra = "allow"


class BusinessUpdateRequest(BaseModel):
    """
    Schema for updating business information.
    All fields are optional - only send what you want to update.
    """
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    business_type: Optional[str] = Field(None, min_length=1, max_length=100)

    # Structured JSON fields with validation
    business_profile: Optional[BusinessProfileSchema] = None
    service_catalog: Optional[Dict[str, ServiceCatalogItem]] = None
    conversation_policies: Optional[Dict[str, str]] = None
    quick_responses: Optional[Dict[str, str]] = None

    # Simple fields
    services: Optional[List[str]] = None  # Legacy field
    timezone: Optional[str] = None
    contact_info: Optional[ContactInfoSchema] = None
    ai_instructions: Optional[str] = None

    # Technical fields
    webhook_urls: Optional[Dict[str, str]] = None
    booking_settings: Optional[BookingSettingsSchema] = None

    @field_validator('service_catalog')
    @classmethod
    def validate_service_catalog(cls, v):
        """Ensure service names are valid keys"""
        if v is None:
            return v
        for service_name in v.keys():
            if not service_name or not service_name.strip():
                raise ValueError('Service names cannot be empty')
        return v

    @field_validator('quick_responses')
    @classmethod
    def validate_quick_responses(cls, v):
        """Ensure Q&A pairs are valid"""
        if v is None:
            return v
        for question, answer in v.items():
            if not question or not question.strip():
                raise ValueError('Questions cannot be empty')
            if not answer or not answer.strip():
                raise ValueError('Answers cannot be empty')
        return v


# ============================================================================
# Response Schemas (for outgoing data)
# ============================================================================

class BusinessResponse(BaseModel):
    """Schema for business data in responses"""
    id: UUID
    name: str
    phone_number: str
    business_type: str

    business_profile: Dict[str, Any]
    service_catalog: Dict[str, Any]
    conversation_policies: Dict[str, Any]
    quick_responses: Dict[str, Any]

    services: List[str]
    timezone: str
    contact_info: Dict[str, Any]
    ai_instructions: Optional[str]

    webhook_urls: Dict[str, Any]
    booking_settings: Dict[str, Any]
    onboarding_status: Dict[str, Any]

    created_at: datetime
    updated_at: datetime
    is_active: bool

    class Config:
        from_attributes = True  # Allows creation from SQLAlchemy models


class ReindexResult(BaseModel):
    """Schema for reindexing operation results"""
    triggered: bool
    success: Optional[bool] = None
    indexed_count: Optional[int] = None
    duration_ms: Optional[float] = None
    reason: Optional[str] = None
    message: Optional[str] = None


class BusinessUpdateResponse(BaseModel):
    """Schema for business update response"""
    success: bool
    business: BusinessResponse
    changes_detected: List[str]
    reindex_result: ReindexResult


class KnowledgeStatsResponse(BaseModel):
    """Schema for knowledge statistics response"""
    success: bool
    total_chunks: int
    category_breakdown: Dict[str, int]
    business_id: UUID
    last_indexed: Optional[datetime] = None


class ManualReindexResponse(BaseModel):
    """Schema for manual reindex operation response"""
    success: bool
    message: str
    indexed_count: int
    business_id: UUID
    duration_ms: Optional[float] = None