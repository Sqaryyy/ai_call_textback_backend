# app/services/business/business_service.py
"""Service for managing business operations"""
from datetime import timezone
from app.models.business.business import Business
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from sqlalchemy.orm import Session
import logging
from uuid import UUID

logger=logging.getLogger(__name__)

class BusinessService:
    """Handles business-related operations"""

    # Onboarding steps configuration - UPDATED TO 2 STEPS
    ONBOARDING_STEPS = {
        "business_info": {
            "label": "Business Information & Hours",
            "description": "Add your business name, type, contact info, timezone, and operating hours",
            "order": 1
        },
        "calendar_connection": {
            "label": "Connect Your Calendar",
            "description": "Sync your calendar (Google, Outlook, Calendly, etc.) for availability",
            "order": 2
        }
    }

    @staticmethod
    def create_default_business(db: Session, user_id: UUID) -> Business:
        """
        Create a default business for a new user during platform invite signup.

        This is called automatically after user registration to ensure every user
        starts with at least one business. Users can create additional businesses later.

        Args:
            db: Database session
            user_id: The user who owns this business (for logging/reference)

        Returns:
            The created Business object
        """
        business = Business(
            name="My Business",
            phone_number=None,
            business_type="",
            timezone="UTC",
            onboarding_status={
                "completed_steps": [],
                "current_step": "business_info",
                "started_at": datetime.utcnow().isoformat(),
                "completed_at": None
            }
        )
        print(business.phone_number)
        db.add(business)
        db.flush()  # Get the ID without committing yet

        return business

    @staticmethod
    def get_onboarding_status(db: Session, business_id: UUID) -> dict:
        """
        Get the current onboarding status for a business with detailed step information.

        Args:
            db: Database session
            business_id: The business ID

        Returns:
            {
                "completed_steps": ["business_info"],
                "current_step": "calendar_connection",
                "progress_percentage": 50,
                "is_completed": False,
                "started_at": "2024-01-15T10:30:00",
                "completed_at": None,
                "steps": [
                    {
                        "id": "business_info",
                        "label": "Business Information & Hours",
                        "description": "...",
                        "order": 1,
                        "completed": True
                    },
                    {
                        "id": "calendar_connection",
                        "label": "Connect Your Calendar",
                        "description": "...",
                        "order": 2,
                        "completed": False
                    }
                ]
            }
        """
        business = db.query(Business).filter(Business.id == business_id).first()

        if not business:
            return None

        status = business.onboarding_status or {}
        completed_steps = status.get("completed_steps", [])

        # Build detailed steps list
        steps = []
        for step_id, step_info in BusinessService.ONBOARDING_STEPS.items():
            steps.append({
                "id": step_id,
                "label": step_info["label"],
                "description": step_info["description"],
                "order": step_info["order"],
                "completed": step_id in completed_steps
            })

        # Sort by order
        steps.sort(key=lambda x: x["order"])

        # Calculate progress
        total_steps = len(BusinessService.ONBOARDING_STEPS)
        progress_percentage = (len(completed_steps) / total_steps * 100) if total_steps > 0 else 0

        return {
            "completed_steps": completed_steps,
            "current_step": status.get("current_step", "business_info"),
            "progress_percentage": round(progress_percentage),
            "is_completed": len(completed_steps) == total_steps,
            "started_at": status.get("started_at"),
            "completed_at": status.get("completed_at"),
            "steps": steps
        }

    @staticmethod
    def mark_onboarding_step_complete(
            db: Session,
            business_id: UUID,
            step_id: str
    ) -> dict:
        """
        Mark an onboarding step as completed and update current_step.
        """
        if step_id not in BusinessService.ONBOARDING_STEPS:
            raise ValueError(f"Invalid onboarding step: {step_id}")

        business = db.query(Business).filter(Business.id == business_id).first()

        if not business:
            raise ValueError(f"Business not found: {business_id}")

        status = business.onboarding_status or {}
        completed_steps = status.get("completed_steps", [])

        # Add step if not already completed
        if step_id not in completed_steps:
            completed_steps.append(step_id)

        # Find next incomplete step
        next_step = None
        for step_id_check, step_info in sorted(
                BusinessService.ONBOARDING_STEPS.items(),
                key=lambda x: x[1]["order"]
        ):
            if step_id_check not in completed_steps:
                next_step = step_id_check
                break

        # Update status
        status["completed_steps"] = completed_steps
        status["current_step"] = next_step or "business_info"

        # Mark as fully completed if all steps done
        if next_step is None and status.get("completed_at") is None:
            status["completed_at"] = datetime.utcnow().isoformat()

        business.onboarding_status = status

        # IMPORTANT: Mark the column as modified for SQLAlchemy to detect the change
        from sqlalchemy.orm import attributes
        attributes.flag_modified(business, "onboarding_status")

        db.commit()
        db.refresh(business)

        return BusinessService.get_onboarding_status(db, business_id)

    @staticmethod
    def get_business_by_phone(db: Session, phone_number: str) -> Optional[Business]:
        """Get business by phone number"""
        return db.query(Business).filter(
            Business.phone_number == phone_number,
            Business.is_active == True
        ).first()

    @staticmethod
    def get_business_context(db: Session, business_id: str) -> Dict:
        """Get comprehensive business context for AI"""
        business = db.query(Business).filter(Business.id == business_id).first()
        if not business:
            return {}

        # Build rich context from structured fields
        context = {
            "business_name": business.name,
            "business_type": business.business_type,
            "timezone": business.timezone,

            # NEW: Structured context
            "business_profile": business.business_profile or {},
            "service_catalog": business.service_catalog or {},
            "conversation_policies": business.conversation_policies or {},
            "quick_responses": business.quick_responses or {},

            # Legacy support
            "services": business.services or [],
            "booking_settings": business.booking_settings or {},

            # Override instructions (still available for edge cases)
            "ai_instructions": business.ai_instructions or ""
        }

        return context

    @staticmethod
    def get_service_by_name(business_context: Dict, service_name: str) -> Optional[Dict]:
        """Find a service in catalog by name (fuzzy match)"""
        service_catalog = business_context.get("service_catalog", {})
        services = service_catalog.get("services", [])

        service_name_lower = service_name.lower()

        # Exact match first
        for service in services:
            if service["name"].lower() == service_name_lower:
                return service

        # Partial match
        for service in services:
            if service_name_lower in service["name"].lower() or service["name"].lower() in service_name_lower:
                return service

        return None

    async def get_services(
            self,
            db: Session,
            business_id: str
    ) -> List[str]:
        """Fetch list of services offered by the business"""
        try:
            from app.models.business.business import Business
            business = db.query(Business).filter(Business.id == business_id).first()
            if business and business.service_catalog:
                return list(business.service_catalog.keys())
            return []
        except Exception as e:
            logger.error(f"Error fetching services for business {business_id}: {e}")
            return []

    @staticmethod
    def should_show_price(service: Dict) -> bool:
        """Determine if price should be shown for a service"""
        return service.get("show_price", False) and service.get("price_display")

    @staticmethod
    def requires_consultation(service: Dict) -> bool:
        """Check if service requires consultation"""
        return service.get("requires_consultation", False)

    @staticmethod
    def get_primary_booking_flow(business_context: Dict) -> str:
        """Get the primary booking flow for the business"""
        profile = business_context.get("business_profile", {})
        return profile.get("primary_booking_flow", "hybrid")

    @staticmethod
    def format_services_for_display(business_context: Dict) -> str:
        """Format services for AI to present to customer"""
        service_catalog = business_context.get("service_catalog", {})
        services = service_catalog.get("services", [])

        if not services:
            # Fallback to legacy services list
            legacy_services = business_context.get("services", [])
            return ", ".join(legacy_services) if legacy_services else "various services"

        formatted = []
        for service in services:
            service_text = service["name"]

            if service.get("description"):
                service_text += f" - {service['description']}"

            if BusinessService.should_show_price(service):
                service_text += f" ({service['price_display']})"

            formatted.append(service_text)

        return "\n".join(formatted)

    @staticmethod
    def get_policy_text(business_context: Dict, policy_type: str) -> Optional[str]:
        """Get formatted policy text for common queries"""
        policies = business_context.get("conversation_policies", {})

        if policy_type == "cancellation":
            cancel_policy = policies.get("cancellation", {})
            return cancel_policy.get("policy_text")

        elif policy_type == "rescheduling":
            reschedule_policy = policies.get("rescheduling", {})
            return reschedule_policy.get("policy_text")

        elif policy_type == "payment":
            payment = policies.get("payment", {})
            return payment.get("payment_message")

        elif policy_type == "emergency":
            emergency = policies.get("emergency_handling", {})
            return emergency.get("emergency_message")

        return None

    @staticmethod
    def get_quick_response(business_context: Dict, response_type: str) -> Optional[str]:
        """Get quick response for common questions"""
        quick_responses = business_context.get("quick_responses", {})

        response_data = quick_responses.get(response_type, {})
        if response_data.get("enabled"):
            return response_data.get("message")

        return None

    @staticmethod
    def search_faq(business_context: Dict, question: str) -> Optional[str]:
        """Search custom FAQs for matching answer"""
        quick_responses = business_context.get("quick_responses", {})
        custom_faqs = quick_responses.get("custom_faqs", [])

        question_lower = question.lower()

        for faq in custom_faqs:
            faq_question = faq.get("question", "").lower()
            if question_lower in faq_question or faq_question in question_lower:
                return faq.get("answer")

        return None

    async def get_available_slots(
            self,
            db: Session,
            business_id: str,
            service: str,
            duration_minutes: int = 30,
            start_date: Optional[str] = None,  # ISO date/datetime string
            end_date: Optional[str] = None,  # ISO date/datetime string
            days_ahead: Optional[int] = None,  # Fallback if no dates provided
            limit: int = 20
    ) -> list[dict]:
        """
        Fetch available slots for AI.

        Priority:
        1. If start_date provided: use it as start
        2. Otherwise: use current time

        For end_date:
        1. If end_date provided: use it
        2. If only start_date provided (no end_date): return slots for that day only
        3. If days_ahead provided: add to start
        4. Default: 7 days ahead
        """

        # Determine start_date
        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
                # If time not specified, start from business hours
                if start_dt.hour == 0 and start_dt.minute == 0:
                    start_dt = start_dt.replace(hour=8, minute=0)
            except ValueError:
                logger.error(f"Invalid start_date format: {start_date}")
                return []
        else:
            start_dt = datetime.now(timezone.utc)

        # Determine end_date
        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
                # If time not specified, go to end of day
                if end_dt.hour == 0 and end_dt.minute == 0:
                    end_dt = end_dt.replace(hour=23, minute=59)
            except ValueError:
                logger.error(f"Invalid end_date format: {end_date}")
                return []
        elif start_date and not days_ahead:
            # If only start_date given, get slots for that day only
            end_dt = start_dt.replace(hour=23, minute=59, second=59)
        elif days_ahead is not None:
            if days_ahead == 0:
                end_dt = start_dt.replace(hour=23, minute=59, second=59)
            else:
                end_dt = start_dt + timedelta(days=days_ahead)
        else:
            # Default: 7 days ahead
            end_dt = start_dt + timedelta(days=7)

        # Ensure valid time range
        if end_dt <= start_dt:
            end_dt = start_dt + timedelta(hours=8)

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

                # Apply limit and format
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