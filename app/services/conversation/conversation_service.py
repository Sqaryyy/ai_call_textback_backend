# ============================================================================
# app/services/conversation/conversation_service.py
# ============================================================================
"""Service for managing conversations"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict
from uuid import uuid4
from sqlalchemy.orm import Session
from app.models.conversation import Conversation

logger = logging.getLogger(__name__)


class ConversationService:
    """Handles conversation management operations"""

    @staticmethod
    def find_or_create_conversation(
            db: Session,
            customer_phone: str,
            business_phone: str,
            business_id: str
    ) -> Conversation:
        """Find active conversation or create new one"""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)

        conversation = db.query(Conversation).filter(
            Conversation.customer_phone == customer_phone,
            Conversation.business_phone == business_phone,
            Conversation.is_active == True,
            Conversation.created_at > cutoff_time
        ).first()

        if conversation:
            logger.info(f"Found existing conversation: {conversation.id}")
            return conversation

        # Generate a unique conversation_sid
        conversation_sid = f"CONV_{uuid4().hex[:16].upper()}"

        conversation = Conversation(
            id=str(uuid4()),
            conversation_sid=conversation_sid,  # ← Added this field
            customer_phone=customer_phone,
            business_phone=business_phone,
            business_id=business_id,
            status="active",
            flow_state="greeting",
            customer_info={},
            context={},
            message_count=0,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            is_active=True
        )

        db.add(conversation)
        db.commit()
        db.refresh(conversation)

        logger.info(f"Created new conversation: {conversation.id} (SID: {conversation_sid})")
        return conversation

    @staticmethod
    def update_conversation(
            db: Session,
            conversation_id: str,
            updates: Dict
    ) -> Optional[Conversation]:
        """Update conversation with new data"""
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id
        ).first()

        if not conversation:
            return None

        for key, value in updates.items():
            if hasattr(conversation, key):
                setattr(conversation, key, value)

        conversation.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(conversation)
        return conversation

    @staticmethod
    def increment_message_count(db: Session, conversation_id: str) -> None:
        """Increment message count for conversation"""
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id
        ).first()
        if conversation:
            conversation.message_count += 1
            db.commit()