from sqlalchemy import Column, String, DateTime, JSON, Boolean, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.models.base import Base


class ConversationState(Base):
    __tablename__ = "conversation_states"

    id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), primary_key=True)
    state_data = Column(JSON, nullable=False)
    flow_state = Column(String(50), nullable=False)
    last_message_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))
    is_waiting_for_response = Column(Boolean, default=False)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
