from sqlalchemy import Column, String, DateTime, Boolean, Integer, ForeignKey, Index, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.models.base import Base


class ConversationMetrics(Base):
    __tablename__ = "conversation_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign keys
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False, unique=True)
    call_event_id = Column(UUID(as_uuid=True), ForeignKey("call_events.id"), nullable=False)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False)

    # Core engagement metrics
    customer_responded = Column(Boolean, default=False)  # Did customer reply to initial outreach?
    conversation_completed = Column(Boolean, default=False)  # Did conversation reach natural end?

    # Booking outcome
    booking_created = Column(Boolean, default=False)
    booking_abandoned = Column(Boolean, default=False)  # Started booking flow but didn't finish
    appointment_id = Column(UUID(as_uuid=True), ForeignKey("appointments.id"), nullable=True)

    # Timing metrics
    outreach_sent_at = Column(DateTime(timezone=True))
    first_response_at = Column(DateTime(timezone=True))  # When customer first replied
    conversation_ended_at = Column(DateTime(timezone=True))
    booking_completed_at = Column(DateTime(timezone=True))

    # Interaction metrics
    total_messages = Column(Integer, default=0)
    customer_messages = Column(Integer, default=0)
    bot_messages = Column(Integer, default=0)

    # Drop-off tracking
    last_flow_state = Column(String(50))  # Where conversation ended
    dropped_off = Column(Boolean, default=False)  # Abandoned mid-conversation

    # Calculated fields (computed on write)
    response_time_seconds = Column(Integer)  # Time from outreach to first response
    conversation_duration_seconds = Column(Integer)  # Total conversation time
    time_to_booking_seconds = Column(Integer)  # Missed call to completed booking

    # Revenue tracking (optional)
    estimated_revenue = Column(Numeric(10, 2))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Indexes for analytics queries
    __table_args__ = (
        Index('ix_metrics_business_created', 'business_id', 'created_at'),
        Index('ix_metrics_booking_created', 'business_id', 'booking_created'),
        Index('ix_metrics_customer_responded', 'business_id', 'customer_responded'),
    )