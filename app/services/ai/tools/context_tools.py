# app/services/ai/tools/context_tools.py
"""Tools for managing conversation context"""
from typing import Dict, List
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)


class ContextTools:
    """Conversation context management tools"""

    @staticmethod
    def get_function_definitions() -> List[Dict]:
        """Return function definitions for OpenAI function calling"""
        return [
            {
                "name": "clear_service_context",
                "description": "Clear the collected service fields when customer wants to inquire about a different service. Use this when customer switches from one service to another to avoid mixing collected information. This preserves customer_info (name, email, phone) but clears service-specific fields.",
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
    async def clear_service_context(
            db: Session,
            conversation_id: str
    ) -> Dict:
        """Clear service context when customer asks about a different service"""
        try:
            from app.models.conversation.conversation_state import ConversationState

            state = db.query(ConversationState).filter(
                ConversationState.id == conversation_id
            ).first()

            if not state:
                logger.warning(f"No conversation state found for {conversation_id}")
                return {
                    "success": False,
                    "message": "Conversation state not found"
                }

            # Keep customer_info but clear service_context
            customer_info = state.state_data.get("customer_info", {})
            state.state_data = {
                "customer_info": customer_info,
                "service_context": {}
            }




            logger.info(f"✅ Cleared service context for conversation {conversation_id}")

            return {
                "success": True,
                "message": "Service context cleared, customer info preserved"
            }

        except Exception as e:

            logger.error(f"Error clearing service context: {e}")
            return {
                "success": False,
                "message": "Failed to clear service context"
            }