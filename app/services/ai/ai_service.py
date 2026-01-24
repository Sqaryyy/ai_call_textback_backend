"""
AI Service - OpenAI Agents SDK implementation
Main interface for AI-powered conversation handling.
"""

from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.services.ai.agents_ai_service import AgentsAIService


class AIService:
    """
    AI Service using OpenAI Agents SDK.
    Provides multi-agent conversation handling with specialized agents.
    """

    def __init__(self):
        """Initialize the AI service with Agents SDK implementation."""
        self._agents_service = AgentsAIService()

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
        """
        Generate AI response using multi-agent system.

        Args:
            messages: Conversation history
            business_context: Business configuration and context
            conversation_context: Current conversation state
            db: Database session
            conversation_id: Conversation ID
            customer_phone: Customer phone number
            business_id: Business ID
            session_id: Demo session ID

        Returns:
            Dict with AI response containing:
                - content: Response text
                - function_call: None (SDK handles internally)
                - role: "assistant"
        """
        return await self._agents_service.generate_response(
            messages=messages,
            business_context=business_context,
            conversation_context=conversation_context,
            db=db,
            conversation_id=conversation_id,
            customer_phone=customer_phone,
            business_id=business_id,
            session_id=session_id
        )

    async def get_customer_info(
        self,
        db: Session,
        conversation_id: str
    ) -> Dict[str, Any]:
        """
        Get customer information from conversation state.

        Args:
            db: Database session
            conversation_id: Conversation ID

        Returns:
            Dict with customer info
        """
        from app.services.conversation.conversation_state_service import ConversationStateService

        conv_state = ConversationStateService.get_or_create_state(db, conversation_id)
        customer_info = conv_state.state_data.get("customer_info", {})

        return {
            "success": True,
            "customer_info": customer_info,
            "has_name": bool(customer_info.get("name")),
            "has_email": bool(customer_info.get("email")),
            "has_phone": bool(customer_info.get("phone"))
        }

    async def set_customer_info(
        self,
        db: Session,
        conversation_id: str,
        customer_name: Optional[str] = None,
        customer_email: Optional[str] = None,
        customer_phone: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Save customer information to conversation state.

        Args:
            db: Database session
            conversation_id: Conversation ID
            customer_name: Customer name
            customer_email: Customer email
            customer_phone: Customer phone

        Returns:
            Dict with success status
        """
        from app.services.conversation.conversation_state_service import ConversationStateService

        try:
            conv_state = ConversationStateService.get_or_create_state(db, conversation_id)
            customer_info = conv_state.state_data.get("customer_info", {})

            # Update with new values
            if customer_name:
                customer_info["name"] = customer_name
            if customer_email:
                customer_info["email"] = customer_email
            if customer_phone:
                customer_info["phone"] = customer_phone

            # Save back to state
            ConversationStateService.update_state(
                db=db,
                conversation_id=conversation_id,
                flow_state=conv_state.flow_state,
                state_data={
                    **conv_state.state_data,
                    "customer_info": customer_info
                }
            )

            return {
                "success": True,
                "customer_info": customer_info,
                "message": "Customer information saved"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to save customer info: {str(e)}"
            }