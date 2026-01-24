from sqlalchemy import Column, String, DateTime, Boolean, Integer, ForeignKey, Index, Numeric, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
import enum
from app.models.base import Base


class ConversationStatus(enum.Enum):
    """Conversation lifecycle states"""
    active = "active"  # Ongoing conversation
    soft_close = "soft_close"  # Natural ending detected, grace period active
    hard_close = "hard_close"  # Definitively complete (booking made or finalized after grace period)
    dropped = "dropped"  # Abandoned/ghosted mid-conversation


class ConversationMetrics(Base):
    __tablename__ = "conversation_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign keys
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False, unique=True)
    call_event_id = Column(UUID(as_uuid=True), ForeignKey("call_events.id"), nullable=False)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False)

    # Core engagement metrics
    customer_responded = Column(Boolean, default=False)
    conversation_completed = Column(Boolean, default=False)  # Keep for backward compatibility

    # NEW: Conversation lifecycle tracking
    conversation_status = Column(
        Enum(ConversationStatus),
        default=ConversationStatus.active,
        nullable=False
    )
    soft_close_at = Column(DateTime(timezone=True), nullable=True)
    hard_close_at = Column(DateTime(timezone=True), nullable=True)

    # Booking outcome
    booking_initiated = Column(Boolean, default=False)
    booking_initiated_at = Column(DateTime(timezone=True), nullable=True)
    booking_created = Column(Boolean, default=False)
    booking_abandoned = Column(Boolean, default=False)
    appointment_id = Column(UUID(as_uuid=True), ForeignKey("appointments.id"), nullable=True)

    # Timing metrics
    outreach_sent_at = Column(DateTime(timezone=True))
    first_response_at = Column(DateTime(timezone=True))
    conversation_ended_at = Column(DateTime(timezone=True))
    booking_completed_at = Column(DateTime(timezone=True))

    # Interaction metrics
    total_messages = Column(Integer, default=0)
    customer_messages = Column(Integer, default=0)
    bot_messages = Column(Integer, default=0)

    # Drop-off tracking
    last_flow_state = Column(String(50))
    dropped_off = Column(Boolean, default=False)  # Keep for backward compatibility

    # Calculated fields
    response_time_seconds = Column(Integer)
    conversation_duration_seconds = Column(Integer)
    time_to_booking_seconds = Column(Integer)

    # Revenue tracking
    estimated_revenue = Column(Numeric(10, 2))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Indexes
    __table_args__ = (
        Index('ix_metrics_business_created', 'business_id', 'created_at'),
        Index('ix_metrics_booking_created', 'business_id', 'booking_created'),
        Index('ix_metrics_customer_responded', 'business_id', 'customer_responded'),
        Index('ix_metrics_conversation_status', 'business_id', 'conversation_status'),  # NEW
    )