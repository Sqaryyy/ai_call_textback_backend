from sqlalchemy import Column, String, DateTime, JSON, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.models.base import Base

class CallEvent(Base):
    __tablename__ = "call_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False)

    # Add this new column for Twilio Call SID
    twilio_call_sid = Column(String(34), unique=True, nullable=False, index=True)

    caller_phone = Column(String(20), nullable=False)
    business_phone = Column(String(20), nullable=False)
    call_status = Column(String(50), nullable=False)
    direction = Column(String(20), nullable=False)
    caller_location = Column(JSON, default=dict)
    caller_name = Column(String(200))
    duration = Column(String(10))
    recording_url = Column(Text)
    call_metadata = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Add index for common queries
    __table_args__ = (
        Index('ix_call_events_business_created', 'business_id', 'created_at'),
    )