# ============================================================================
# FILE 1: app/services/appointment_query_service.py
# Pure business logic - no FastAPI dependencies, fully testable
# ============================================================================
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any
from uuid import UUID

from app.models.appointment import Appointment


class AppointmentService:
    """Service layer for appointment-related business logic."""

    @staticmethod
    def list_appointments(
            db: Session,
            business_id: UUID,
            start_date: Optional[date] = None,
            end_date: Optional[date] = None,
            status: Optional[str] = None,
            customer_phone: Optional[str] = None,
            service_type: Optional[str] = None,
            skip: int = 0,
            limit: int = 50
    ) -> Dict[str, Any]:
        """Get paginated list of appointments with filters."""
        query = db.query(Appointment).filter(Appointment.business_id == business_id)

        if start_date:
            query = query.filter(Appointment.appointment_datetime >= datetime.combine(start_date, datetime.min.time()))
        if end_date:
            query = query.filter(Appointment.appointment_datetime < datetime.combine(end_date, datetime.max.time()))
        if status:
            query = query.filter(Appointment.status == status)
        if customer_phone:
            query = query.filter(Appointment.customer_phone == customer_phone)
        if service_type:
            query = query.filter(Appointment.service_type == service_type)

        query = query.order_by(Appointment.appointment_datetime.asc())
        total = query.count()
        appointments = query.offset(skip).limit(limit).all()

        return {
            "business_id": str(business_id),
            "total_appointments": total,
            "page": {
                "skip": skip,
                "limit": limit,
                "total_pages": (total + limit - 1) // limit if total > 0 else 0
            },
            "filters": {
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "status": status,
                "customer_phone": customer_phone,
                "service_type": service_type
            },
            "appointments": [AppointmentService._serialize_appointment(appt) for appt in appointments]
        }

    @staticmethod
    def get_appointment_by_id(
            db: Session,
            business_id: UUID,
            appointment_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """Get a single appointment by ID. Returns None if not found."""
        appointment = db.query(Appointment).filter(
            Appointment.id == appointment_id,
            Appointment.business_id == business_id
        ).first()

        if not appointment:
            return None

        return AppointmentService._serialize_appointment(appointment, detailed=True)

    @staticmethod
    def get_todays_appointments(
            db: Session,
            business_id: UUID
    ) -> Dict[str, Any]:
        """Get all appointments scheduled for today."""
        today = date.today()

        appointments = db.query(Appointment).filter(
            Appointment.business_id == business_id,
            Appointment.appointment_datetime >= datetime.combine(today, datetime.min.time()),
            Appointment.appointment_datetime < datetime.combine(today, datetime.max.time()),
            Appointment.status.in_(["scheduled", "confirmed"])
        ).order_by(Appointment.appointment_datetime.asc()).all()

        return {
            "business_id": str(business_id),
            "date": today.isoformat(),
            "total_appointments": len(appointments),
            "appointments": [
                {
                    "id": str(appt.id),
                    "customer_name": appt.customer_name,
                    "customer_phone": appt.customer_phone,
                    "service_type": appt.service_type,
                    "appointment_datetime": appt.appointment_datetime.isoformat(),
                    "duration_minutes": appt.duration_minutes,
                    "status": appt.status,
                    "notes": appt.notes
                }
                for appt in appointments
            ]
        }

    @staticmethod
    def get_week_appointments(
            db: Session,
            business_id: UUID
    ) -> Dict[str, Any]:
        """Get all appointments scheduled for the next 7 days."""
        today = datetime.now()
        week_end = datetime.now().replace(hour=23, minute=59, second=59) + timedelta(days=7)

        appointments = db.query(Appointment).filter(
            Appointment.business_id == business_id,
            Appointment.appointment_datetime >= today,
            Appointment.appointment_datetime <= week_end,
            Appointment.status.in_(["scheduled", "confirmed"])
        ).order_by(Appointment.appointment_datetime.asc()).all()

        return {
            "business_id": str(business_id),
            "period": {
                "start": today.date().isoformat(),
                "end": week_end.date().isoformat()
            },
            "total_appointments": len(appointments),
            "appointments": [
                {
                    "id": str(appt.id),
                    "customer_name": appt.customer_name,
                    "customer_phone": appt.customer_phone,
                    "service_type": appt.service_type,
                    "appointment_datetime": appt.appointment_datetime.isoformat(),
                    "duration_minutes": appt.duration_minutes,
                    "status": appt.status
                }
                for appt in appointments
            ]
        }

    @staticmethod
    def search_appointments_by_phone(
            db: Session,
            business_id: UUID,
            phone: str,
            skip: int = 0,
            limit: int = 20
    ) -> Dict[str, Any]:
        """Search for all appointments for a specific phone number."""
        query = db.query(Appointment).filter(
            Appointment.business_id == business_id,
            Appointment.customer_phone == phone
        ).order_by(desc(Appointment.appointment_datetime))

        total = query.count()
        appointments = query.offset(skip).limit(limit).all()

        return {
            "business_id": str(business_id),
            "phone": phone,
            "total_appointments": total,
            "page": {
                "skip": skip,
                "limit": limit,
                "total_pages": (total + limit - 1) // limit if total > 0 else 0
            },
            "appointments": [
                {
                    "id": str(appt.id),
                    "customer_name": appt.customer_name,
                    "service_type": appt.service_type,
                    "appointment_datetime": appt.appointment_datetime.isoformat(),
                    "duration_minutes": appt.duration_minutes,
                    "status": appt.status,
                    "booking_source": appt.booking_source,
                    "created_at": appt.created_at.isoformat()
                }
                for appt in appointments
            ]
        }

    @staticmethod
    def get_appointment_stats(
            db: Session,
            business_id: UUID,
            start_date: Optional[date] = None,
            end_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """Calculate appointment statistics for a business."""
        query = db.query(Appointment).filter(Appointment.business_id == business_id)

        if start_date:
            query = query.filter(Appointment.appointment_datetime >= datetime.combine(start_date, datetime.min.time()))
        if end_date:
            query = query.filter(Appointment.appointment_datetime < datetime.combine(end_date, datetime.max.time()))

        appointments = query.all()

        if not appointments:
            return {
                "business_id": str(business_id),
                "period": {
                    "start": start_date.isoformat() if start_date else None,
                    "end": end_date.isoformat() if end_date else None
                },
                "total_appointments": 0,
                "by_status": {},
                "by_service": {},
                "by_source": {},
                "sync_stats": {},
                "unique_customers": 0,
                "avg_duration_minutes": None
            }

        # Calculate statistics
        total_appointments = len(appointments)

        by_status = {}
        for appt in appointments:
            status = appt.status or "unknown"
            by_status[status] = by_status.get(status, 0) + 1

        by_service = {}
        for appt in appointments:
            service = appt.service_type or "unknown"
            by_service[service] = by_service.get(service, 0) + 1

        by_source = {}
        for appt in appointments:
            source = appt.booking_source or "unknown"
            by_source[source] = by_source.get(source, 0) + 1

        sync_stats = {
            "synced": sum(1 for appt in appointments if appt.sync_status == "synced"),
            "pending": sum(1 for appt in appointments if appt.sync_status == "pending"),
            "failed": sum(1 for appt in appointments if appt.sync_status == "failed"),
            "sync_disabled": sum(1 for appt in appointments if appt.sync_status == "sync_disabled")
        }

        unique_customers = len(set(appt.customer_phone for appt in appointments if appt.customer_phone))

        durations = [appt.duration_minutes for appt in appointments if appt.duration_minutes]
        avg_duration = sum(durations) / len(durations) if durations else None

        return {
            "business_id": str(business_id),
            "period": {
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None
            },
            "total_appointments": total_appointments,
            "by_status": by_status,
            "by_service": by_service,
            "by_source": by_source,
            "sync_stats": sync_stats,
            "unique_customers": unique_customers,
            "avg_duration_minutes": round(avg_duration, 2) if avg_duration else None
        }

    @staticmethod
    def _serialize_appointment(appointment: Appointment, detailed: bool = False) -> Dict[str, Any]:
        """Convert Appointment model to dictionary."""
        base = {
            "id": str(appointment.id),
            "conversation_id": str(appointment.conversation_id),
            "customer_phone": appointment.customer_phone,
            "customer_name": appointment.customer_name,
            "customer_email": appointment.customer_email,
            "service_type": appointment.service_type,
            "appointment_datetime": appointment.appointment_datetime.isoformat(),
            "duration_minutes": appointment.duration_minutes,
            "status": appointment.status,
            "booking_source": appointment.booking_source,
            "notes": appointment.notes,
            "sync_status": appointment.sync_status,
            "external_event_id": appointment.external_event_id,
            "external_event_url": appointment.external_event_url,
            "created_at": appointment.created_at.isoformat(),
            "updated_at": appointment.updated_at.isoformat()
        }

        if detailed:
            base.update({
                "calendar_integration_id": str(
                    appointment.calendar_integration_id) if appointment.calendar_integration_id else None,
                "sync_attempts": appointment.sync_attempts,
                "last_sync_error": appointment.last_sync_error,
                "last_synced_at": appointment.last_synced_at.isoformat() if appointment.last_synced_at else None,
                "reminder_sent_at": appointment.reminder_sent_at.isoformat() if appointment.reminder_sent_at else None,
                "confirmation_sent_at": appointment.confirmation_sent_at.isoformat() if appointment.confirmation_sent_at else None,
                "cancelled_at": appointment.cancelled_at.isoformat() if appointment.cancelled_at else None,
                "cancellation_reason": appointment.cancellation_reason
            })

        return base

