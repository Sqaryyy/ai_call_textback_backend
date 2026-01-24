# app/services/ai/tools/customer_tools.py
"""Tools for customer information management"""
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)


class CustomerTools:
    """Customer information storage and retrieval tools"""

    @staticmethod
    def get_function_definitions() -> List[Dict]:
        """Return function definitions for OpenAI function calling"""
        return [
            {
                "name": "set_customer_info",
                "description": "Store standard customer information (name, email, phone) when customer provides it. Call this immediately after customer gives you their details.",
                "parameters": {
                    "type": "object",
                    "properties": {
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
                "description": "Check what standard customer information is already known (name, email, phone). Call this BEFORE asking for customer details to avoid asking for information you already have.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "conversation_id": {
                            "type": "string",
                            "description": "The conversation ID"
                        }
                    },
                    "required": ["conversation_id"]
                }
            }
        ]

    @staticmethod
    async def set_customer_info(
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

            logger.info(f"✅ Stored customer info: {customer_info}")

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

    @staticmethod
    async def get_customer_info(
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
                "has_email": bool(customer_info.get("email")),
                "has_phone": bool(customer_info.get("phone"))
            }
        except Exception as e:
            logger.error(f"Error fetching customer info: {e}")
            return {
                "success": False,
                "customer_info": {},
                "has_name": False,
                "has_email": False,
                "has_phone": False
            }