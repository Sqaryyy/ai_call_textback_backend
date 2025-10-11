# app/models/conversation.py
from sqlalchemy import Column, String, DateTime, JSON, Boolean, Integer, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from .business import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Add this new column for custom conversation identifier
    conversation_sid = Column(String(50), unique=True, nullable=False, index=True)

    customer_phone = Column(String(20), nullable=False)
    business_phone = Column(String(20), nullable=False)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False)

    status = Column(String(20), default="active")
    flow_state = Column(String(50), default="greeting")
    customer_info = Column(JSON, default=dict)
    context = Column(JSON, default=dict)
    message_count = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    expires_at = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True)

    # Add indexes for common queries
    __table_args__ = (
        Index('ix_conversations_customer_phone', 'customer_phone'),
        Index('ix_conversations_business_active', 'business_id', 'is_active'),
    )