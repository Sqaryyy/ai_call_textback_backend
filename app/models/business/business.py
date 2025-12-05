# app/models/business.py
"""
Business Model - De-bloated version
Structured data moved to Services and Documents tables
"""
from sqlalchemy import Column, String, Boolean, DateTime, JSON, Text, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import uuid
from app.models.base import Base
from sqlalchemy.orm import relationship


class Business(Base):
    __tablename__ = "businesses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    phone_number = Column(String(20), nullable=False, unique=True)
    business_type = Column(String(100), nullable=False)

    # Basic business configuration (kept for backward compatibility during transition)
    business_profile = Column(JSON, default=dict)  # Personality, tone, general info

    # DEPRECATED: These will be removed after full migration
    # Keep temporarily for backward compatibility
    service_catalog = Column(JSON, default=dict)  # MIGRATE TO: services table
    conversation_policies = Column(JSON, default=dict)  # MIGRATE TO: documents table (POLICY type)
    quick_responses = Column(JSON, default=dict)  # MIGRATE TO: documents table (FAQ type)
    services = Column(JSON, default=list)  # MIGRATE TO: services table

    # Contact information (kept as JSON for flexibility)
    contact_info = Column(JSON, default=dict)

    # System configuration
    timezone = Column(String(50), default="UTC")
    webhook_urls = Column(JSON, default=dict)
    booking_settings = Column(JSON, default=dict)
    onboarding_status = Column(JSON, default=dict)

    # AI behavior overrides (kept for specific business rules)
    ai_instructions = Column(Text, default="")  # Additional instructions not in documents

    service_relationships = relationship("Service", back_populates="business")
    # Technical fields
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    is_active = Column(Boolean, default=True)

    def __repr__(self):
        return f"<Business(id={self.id}, name={self.name})>"

    def to_dict(self, include_deprecated=False):
        """Convert to dictionary for API responses"""
        data = {
            "id": str(self.id),
            "name": self.name,
            "phone_number": self.phone_number,
            "business_type": self.business_type,
            "business_profile": self.business_profile,
            "contact_info": self.contact_info,
            "timezone": self.timezone,
            "webhook_urls": self.webhook_urls,
            "booking_settings": self.booking_settings,
            "onboarding_status": self.onboarding_status,
            "ai_instructions": self.ai_instructions,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "is_active": self.is_active,
        }

        # Only include deprecated fields if explicitly requested
        if include_deprecated:
            data.update({
                "service_catalog": self.service_catalog,
                "conversation_policies": self.conversation_policies,
                "quick_responses": self.quick_responses,
                "services": self.services,
            })

        return data


class BusinessHours(Base):
    __tablename__ = "business_hours"

    id = Column(Integer, primary_key=True)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0=Monday, 6=Sunday
    open_time = Column(String(5), nullable=False)  # HH:MM format
    close_time = Column(String(5), nullable=False)  # HH:MM format
    is_closed = Column(Boolean, default=False)

    def __repr__(self):
        return f"<BusinessHours(business_id={self.business_id}, day={self.day_of_week})>"