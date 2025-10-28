# ===== app/models/webhook_endpoint.py =====
from sqlalchemy import Column, String, DateTime, Boolean, JSON, Integer, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.models.base import Base


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False)

    # Endpoint configuration
    url = Column(String(500), nullable=False)
    description = Column(String(500))

    # Events to listen for
    enabled_events = Column(JSON, default=list)  # ["call.missed", "booking.created", "*"]

    # Security
    secret = Column(String(128), nullable=False)  # For HMAC signature verification

    # Status
    is_active = Column(Boolean, default=True)

    # Health tracking
    consecutive_failures = Column(Integer, default=0)
    last_success_at = Column(DateTime(timezone=True))
    last_failure_at = Column(DateTime(timezone=True))
    last_failure_reason = Column(String(500))

    # Auto-disable after N failures
    max_consecutive_failures = Column(Integer, default=10)
    auto_disabled_at = Column(DateTime(timezone=True))

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('ix_webhook_endpoints_business_active', 'business_id', 'is_active'),
    )