# app/services/ai/tools/booking_tools.py
"""Tools for booking appointments and checking availability"""
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)


class BookingTools:
    """Appointment booking and slot availability tools"""

    @staticmethod
    def get_function_definitions() -> List[Dict]:
        """Return function definitions for OpenAI function calling"""
        return [
            {
                "name": "get_available_slots",
                "description": "Get available appointment slots for a service. The system automatically uses the correct duration based on booking type (consultation_duration for consultation_required services, service duration for direct booking).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "business_id": {
                            "type": "string",
                            "description": "The business ID"
                        },
                        "service": {
                            "type": "string",
                            "description": "Service name (not ID)"
                        },
                        "start_date": {
                            "type": "string",
                            "description": "Start date/datetime in ISO format (e.g., '2025-10-08' for Oct 8, or '2025-10-08T14:00:00' for specific time)"
                        },
                        "end_date": {
                            "type": "string",
                            "description": "End date/datetime in ISO format. If omitted, returns slots for just the start_date."
                        },
                        "limit": {
                            "type": "integer",
                            "default": 20,
                            "description": "Maximum number of slots to return"
                        }
                    },
                    "required": ["business_id", "service"]
                }
            },
            {
                "name": "book_appointment",
                "description": "Book an appointment or store lead based on service booking_type. CRITICAL: Only call after validate_service_fields confirms all fields collected. For consultation_required services, this books the discovery call. For lead_only services, this stores the lead without creating a calendar booking.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "business_id": {
                            "type": "string",
                            "description": "The business ID"
                        },
                        "conversation_id": {
                            "type": "string",
                            "description": "The conversation ID"
                        },
                        "customer_name": {
                            "type": "string",
                            "description": "Customer's full name"
                        },
                        "customer_email": {
                            "type": "string",
                            "description": "Customer's email"
                        },
                        "customer_phone": {
                            "type": "string",
                            "description": "Customer's phone"
                        },
                        "service_type": {
                            "type": "string",
                            "description": "Service name"
                        },
                        "appointment_datetime": {
                            "type": "string",
                            "description": "Appointment date/time in ISO format"
                        },
                        "notes": {
                            "type": "string",
                            "description": "Additional notes or comments"
                        }
                    },
                    "required": [
                        "business_id",
                        "conversation_id",
                        "customer_name",
                        "customer_email",
                        "customer_phone",
                        "service_type",
                        "appointment_datetime"
                    ]
                }
            }
        ]

    @staticmethod
    async def get_available_slots(
        db: Session,
        business_id: str,
        service: str,
        duration_minutes: int = 30,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict]:
        """Fetch available slots for scheduling"""
        try:
            from app.models.business.service import Service
            from app.models.appointment.calendar_integration import CalendarIntegration

            # Get the service to determine correct duration
            service_obj = db.query(Service).filter(
                Service.business_id == business_id,
                Service.name == service,
                Service.is_active == True
            ).first()

            # Use service's get_booking_duration() if service found
            if service_obj:
                duration_minutes = service_obj.get_booking_duration()
                logger.info(
                    f"📅 Using {duration_minutes}min duration for {service} "
                    f"(booking_type: {service_obj.booking_type.value})"
                )

            # Determine start_date
            if start_date:
                try:
                    start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    if start_dt.tzinfo is None:
                        start_dt = start_dt.replace(tzinfo=timezone.utc)
                    # If just a date (no time), start from business open
                    if start_dt.hour == 0 and start_dt.minute == 0:
                        start_dt = start_dt.replace(hour=8, minute=0)
                except ValueError:
                    logger.error(f"Invalid start_date format: {start_date}")
                    return []
            else:
                # Default: start from next available time
                now = datetime.now(timezone.utc)
                if now.hour >= 17:  # Past business hours
                    start_dt = (now + timedelta(days=1)).replace(
                        hour=8, minute=0, second=0, microsecond=0
                    )
                else:
                    # Round up to next 30-min interval
                    start_dt = now.replace(second=0, microsecond=0)
                    minutes = (start_dt.minute // 30 + 1) * 30
                    if minutes >= 60:
                        start_dt = start_dt.replace(hour=start_dt.hour + 1, minute=0)
                    else:
                        start_dt = start_dt.replace(minute=minutes)

            # Determine end_date
            if end_date:
                try:
                    end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    if end_dt.tzinfo is None:
                        end_dt = end_dt.replace(tzinfo=timezone.utc)
                    # If just a date, search until end of day
                    if end_dt.hour == 0 and end_dt.minute == 0:
                        end_dt = end_dt.replace(hour=23, minute=59)
                except ValueError:
                    logger.error(f"Invalid end_date format: {end_date}")
                    return []
            else:
                # If specific date requested, just that day; otherwise next 3 days
                if start_date:
                    end_dt = start_dt.replace(hour=23, minute=59, second=59)
                else:
                    end_dt = start_dt + timedelta(days=3)

            logger.info(f"📅 Fetching slots from {start_dt.isoformat()} to {end_dt.isoformat()}")

            # Get calendar integration
            integration = db.query(CalendarIntegration).filter_by(
                business_id=business_id,
                is_active=True,
                is_primary=True
            ).first()

            if not integration:
                logger.warning(f"No active calendar integration for business {business_id}")
                return []

            # Get calendar service based on provider
            if integration.provider == 'google':
                from app.services.calendar.google_calendar_service import GoogleCalendarService
                calendar_service = GoogleCalendarService()
            elif integration.provider == 'outlook':
                from app.services.calendar.outlook_service import OutlookCalendarService
                calendar_service = OutlookCalendarService()
            else:
                logger.warning(f"Unknown calendar provider: {integration.provider}")
                return []

            # Fetch slots
            slots = await calendar_service.get_available_slots(
                integration=integration,
                db=db,
                start_date=start_dt,
                end_date=end_dt,
                duration_minutes=duration_minutes
            )

            logger.info(f"✅ Found {len(slots)} slots, returning up to {limit}")

            limited_slots = slots[:limit] if limit else slots

            # Format slots for display
            display_slots = []
            for slot in limited_slots:
                if isinstance(slot["start"], str):
                    slot_dt = datetime.fromisoformat(slot["start"].replace('Z', '+00:00'))
                else:
                    slot_dt = slot["start"]

                display_slots.append({
                    "start_time": slot_dt.isoformat(),
                    "end_time": slot["end"] if isinstance(slot["end"], str) else slot["end"].isoformat(),
                    "display_time": slot_dt.strftime("%A, %B %d at %I:%M %p")
                })

            return display_slots

        except Exception as e:
            logger.error(f"Error fetching available slots: {e}", exc_info=True)
            return []

    @staticmethod
    async def book_appointment(
        db: Session,
        business_id: str,
        conversation_id: str,
        customer_name: str,
        customer_email: str,
        customer_phone: str,
        service_type: str,
        appointment_datetime: str,
        notes: str = ""
    ) -> Dict:
        """Book an appointment - handles all booking types"""
        try:
            from app.models.business.service import Service
            from app.models.appointment.appointment import Appointment
            from app.models.appointment.calendar_integration import CalendarIntegration
            from app.services.conversation.conversation_state_service import ConversationStateService

            # Get the service
            service = db.query(Service).filter(
                Service.business_id == business_id,
                Service.name == service_type,
                Service.is_active == True
            ).first()

            if not service:
                return {
                    "success": False,
                    "message": f"Service '{service_type}' not found"
                }

            # Get all collected fields (standard + custom)
            conv_state = ConversationStateService.get_or_create_state(
                db=db,
                conversation_id=conversation_id
            )

            customer_info = conv_state.state_data.get("customer_info", {})
            service_context = conv_state.state_data.get("service_context", {})
            collected_fields = service_context.get("collected_fields", {})

            all_collected_data = {
                "name": customer_info.get("name") or customer_name,
                "email": customer_info.get("email") or customer_email,
                "phone": customer_info.get("phone") or customer_phone,
                **collected_fields
            }

            # Validate required fields
            is_valid, missing_fields = service.validate_required_fields(all_collected_data)

            if not is_valid:
                missing_names = [f.get("label", f.get("field")) for f in missing_fields]
                logger.warning(f"⚠️ Cannot book - missing fields: {missing_names}")
                return {
                    "success": False,
                    "message": f"Before I can book, I need: {', '.join(missing_names)}"
                }

            # Handle LEAD_ONLY booking type
            if service.booking_type.value == 'lead_only':
                logger.info(f"📋 Lead-only service - storing lead info without booking")

                lead_data = {
                    "business_id": business_id,
                    "service_name": service.name,
                    "customer_name": customer_name,
                    "customer_email": customer_email,
                    "customer_phone": customer_phone,
                    "collected_fields": collected_fields,
                    "created_at": datetime.now(timezone.utc)
                }

                # TODO: Save to leads table or notify owner
                logger.info(f"💼 Lead captured: {lead_data}")

                return {
                    "success": True,
                    "message": f"Thanks {customer_name}! We've received your information about {service.name}. Someone from our team will contact you soon.",
                    "is_lead": True
                }

            # Determine duration and booking notes based on booking type
            if service.booking_type.value == 'consultation_required':
                duration_minutes = service.consultation_duration or 30
                booking_notes = f"Discovery call for {service.name}"
                if notes:
                    booking_notes += f"\n{notes}"
                if collected_fields:
                    booking_notes += f"\n\nCollected info:\n" + "\n".join(
                        [f"{k}: {v}" for k, v in collected_fields.items()]
                    )
            else:
                duration_minutes = service.duration or 30
                booking_notes = notes
                if collected_fields:
                    booking_notes += f"\n\nAdditional info:\n" + "\n".join(
                        [f"{k}: {v}" for k, v in collected_fields.items()]
                    )

            # Parse appointment datetime
            try:
                apt_dt = datetime.fromisoformat(appointment_datetime.replace('Z', '+00:00'))
                if apt_dt.tzinfo is None:
                    apt_dt = apt_dt.replace(tzinfo=timezone.utc)
            except ValueError:
                return {
                    "success": False,
                    "message": "Invalid appointment date/time format"
                }

            # Get calendar integration
            integration = db.query(CalendarIntegration).filter_by(
                business_id=business_id,
                is_active=True,
                is_primary=True
            ).first()

            external_event_id = None
            calendar_integration_id = None

            # Create calendar event if integration exists
            if integration:
                calendar_integration_id = integration.id
                end_dt = apt_dt + timedelta(minutes=duration_minutes)

                if integration.provider == 'google':
                    from app.services.calendar.google_calendar_service import GoogleCalendarService
                    calendar_service = GoogleCalendarService()

                    try:
                        event = await calendar_service.create_event(
                            integration=integration,
                            db=db,
                            event_data={
                                'summary': f"{service_type} - {customer_name}",
                                'start': apt_dt,
                                'end': end_dt,
                                'description': f"Service: {service_type}\nCustomer: {customer_name}\nEmail: {customer_email}\nPhone: {customer_phone}\n\n{booking_notes}"
                            }
                        )
                        external_event_id = event.get('id')
                        logger.info(f"✅ Created calendar event: {external_event_id}")
                    except Exception as e:
                        logger.error(f"Failed to create calendar event: {e}")

            # Create appointment in database
            appointment = Appointment(
                business_id=business_id,
                customer_name=customer_name,
                customer_email=customer_email,
                customer_phone=customer_phone,
                service_type=service_type,
                appointment_datetime=apt_dt,
                duration_minutes=duration_minutes,
                status='scheduled',
                notes=booking_notes,
                external_event_id=external_event_id,
                calendar_integration_id=calendar_integration_id,
                sync_status='synced' if external_event_id else 'not_synced'
            )

            db.add(appointment)

            booking_type_label = "discovery call" if service.booking_type.value == 'consultation_required' else "appointment"

            logger.info(
                f"✅ Booked {booking_type_label} for {customer_name} - "
                f"{service_type} at {apt_dt.isoformat()}"
            )

            return {
                "success": True,
                "message": f"Perfect! Your {booking_type_label} for {service_type} is confirmed for {apt_dt.strftime('%A, %B %d at %I:%M %p')}.",
                "appointment_id": str(appointment.id),
                "is_consultation": service.booking_type.value == 'consultation_required'
            }

        except Exception as e:
            logger.error(f"Error booking appointment: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "message": "Sorry, there was an error booking your appointment. Please try again."
            }