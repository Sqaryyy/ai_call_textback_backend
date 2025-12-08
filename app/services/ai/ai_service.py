# app/services/ai/ai_service.py - WITH DYNAMIC SERVICE LOADING
"""Service for AI/OpenAI interactions - Services fetched via function calls only"""
import json
from openai import OpenAI
import os
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List
import logging
from app.config.settings import Settings
from app.services.availability.availability_service import AvailabilityService
from app.services.ai.rag_service import RAGService
from app.models.conversation.conversation_state import ConversationState
logger = logging.getLogger(__name__)
settings = Settings()


class AIService:
    """Handles AI chat operations"""

    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.rag_service = RAGService()  # ADD THIS LINE

    async def set_customer_info(
            self,
            db: Session,
            conversation_id: str,
            customer_name: Optional[str] = None,
            customer_email: Optional[str] = None,
            customer_phone: Optional[str] = None
    ) -> Dict:
        """Store customer information in conversation state"""
        try:
            from app.services.conversation.conversation_state_service import ConversationStateService

            conv_state = ConversationStateService.get_or_create_state(
                db=db,
                conversation_id=conversation_id
            )

            # Get existing customer info
            customer_info = conv_state.state_data.get("customer_info", {})

            # Update only provided fields
            if customer_name:
                customer_info["name"] = customer_name
            if customer_email:
                customer_info["email"] = customer_email
            if customer_phone:
                customer_info["phone"] = customer_phone

            # Save updated info
            ConversationStateService.update_state(
                db=db,
                conversation_id=conversation_id,
                state_data={"customer_info": customer_info}
            )

            return {
                "success": True,
                "message": "Customer information stored successfully",
                "customer_info": customer_info
            }
        except Exception as e:
            logger.error(f"Error storing customer info: {e}")
            return {
                "success": False,
                "message": "Failed to store customer information"
            }


    async def get_customer_info(
            self,
            db: Session,
            conversation_id: str
    ) -> Dict:
        """Get known customer information from conversation state"""
        try:
            from app.services.conversation.conversation_state_service import ConversationStateService

            conv_state = ConversationStateService.get_or_create_state(
                db=db,
                conversation_id=conversation_id
            )

            customer_info = conv_state.state_data.get("customer_info", {})

            return {
                "success": True,
                "customer_info": {
                    "name": customer_info.get("name"),
                    "email": customer_info.get("email"),
                    "phone": customer_info.get("phone")
                },
                "has_name": bool(customer_info.get("name")),
                "has_email": bool(customer_info.get("email"))
            }
        except Exception as e:
            logger.error(f"Error fetching customer info: {e}")
            return {
                "success": False,
                "customer_info": {},
                "has_name": False,
                "has_email": False
            }

    async def set_service_field(
            self,
            db: Session,
            conversation_id: str,
            service_id: str,
            field_name: str,
            field_value: str
    ) -> Dict:
        """Store a collected service field value in conversation state"""
        try:
            from app.services.conversation.conversation_state_service import ConversationStateService

            conv_state = ConversationStateService.get_or_create_state(
                db=db,
                conversation_id=conversation_id
            )

            # Get or initialize service_context
            service_context = conv_state.state_data.get("service_context", {})

            # Set the service_id if not already set
            if not service_context.get("interested_service_id"):
                service_context["interested_service_id"] = service_id

            # Get or initialize collected_fields
            collected_fields = service_context.get("collected_fields", {})

            # Store the field value
            collected_fields[field_name] = field_value
            service_context["collected_fields"] = collected_fields

            # Save updated state
            ConversationStateService.update_state(
                db=db,
                conversation_id=conversation_id,
                state_data={"service_context": service_context}
            )

            logger.info(f"✅ Stored field '{field_name}' = '{field_value}' for service {service_id}")

            return {
                "success": True,
                "message": f"Stored {field_name}",
                "collected_fields": collected_fields
            }

        except Exception as e:
            logger.error(f"Error storing service field: {e}")
            return {
                "success": False,
                "message": "Failed to store field"
            }

    async def get_service_fields(
            self,
            db: Session,
            conversation_id: str,
            service_id: str
    ) -> Dict:
        """Get all collected fields for a service and check what's still needed"""
        try:
            from app.services.conversation.conversation_state_service import ConversationStateService
            from app.models.business.service import Service

            # Get conversation state
            conv_state = ConversationStateService.get_or_create_state(
                db=db,
                conversation_id=conversation_id
            )

            service_context = conv_state.state_data.get("service_context", {})
            collected_fields = service_context.get("collected_fields", {})

            # Get the service to check required_fields
            service = db.query(Service).filter(Service.id == service_id).first()

            if not service:
                return {
                    "success": False,
                    "message": "Service not found"
                }

            required_fields = service.required_fields or []

            # Check which fields are missing
            missing_fields = []
            for field_def in required_fields:
                field_name = field_def.get("field")
                if field_def.get("required", True):
                    if not collected_fields.get(field_name):
                        missing_fields.append(field_def)

            all_collected = len(missing_fields) == 0

            logger.info(
                f"📋 Service {service_id}: {len(collected_fields)} fields collected, {len(missing_fields)} missing")

            return {
                "success": True,
                "collected_fields": collected_fields,
                "missing_fields": missing_fields,
                "all_fields_collected": all_collected,
                "service_id": str(service.id),
                "service_name": service.name,
                "booking_type": service.booking_type.value
            }

        except Exception as e:
            logger.error(f"Error getting service fields: {e}")
            return {
                "success": False,
                "message": "Failed to retrieve fields",
                "collected_fields": {},
                "missing_fields": [],
                "all_fields_collected": False
            }

    async def validate_service_fields(
            self,
            db: Session,
            conversation_id: str,
            service_id: str
    ) -> Dict:
        """Validate that all required fields are collected before proceeding with booking/lead capture"""
        try:
            from app.services.conversation.conversation_state_service import ConversationStateService
            from app.models.business.service import Service

            # Get conversation state
            conv_state = ConversationStateService.get_or_create_state(
                db=db,
                conversation_id=conversation_id
            )

            service_context = conv_state.state_data.get("service_context", {})
            collected_fields = service_context.get("collected_fields", {})

            # Get the service
            service = db.query(Service).filter(Service.id == service_id).first()

            if not service:
                return {
                    "valid": False,
                    "message": "Service not found",
                    "missing_fields": []
                }

            # Use the service's validate method
            is_valid, missing_fields = service.validate_required_fields(collected_fields)

            if is_valid:
                logger.info(f"✅ All required fields collected for service {service.name}")
                return {
                    "valid": True,
                    "message": "All required fields collected",
                    "missing_fields": [],
                    "can_proceed": True
                }
            else:
                missing_field_names = [f.get("label", f.get("field")) for f in missing_fields]
                logger.warning(f"⚠️ Missing fields for {service.name}: {missing_field_names}")
                return {
                    "valid": False,
                    "message": f"Still need: {', '.join(missing_field_names)}",
                    "missing_fields": missing_fields,
                    "can_proceed": False
                }

        except Exception as e:
            logger.error(f"Error validating service fields: {e}")
            return {
                "valid": False,
                "message": "Validation error",
                "missing_fields": [],
                "can_proceed": False
            }

    async def get_available_slots(
            self,
            db: Session,
            business_id: str,
            service: str,
            duration_minutes: int = 30,
            start_date: Optional[str] = None,
            end_date: Optional[str] = None,
            limit: int = 20
    ) -> list[dict]:
        """Fetch available slots for AI - now uses correct duration based on booking type"""

        # Get the service to determine correct duration
        from app.models.business.service import Service
        service_obj = db.query(Service).filter(
            Service.business_id == business_id,
            Service.name == service,
            Service.is_active == True
        ).first()

        # Use service's get_booking_duration() if service found, otherwise use provided duration
        if service_obj:
            duration_minutes = service_obj.get_booking_duration()
            logger.info(
                f"📅 Using {duration_minutes}min duration for {service} (booking_type: {service_obj.booking_type.value})")

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
                start_dt = (now + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
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

        try:
            from app.models.appointment.calendar_integration import CalendarIntegration
            integration = db.query(CalendarIntegration).filter_by(
                business_id=business_id,
                is_active=True,
                is_primary=True
            ).first()

            if integration:
                if integration.provider == 'google':
                    from app.services.calendar.google_calendar_service import GoogleCalendarService
                    calendar_service = GoogleCalendarService()
                elif integration.provider == 'outlook':
                    from app.services.calendar.outlook_service import OutlookCalendarService
                    calendar_service = OutlookCalendarService()
                else:
                    logger.warning(f"Unknown calendar provider: {integration.provider}")
                    return []

                slots = await calendar_service.get_available_slots(
                    integration=integration,
                    db=db,
                    start_date=start_dt,
                    end_date=end_dt,
                    duration_minutes=duration_minutes
                )

                logger.info(f"✅ Found {len(slots)} slots, returning up to {limit}")

                limited_slots = slots[:limit] if limit else slots

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
            else:
                logger.warning(f"No active calendar integration for business {business_id}")
                return []

        except Exception as e:
            logger.error(f"Error fetching available slots: {e}", exc_info=True)
            return []

    async def book_appointment(
            self,
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
        """Book an appointment - now validates required fields and handles booking types"""
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

            # Check booking type - LEAD_ONLY doesn't create appointments
            if service.booking_type.value == 'lead_only':
                logger.info(f"📋 Lead-only service - storing lead info without booking")

                # Store lead data (you might want to create a Lead model)
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
                        [f"{k}: {v}" for k, v in collected_fields.items()])
            else:
                duration_minutes = service.duration or 30
                booking_notes = notes
                if collected_fields:
                    booking_notes += f"\n\nAdditional info:\n" + "\n".join(
                        [f"{k}: {v}" for k, v in collected_fields.items()])

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
            db.commit()
            db.refresh(appointment)

            booking_type_label = "discovery call" if service.booking_type.value == 'consultation_required' else "appointment"

            logger.info(f"✅ Booked {booking_type_label} for {customer_name} - {service_type} at {apt_dt.isoformat()}")

            return {
                "success": True,
                "message": f"Perfect! Your {booking_type_label} for {service_type} is confirmed for {apt_dt.strftime('%A, %B %d at %I:%M %p')}.",
                "appointment_id": str(appointment.id),
                "is_consultation": service.booking_type.value == 'consultation_required'
            }

        except Exception as e:
            db.rollback()
            logger.error(f"Error booking appointment: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "message": "Sorry, there was an error booking your appointment. Please try again."
            }

    @staticmethod
    def clear_service_context(
            db: Session,
            conversation_id: str
    ) -> Optional[ConversationState]:
        """Clear service context when customer asks about a different service"""
        state = db.query(ConversationState).filter(
            ConversationState.id == conversation_id
        ).first()

        if not state:
            return None

        # Keep customer_info but clear service_context
        if "service_context" in state.state_data:
            state.state_data = {
                "customer_info": state.state_data.get("customer_info", {}),
                "service_context": {}
            }
            db.commit()
            db.refresh(state)

        return state

    async def get_services(
            self,
            db: Session,
            business_id: str
    ) -> List[Dict]:
        """Fetch list of services offered by the business from Service table"""
        try:
            from app.models.business.service import Service

            # Query active services from the Service table
            services_query = db.query(Service).filter(
                Service.business_id == business_id,
                Service.is_active == True
            ).order_by(Service.display_order, Service.name).all()

            if not services_query:
                logger.warning(f"No services found for business {business_id}")
                return []

            # Format services for AI response
            services = []
            for service in services_query:
                service_data = {
                    "id": str(service.id),
                    "name": service.name,
                    "price": service.formatted_price,
                    "duration_minutes": service.duration if service.duration else 30,
                    "description": service.description or "",
                    "booking_type": service.booking_type.value,  # 'direct', 'consultation_required', 'lead_only'
                    "required_fields": service.required_fields or []
                }

                # Add consultation details if applicable
                if service.booking_type.value == 'consultation_required':
                    service_data["consultation_duration"] = service.consultation_duration
                    service_data["consultation_price"] = (
                        f"${service.consultation_price:.2f}" if service.consultation_price else "Free"
                    )

                services.append(service_data)

            logger.info(
                f"📋 Retrieved {len(services)} services for business {business_id}: {[s['name'] for s in services]}")
            return services

        except Exception as e:
            logger.error(f"Error fetching services for business {business_id}: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def get_customer_appointments(
            self,
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

            return result

        except Exception as e:
            logger.error(f"Error fetching customer appointments: {e}")
            return []

    async def cancel_appointment(
            self,
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

            old_status = appointment.status
            appointment.status = 'cancelled'

            cancellation_note = f"\n[Cancelled on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}]"
            if reason:
                cancellation_note += f" Reason: {reason}"
            appointment.notes = (appointment.notes or "") + cancellation_note

            db.commit()

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
                        db.commit()
                    except Exception as e:
                        logger.error(f"Failed to delete calendar event: {e}")

            return {
                "success": True,
                "message": f"Your {appointment.service_type} appointment on {appointment.appointment_datetime.strftime('%A, %B %d at %I:%M %p')} has been cancelled.",
                "action_completed": True
            }

        except Exception as e:
            db.rollback()
            logger.error(f"Error cancelling appointment: {e}")
            return {
                "success": False,
                "message": "Failed to cancel appointment. Please try again or contact us directly."
            }

    async def reschedule_appointment(
            self,
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

            new_start = datetime.fromisoformat(new_datetime)
            duration_minutes = appointment.duration_minutes
            new_end = new_start + timedelta(minutes=duration_minutes)

            check_slots = await AvailabilityService.get_available_slots(
                db=db,
                business_id=appointment.business_id,
                start_date=new_start,
                end_date=new_end,
                duration_minutes=duration_minutes
            )

            is_available = any(
                datetime.fromisoformat(slot['start']) == new_start
                for slot in check_slots
            )

            if not is_available:
                return {
                    "success": False,
                    "message": "The requested time slot is not available. Please choose another time."
                }

            old_time = appointment.appointment_datetime.strftime('%A, %B %d at %I:%M %p')

            appointment.appointment_datetime = new_start

            reschedule_note = f"\n[Rescheduled from {old_time} on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}]"
            if reason:
                reschedule_note += f" Reason: {reason}"
            appointment.notes = (appointment.notes or "") + reschedule_note

            db.commit()

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
                        db.commit()
                    except Exception as e:
                        logger.error(f"Failed to update calendar event: {e}")

            return {
                "success": True,
                "message": f"Your appointment has been rescheduled from {old_time} to {new_start.strftime('%A, %B %d at %I:%M %p')}.",
                "action_completed": True
            }

        except Exception as e:
            db.rollback()
            logger.error(f"Error rescheduling appointment: {e}")
            return {
                "success": False,
                "message": "Failed to reschedule appointment. Please try again or contact us directly."
            }

    def generate_response(
            self,
            messages: List[Dict],
            business_context: Dict,
            conversation_context: Dict,
            db: Session = None
    ) -> Dict:
        """Generate AI response for conversation"""
        try:
            # Get the last user message for RAG retrieval
            last_user_message = None
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    last_user_message = msg.get("content", "")
                    break

            # Build base system prompt
            system_prompt = self._build_system_prompt(business_context, conversation_context)

            # Retrieve relevant context from RAG if we have a user message and db session
            rag_context = ""
            if last_user_message and db:
                try:
                    business_id = business_context.get('business_id')
                    if business_id:
                        from app.models.business.business import Business

                        # CRITICAL: Use a separate session for RAG to avoid transaction pollution
                        from sqlalchemy.orm import sessionmaker
                        from app.config.database import engine

                        SessionLocal = sessionmaker(bind=engine)
                        rag_db = SessionLocal()

                        try:
                            business = rag_db.query(Business).filter(Business.id == business_id).first()

                            if business:
                                # Retrieve context with separate session
                                rag_context = self.rag_service.retrieve_context_sync(
                                    query=last_user_message,
                                    business_id=business_id,
                                    db=rag_db,
                                )

                            if rag_context:
                                logger.info(f"📚 RAG context retrieved ({len(rag_context)} chars)")
                            else:
                                logger.info("📚 No relevant RAG context found or skipped")

                        except Exception as rag_error:
                            logger.error(f"RAG retrieval failed: {rag_error}")
                            rag_context = ""
                        finally:
                            # Always close the RAG session
                            rag_db.close()

                except Exception as e:
                    logger.error(f"Error retrieving RAG context: {e}")
                    rag_context = ""

            # Combine system prompt with RAG context
            if rag_context:
                enhanced_prompt = f"{system_prompt}\n\n{rag_context}"
            else:
                enhanced_prompt = system_prompt

            api_messages = [{"role": "system", "content": enhanced_prompt}] + messages

            response = self.client.chat.completions.create(
                model=self.model,
                messages=api_messages,
                temperature=0.7,
                max_tokens=500,
                functions=self._get_function_definitions(),
                function_call="auto"
            )

            message = response.choices[0].message
            result = {
                "content": message.content,
                "function_call": None,
                "finish_reason": response.choices[0].finish_reason
            }

            if message.function_call:
                function_call_data = {
                    "name": message.function_call.name,
                    "arguments": json.loads(message.function_call.arguments)
                }

                if function_call_data["name"] == "book_appointment":
                    customer_name = function_call_data["arguments"].get("customer_name", "")

                    if not customer_name or customer_name.strip().lower() in ["", "there", "customer", "user"]:
                        logger.warning(f"AI attempted to book without valid name: '{customer_name}'")
                        return {
                            "content": "Before I book that for you, may I have your name?",
                            "function_call": None,
                            "finish_reason": "validation_failed"
                        }

                result["function_call"] = function_call_data

            return result

        except Exception as e:
            logger.error(f"Error generating AI response: {str(e)}")
            return {
                "content": "I apologize, but I'm having trouble processing your request right now.",
                "function_call": None,
                "finish_reason": "error"
            }

    def _build_system_prompt(
            self,
            business_context: Dict,
            conversation_context: Dict,
    ) -> str:
        """Creates system prompt with clear, direct instructions"""
        current_time = datetime.now(timezone.utc)
        flow_state = conversation_context.get('flow_state', 'greeting')

        prompt = f"""You are a booking assistant for {business_context.get('business_name', 'company')}.

    BUSINESS INFORMATION
    - Business ID: {business_context.get('business_id')}
    - Type: {business_context.get('business_type', 'N/A')}
    - Current time: {current_time.strftime('%A, %B %d, %Y at %H:%M')} (UTC)
    - Conversation state: {flow_state}

    ═══════════════════════════════════════════════════════════════════════════
    CORE BEHAVIOR RULES
    ═══════════════════════════════════════════════════════════════════════════

    1. SILENT FUNCTION CALLS
    Execute all function calls without any message to the user. No "let me check", "one moment", "just a second". Call functions, then respond with results.

    2. NATURAL CONVERSATION
    Keep responses short (2-3 sentences maximum), natural, and conversational. Never mention technical terms like "database", "function", "system", "required_fields", "validation", "storage". Never reveal you're an AI or mention internal processes.

    3. ONE THING AT A TIME
    Ask for one piece of information per turn. Don't list multiple fields. Don't say what you need in advance.

    4. USE BUSINESS CONTEXT
    If you see "RELEVANT BUSINESS INFORMATION" below this prompt, use those exact details in your responses. Be concrete and specific, not vague.

    ═══════════════════════════════════════════════════════════════════════════
    INFORMATION STORAGE - CRITICAL
    ═══════════════════════════════════════════════════════════════════════════

    MANDATORY STORAGE PROTOCOL:
    When a user provides information in response to your question, you MUST call the appropriate storage function in that same turn, BEFORE generating your next message.

    DECISION TREE FOR EVERY USER MESSAGE:
    → Did I just ask for name/email/phone? 
      YES → Call set_customer_info with the provided value

    → Did I just ask for a custom field (budget, timeline, property type, style, etc.)?
      YES → Call set_service_field with field_name and field_value

    → Only AFTER calling the storage function → Generate your next question or response

    STORAGE FUNCTIONS:
    - set_customer_info: For name, email, phone
    - set_service_field: For ALL other required fields (budget_range, project_timeline, property_type, square_footage, style_preferences, special_requirements, etc.)

    FIELD NAME MAPPING:
    Use the exact "field" property from the service's required_fields, not the "label":
    - If label is "Budget Range" → field_name is "budget_range"
    - If label is "Project Timeline" → field_name is "project_timeline"  
    - If label is "Property Type" → field_name is "property_type"
    - If label is "Square Footage" → field_name is "square_footage"
    - If label is "Style Preferences" → field_name is "style_preferences"
    - If label is "Special Requirements" → field_name is "special_requirements"

    STORAGE SEQUENCE:
    Every time you ask a question and receive an answer, this must happen:
    1. Identify which field the user just answered
    2. Call the storage function (set_customer_info or set_service_field)
    3. Wait for function result
    4. Then generate your next message

    ═══════════════════════════════════════════════════════════════════════════
    BOOKING WORKFLOW
    ═══════════════════════════════════════════════════════════════════════════

    STEP 1: IDENTIFY SERVICE
    When customer asks about booking or mentions a service:
    → Call get_services
    → Present services naturally with prices and descriptions
    → Let customer choose

    STEP 2: CHECK REQUIREMENTS
    When customer chooses a service:
    → Call get_service_fields to see what's needed and what's already collected
    → Each service has a booking_type:
      • DIRECT: Can book appointments directly
      • CONSULTATION_REQUIRED: Book a discovery call first (not the full service)
      • LEAD_ONLY: Just collect info, no appointment scheduling

    STEP 3: COLLECT INFORMATION
    For each missing field:
    → Ask for ONE field naturally
    → Wait for user response
    → IMMEDIATELY call storage function (set_customer_info or set_service_field)
    → Then ask for next field
    → Repeat until all fields collected

    Call get_customer_info first to check what you already have, so you don't re-ask.

    STEP 4: VALIDATE COMPLETENESS
    Before proceeding to booking:
    → Call validate_service_fields
    → This checks ALL required fields (standard + custom)
    → If validation returns missing_fields: Continue collecting them
    → If validation passes: Proceed to Step 5

    STEP 5: SCHEDULE OR CAPTURE LEAD
    Based on booking_type:

    A) DIRECT BOOKING:
       → Call get_available_slots
       → Show available times conversationally
       → Customer picks time
       → Call book_appointment
       → Confirm booking

    B) CONSULTATION_REQUIRED:
       → Explain you're scheduling a discovery call
       → Call get_available_slots (automatically uses consultation_duration)
       → Show available times
       → Customer picks time
       → Call book_appointment
       → Confirm discovery call booking

    C) LEAD_ONLY:
       → Call book_appointment (stores lead, no calendar booking)
       → Confirm information received

    ═══════════════════════════════════════════════════════════════════════════
    APPOINTMENT MANAGEMENT
    ═══════════════════════════════════════════════════════════════════════════

    VIEWING APPOINTMENTS:
    When customer asks about their appointments:
    → Call get_customer_appointments
    → List appointments naturally

    CANCELLING APPOINTMENTS:
    NEVER guess appointment IDs. Always:
    1. Call get_customer_appointments
    2. Show their appointments
    3. If multiple: Ask which one to cancel
    4. After they specify: Call cancel_appointment with correct ID
    5. Confirm cancellation

    RESCHEDULING APPOINTMENTS:
    NEVER guess appointment IDs. Always:
    1. Call get_customer_appointments  
    2. Show their appointments
    3. Ask which one to reschedule
    4. After they specify: Call get_available_slots
    5. Show new times
    6. After they pick: Call reschedule_appointment with correct ID and new time
    7. Confirm change

    ═══════════════════════════════════════════════════════════════════════════
    EDGE CASES
    ═══════════════════════════════════════════════════════════════════════════

    SERVICE SWITCHING:
    If customer asks about a different service mid-conversation:
    → Call clear_service_context
    → Start fresh with new service

    FUNCTION FAILURES:
    If a function returns an error or empty result:
    → Acknowledge briefly
    → Offer alternative or ask if they need help with something else
    → Don't retry more than once

    MISSING INFORMATION:
    → Never assume or make up values
    → Always ask the customer
    → Never skip required fields

    VALIDATION:
    → ALWAYS call validate_service_fields before book_appointment
    → Don't assume validation passes just because you asked questions
    → Only proceed to booking after validation confirms all fields collected

    ═══════════════════════════════════════════════════════════════════════════
    CRITICAL REMINDERS
    ═══════════════════════════════════════════════════════════════════════════

    ✓ Call storage functions IMMEDIATELY when user provides information
    ✓ Call functions silently - user sees results, not process
    ✓ Be natural and conversational
    ✓ One question at a time
    ✓ Always get appointment IDs before canceling/rescheduling
    ✓ Validate fields before booking
    ✓ Keep responses concise (2-3 sentences)

    ✗ Never skip calling storage functions
    ✗ Never say "let me check" or "one moment"
    ✗ Never mention technical details
    ✗ Never guess appointment IDs
    ✗ Never skip required fields
    ✗ Never list fields like a form
    ✗ Never acknowledge information without storing it first

    """

        return prompt

    def _get_function_definitions(self) -> List[Dict]:
        """Define functions that AI can call"""
        return [
            {
                "name": "get_services",
                "description": "Fetch the list of services offered by the business. ALWAYS call this FIRST when customer asks about booking. The response includes an 'id' field (UUID string) which you MUST use in subsequent calls to set_service_field, get_service_fields, and validate_service_fields.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "business_id": {"type": "string", "description": "The business ID"}
                    },
                    "required": ["business_id"]
                }
            },
            {
                "name": "get_service_fields",
                "description": "Check what information has been collected for a service and what's still needed. Returns collected_fields, missing_fields, and booking_type.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "conversation_id": {"type": "string", "description": "The conversation ID (auto-filled)"},
                        "service_id": {
                            "type": "string",
                            "description": "CRITICAL: Use the exact UUID string from the 'id' field in get_services response (e.g., 'cf6160d3-6688-4661-bd24-f127545c3170'). DO NOT use the service name. DO NOT make up an ID. Use the EXACT 'id' value from get_services."
                        }
                    },
                    "required": ["conversation_id", "service_id"]
                }
            },
            {
                "name": "set_service_field",
                "description": "Store a custom service field value immediately after customer provides it. For name/email/phone, use set_customer_info instead. Call this function EVERY TIME the customer provides information for a required field.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "conversation_id": {"type": "string", "description": "The conversation ID (auto-filled)"},
                        "service_id": {
                            "type": "string",
                            "description": "CRITICAL: Use the exact UUID string from the 'id' field in get_services response (e.g., 'cf6160d3-6688-4661-bd24-f127545c3170'). DO NOT use the service name. DO NOT make up an ID. Use the EXACT 'id' value from get_services."
                        },
                        "field_name": {
                            "type": "string",
                            "description": "The exact field name from required_fields (e.g., 'budget_range', 'project_timeline', 'property_type'). Use the 'field' property, not the 'label'."
                        },
                        "field_value": {"type": "string", "description": "The value provided by customer"}
                    },
                    "required": ["conversation_id", "service_id", "field_name", "field_value"]
                }
            },
            {
                "name": "validate_service_fields",
                "description": "Validate that ALL required fields have been collected before booking. ALWAYS call this before attempting to book.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "conversation_id": {"type": "string", "description": "The conversation ID (auto-filled)"},
                        "service_id": {
                            "type": "string",
                            "description": "CRITICAL: Use the exact UUID string from the 'id' field in get_services response. DO NOT use the service name or make up an ID."
                        }
                    },
                    "required": ["conversation_id", "service_id"]
                }
            },
            {
                "name": "set_customer_info",
                "description": "Store standard customer information (name, email, phone) when customer provides it. Call this immediately after customer gives you their details.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "conversation_id": {"type": "string", "description": "The conversation ID (auto-filled)"},
                        "customer_name": {"type": "string", "description": "Customer's full name"},
                        "customer_email": {"type": "string", "description": "Customer's email address"},
                        "customer_phone": {"type": "string", "description": "Customer's phone number"}
                    },
                    "required": ["conversation_id"]
                }
            },
            {
                "name": "get_customer_info",
                "description": "Check what standard customer information is already known (name, email, phone). Call this BEFORE asking for customer details to avoid asking for information you already have.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "conversation_id": {"type": "string", "description": "The conversation ID (auto-filled)"}
                    },
                    "required": ["conversation_id"]
                }
            },
            {
                "name": "get_available_slots",
                "description": "Get available appointment slots for a service. The system automatically uses the correct duration based on booking type (consultation_duration for consultation_required services, service duration for direct booking).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "business_id": {"type": "string"},
                        "service": {"type": "string", "description": "Service name (not ID)"},
                        "start_date": {
                            "type": "string",
                            "description": "Start date/datetime in ISO format (e.g., '2025-10-08' for Oct 8, or '2025-10-08T14:00:00' for specific time)"
                        },
                        "end_date": {
                            "type": "string",
                            "description": "End date/datetime in ISO format. If omitted, returns slots for just the start_date."
                        },
                        "limit": {"type": "integer", "default": 20}
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
                        "business_id": {"type": "string", "description": "The business ID (auto-filled)"},
                        "conversation_id": {"type": "string", "description": "The conversation ID (auto-filled)"},
                        "customer_name": {"type": "string", "description": "Customer's full name"},
                        "customer_email": {"type": "string", "description": "Customer's email"},
                        "customer_phone": {"type": "string", "description": "Customer's phone (auto-filled)"},
                        "service_type": {"type": "string", "description": "Service name"},
                        "appointment_datetime": {"type": "string",
                                                 "description": "Appointment date/time in ISO format"},
                        "notes": {"type": "string", "description": "Additional notes or comments"}
                    },
                    "required": ["business_id", "conversation_id", "customer_name", "customer_email", "customer_phone",
                                 "service_type", "appointment_datetime"]
                }
            },
            {
                "name": "get_customer_appointments",
                "description": "Retrieve appointments for a customer by phone number. Use when customer asks about their appointments or wants to cancel/reschedule. The customer_phone is automatically provided.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "customer_phone": {"type": "string",
                                           "description": "Customer's phone number (auto-filled from conversation)"},
                        "business_id": {"type": "string", "description": "The business ID"},
                        "include_past": {"type": "boolean", "default": False,
                                         "description": "Include past appointments"}
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
                        "appointment_id": {"type": "string", "description": "The appointment ID to cancel"},
                        "customer_phone": {"type": "string",
                                           "description": "Customer's phone number (auto-filled from conversation)"},
                        "reason": {"type": "string", "description": "Optional cancellation reason"}
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
                        "appointment_id": {"type": "string", "description": "The appointment ID to reschedule"},
                        "customer_phone": {"type": "string",
                                           "description": "Customer's phone number (auto-filled from conversation)"},
                        "new_datetime": {"type": "string", "description": "New appointment date/time in ISO format"},
                        "reason": {"type": "string", "description": "Optional reason for rescheduling"}
                    },
                    "required": ["appointment_id", "customer_phone", "new_datetime"]
                }
            },
            {
                "name": "clear_service_context",
                "description": "Clear the collected service fields when customer wants to inquire about a different service. Use this when customer switches from one service to another to avoid mixing collected information. This preserves customer_info (name, email, phone) but clears service-specific fields.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "conversation_id": {
                            "type": "string",
                            "description": "The conversation ID (auto-filled)"
                        }
                    },
                    "required": ["conversation_id"]
                }
            }
        ]