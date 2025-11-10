"""
Demo Models - Separate tables for demo conversations and analytics
File: app/models/demo.py
"""
from sqlalchemy import Column, String, DateTime, JSON, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.models.base import Base


class DemoConversation(Base):
    """Demo conversation sessions"""
    __tablename__ = "demo_conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String(50), unique=True, nullable=False, index=True)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=True)
    customer_phone = Column(String(20), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    messages = relationship("DemoMessage", back_populates="conversation", cascade="all, delete-orphan")
    ai_logs = relationship("DemoAIContextLog", back_populates="conversation", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<DemoConversation(session_id={self.session_id}, business_id={self.business_id})>"


class DemoMessage(Base):
    """Demo chat messages - full conversation history"""
    __tablename__ = "demo_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    demo_conversation_id = Column(UUID(as_uuid=True), ForeignKey("demo_conversations.id", ondelete="CASCADE"),
                                  nullable=False)
    role = Column(String(20), nullable=False)  # 'customer', 'assistant', 'system'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    conversation = relationship("DemoConversation", back_populates="messages")
    ai_logs = relationship("DemoAIContextLog", back_populates="message", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_demo_messages_conversation', 'demo_conversation_id'),
        Index('idx_demo_messages_created', 'created_at'),
    )

    def __repr__(self):
        return f"<DemoMessage(role={self.role}, conversation_id={self.demo_conversation_id})>"


class DemoAIContextLog(Base):
    """Logs what data was given to AI for each call"""
    __tablename__ = "demo_ai_context_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    demo_conversation_id = Column(UUID(as_uuid=True), ForeignKey("demo_conversations.id", ondelete="CASCADE"),
                                  nullable=False)
    demo_message_id = Column(UUID(as_uuid=True), ForeignKey("demo_messages.id", ondelete="CASCADE"), nullable=True)

    # What was fed to AI
    business_context = Column(JSONB, nullable=False)
    conversation_context = Column(JSONB, nullable=False)
    rag_context = Column(Text, nullable=True)
    messages_sent_to_ai = Column(JSONB, nullable=False)  # Full message array

    # Function calls made (can be multiple per AI call)
    function_calls = Column(JSONB, default=list, nullable=False)

    # AI response
    ai_response = Column(Text, nullable=True)
    finish_reason = Column(String(50), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    conversation = relationship("DemoConversation", back_populates="ai_logs")
    message = relationship("DemoMessage", back_populates="ai_logs")

    __table_args__ = (
        Index('idx_demo_ai_log_conversation', 'demo_conversation_id'),
        Index('idx_demo_ai_log_message', 'demo_message_id'),
        Index('idx_demo_ai_log_created', 'created_at'),
    )

    def __repr__(self):
        return f"<DemoAIContextLog(conversation_id={self.demo_conversation_id}, functions={len(self.function_calls)})>"