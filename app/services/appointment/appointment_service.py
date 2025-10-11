# ============================================================================
# app/services/appointment/appointment_service.py
# ============================================================================
"""Service for managing appointments"""
from uuid import uuid4

from app.models.appointment import Appointment
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

class AppointmentService:
    """Handles appointment operations"""

    @staticmethod
    def create_appointment(
            db: Session,
            conversation_id: str,
            business_id: str,
            customer_phone: str,
            customer_name: str,
            service_type: str,
            appointment_datetime: datetime,
            duration_minutes: int = 60,
            customer_email: Optional[str] = None,
            notes: str = ""
    ) -> Appointment:
        """Create a new appointment"""
        appointment = Appointment(
            id=str(uuid4()),
            conversation_id=conversation_id,
            business_id=business_id,
            customer_phone=customer_phone,
            customer_name=customer_name,
            customer_email=customer_email,
            service_type=service_type,
            appointment_datetime=appointment_datetime,
            duration_minutes=duration_minutes,
            status="tentative",
            notes=notes,
        )

        db.add(appointment)
        db.commit()
        db.refresh(appointment)
        return appointment

