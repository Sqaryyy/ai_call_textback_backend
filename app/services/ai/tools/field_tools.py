# app/services/ai/tools/field_tools.py
"""Tools for service field collection with validation guardrails"""
from typing import Dict, List
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)


class FieldTools:
    """Service-specific field collection tools"""

    # Prohibited values that should never be stored
    PROHIBITED_VALUES = [
        "",  # Empty string
        "[not specified]",
        "[not provided]",
        "n/a",
        "na",
        "none",
        "null",
        "undefined",
        "tbd",
        "to be determined",
        "unknown",
        "?",
        "...",
        "—",  # em dash
        "-",  # just a dash
    ]

    @staticmethod
    def get_function_definitions() -> List[Dict]:
        """Return function definitions for OpenAI function calling"""
        return [
            {
                "name": "set_service_field",
                "description": "Store a custom service field value immediately after customer provides it. For name/email/phone, use set_customer_info instead. Call this function EVERY TIME the customer provides information for a required field.",
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
                        },
                        "field_name": {
                            "type": "string",
                            "description": "The exact field name from required_fields (e.g., 'budget_range', 'project_timeline', 'property_type'). Use the 'field' property, not the 'label'."
                        },
                        "field_value": {
                            "type": "string",
                            "description": "The value provided by customer"
                        }
                    },
                    "required": ["conversation_id", "service_id", "field_name", "field_value"]
                }
            }
        ]

    @staticmethod
    def _validate_field_value(field_value: str, field_name: str) -> tuple[bool, str]:
        """
        Validate that a field value is acceptable to store.

        Returns:
            tuple: (is_valid, error_message)
        """
        # Check if value is None
        if field_value is None:
            return False, f"Cannot store None value for {field_name}. Ask the user for this information."

        # Strip whitespace for validation
        cleaned_value = field_value.strip()

        # Check if empty after stripping
        if not cleaned_value:
            return False, f"Cannot store empty value for {field_name}. Ask the user for this information."

        # Check against prohibited values (case-insensitive)
        if cleaned_value.lower() in FieldTools.PROHIBITED_VALUES:
            return False, f"Cannot store placeholder value '{field_value}' for {field_name}. Ask the user for this information."

        # Check for very short values that are likely placeholders
        if len(cleaned_value) <= 1 and cleaned_value not in ["1", "2", "3", "4",
                                                             "5"]:  # Allow single digits for some fields
            return False, f"Value '{field_value}' is too short for {field_name}. Ask the user for more detail."

        return True, ""

    @staticmethod
    async def set_service_field(
            db: Session,
            conversation_id: str,
            service_id: str,
            field_name: str,
            field_value: str
    ) -> Dict:
        """
        Store a collected service field value in conversation state.

        GUARDRAILS:
        - Rejects empty values
        - Rejects placeholder values like "N/A", "[Not specified]", etc.
        - Rejects values that are too short to be meaningful
        - Forces agent to ask user for real information
        """
        try:
            # ============================================
            # GUARDRAIL: Validate field value
            # ============================================
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
            # Store the field value
            # ============================================
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

            # Store the field value (now validated)
            collected_fields[field_name] = field_value.strip()  # Store cleaned value
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
                "collected_fields": collected_fields,
                "field_name": field_name,
                "field_value": field_value.strip()
            }

        except Exception as e:
            logger.error(f"Error storing service field: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "message": f"Failed to store field: {str(e)}",
                "error_type": "system_error"
            }