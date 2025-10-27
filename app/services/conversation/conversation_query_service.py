# ============================================================================
# FILE 1: app/services/conversation_query_service.py
# Pure business logic for conversation reads - no FastAPI dependencies
# ============================================================================
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID

from app.models.conversation import Conversation
from app.models.message import Message


class ConversationQueryService:
    """Service layer for conversation read operations."""

    @staticmethod
    def list_conversations(
            db: Session,
            business_id: UUID,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None,
            status: Optional[str] = None,
            customer_phone: Optional[str] = None,
            flow_state: Optional[str] = None,
            skip: int = 0,
            limit: int = 50
    ) -> Dict[str, Any]:
        """Get paginated list of conversations with filters."""
        query = db.query(Conversation).filter(Conversation.business_id == business_id)

        if start_date:
            query = query.filter(Conversation.created_at >= start_date)
        if end_date:
            query = query.filter(Conversation.created_at <= end_date)
        if status:
            query = query.filter(Conversation.status == status)
        if customer_phone:
            query = query.filter(Conversation.customer_phone == customer_phone)
        if flow_state:
            query = query.filter(Conversation.flow_state == flow_state)

        query = query.order_by(desc(Conversation.created_at))
        total = query.count()
        conversations = query.offset(skip).limit(limit).all()

        return {
            "business_id": str(business_id),
            "total_conversations": total,
            "page": {
                "skip": skip,
                "limit": limit,
                "total_pages": (total + limit - 1) // limit if total > 0 else 0
            },
            "filters": {
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "status": status,
                "customer_phone": customer_phone,
                "flow_state": flow_state
            },
            "conversations": [ConversationQueryService._serialize_conversation(conv) for conv in conversations]
        }

    @staticmethod
    def get_conversation_by_id(
            db: Session,
            business_id: UUID,
            conversation_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """Get a single conversation by ID. Returns None if not found."""
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.business_id == business_id
        ).first()

        if not conversation:
            return None

        return ConversationQueryService._serialize_conversation(conversation)

    @staticmethod
    def get_conversation_messages(
            db: Session,
            business_id: UUID,
            conversation_id: UUID,
            skip: int = 0,
            limit: int = 100
    ) -> Optional[Dict[str, Any]]:
        """Get all messages for a conversation. Returns None if conversation not found."""
        # Verify conversation belongs to this business
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.business_id == business_id
        ).first()

        if not conversation:
            return None

        # Get messages for this conversation
        query = db.query(Message).filter(
            Message.conversation_id == conversation_id
        ).order_by(Message.created_at.asc())

        total = query.count()
        messages = query.offset(skip).limit(limit).all()

        return {
            "conversation_id": str(conversation_id),
            "customer_phone": conversation.customer_phone,
            "total_messages": total,
            "page": {
                "skip": skip,
                "limit": limit,
                "total_pages": (total + limit - 1) // limit if total > 0 else 0
            },
            "messages": [
                {
                    "id": str(msg.id),
                    "sender_phone": msg.sender_phone,
                    "recipient_phone": msg.recipient_phone,
                    "role": msg.role,
                    "content": msg.content,
                    "message_status": msg.message_status,
                    "is_inbound": msg.is_inbound,
                    "media_urls": msg.media_urls,
                    "message_metadata": msg.message_metadata,
                    "error_code": msg.error_code,
                    "error_message": msg.error_message,
                    "created_at": msg.created_at.isoformat(),
                    "updated_at": msg.updated_at.isoformat()
                }
                for msg in messages
            ]
        }

    @staticmethod
    def search_conversations_by_phone(
            db: Session,
            business_id: UUID,
            phone: str,
            skip: int = 0,
            limit: int = 20
    ) -> Dict[str, Any]:
        """Search for all conversations with a specific phone number."""
        query = db.query(Conversation).filter(
            Conversation.business_id == business_id,
            Conversation.customer_phone == phone
        ).order_by(desc(Conversation.created_at))

        total = query.count()
        conversations = query.offset(skip).limit(limit).all()

        return {
            "business_id": str(business_id),
            "phone": phone,
            "total_conversations": total,
            "page": {
                "skip": skip,
                "limit": limit,
                "total_pages": (total + limit - 1) // limit if total > 0 else 0
            },
            "conversations": [
                {
                    "id": str(conv.id),
                    "conversation_sid": conv.conversation_sid,
                    "status": conv.status,
                    "flow_state": conv.flow_state,
                    "message_count": conv.message_count,
                    "is_active": conv.is_active,
                    "created_at": conv.created_at.isoformat(),
                    "updated_at": conv.updated_at.isoformat()
                }
                for conv in conversations
            ]
        }

    @staticmethod
    def get_conversation_stats(
            db: Session,
            business_id: UUID,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Calculate conversation statistics for a business."""
        query = db.query(Conversation).filter(Conversation.business_id == business_id)

        if start_date:
            query = query.filter(Conversation.created_at >= start_date)
        if end_date:
            query = query.filter(Conversation.created_at <= end_date)

        conversations = query.all()

        if not conversations:
            return {
                "business_id": str(business_id),
                "period": {
                    "start": start_date.isoformat() if start_date else None,
                    "end": end_date.isoformat() if end_date else None
                },
                "total_conversations": 0,
                "active_conversations": 0,
                "by_status": {},
                "by_flow_state": {},
                "unique_customers": 0,
                "avg_messages_per_conversation": 0
            }

        # Calculate statistics
        total_conversations = len(conversations)

        by_status = {}
        for conv in conversations:
            status = conv.status or "unknown"
            by_status[status] = by_status.get(status, 0) + 1

        by_flow_state = {}
        for conv in conversations:
            flow_state = conv.flow_state or "unknown"
            by_flow_state[flow_state] = by_flow_state.get(flow_state, 0) + 1

        unique_customers = len(set(conv.customer_phone for conv in conversations if conv.customer_phone))

        total_messages = sum(conv.message_count for conv in conversations)
        avg_messages = total_messages / total_conversations if total_conversations > 0 else 0

        active_conversations = sum(1 for conv in conversations if conv.is_active)

        return {
            "business_id": str(business_id),
            "period": {
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None
            },
            "total_conversations": total_conversations,
            "active_conversations": active_conversations,
            "by_status": by_status,
            "by_flow_state": by_flow_state,
            "unique_customers": unique_customers,
            "avg_messages_per_conversation": round(avg_messages, 2)
        }

    @staticmethod
    def get_conversation_context(
            db: Session,
            business_id: UUID,
            conversation_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """Get context and customer info for a conversation. Returns None if not found."""
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.business_id == business_id
        ).first()

        if not conversation:
            return None

        return {
            "conversation_id": str(conversation_id),
            "customer_phone": conversation.customer_phone,
            "customer_info": conversation.customer_info,
            "context": conversation.context,
            "flow_state": conversation.flow_state,
            "status": conversation.status
        }

    @staticmethod
    def _serialize_conversation(conversation: Conversation) -> Dict[str, Any]:
        """Convert Conversation model to dictionary."""
        return {
            "id": str(conversation.id),
            "conversation_sid": conversation.conversation_sid,
            "customer_phone": conversation.customer_phone,
            "business_phone": conversation.business_phone,
            "status": conversation.status,
            "flow_state": conversation.flow_state,
            "customer_info": conversation.customer_info,
            "context": conversation.context,
            "message_count": conversation.message_count,
            "is_active": conversation.is_active,
            "created_at": conversation.created_at.isoformat(),
            "updated_at": conversation.updated_at.isoformat(),
            "expires_at": conversation.expires_at.isoformat() if conversation.expires_at else None
        }