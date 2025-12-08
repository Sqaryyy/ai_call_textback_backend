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

logger = logging.getLogger(__name__)
settings = Settings()


class DemoAIService:
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
        """Fetch available slots for AI."""

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
                services.append({
                    "name": service.name,
                    "price": service.formatted_price,
                    "duration_minutes": service.duration if service.duration else 30,
                    "description": service.description or ""
                })

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

    FUNCTION CALLING BEHAVIOR:
    - When you call a function to retrieve information, DO NOT include any message to the user
    - Call the function silently, then respond with the actual data
    - Never say "let me check", "one moment", "just a second", etc.
    - The user should only see the final result, not the process

    CRITICAL: When retrieving services with get_services:
    - Call get_services WITHOUT any accompanying text
    - After getting results, present the services naturally based on what's available
    - If there's only ONE service, mention it directly and move to scheduling
    - If there are MULTIPLE services, list them and ask which one they'd like

    SERVICES:
    - ALWAYS call get_services first when customer mentions booking
    - NEVER assume what services exist or their prices
    - After getting service data, present it clearly with prices

    USING BUSINESS INFORMATION:
    Below this prompt you may see "RELEVANT BUSINESS INFORMATION" with specific details.
    Use those exact details when responding - be concrete, not vague.

    COMMUNICATION RULES:
    - Keep responses short (2-3 sentences for SMS)
    - Be natural and conversational
    - Never mention technical terms like "database", "function", "system"
    - Never reveal you're an AI

    BOOKING FLOW:
    1. Customer wants to book → call get_services (no message)
    2. Present services naturally:
       - One service: "I can book you for [service] at $[price]. When works for you?"
       - Multiple services: "We offer [list with prices]. Which would you like?"
    3. Customer chooses → call get_available_slots (no message)
    4. Show available times
    5. Customer picks time → call get_customer_info (no message)
    6. If no name → ask for name, then call set_customer_info (no message)
    7. Call book_appointment (no message), then confirm

    CUSTOMER INFORMATION:
    - Always call get_customer_info before asking for details
    - Call set_customer_info immediately after they provide information
    - Never book without a real customer name

    """

        return prompt

    def _get_function_definitions(self) -> List[Dict]:
        """Define functions that AI can call"""
        return [
            {
                "name": "get_services",
                "description": "Fetch the list of services offered by the business with pricing and duration. ALWAYS call this FIRST when customer asks about booking or mentions any service. Do not assume what services exist.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "business_id": {"type": "string", "description": "The business ID"}
                    },
                    "required": ["business_id"]
                }
            },
            {
                "name": "set_customer_info",
                "description": "Store customer information (name, email, phone) when customer provides it. Call this immediately after customer gives you their details.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "conversation_id": {
                            "type": "string",
                            "description": "The conversation ID (auto-filled)"
                        },
                        "customer_name": {
                            "type": "string",
                            "description": "Customer's full name"
                        },
                        "customer_email": {
                            "type": "string",
                            "description": "Customer's email address"
                        },
                        "customer_phone": {
                            "type": "string",
                            "description": "Customer's phone number"
                        }
                    },
                    "required": ["conversation_id"]
                }
            },
            {
                "name": "get_customer_info",
                "description": "Check what customer information is already known (name, email, phone). Call this BEFORE asking for customer details or booking appointments to avoid asking for information you already have.",
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
            },
            {
                "name": "book_appointment",
                "description": "Book an appointment when customer confirms. CRITICAL: Only call this when you have a VALID customer name (not empty, not 'there', not a placeholder). If name is missing from customer_info, ask for it first before calling this function.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "customer_name": {
                            "type": "string",
                            "description": "Customer's full name - MUST be a real name, not empty or placeholder"
                        },
                        "service_type": {"type": "string"},
                        "appointment_datetime": {"type": "string"},
                        "notes": {"type": "string"}
                    },
                    "required": ["customer_name", "service_type", "appointment_datetime"]
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
                "name": "get_available_slots",
                "description": "Get available appointment slots for a service.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "business_id": {"type": "string"},
                        "service": {"type": "string"},
                        "duration_minutes": {"type": "integer", "default": 30},
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
            }
        ]