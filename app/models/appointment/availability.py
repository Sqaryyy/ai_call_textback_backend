# ===== app/models/availability.py =====
from sqlalchemy import Column, String, Integer, Boolean, Time, Date, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.models.base import Base
import uuid


class AvailabilityRule(Base):
    """Business-defined availability rules (fallback when no calendar)"""
    __tablename__ = "availability_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"))

    day_of_week = Column(Integer)  # 0=Monday, 6=Sunday
    start_time = Column(Time)
    end_time = Column(Time)
    slot_duration_minutes = Column(Integer, default=30)
    buffer_time_minutes = Column(Integer, default=0)  # Between appointments

    is_active = Column(Boolean, default=True)


class AvailabilityOverride(Base):
    """Specific date overrides (holidays, time-off, special hours)"""
    __tablename__ = "availability_overrides"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"))

    date = Column(Date)
    is_available = Column(Boolean)  # False = day off
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)
    reason = Column(String, nullable=True)  # "Holiday", "Vacation", etc.
