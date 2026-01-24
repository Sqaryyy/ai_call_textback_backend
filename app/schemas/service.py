"""
Pydantic schemas for service management endpoints
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum


class BookingTypeEnum(str, Enum):
    """Pydantic enum for booking types"""
    DIRECT = "direct"
    CONSULTATION_REQUIRED = "consultation_required"
    LEAD_ONLY = "lead_only"


class RequiredFieldSchema(BaseModel):
    """Schema for required field definition"""
    field: str = Field(..., description="Field name (e.g., 'budget', 'timeline')")
    label: Optional[str] = Field(None, description="Display label for the field")
    type: str = Field(default="text", description="Field type: text, select, multiselect, number, date")
    required: bool = Field(default=True, description="Whether this field is required")
    options: Optional[List[str]] = Field(None, description="Options for select/multiselect types")


class ServiceCreate(BaseModel):
    """Request model for creating a service"""
    business_id: str
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    price: Optional[float] = Field(None, ge=0)
    price_display: Optional[str] = Field(None, max_length=50)
    duration: Optional[int] = Field(None, ge=0,
                                    description="Duration in minutes (optional if consultation_required or lead_only)")

    # New booking fields
    booking_type: BookingTypeEnum = Field(default=BookingTypeEnum.DIRECT)
    consultation_duration: Optional[int] = Field(None, ge=5, description="Discovery call duration in minutes")
    consultation_price: Optional[float] = Field(None, ge=0, description="Discovery call price (usually 0)")
    required_fields: List[RequiredFieldSchema] = Field(default_factory=list,
                                                       description="Fields that must be collected")

    display_order: int = Field(default=0)


class ServiceUpdate(BaseModel):
    """Request model for updating a service"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    price: Optional[float] = Field(None, ge=0)
    price_display: Optional[str] = Field(None, max_length=50)
    duration: Optional[int] = Field(None, ge=0)

    # New booking fields
    booking_type: Optional[BookingTypeEnum] = None
    consultation_duration: Optional[int] = Field(None, ge=5)
    consultation_price: Optional[float] = Field(None, ge=0)
    required_fields: Optional[List[RequiredFieldSchema]] = None

    display_order: Optional[int] = None
    is_active: Optional[bool] = None


class ServiceResponse(BaseModel):
    """Response model for service data"""
    id: str
    business_id: str
    name: str
    description: Optional[str]
    price: Optional[float]
    price_display: Optional[str]
    formatted_price: str
    duration: Optional[int]
    formatted_duration: str

    # New booking fields
    booking_type: str
    consultation_duration: Optional[int]
    consultation_price: Optional[float]
    formatted_consultation_duration: Optional[str]
    required_fields: List[Dict[str, Any]]

    is_active: bool
    display_order: int
    created_at: str
    updated_at: str
    linked_documents_count: int = 0


class ServiceListResponse(BaseModel):
    """Response model for service list"""
    total: int
    services: List[ServiceResponse]


class ServiceBulkCreate(BaseModel):
    """Request model for bulk service creation"""
    business_id: str
    services: List[ServiceCreate]