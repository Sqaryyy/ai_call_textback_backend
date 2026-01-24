from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from uuid import UUID
from decimal import Decimal
from app.models.business.service import BookingType,Service
# ============================================================================
# Request/Response Models
# ============================================================================

class RequiredFieldSchema(BaseModel):
    """Schema for service required fields"""
    field: str = Field(..., description="Field name/key")
    label: str = Field(..., description="Display label")
    type: str = Field(..., description="Field type: text, email, phone, textarea, etc.")
    required: bool = Field(True, description="Whether field is required")
    placeholder: Optional[str] = Field(None, description="Placeholder text")


class ServiceCreate(BaseModel):
    business_id: str = Field(..., description="Business ID this service belongs to")
    name: str = Field(..., min_length=1, max_length=200, description="Service name")
    description: Optional[str] = Field(None, description="Service description")
    price: Optional[Decimal] = Field(None, ge=0, description="Service price")
    price_display: Optional[str] = Field(None, max_length=50, description="Display price string")
    duration: Optional[int] = Field(None, ge=1, description="Duration in minutes")
    booking_type: BookingType = Field(BookingType.DIRECT, description="How service should be booked")
    consultation_duration: Optional[int] = Field(None, ge=1, description="Consultation duration in minutes")
    consultation_price: Optional[Decimal] = Field(None, ge=0, description="Consultation price")
    required_fields: List[RequiredFieldSchema] = Field(default_factory=list, description="Required fields to collect")
    is_active: bool = Field(True, description="Whether service is active")
    display_order: int = Field(0, description="Display order for sorting")

    @field_validator('consultation_duration')
    @classmethod
    def validate_consultation_duration(cls, v, info):
        booking_type = info.data.get('booking_type')
        if booking_type == BookingType.CONSULTATION_REQUIRED and v is None:
            raise ValueError('consultation_duration is required when booking_type is CONSULTATION_REQUIRED')
        return v


class ServiceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    price: Optional[Decimal] = Field(None, ge=0)
    price_display: Optional[str] = Field(None, max_length=50)
    duration: Optional[int] = Field(None, ge=1)
    booking_type: Optional[BookingType] = None
    consultation_duration: Optional[int] = Field(None, ge=1)
    consultation_price: Optional[Decimal] = Field(None, ge=0)
    required_fields: Optional[List[RequiredFieldSchema]] = None
    is_active: Optional[bool] = None
    display_order: Optional[int] = None


class ServiceResponse(BaseModel):
    id: UUID
    business_id: UUID
    name: str
    description: Optional[str]
    price: Optional[float]
    price_display: Optional[str]
    duration: Optional[int]
    booking_type: str
    consultation_duration: Optional[int]
    consultation_price: Optional[float]
    required_fields: List[dict]
    is_active: bool
    display_order: int
    formatted_price: str
    formatted_duration: str
    formatted_consultation_duration: str
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True

    @classmethod
    def from_orm(cls, service: Service):
        """Custom from_orm to include computed properties"""
        data = service.to_dict()
        data['formatted_price'] = service.formatted_price
        data['formatted_duration'] = service.formatted_duration
        data['formatted_consultation_duration'] = service.formatted_consultation_duration
        return cls(**data)


class ServiceListResponse(BaseModel):
    """Response with business context"""
    id: UUID
    business_id: UUID
    business_name: str
    name: str
    description: Optional[str]
    price: Optional[float]
    price_display: Optional[str]
    duration: Optional[int]
    booking_type: str
    consultation_duration: Optional[int]
    consultation_price: Optional[float]
    required_fields: List[dict]
    is_active: bool
    display_order: int
    formatted_price: str
    formatted_duration: str
    formatted_consultation_duration: str
    created_at: str
    updated_at: str
