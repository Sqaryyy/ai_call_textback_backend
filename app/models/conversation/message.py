from sqlalchemy import Column, String, DateTime, JSON, Text, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.models.base import Base


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False)
    sender_phone = Column(String(20), nullable=False)
    recipient_phone = Column(String(20), nullable=False)
    role = Column(String(20), nullable=False)  # customer, assistant, system
    content = Column(Text, nullable=False)
    message_status = Column(String(20))  # received, sending, sent, failed, delivered
    media_urls = Column(JSON, default=list)
    message_metadata = Column(JSON, default=dict)  # Changed from metadata
    error_code = Column(String(10))
    error_message = Column(Text)
    is_inbound = Column(Boolean, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
