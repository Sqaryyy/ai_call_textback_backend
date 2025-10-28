# app/models/business.py
from sqlalchemy import Column, String, Boolean, DateTime, JSON, Text, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import uuid
from app.models.base import Base


class Business(Base):
    __tablename__ = "businesses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    phone_number = Column(String(20), nullable=False, unique=True)
    business_type = Column(String(100), nullable=False)  # Keep for backward compatibility

    # NEW: Structured business configuration
    business_profile = Column(JSON, default=dict)  # Personality, tone, booking flow type
    service_catalog = Column(JSON, default=dict)  # Detailed service definitions
    conversation_policies = Column(JSON, default=dict)  # Business rules and policies
    quick_responses = Column(JSON, default=dict)  # FAQ and common answers

    # Legacy/simple fields (keep for backward compatibility)
    services = Column(JSON, default=list)  # Simple list - will migrate to service_catalog
    timezone = Column(String(50), default="UTC")
    contact_info = Column(JSON, default=dict)
    ai_instructions = Column(Text, default="")  # Override/additional instructions

    # Technical fields
    webhook_urls = Column(JSON, default=dict)
    booking_settings = Column(JSON, default=dict)
    onboarding_status = Column(JSON, default=dict)  # Track onboarding completion

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    is_active = Column(Boolean, default=True)


class BusinessHours(Base):
    __tablename__ = "business_hours"

    id = Column(Integer, primary_key=True)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0=Monday, 6=Sunday
    open_time = Column(String(5), nullable=False)  # HH:MM format
    close_time = Column(String(5), nullable=False)  # HH:MM format
    is_closed = Column(Boolean, default=False)
