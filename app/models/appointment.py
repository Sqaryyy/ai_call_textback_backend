# ===== app/models/appointment.py =====
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from .business import Base
import uuid


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # References
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False)
    calendar_integration_id = Column(UUID(as_uuid=True), ForeignKey("calendar_integrations.id"), nullable=True)

    # Customer info
    customer_phone = Column(String, nullable=False)
    customer_name = Column(String, nullable=True)
    customer_email = Column(String, nullable=True)

    # Appointment details
    service_type = Column(String, nullable=False)
    appointment_datetime = Column(DateTime(timezone=True), nullable=False)
    duration_minutes = Column(Integer, default=30)
    notes = Column(Text, nullable=True)

    # Status tracking
    status = Column(String, default="scheduled")  # scheduled, confirmed, cancelled, completed, no_show
    booking_source = Column(String, default="sms")  # sms, web, api, manual

    # Calendar sync
    external_event_id = Column(String, nullable=True)
    external_event_url = Column(String, nullable=True)
    sync_status = Column(String, default="pending")  # pending, synced, failed, sync_disabled
    sync_attempts = Column(Integer, default=0)
    last_sync_error = Column(Text, nullable=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)

    # Reminders & notifications
    reminder_sent_at = Column(DateTime(timezone=True), nullable=True)
    confirmation_sent_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancellation_reason = Column(Text, nullable=True)
