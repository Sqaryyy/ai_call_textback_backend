# app/services/ai/tools/appointment_tools.py
"""Tools for managing existing appointments"""
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)


class AppointmentTools:
    """Appointment management tools (view, cancel, reschedule)"""

    @staticmethod
    def get_function_definitions() -> List[Dict]:
        """Return function definitions for OpenAI function calling"""
        return [
            {
                "name": "get_customer_appointments",
                "description": "Retrieve appointments for a customer by phone number. Use when customer asks about their appointments or wants to cancel/reschedule. The customer_phone is automatically provided.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "customer_phone": {
                            "type": "string",
                            "description": "Customer's phone number (auto-filled from conversation)"
                        },
                        "business_id": {
                            "type": "string",
                            "description": "The business ID"
                        },
                        "include_past": {
                            "type": "boolean",
                            "default": False,
                            "description": "Include past appointments"
                        }
                    },
                    "required": ["customer_phone", "business_id"]
                }
            },
            {
                "name": "cancel_appointment",
                "description": "Cancel an existing appointment. Use when customer wants to cancel. The customer_phone is automatically provided from the conversation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "appointment_id": {
                            "type": "string",
                            "description": "The appointment ID to cancel"
                        },
                        "customer_phone": {
                            "type": "string",
                            "description": "Customer's phone number (auto-filled from conversation)"
                        },
                        "reason": {
                            "type": "string",
                            "description": "Optional cancellation reason"
                        }
                    },
                    "required": ["appointment_id", "customer_phone"]
                }
            },
            {
                "name": "reschedule_appointment",
                "description": "Reschedule an existing appointment to a new date/time. Use when customer wants to change their appointment time. The customer_phone is automatically provided.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "appointment_id": {
                            "type": "string",
                            "description": "The appointment ID to reschedule"
                        },
                        "customer_phone": {
                            "type": "string",
                            "description": "Customer's phone number (auto-filled from conversation)"
                        },
                        "new_datetime": {
                            "type": "string",
                            "description": "New appointment date/time in ISO format"
                        },
                        "reason": {
                            "type": "string",
                            "description": "Optional reason for rescheduling"
                        }
                    },
                    "required": ["appointment_id", "customer_phone", "new_datetime"]
                }
            }
        ]

    @staticmethod
    async def get_customer_appointments(
            db: Session,
            customer_phone: str,
            business_id: str,
            include_past: bool = False
    ) -> List[Dict]:
        """Fetch appointments for a customer by phone number"""
        try:
            from app.models.appointment.appointment import Appointment

            query = db.query(Appointment).filter(
                Appointment.customer_phone == customer_phone,
                Appointment.business_id == business_id
            )

            if not include_past:
                query = query.filter(
                    Appointment.status.in_(['scheduled', 'confirmed'])
                )
                query = query.filter(
                    Appointment.appointment_datetime >= datetime.now(timezone.utc)
                )

            appointments = query.order_by(Appointment.appointment_datetime).all()

            result = []
            for apt in appointments:
                end_time = apt.appointment_datetime + timedelta(minutes=apt.duration_minutes)
                result.append({
                    "id": str(apt.id),
                    "service": apt.service_type,
                    "start_time": apt.appointment_datetime.isoformat(),
                    "end_time": end_time.isoformat(),
                    "status": apt.status,
                    "customer_name": apt.customer_name,
                    "display_time": apt.appointment_datetime.strftime("%A, %B %d at %I:%M %p")
                })

            logger.info(f"📅 Found {len(result)} appointments for phone {customer_phone}")
            return result

        except Exception as e:
            logger.error(f"Error fetching customer appointments: {e}")
            return []

    @staticmethod
    async def cancel_appointment(
            db: Session,
            appointment_id: str,
            customer_phone: str,
            reason: Optional[str] = None
    ) -> Dict:
        """Cancel an appointment"""
        try:
            from app.models.appointment.appointment import Appointment
            from app.models.appointment.calendar_integration import CalendarIntegration

            appointment = db.query(Appointment).filter(
                Appointment.id == appointment_id,
                Appointment.customer_phone == customer_phone
            ).first()

            if not appointment:
                return {
                    "success": False,
                    "message": "Appointment not found or doesn't belong to this phone number"
                }

            if appointment.status == 'cancelled':
                return {
                    "success": False,
                    "message": "This appointment is already cancelled"
                }

            # Update appointment status
            appointment.status = 'cancelled'

            cancellation_note = f"\n[Cancelled on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}]"
            if reason:
                cancellation_note += f" Reason: {reason}"
            appointment.notes = (appointment.notes or "") + cancellation_note


            # Delete from calendar if synced
            if appointment.external_event_id and appointment.calendar_integration_id:
                integration = db.query(CalendarIntegration).filter_by(
                    id=appointment.calendar_integration_id,
                    is_active=True
                ).first()

                if integration and integration.provider == 'google':
                    from app.services.calendar.google_calendar_service import GoogleCalendarService
                    calendar_service = GoogleCalendarService()

                    try:
                        await calendar_service.delete_event(
                            integration=integration,
                            db=db,
                            event_id=appointment.external_event_id
                        )
                        appointment.sync_status = "deleted"

                        logger.info(f"✅ Deleted calendar event for cancelled appointment")
                    except Exception as e:
                        logger.error(f"Failed to delete calendar event: {e}")

            logger.info(f"✅ Cancelled appointment {appointment_id}")

            return {
                "success": True,
                "message": f"Your {appointment.service_type} appointment on {appointment.appointment_datetime.strftime('%A, %B %d at %I:%M %p')} has been cancelled.",
                "action_completed": True
            }

        except Exception as e:

            logger.error(f"Error cancelling appointment: {e}")
            return {
                "success": False,
                "message": "Failed to cancel appointment. Please try again or contact us directly."
            }

    @staticmethod
    async def reschedule_appointment(
            db: Session,
            appointment_id: str,
            customer_phone: str,
            new_datetime: str,
            reason: Optional[str] = None
    ) -> Dict:
        """Reschedule an appointment"""
        try:
            from app.models.appointment.appointment import Appointment
            from app.models.appointment.calendar_integration import CalendarIntegration

            appointment = db.query(Appointment).filter(
                Appointment.id == appointment_id,
                Appointment.customer_phone == customer_phone
            ).first()

            if not appointment:
                return {
                    "success": False,
                    "message": "Appointment not found or doesn't belong to this phone number"
                }

            if appointment.status == 'cancelled':
                return {
                    "success": False,
                    "message": "Cannot reschedule a cancelled appointment. Please book a new one."
                }

            # Parse new datetime
            try:
                new_start = datetime.fromisoformat(new_datetime.replace('Z', '+00:00'))
                if new_start.tzinfo is None:
                    new_start = new_start.replace(tzinfo=timezone.utc)
            except ValueError:
                return {
                    "success": False,
                    "message": "Invalid date/time format"
                }

            duration_minutes = appointment.duration_minutes
            new_end = new_start + timedelta(minutes=duration_minutes)

            # Check availability using BookingTools
            from app.services.ai.tools.booking_tools import BookingTools

            check_slots = await BookingTools.get_available_slots(
                db=db,
                business_id=appointment.business_id,
                service=appointment.service_type,
                start_date=new_start.isoformat(),
                end_date=new_end.isoformat(),
                duration_minutes=duration_minutes
            )

            is_available = any(
                datetime.fromisoformat(slot['start_time'].replace('Z', '+00:00')) == new_start
                for slot in check_slots
            )

            if not is_available:
                return {
                    "success": False,
                    "message": "The requested time slot is not available. Please choose another time."
                }

            old_time = appointment.appointment_datetime.strftime('%A, %B %d at %I:%M %p')

            # Update appointment
            appointment.appointment_datetime = new_start

            reschedule_note = f"\n[Rescheduled from {old_time} on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}]"
            if reason:
                reschedule_note += f" Reason: {reason}"
            appointment.notes = (appointment.notes or "") + reschedule_note



            # Update calendar event if synced
            if appointment.external_event_id and appointment.calendar_integration_id:
                integration = db.query(CalendarIntegration).filter_by(
                    id=appointment.calendar_integration_id,
                    is_active=True
                ).first()

                if integration and integration.provider == 'google':
                    from app.services.calendar.google_calendar_service import GoogleCalendarService
                    calendar_service = GoogleCalendarService()

                    try:
                        await calendar_service.update_event(
                            integration=integration,
                            db=db,
                            event_id=appointment.external_event_id,
                            event_data={
                                'start': new_start,
                                'end': new_end,
                                'description': f"Service: {appointment.service_type}\nCustomer: {appointment.customer_name}\nPhone: {appointment.customer_phone}\n{appointment.notes or ''}"
                            }
                        )
                        appointment.sync_status = "synced"
                        appointment.last_synced_at = datetime.now(timezone.utc)

                        logger.info(f"✅ Updated calendar event for rescheduled appointment")
                    except Exception as e:
                        logger.error(f"Failed to update calendar event: {e}")

            logger.info(f"✅ Rescheduled appointment {appointment_id}")

            return {
                "success": True,
                "message": f"Your appointment has been rescheduled from {old_time} to {new_start.strftime('%A, %B %d at %I:%M %p')}.",
                "action_completed": True
            }

        except Exception as e:

            logger.error(f"Error rescheduling appointment: {e}")
            return {
                "success": False,
                "message": "Failed to reschedule appointment. Please try again or contact us directly."
            }