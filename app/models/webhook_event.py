# ===== app/models/webhook_event.py =====
from sqlalchemy import Column, String, DateTime, Integer, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid
from app.models.base import Base


class WebhookEvent(Base):
    """Log of all webhook delivery attempts"""
    __tablename__ = "webhook_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    webhook_endpoint_id = Column(UUID(as_uuid=True), ForeignKey("webhook_endpoints.id"), nullable=False)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False)

    # Event details
    event_type = Column(String(50), nullable=False)  # "call.missed", "booking.created"
    event_data = Column(JSONB, nullable=False)  # The actual payload sent

    # Delivery tracking
    status = Column(String(20), nullable=False)  # "pending", "delivered", "failed", "retrying"
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=5)

    # Response tracking
    response_status_code = Column(Integer)
    response_body = Column(Text)
    response_time_ms = Column(Integer)

    # Error tracking
    error_message = Column(Text)
    last_attempt_at = Column(DateTime(timezone=True))
    next_retry_at = Column(DateTime(timezone=True))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    delivered_at = Column(DateTime(timezone=True))
    failed_at = Column(DateTime(timezone=True))

    __table_args__ = (
        Index('ix_webhook_events_status', 'status', 'next_retry_at'),
        Index('ix_webhook_events_business_created', 'business_id', 'created_at'),
        Index('ix_webhook_events_endpoint_status', 'webhook_endpoint_id', 'status'),
    )
