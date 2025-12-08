# app/models/service.py
"""
Service Model - Structured service definitions
Each service belongs to one business and contains definitive service details.
"""
from sqlalchemy import Column, String, Numeric, Integer, ForeignKey, Boolean, DateTime, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum
from app.models.base import Base


class BookingType(enum.Enum):
    """Defines how a service should be booked"""
    DIRECT = "direct"  # Book the service directly into calendar
    CONSULTATION_REQUIRED = "consultation_required"  # Must book discovery call first
    LEAD_ONLY = "lead_only"  # Collect info only, notify owner, no booking


class Service(Base):
    """
    Stores structured service information (source of truth for price/duration).
    Replaces the unstructured Business.service_catalog JSON field.
    """
    __tablename__ = "services"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Core service details
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # Pricing (nullable - some services may not have fixed pricing)
    price = Column(Numeric(10, 2), nullable=True)  # Stored as decimal for precision
    price_display = Column(String(50), nullable=True)  # e.g., "Free", "Starting at $50"

    # Duration in minutes (nullable - some services like projects don't have fixed duration)
    duration = Column(Integer, nullable=True)

    # Booking behavior
    booking_type = Column(
        SQLEnum(BookingType),
        default=BookingType.DIRECT,
        nullable=False,
        server_default="direct"
    )

    # Consultation/Discovery call settings (used when booking_type = CONSULTATION_REQUIRED)
    consultation_duration = Column(Integer, nullable=True)  # Duration in minutes
    consultation_price = Column(Numeric(10, 2), nullable=True)  # Usually 0 or low cost

    # Required information fields that must be collected before booking/processing
    # Structure: [{"field": "name", "label": "Full Name", "type": "text", "required": true}, ...]
    required_fields = Column(JSON, nullable=False, default=list, server_default='[]')

    # Status and ordering
    is_active = Column(Boolean, default=True, index=True)
    display_order = Column(Integer, default=0)  # For UI sorting

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # Relationships
    business = relationship("Business", back_populates="service_relationships")
    documents = relationship(
        "Document",
        back_populates="service",
        foreign_keys="Document.related_service_id"
    )

    def __repr__(self):
        return f"<Service(id={self.id}, name={self.name}, business_id={self.business_id})>"

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": str(self.id),
            "business_id": str(self.business_id),
            "name": self.name,
            "description": self.description,
            "price": float(self.price) if self.price else None,
            "price_display": self.price_display,
            "duration": self.duration,
            "booking_type": self.booking_type.value if self.booking_type else "direct",
            "consultation_duration": self.consultation_duration,
            "consultation_price": float(self.consultation_price) if self.consultation_price else None,
            "required_fields": self.required_fields or [],
            "is_active": self.is_active,
            "display_order": self.display_order,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @property
    def formatted_price(self) -> str:
        """Return human-readable price string"""
        if self.price_display:
            return self.price_display
        elif self.price:
            return f"${self.price:.2f}"
        else:
            return "Contact for pricing"

    @property
    def formatted_duration(self) -> str:
        """Return human-readable duration string"""
        if not self.duration:
            return "Duration varies"

        hours = self.duration // 60
        minutes = self.duration % 60

        if hours > 0 and minutes > 0:
            return f"{hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h"
        else:
            return f"{minutes}m"

    @property
    def formatted_consultation_duration(self) -> str:
        """Return human-readable consultation duration string"""
        if not self.consultation_duration:
            return ""

        hours = self.consultation_duration // 60
        minutes = self.consultation_duration % 60

        if hours > 0 and minutes > 0:
            return f"{hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h"
        else:
            return f"{minutes}m"

    def get_booking_duration(self) -> int:
        """
        Get the duration to use for calendar booking.
        Returns consultation_duration if consultation required, otherwise service duration.
        """
        if self.booking_type == BookingType.CONSULTATION_REQUIRED and self.consultation_duration:
            return self.consultation_duration
        return self.duration or 30  # Default to 30 minutes if not set

    def validate_required_fields(self, collected_data: dict) -> tuple[bool, list]:
        """
        Validate that all required fields have been collected.

        Args:
            collected_data: Dictionary of collected field values

        Returns:
            Tuple of (is_valid, missing_fields)
        """
        if not self.required_fields:
            return True, []

        missing_fields = []
        for field_def in self.required_fields:
            if field_def.get("required", True):
                field_name = field_def.get("field")
                if not collected_data.get(field_name):
                    missing_fields.append(field_def)

        return len(missing_fields) == 0, missing_fields