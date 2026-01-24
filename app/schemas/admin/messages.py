from pydantic import BaseModel, Field
from typing import Optional, List

# ============================================================================
# Pydantic Schemas
# ============================================================================

class MessageResponse(BaseModel):
    """Response schema for message with business context"""
    id: str
    conversation_id: str
    business_id: Optional[str]
    business_name: Optional[str]
    sender_phone: str
    recipient_phone: str
    role: str
    content: str
    message_status: Optional[str]
    media_urls: List[str]
    message_metadata: dict
    error_code: Optional[str]
    error_message: Optional[str]
    is_inbound: bool
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class MessageListResponse(BaseModel):
    """Response schema for paginated messages list"""
    total: int
    page: int
    page_size: int
    pages: int
    items: List[MessageResponse]


class MessageStatsResponse(BaseModel):
    """Response schema for message statistics"""
    total_messages: int
    inbound_messages: int
    outbound_messages: int
    messages_by_role: dict
    messages_by_status: dict
    failed_messages: int
    messages_with_media: int
    avg_messages_per_conversation: float
    messages_last_24h: int
    messages_last_7d: int
    messages_last_30d: int
    unique_senders: int
    unique_recipients: int
    messages_by_business: dict


class MessagesByConversationResponse(BaseModel):
    """Response schema for messages grouped by conversation"""
    conversation_id: str
    conversation_sid: str
    business_id: Optional[str]
    business_name: Optional[str]
    total_messages: int
    inbound_messages: int
    outbound_messages: int
    failed_messages: int
    first_message_at: str
    last_message_at: str


class UpdateMessageRequest(BaseModel):
    """Request schema for updating message"""
    message_status: Optional[str] = Field(None, description="Update message status")
    error_code: Optional[str] = Field(None, description="Update error code")
    error_message: Optional[str] = Field(None, description="Update error message")
    message_metadata: Optional[dict] = Field(None, description="Update message metadata")


class GenericMessageResponse(BaseModel):
    """Generic message response"""
    message: str
    details: Optional[dict] = None


class BusinessMessageStatsResponse(BaseModel):
    """Stats for a specific business"""
    business_id: str
    business_name: str
    total_messages: int
    inbound_messages: int
    outbound_messages: int
    failed_messages: int
    unique_conversations: int
    avg_messages_per_conversation: float
    messages_last_24h: int
    messages_last_7d: int
    messages_last_30d: int

