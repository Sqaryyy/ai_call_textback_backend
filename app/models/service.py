# app/models/service.py
"""
Service Model - Structured service definitions
Each service belongs to one business and contains definitive service details.
"""
from sqlalchemy import Column, String, Numeric, Integer, ForeignKey, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.models.base import Base


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

    # Duration in minutes (nullable)
    duration = Column(Integer, nullable=True)

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
    business = relationship("Business", backref="services")
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