"""
Agents AI Service - OpenAI Agents SDK implementation
Orchestrates multiple specialized agents for conversation handling.
"""

from agents import Agent, Runner, SQLiteSession
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
import os
import logging

logger = logging.getLogger(__name__)

from app.services.ai.agents.router_agent import RouterAgent
from app.services.ai.agents.booking_agent import BookingAgent
from app.services.ai.agents.appointment_mgmt_agent import AppointmentManagementAgent
from app.services.ai.agents.general_assistant_agent import GeneralAssistantAgent
from app.services.ai.tools.service_tools import ServiceTools

class AgentsAIService:
    """
    AI Service using OpenAI Agents SDK.
    Manages multi-agent workflows for customer conversations.
    """

    def __init__(self, session_storage_path: str = "agent_sessions.db"):
        """
        Initialize the Agents AI Service.

        Args:
            session_storage_path: Path to SQLite database for session storage
        """
        self.session_storage_path = session_storage_path

        # Set OpenAI API key from your config
        self._setup_openai_key()

    def _setup_openai_key(self):
        """Setup OpenAI API key from your existing config."""
        # Check if already set in environment
        if os.getenv("OPENAI_API_KEY"):
            return

        # Import from your settings
        try:
            from app.config.settings import get_settings
            settings = get_settings()
            api_key = settings.OPENAI_API_KEY

            if api_key:
                os.environ["OPENAI_API_KEY"] = api_key
                print("✅ OpenAI API key loaded from settings")
            else:
                print("⚠️ WARNING: OPENAI_API_KEY is None in settings")
        except Exception as e:
            print(f"⚠️ WARNING: Could not load OPENAI_API_KEY from settings: {e}")

    def _create_tool_factory(
            self,
            db: Session,
            conversation_id: str,
            customer_phone: str,
            business_id: str,
            session_id: str
    ):
        """
        Create a tool factory that wraps ALL existing tool classes.
        Each tool is bound with the necessary context (db, conversation_id, etc.)
        Tools are demo-aware and use appropriate storage mechanism.
        """
        from agents import function_tool

        # Import all your existing tool classes
        from app.services.ai.tools.service_tools import ServiceTools
        from app.services.ai.tools.booking_tools import BookingTools
        from app.services.ai.tools.appointment_tools import AppointmentTools
        from app.services.ai.tools.customer_tools import CustomerTools
        from app.services.ai.tools.field_tools import FieldTools
        from app.services.ai.tools.context_tools import ContextTools
        from app.services.demo.demo_session_service import DemoSessionService

        # Helper function to check if demo mode
        def is_demo_mode() -> bool:
            return DemoSessionService.session_exists(session_id)

        # ============================================
        # SERVICE TOOLS
        # ============================================

        @function_tool
        async def get_services() -> dict:
            """
            Get list of available services with full details.
            Returns service IDs (UUIDs), names, prices, durations, descriptions, and required fields.
            """
            try:
                services = await ServiceTools.get_services(db=db, business_id=business_id)

                if not services:
                    return {
                        "success": False,
                        "services": [],
                        "message": "No services found for this business"
                    }

                # Format for easy lookup
                service_dict = {service["name"]: service for service in services}

                return {
                    "success": True,
                    "services": services,
                    "service_details": service_dict,
                    "count": len(services)
                }
            except Exception as e:
                import traceback
                logger.error(f"❌ Error in get_services: {str(e)}")
                traceback.print_exc()
                return {
                    "success": False,
                    "services": [],
                    "error": str(e)
                }

        @function_tool
        async def get_services_summary() -> dict:
            """
            Get a simplified overview of services WITHOUT required fields.
            Use this for general information queries. For booking, use get_services() instead.
            """
            try:
                services = await ServiceTools.get_services(db=db, business_id=business_id)

                if not services:
                    return {
                        "success": False,
                        "services": [],
                        "message": "No services found for this business"
                    }

                # Remove required_fields from each service
                simplified_services = []
                for service in services:
                    simplified = {
                        "id": service["id"],
                        "name": service["name"],
                        "price": service["price"],
                        "duration_minutes": service["duration_minutes"],
                        "description": service["description"],
                        "booking_type": service["booking_type"]
                    }

                    # Add consultation details if applicable
                    if service["booking_type"] == "consultation_required":
                        simplified["consultation_duration"] = service.get("consultation_duration")
                        simplified["consultation_price"] = service.get("consultation_price")

                    simplified_services.append(simplified)

                service_dict = {s["name"]: s for s in simplified_services}

                return {
                    "success": True,
                    "services": simplified_services,
                    "service_details": service_dict,
                    "count": len(simplified_services)
                }
            except Exception as e:
                import traceback
                logger.error(f"❌ Error in get_services_summary: {str(e)}")
                traceback.print_exc()
                return {
                    "success": False,
                    "services": [],
                    "error": str(e)
                }

        @function_tool
        async def get_service_fields(service_id: str) -> dict:
            """
            Get collected fields and missing fields for a service.
            SMART MAPPING: Automatically maps name/email/phone from customer_info to service fields.
            Use this to check what information still needs to be collected.
            """
            try:
                if is_demo_mode():
                    # DEMO MODE: Use demo session
                    session = DemoSessionService.get_session(session_id)
                    service_context = session.get("service_context", {})
                    collected_fields = service_context.get("collected_fields", {})
                    customer_info = session.get("customer_info", {})

                    # SMART MAPPING: Auto-populate name/email/phone from customer_info
                    if customer_info.get("name") and not collected_fields.get("name"):
                        collected_fields["name"] = customer_info["name"]
                        logger.info(f"🔄 Auto-mapped 'name' from customer_info: {customer_info['name']}")

                    if customer_info.get("email") and not collected_fields.get("email"):
                        collected_fields["email"] = customer_info["email"]
                        logger.info(f"🔄 Auto-mapped 'email' from customer_info: {customer_info['email']}")

                    if customer_info.get("phone") and not collected_fields.get("phone"):
                        collected_fields["phone"] = customer_info["phone"]
                        logger.info(f"🔄 Auto-mapped 'phone' from customer_info: {customer_info['phone']}")

                    # Update session with mapped fields
                    service_context["collected_fields"] = collected_fields
                    session["service_context"] = service_context

                    # Get service from database to check required fields
                    from app.models.business.service import Service
                    service = db.query(Service).filter(Service.id == service_id).first()

                    if not service:
                        return {"success": False, "message": "Service not found"}

                    required_fields = service.required_fields or []
                    missing_fields = []

                    for field_def in required_fields:
                        field_name = field_def.get("field")
                        if field_def.get("required", True):
                            if not collected_fields.get(field_name):
                                missing_fields.append(field_def)

                    all_collected = len(missing_fields) == 0

                    return {
                        "success": True,
                        "collected_fields": collected_fields,
                        "missing_fields": missing_fields,
                        "all_fields_collected": all_collected,
                        "service_id": str(service.id),
                        "service_name": service.name,
                        "booking_type": service.booking_type.value
                    }
                else:
                    # PRODUCTION MODE: Use database with smart mapping
                    # First get customer info from conversation state
                    from app.models.conversation import ConversationState

                    conv_state = db.query(ConversationState).filter(
                        ConversationState.conversation_id == conversation_id
                    ).first()

                    customer_info = {}
                    if conv_state and conv_state.customer_info:
                        customer_info = conv_state.customer_info

                    # Get service fields
                    result = await ServiceTools.get_service_fields(
                        db=db,
                        conversation_id=conversation_id,
                        service_id=service_id
                    )

                    if not result.get("success"):
                        return result

                    # SMART MAPPING: Auto-populate name/email/phone from customer_info
                    collected_fields = result.get("collected_fields", {})

                    if customer_info.get("name") and not collected_fields.get("name"):
                        collected_fields["name"] = customer_info["name"]
                        logger.info(f"🔄 Auto-mapped 'name' from customer_info: {customer_info['name']}")
                        # Store in database
                        await FieldTools.set_service_field(
                            db=db,
                            conversation_id=conversation_id,
                            service_id=service_id,
                            field_name="name",
                            field_value=customer_info["name"]
                        )

                    if customer_info.get("email") and not collected_fields.get("email"):
                        collected_fields["email"] = customer_info["email"]
                        logger.info(f"🔄 Auto-mapped 'email' from customer_info: {customer_info['email']}")
                        await FieldTools.set_service_field(
                            db=db,
                            conversation_id=conversation_id,
                            service_id=service_id,
                            field_name="email",
                            field_value=customer_info["email"]
                        )

                    if customer_info.get("phone") and not collected_fields.get("phone"):
                        collected_fields["phone"] = customer_info["phone"]
                        logger.info(f"🔄 Auto-mapped 'phone' from customer_info: {customer_info['phone']}")
                        await FieldTools.set_service_field(
                            db=db,
                            conversation_id=conversation_id,
                            service_id=service_id,
                            field_name="phone",
                            field_value=customer_info["phone"]
                        )

                    # Re-fetch to get updated missing fields
                    result = await ServiceTools.get_service_fields(
                        db=db,
                        conversation_id=conversation_id,
                        service_id=service_id
                    )

                    return result

            except Exception as e:
                logger.error(f"Error in get_service_fields: {e}")
                return {"success": False, "message": str(e)}

        @function_tool
        async def validate_service_fields(service_id: str) -> dict:
            """
            Validate that all required fields are collected before booking.
            Always call this before attempting to book an appointment.
            """
            try:
                if is_demo_mode():
                    # DEMO MODE: Use demo session
                    session = DemoSessionService.get_session(session_id)
                    service_context = session.get("service_context", {})
                    collected_fields = service_context.get("collected_fields", {})

                    from app.models.business.service import Service
                    service = db.query(Service).filter(Service.id == service_id).first()

                    if not service:
                        return {"valid": False, "message": "Service not found", "missing_fields": []}

                    is_valid, missing_fields = service.validate_required_fields(collected_fields)

                    if is_valid:
                        return {
                            "valid": True,
                            "message": "All required fields collected",
                            "missing_fields": [],
                            "can_proceed": True
                        }
                    else:
                        missing_field_names = [f.get("label", f.get("field")) for f in missing_fields]
                        return {
                            "valid": False,
                            "message": f"Still need: {', '.join(missing_field_names)}",
                            "missing_fields": missing_fields,
                            "can_proceed": False
                        }
                else:
                    # PRODUCTION MODE: Use database
                    return await ServiceTools.validate_service_fields(
                        db=db,
                        conversation_id=conversation_id,
                        service_id=service_id
                    )
            except Exception as e:
                logger.error(f"Error validating service fields: {e}")
                return {"valid": False, "message": str(e), "can_proceed": False}

        # ============================================
        # CUSTOMER TOOLS
        # ============================================

        @function_tool
        async def get_customer_info() -> dict:
            """Check what standard customer information is already known."""
            try:
                if is_demo_mode():
                    # DEMO MODE: Use demo_sessions
                    session = DemoSessionService.get_session(session_id)
                    customer_info = session.get("customer_info", {})
                    return {
                        "success": True,
                        "customer_info": customer_info,
                        "has_name": bool(customer_info.get("name")),
                        "has_email": bool(customer_info.get("email")),
                        "has_phone": bool(customer_info.get("phone"))
                    }
                else:
                    # PRODUCTION MODE: Use conversation_states table
                    return await CustomerTools.get_customer_info(
                        db=db,
                        conversation_id=conversation_id
                    )
            except Exception as e:
                logger.error(f"Error in get_customer_info: {e}")
                return {
                    "success": False,
                    "customer_info": {},
                    "has_name": False,
                    "has_email": False,
                    "has_phone": False
                }

        @function_tool
        async def set_customer_info(
                customer_name: Optional[str] = None,
                customer_email: Optional[str] = None,
                customer_phone_override: Optional[str] = None
        ) -> dict:
            """
            Store standard customer information (name, email, phone).
            Call this immediately after customer provides their details.
            """
            try:
                if is_demo_mode():
                    # DEMO MODE: Update demo session
                    session = DemoSessionService.get_session(session_id)
                    customer_info = session.get("customer_info", {})

                    # Update with new values
                    if customer_name:
                        customer_info["name"] = customer_name
                    if customer_email:
                        customer_info["email"] = customer_email
                    if customer_phone_override:
                        customer_info["phone"] = customer_phone_override

                    session["customer_info"] = customer_info

                    logger.info(f"✅ Stored demo customer info: {customer_info}")

                    return {
                        "success": True,
                        "message": "Customer information stored successfully",
                        "customer_info": customer_info
                    }
                else:
                    # PRODUCTION MODE: Use database
                    return await CustomerTools.set_customer_info(
                        db=db,
                        conversation_id=conversation_id,
                        customer_name=customer_name,
                        customer_email=customer_email,
                        customer_phone=customer_phone_override or customer_phone
                    )
            except Exception as e:
                logger.error(f"Error setting customer info: {e}")
                return {"success": False, "message": str(e)}

        # ============================================
        # FIELD TOOLS
        # ============================================

        # In your AgentsAIService._create_tool_factory() method
        # Replace the existing set_service_field function with this:

        @function_tool
        async def set_service_field(
                service_id: str,
                field_name: str,
                field_value: str
        ) -> dict:
            """
            Store a custom service field value immediately after customer provides it.
            For name/email/phone, use set_customer_info instead.

            GUARDRAILS: Will reject empty or placeholder values.
            """
            try:
                # ============================================
                # GUARDRAIL: Validate field value
                # ============================================
                from app.services.ai.tools.field_tools import FieldTools

                is_valid, error_message = FieldTools._validate_field_value(field_value, field_name)

                if not is_valid:
                    logger.warning(f"❌ Rejected invalid field value: {field_name}='{field_value}'")
                    return {
                        "success": False,
                        "message": error_message,
                        "error_type": "invalid_value",
                        "field_name": field_name,
                        "rejected_value": field_value
                    }

                # ============================================
                # Store the validated value
                # ============================================
                if is_demo_mode():
                    # DEMO MODE: Update demo session
                    session = DemoSessionService.get_session(session_id)
                    service_context = session.get("service_context", {})

                    # Set the service_id if not already set
                    if not service_context.get("interested_service_id"):
                        service_context["interested_service_id"] = service_id

                    # Get or initialize collected_fields
                    collected_fields = service_context.get("collected_fields", {})

                    # Store the field value (cleaned)
                    collected_fields[field_name] = field_value.strip()
                    service_context["collected_fields"] = collected_fields

                    session["service_context"] = service_context

                    logger.info(f"✅ Stored demo field '{field_name}' = '{field_value}'")

                    return {
                        "success": True,
                        "message": f"Stored {field_name}",
                        "collected_fields": collected_fields
                    }
                else:
                    # PRODUCTION MODE: Use database
                    return await FieldTools.set_service_field(
                        db=db,
                        conversation_id=conversation_id,
                        service_id=service_id,
                        field_name=field_name,
                        field_value=field_value
                    )
            except Exception as e:
                logger.error(f"Error storing service field: {e}")
                return {
                    "success": False,
                    "message": str(e),
                    "error_type": "system_error"
                }

        # ============================================
        # BOOKING TOOLS
        # ============================================

        @function_tool
        async def get_available_slots(
                service: str,
                start_date: Optional[str] = None,
                end_date: Optional[str] = None,
                duration_minutes: int = 30,
                limit: int = 20
        ) -> dict:
            """
            Get available appointment slots for a service.
            The system automatically uses the correct duration based on booking type.
            """
            try:
                if is_demo_mode():
                    # DEMO MODE: Use demo session mock availability
                    slots = DemoSessionService.generate_available_slots(
                        session_id=session_id,
                        start_date=start_date,
                        end_date=end_date,
                        duration_minutes=duration_minutes,
                        limit=limit
                    )
                    return {"success": True, "slots": slots, "count": len(slots)}
                else:
                    # PRODUCTION MODE: Use real calendar
                    slots = await BookingTools.get_available_slots(
                        db=db,
                        business_id=business_id,
                        service=service,
                        duration_minutes=duration_minutes,
                        start_date=start_date,
                        end_date=end_date,
                        limit=limit
                    )
                    return {"success": True, "slots": slots, "count": len(slots)}
            except Exception as e:
                logger.error(f"Error getting available slots: {e}")
                return {"success": False, "slots": [], "count": 0, "error": str(e)}

        # In your AgentsAIService._create_tool_factory() method
        # Replace the existing book_appointment function with this:

        @function_tool
        async def book_appointment(
                service_type: str,
                appointment_datetime: str,
                customer_name: str,
                customer_email: str,
                notes: Optional[str] = None
        ) -> dict:
            """
            Book an appointment or store lead based on service booking_type.
            CRITICAL: Only call after validate_service_fields confirms all fields collected.
            """
            try:
                # ============================================
                # GUARDRAIL 1: Verify customer info matches stored data
                # ============================================
                if is_demo_mode():
                    # Demo mode: check session
                    session = DemoSessionService.get_session(session_id)
                    stored_customer_info = session.get("customer_info", {})
                else:
                    # Production mode: check database
                    from app.models.conversation import ConversationState
                    conv_state = db.query(ConversationState).filter(
                        ConversationState.conversation_id == conversation_id
                    ).first()
                    stored_customer_info = conv_state.customer_info if conv_state else {}

                # Normalize and compare name
                stored_name = stored_customer_info.get("name", "").lower().strip()
                provided_name = customer_name.lower().strip()

                if stored_name and provided_name and stored_name != provided_name:
                    logger.error(f"❌ HALLUCINATION DETECTED - Name mismatch!")
                    logger.error(f"   Stored: '{stored_name}'")
                    logger.error(f"   Provided: '{provided_name}'")
                    return {
                        "success": False,
                        "message": f"The name you provided ('{customer_name}') doesn't match our records ('{stored_customer_info.get('name')}'). Please use get_customer_info() to get the correct name.",
                        "error_type": "data_mismatch",
                        "field": "name"
                    }

                # Normalize and compare email
                stored_email = stored_customer_info.get("email", "").lower().strip()
                provided_email = customer_email.lower().strip()

                if stored_email and provided_email and stored_email != provided_email:
                    logger.error(f"❌ HALLUCINATION DETECTED - Email mismatch!")
                    logger.error(f"   Stored: '{stored_email}'")
                    logger.error(f"   Provided: '{provided_email}'")
                    return {
                        "success": False,
                        "message": f"The email you provided ('{customer_email}') doesn't match our records ('{stored_customer_info.get('email')}'). Please use get_customer_info() to get the correct email.",
                        "error_type": "data_mismatch",
                        "field": "email"
                    }

                # ============================================
                # GUARDRAIL 2: Validate datetime format
                # ============================================
                try:
                    from datetime import datetime
                    parsed_dt = datetime.fromisoformat(appointment_datetime.replace('Z', '+00:00'))
                    # Check if datetime is in the past
                    if parsed_dt < datetime.now(parsed_dt.tzinfo):
                        logger.error(f"❌ Attempted to book appointment in the past: {appointment_datetime}")
                        return {
                            "success": False,
                            "message": "Cannot book appointments in the past. Please select a future time slot.",
                            "error_type": "invalid_datetime"
                        }
                except (ValueError, AttributeError) as e:
                    logger.error(f"❌ Invalid datetime format: {appointment_datetime}")
                    return {
                        "success": False,
                        "message": f"Invalid datetime format: '{appointment_datetime}'. Must be ISO format (YYYY-MM-DDTHH:MM:SS).",
                        "error_type": "invalid_datetime"
                    }

                # ============================================
                # GUARDRAIL 3: Verify service exists
                # ============================================
                from app.models.business.service import Service
                service = db.query(Service).filter(
                    Service.business_id == business_id,
                    Service.name == service_type
                ).first()

                if not service:
                    logger.error(f"❌ Attempted to book non-existent service: {service_type}")
                    return {
                        "success": False,
                        "message": f"Service '{service_type}' not found. Please use get_services() to see available services.",
                        "error_type": "invalid_service"
                    }

                # ============================================
                # GUARDRAIL 4: Verify all required fields collected (consultation_required only)
                # ============================================
                if service.booking_type.value in ["consultation_required", "lead_only"]:
                    if is_demo_mode():
                        session = DemoSessionService.get_session(session_id)
                        service_context = session.get("service_context", {})
                        collected_fields = service_context.get("collected_fields", {})
                    else:
                        result = await ServiceTools.get_service_fields(
                            db=db,
                            conversation_id=conversation_id,
                            service_id=str(service.id)
                        )
                        collected_fields = result.get("collected_fields", {})

                    # Validate against service requirements
                    is_valid, missing_fields = service.validate_required_fields(collected_fields)

                    if not is_valid:
                        missing_labels = [f.get("label", f.get("field")) for f in missing_fields]
                        logger.error(f"❌ Attempted booking with missing fields: {missing_labels}")
                        return {
                            "success": False,
                            "message": f"Cannot book yet. Still need: {', '.join(missing_labels)}. Use get_service_fields() to check.",
                            "error_type": "incomplete_fields",
                            "missing_fields": missing_fields
                        }

                # ============================================
                # All validations passed - proceed with booking
                # ============================================
                if is_demo_mode():
                    import uuid
                    from datetime import datetime

                    appointment = {
                        "id": str(uuid.uuid4()),
                        "service": service_type,
                        "start_time": appointment_datetime,
                        "customer_name": customer_name,
                        "customer_email": customer_email,
                        "status": "scheduled",
                        "notes": notes or "",
                        "created_at": datetime.now().isoformat()
                    }

                    DemoSessionService.add_appointment(session_id, appointment)

                    logger.info(f"✅ Booked demo appointment: {service_type} at {appointment_datetime}")

                    return {
                        "success": True,
                        "message": f"Perfect! Your appointment for {service_type} is confirmed for {appointment_datetime}.",
                        "appointment_id": appointment["id"]
                    }
                else:
                    # PRODUCTION MODE: Real booking
                    return await BookingTools.book_appointment(
                        db=db,
                        business_id=business_id,
                        conversation_id=conversation_id,
                        customer_name=customer_name,
                        customer_email=customer_email,
                        customer_phone=customer_phone,
                        service_type=service_type,
                        appointment_datetime=appointment_datetime,
                        notes=notes or ""
                    )
            except Exception as e:
                import traceback
                logger.error(f"❌ Error booking appointment: {e}")
                traceback.print_exc()
                return {
                    "success": False,
                    "message": f"Booking error: {str(e)}",
                    "error_type": "system_error"
                }

        # ============================================
        # APPOINTMENT MANAGEMENT TOOLS
        # ============================================

        @function_tool
        async def get_customer_appointments(include_past: bool = False) -> dict:
            """
            Retrieve appointments for the customer.
            Use when customer asks about their appointments or wants to cancel/reschedule.
            """
            try:
                if is_demo_mode():
                    # DEMO MODE: Get from demo session
                    appointments = DemoSessionService.get_appointments(session_id)

                    # Filter out cancelled if not including past
                    if not include_past:
                        appointments = [apt for apt in appointments if apt.get("status") != "cancelled"]

                    # Format for response
                    formatted = []
                    for apt in appointments:
                        formatted.append({
                            "id": apt["id"],
                            "service": apt["service"],
                            "start_time": apt["start_time"],
                            "status": apt.get("status", "scheduled"),
                            "customer_name": apt.get("customer_name"),
                            "display_time": apt.get("display_time", apt["start_time"])
                        })

                    return {
                        "success": True,
                        "appointments": formatted,
                        "count": len(formatted)
                    }
                else:
                    # PRODUCTION MODE: Get from database
                    appointments = await AppointmentTools.get_customer_appointments(
                        db=db,
                        customer_phone=customer_phone,
                        business_id=business_id,
                        include_past=include_past
                    )
                    return {
                        "success": True,
                        "appointments": appointments,
                        "count": len(appointments)
                    }
            except Exception as e:
                logger.error(f"Error getting appointments: {e}")
                return {
                    "success": False,
                    "appointments": [],
                    "error": str(e)
                }

        @function_tool
        async def cancel_appointment(
                appointment_id: str,
                reason: Optional[str] = None
        ) -> dict:
            """
            Cancel an existing appointment.
            Use when customer wants to cancel.
            """
            try:
                if is_demo_mode():
                    # DEMO MODE: Cancel in demo session
                    success = DemoSessionService.cancel_appointment(session_id, appointment_id)

                    if success:
                        return {
                            "success": True,
                            "message": "Your appointment has been cancelled.",
                            "action_completed": True
                        }
                    else:
                        return {
                            "success": False,
                            "message": "Appointment not found"
                        }
                else:
                    # PRODUCTION MODE: Cancel in database
                    return await AppointmentTools.cancel_appointment(
                        db=db,
                        appointment_id=appointment_id,
                        customer_phone=customer_phone,
                        reason=reason
                    )
            except Exception as e:
                logger.error(f"Error cancelling appointment: {e}")
                return {
                    "success": False,
                    "message": f"Cancellation error: {str(e)}"
                }

        @function_tool
        async def reschedule_appointment(
                appointment_id: str,
                new_datetime: str,
                reason: Optional[str] = None
        ) -> dict:
            """
            Reschedule an existing appointment to a new date/time.
            Use when customer wants to change their appointment time.
            """
            try:
                if is_demo_mode():
                    # DEMO MODE: Reschedule in demo session
                    success = DemoSessionService.reschedule_appointment(
                        session_id,
                        appointment_id,
                        new_datetime
                    )

                    if success:
                        return {
                            "success": True,
                            "message": f"Your appointment has been rescheduled to {new_datetime}.",
                            "action_completed": True
                        }
                    else:
                        return {
                            "success": False,
                            "message": "Appointment not found"
                        }
                else:
                    # PRODUCTION MODE: Reschedule in database
                    return await AppointmentTools.reschedule_appointment(
                        db=db,
                        appointment_id=appointment_id,
                        customer_phone=customer_phone,
                        new_datetime=new_datetime,
                        reason=reason
                    )
            except Exception as e:
                logger.error(f"Error rescheduling appointment: {e}")
                return {
                    "success": False,
                    "message": f"Reschedule error: {str(e)}"
                }

        # ============================================
        # CONTEXT TOOLS
        # ============================================

        @function_tool
        async def clear_service_context() -> dict:
            """
            Clear the collected service fields when customer wants to inquire about a different service.
            This preserves customer_info (name, email, phone) but clears service-specific fields.
            """
            try:
                if is_demo_mode():
                    # DEMO MODE: Clear in demo session
                    session = DemoSessionService.get_session(session_id)
                    session["service_context"] = {}

                    logger.info(f"✅ Cleared demo service context")

                    return {
                        "success": True,
                        "message": "Service context cleared, customer info preserved"
                    }
                else:
                    # PRODUCTION MODE: Clear in database
                    return await ContextTools.clear_service_context(
                        db=db,
                        conversation_id=conversation_id
                    )
            except Exception as e:
                logger.error(f"Error clearing service context: {e}")
                return {"success": False, "message": str(e)}

        # ============================================
        # RETURN ALL TOOLS
        # ============================================

        return {
            # Service Tools
            "get_services": get_services,
            "get_services_summary": get_services_summary,
            "get_service_fields": get_service_fields,
            "validate_service_fields": validate_service_fields,

            # Customer Tools
            "get_customer_info": get_customer_info,
            "set_customer_info": set_customer_info,

            # Field Tools
            "set_service_field": set_service_field,

            # Booking Tools
            "get_available_slots": get_available_slots,
            "book_appointment": book_appointment,

            # Appointment Management Tools
            "get_customer_appointments": get_customer_appointments,
            "cancel_appointment": cancel_appointment,
            "reschedule_appointment": reschedule_appointment,

            # Context Tools
            "clear_service_context": clear_service_context,
        }

    def _build_agent_network(
            self,
            business_context: Dict[str, Any],
            conversation_context: Dict[str, Any],
            tools: Dict[str, Any]
    ) -> Agent:
        """
        Build the agent network with proper tool distribution.
        Returns the router agent as the entry point.
        """

        # ============================================
        # BOOKING AGENT TOOLS (Complete booking workflow)
        # ============================================
        booking_tools = [
            # Service Discovery
            tools["get_services"],
            tools["get_service_fields"],
            tools["validate_service_fields"],

            # Field Collection
            tools["set_service_field"],
            tools["clear_service_context"],

            # Customer Info
            tools["get_customer_info"],
            tools["set_customer_info"],

            # Slot & Booking
            tools["get_available_slots"],
            tools["book_appointment"]
        ]

        # ============================================
        # APPOINTMENT MANAGEMENT AGENT TOOLS
        # ============================================
        appointment_tools = [
            tools["get_customer_appointments"],
            tools["cancel_appointment"],
            tools["reschedule_appointment"],
            tools["get_available_slots"]  # For rescheduling
        ]

        # ============================================
        # GENERAL ASSISTANT TOOLS (Read-only)
        # ============================================
        general_tools = [
            tools["get_services_summary"],  # Can show services
            # NO write tools - just informational
        ]

        # ============================================
        # BUILD AGENT NETWORK
        # ============================================

        # Create Booking Agent
        booking = BookingAgent.create(
            business_context=business_context,
            conversation_context=conversation_context,
            tools=booking_tools,
        )

        # Create Appointment Management Agent
        appointment_mgmt = AppointmentManagementAgent.create(
            business_context=business_context,
            conversation_context=conversation_context,
            tools=appointment_tools
        )

        # Create General Assistant Agent
        general = GeneralAssistantAgent.create(
            business_context=business_context,
            conversation_context=conversation_context,
            tools=general_tools,
            booking_agent=booking
        )

        # ✅ ADD THIS: Import handoff at the top of the method
        from agents import handoff, RunContextWrapper

        # ✅ ADD THIS: Define callback for booking handoff
        def on_booking_handoff(ctx: RunContextWrapper):
            """Track when booking flow is initiated"""
            try:
                # Skip for demo mode
                from app.services.demo.demo_session_service import DemoSessionService
                if hasattr(self, '_current_session_id') and DemoSessionService.session_exists(self._current_session_id):
                    logger.info("📊 Skipping booking tracking (demo mode)")
                    return

                # Track booking initiated in production
                if hasattr(self, '_current_db') and hasattr(self, '_current_conversation_id'):
                    from app.services.conversation.conversation_metrics_service import ConversationMetricsService
                    ConversationMetricsService.mark_booking_initiated(
                        db=self._current_db,
                        conversation_id=self._current_conversation_id
                    )
                    logger.info(f"📊 Booking flow initiated: {self._current_conversation_id}")
            except Exception as e:
                logger.error(f"Error tracking booking handoff: {e}")
                # Don't raise - let AI continue normally

        booking_handoff = handoff(
            agent=booking,
            on_handoff=on_booking_handoff
        )

        router = RouterAgent.create(
            business_context=business_context,
            conversation_context=conversation_context,
            specialized_agents=[booking_handoff, appointment_mgmt, general]  # ← booking_handoff instead of booking
        )

        return router

    async def generate_response(
            self,
            messages: List[Dict[str, Any]],
            business_context: Dict[str, Any],
            conversation_context: Dict[str, Any],
            db: Session,
            conversation_id: str,
            customer_phone: str,
            business_id: str,
            session_id: str
    ) -> Dict[str, Any]:
        """Generate AI response with conversation completion signals."""

        self._current_db = db
        self._current_conversation_id = conversation_id
        self._current_session_id = session_id

        tools = self._create_tool_factory(
            db=db,
            conversation_id=conversation_id,
            customer_phone=customer_phone,
            business_id=business_id,
            session_id=session_id
        )

        router_agent = self._build_agent_network(
            business_context=business_context,
            conversation_context=conversation_context,
            tools=tools
        )

        # Get last user message
        user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_message = msg.get("content", "")
                break

        agent_session = SQLiteSession(
            session_id=conversation_id,
            db_path=self.session_storage_path
        )

        try:
            result = await Runner.run(
                router_agent,
                input=user_message,
                session=agent_session
            )

            final_output = result.final_output if hasattr(result, 'final_output') else str(result)

            # ============================================
            # NEW: Detect conversation completion signals
            # ============================================
            conversation_signal = self._detect_conversation_signal(
                user_message=user_message,
                ai_response=final_output,
                conversation_context=conversation_context
            )

            return {
                "content": final_output,
                "function_call": None,
                "role": "assistant",
                "conversation_signal": conversation_signal  # NEW
            }

        except Exception as e:
            logger.error(f"Error in generate_response: {e}")
            import traceback
            traceback.print_exc()
            return {
                "content": f"I apologize, but I encountered an error: {str(e)}. Please try again.",
                "function_call": None,
                "role": "assistant",
                "error": str(e),
                "conversation_signal": "active"  # Keep active on error
            }

    def _detect_conversation_signal(
            self,
            user_message: str,
            ai_response: str,
            conversation_context: Dict[str, Any]
    ) -> str:
        """
        Detect if conversation is naturally ending.

        Returns:
            - "active": Conversation ongoing
            - "soft_close": Natural ending detected
            - "hard_close": Definitive closure (booking completed)
        """
        user_lower = user_message.lower().strip()
        ai_lower = ai_response.lower().strip()

        # Already completed action (booking, cancellation, etc.)
        if conversation_context.get("flow_state") == "action_completed":
            return "hard_close"

        # Customer gratitude/farewell patterns
        gratitude_patterns = [
            "thanks", "thank you", "thx", "ty", "appreciate",
            "perfect", "great", "awesome", "sounds good"
        ]

        farewell_patterns = [
            "bye", "goodbye", "see you", "have a good",
            "talk to you later", "ttyl", "later"
        ]

        decline_patterns = [
            "not interested", "no thanks", "maybe later",
            "i'll think about it", "let me think", "not right now",
            "not now", "another time"
        ]

        # Check customer message for closing signals
        for pattern in gratitude_patterns + farewell_patterns:
            if pattern in user_lower:
                # Customer said thanks/bye
                return "soft_close"

        for pattern in decline_patterns:
            if pattern in user_lower:
                # Customer declined/postponed
                return "soft_close"

        # Check AI response for farewell
        ai_farewell_patterns = [
            "have a great day", "have a good day", "goodbye",
            "take care", "talk to you soon", "see you soon",
            "feel free to reach out", "let me know if you need"
        ]

        for pattern in ai_farewell_patterns:
            if pattern in ai_lower:
                # AI is closing conversation
                return "soft_close"

        # Simple info queries that got answered
        info_query_answered = (
                user_lower in ["what are your hours", "hours?", "when are you open", "location?", "address?",
                               "phone?"]
                and len(ai_response) < 300  # Short factual answer
        )

        if info_query_answered:
            return "soft_close"

        return "active"