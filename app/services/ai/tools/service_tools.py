# app/services/ai/tools/service_tools.py
"""Tools for service-related operations"""
from typing import Dict, List
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)


class ServiceTools:
    """Service information and validation tools"""

    @staticmethod
    def get_function_definitions() -> List[Dict]:
        """Return function definitions for OpenAI function calling"""
        return [
            {
                "name": "get_services",
                "description": "Fetch the list of services offered by the business. ALWAYS call this FIRST when customer asks about booking. The response includes an 'id' field (UUID string) which you MUST use in subsequent calls.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "business_id": {
                            "type": "string",
                            "description": "The business ID"
                        }
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
                        "conversation_id": {
                            "type": "string",
                            "description": "The conversation ID"
                        },
                        "service_id": {
                            "type": "string",
                            "description": "CRITICAL: Use the exact UUID string from the 'id' field in get_services response. DO NOT use the service name or make up an ID."
                        }
                    },
                    "required": ["conversation_id", "service_id"]
                }
            },
            {
                "name": "validate_service_fields",
                "description": "Validate that ALL required fields have been collected before booking. Checks BOTH customer_info (name, email, phone) AND service-specific fields. ALWAYS call this before attempting to book.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "conversation_id": {
                            "type": "string",
                            "description": "The conversation ID"
                        },
                        "service_id": {
                            "type": "string",
                            "description": "CRITICAL: Use the exact UUID string from the 'id' field in get_services response."
                        }
                    },
                    "required": ["conversation_id", "service_id"]
                }
            }
        ]

    @staticmethod
    async def get_services(db: Session, business_id: str) -> List[Dict]:
        """Fetch list of services offered by the business"""
        try:
            from app.models.business.service import Service

            services_query = db.query(Service).filter(
                Service.business_id == business_id,
                Service.is_active == True
            ).order_by(Service.display_order, Service.name).all()

            if not services_query:
                logger.warning(f"No services found for business {business_id}")
                return []

            services = []
            for service in services_query:
                service_data = {
                    "id": str(service.id),
                    "name": service.name,
                    "price": service.formatted_price,
                    "duration_minutes": service.duration if service.duration else 30,
                    "description": service.description or "",
                    "booking_type": service.booking_type.value,
                    "required_fields": service.required_fields or []
                }

                if service.booking_type.value == 'consultation_required':
                    service_data["consultation_duration"] = service.consultation_duration
                    service_data["consultation_price"] = (
                        f"${service.consultation_price:.2f}" if service.consultation_price else "Free"
                    )

                services.append(service_data)

            logger.info(f"📋 Retrieved {len(services)} services for business {business_id}")
            return services

        except Exception as e:
            logger.error(f"Error fetching services: {e}")
            import traceback
            traceback.print_exc()
            return []

    @staticmethod
    async def get_service_fields(
            db: Session,
            conversation_id: str,
            service_id: str
    ) -> Dict:
        """Get all collected fields for a service and check what's still needed"""
        try:
            from app.services.conversation.conversation_state_service import ConversationStateService
            from app.models.business.service import Service

            conv_state = ConversationStateService.get_or_create_state(
                db=db,
                conversation_id=conversation_id
            )

            service_context = conv_state.state_data.get("service_context", {})
            collected_fields = service_context.get("collected_fields", {})

            service = db.query(Service).filter(Service.id == service_id).first()

            if not service:
                return {
                    "success": False,
                    "message": "Service not found"
                }

            required_fields = service.required_fields or []

            missing_fields = []
            for field_def in required_fields:
                field_name = field_def.get("field")
                if field_def.get("required", True):
                    if not collected_fields.get(field_name):
                        missing_fields.append(field_def)

            all_collected = len(missing_fields) == 0

            logger.info(
                f"📋 Service {service_id}: {len(collected_fields)} fields collected, "
                f"{len(missing_fields)} missing"
            )

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

    @staticmethod
    async def validate_service_fields(
            db: Session,
            conversation_id: str,
            service_id: str
    ) -> Dict:
        """
        Validate that all required fields are collected.
        Checks BOTH customer_info (name, email, phone) AND service_context (service-specific fields).
        """
        try:
            from app.services.conversation.conversation_state_service import ConversationStateService
            from app.models.business.service import Service

            conv_state = ConversationStateService.get_or_create_state(
                db=db,
                conversation_id=conversation_id
            )

            # Get both data sources
            customer_info = conv_state.state_data.get("customer_info", {})
            service_context = conv_state.state_data.get("service_context", {})
            service_fields = service_context.get("collected_fields", {})

            # Merge both sources - customer_info takes precedence for basic fields
            all_collected_data = {**service_fields, **customer_info}

            logger.info(f"🔍 Validating with merged data: {list(all_collected_data.keys())}")

            service = db.query(Service).filter(Service.id == service_id).first()

            if not service:
                return {
                    "valid": False,
                    "message": "Service not found",
                    "missing_fields": [],
                    "can_proceed": False
                }

            # Check required fields against merged data
            required_fields = service.required_fields or []
            missing_fields = []

            for field_def in required_fields:
                field_name = field_def.get("field")
                if field_def.get("required", True):
                    field_value = all_collected_data.get(field_name)
                    if not field_value or (isinstance(field_value, str) and not field_value.strip()):
                        missing_fields.append(field_def)
                        logger.warning(f"⚠️ Missing required field: {field_name}")

            is_valid = len(missing_fields) == 0

            if is_valid:
                logger.info(f"✅ All required fields collected for service {service.name}")
                return {
                    "valid": True,
                    "message": "All required fields collected",
                    "missing_fields": [],
                    "can_proceed": True,
                    "collected_data": all_collected_data
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
            import traceback
            traceback.print_exc()
            return {
                "valid": False,
                "message": "Validation error",
                "missing_fields": [],
                "can_proceed": False
            }