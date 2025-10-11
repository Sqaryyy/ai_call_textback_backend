# app/services/message/message_service.py
"""Message management service"""
import logging
import uuid
from typing import Union

from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from datetime import datetime, timezone

from app.models.message import Message

logger = logging.getLogger(__name__)


class MessageService:
    @staticmethod
    def create_message(
            db: Session,
            message_sid: str,
            conversation_id: Union[str, uuid.UUID],
            sender_phone: str,
            recipient_phone: str,
            role: str,
            content: str,
            is_inbound: bool,
            media_urls: Optional[List[str]] = None,
            message_status: str = "received",
            error_code: Optional[str] = None,
            error_message: Optional[str] = None,
            message_metadata: Optional[Dict] = None,
    ) -> Message:
        """Persist a message in the database"""
        # Convert conversation_id to UUID if it's a string
        if isinstance(conversation_id, str):
            conversation_id = uuid.UUID(conversation_id)

        message = Message(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            sender_phone=sender_phone,
            recipient_phone=recipient_phone,
            role=role,
            content=content,
            is_inbound=is_inbound,
            message_status=message_status,
            error_code=error_code,
            error_message=error_message,
            media_urls=media_urls or [],
            message_metadata=message_metadata or {},
            created_at=datetime.now(timezone.utc),
        )

        db.add(message)
        db.commit()
        db.refresh(message)

        logger.info(
            f"Message logged: {message.id} "
            f"({'inbound' if is_inbound else 'outbound'}) "
            f"status={message_status}"
        )
        return message

    @staticmethod
    def get_conversation_messages(db: Session, conversation_id: Union[str, uuid.UUID]) -> List[Message]:
        """Fetch all messages for a conversation"""
        # Convert conversation_id to UUID if it's a string
        if isinstance(conversation_id, str):
            conversation_id = uuid.UUID(conversation_id)

        stmt = select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.asc())
        result = db.execute(stmt).scalars().all()
        return result  # type: List[Message]

    @staticmethod
    def format_messages_for_ai(messages: List[Message]) -> List[Dict]:
        """
        Convert stored messages into AI-friendly format for OpenAI API.
        Maps database roles to OpenAI-compatible roles.
        """
        # Map database roles to OpenAI API roles
        ROLE_MAPPING = {
            "customer": "user",  # Customer messages become "user" messages
            "assistant": "assistant",  # AI responses stay as "assistant"
            "system": "system"  # System messages stay as "system"
        }

        return [
            {
                "role": ROLE_MAPPING.get(m.role, "user"),  # Default to "user" if unknown role
                "content": m.content,
                "metadata": m.message_metadata,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ]