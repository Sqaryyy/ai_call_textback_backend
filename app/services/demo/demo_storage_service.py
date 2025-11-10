"""
Demo Storage Service - Handles logging demo conversations for analytics
File: app/services/demo/demo_storage_service.py
"""
import logging
from typing import Optional, Dict, List, Any
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
import uuid

from app.models.demo import DemoConversation, DemoMessage, DemoAIContextLog

logger = logging.getLogger(__name__)


class DemoStorageService:
    """Service for storing and retrieving demo conversation data"""

    @staticmethod
    def create_demo_conversation(
            db: Session,
            session_id: str,
            business_id: str,
            customer_phone: str
    ) -> DemoConversation:
        """Create a new demo conversation session"""
        try:
            conversation = DemoConversation(
                session_id=session_id,
                business_id=business_id,
                customer_phone=customer_phone
            )
            db.add(conversation)
            db.commit()
            db.refresh(conversation)

            logger.info(f"📝 Created demo conversation: {session_id}")
            return conversation

        except Exception as e:
            db.rollback()
            logger.error(f"Error creating demo conversation: {e}")
            raise

    @staticmethod
    def get_demo_conversation(
            db: Session,
            session_id: str
    ) -> Optional[DemoConversation]:
        """Get demo conversation by session_id"""
        return db.query(DemoConversation).filter(
            DemoConversation.session_id == session_id
        ).first()

    @staticmethod
    def log_demo_message(
            db: Session,
            demo_conversation_id: str,
            role: str,
            content: str
    ) -> DemoMessage:
        """Log a message in demo conversation"""
        try:
            message = DemoMessage(
                demo_conversation_id=demo_conversation_id,
                role=role,
                content=content
            )
            db.add(message)
            db.commit()
            db.refresh(message)

            logger.debug(f"💬 Logged demo message: {role}")
            return message

        except Exception as e:
            db.rollback()
            logger.error(f"Error logging demo message: {e}")
            raise

    @staticmethod
    def log_ai_context(
            db: Session,
            demo_conversation_id: str,
            demo_message_id: Optional[str],
            business_context: Dict,
            conversation_context: Dict,
            messages_sent_to_ai: List[Dict],
            rag_context: Optional[str] = None,
            function_calls: Optional[List[Dict]] = None,
            ai_response: Optional[str] = None,
            finish_reason: Optional[str] = None
    ) -> DemoAIContextLog:
        """
        Log complete AI context for analytics.
        This captures everything that was fed to the AI for a response.
        """
        try:
            log_entry = DemoAIContextLog(
                demo_conversation_id=demo_conversation_id,
                demo_message_id=demo_message_id,
                business_context=business_context,
                conversation_context=conversation_context,
                rag_context=rag_context,
                messages_sent_to_ai=messages_sent_to_ai,
                function_calls=function_calls or [],
                ai_response=ai_response,
                finish_reason=finish_reason
            )
            db.add(log_entry)
            db.commit()
            db.refresh(log_entry)

            logger.debug(f"🤖 Logged AI context: {len(function_calls or [])} function calls")
            return log_entry

        except Exception as e:
            db.rollback()
            logger.error(f"Error logging AI context: {e}")
            raise

    @staticmethod
    def get_conversation_history(
            db: Session,
            session_id: str
    ) -> Optional[Dict]:
        """
        Get full conversation history with all AI context.
        Useful for debugging and analysis.
        """
        conversation = DemoStorageService.get_demo_conversation(db, session_id)
        if not conversation:
            return None

        messages = db.query(DemoMessage).filter(
            DemoMessage.demo_conversation_id == conversation.id
        ).order_by(DemoMessage.created_at).all()

        ai_logs = db.query(DemoAIContextLog).filter(
            DemoAIContextLog.demo_conversation_id == conversation.id
        ).order_by(DemoAIContextLog.created_at).all()

        return {
            "session_id": conversation.session_id,
            "business_id": str(conversation.business_id),
            "customer_phone": conversation.customer_phone,
            "created_at": conversation.created_at.isoformat(),
            "messages": [
                {
                    "id": str(msg.id),
                    "role": msg.role,
                    "content": msg.content,
                    "created_at": msg.created_at.isoformat()
                }
                for msg in messages
            ],
            "ai_context_logs": [
                {
                    "id": str(log.id),
                    "business_context": log.business_context,
                    "conversation_context": log.conversation_context,
                    "rag_context": log.rag_context,
                    "messages_sent_to_ai": log.messages_sent_to_ai,
                    "function_calls": log.function_calls,
                    "ai_response": log.ai_response,
                    "finish_reason": log.finish_reason,
                    "created_at": log.created_at.isoformat()
                }
                for log in ai_logs
            ]
        }

    @staticmethod
    def cleanup_old_demos(db: Session, days: int = 90) -> int:
        """
        Manually cleanup demos older than specified days.
        Returns number of deleted conversations.
        """
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

            old_conversations = db.query(DemoConversation).filter(
                DemoConversation.created_at < cutoff_date
            ).all()

            count = len(old_conversations)

            for conv in old_conversations:
                db.delete(conv)

            db.commit()
            logger.info(f"🗑️ Cleaned up {count} old demo conversations")
            return count

        except Exception as e:
            db.rollback()
            logger.error(f"Error cleaning up old demos: {e}")
            raise