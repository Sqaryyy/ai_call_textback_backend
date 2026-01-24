from pydantic import BaseModel, Field
from typing import Optional, List
# ============================================================================
# Pydantic Schemas
# ============================================================================

class ConversationResponse(BaseModel):
    """Response schema for conversation."""
    id: str
    conversation_sid: str
    customer_phone: str
    business_phone: str
    business_id: str
    status: str
    flow_state: str
    customer_info: dict
    context: dict
    message_count: int
    created_at: str
    updated_at: str
    expires_at: Optional[str]
    is_active: bool

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "conversation_sid": "CONV_abc123xyz789",
                "customer_phone": "+1234567890",
                "business_phone": "+0987654321",
                "business_id": "660e8400-e29b-41d4-a716-446655440001",
                "status": "active",
                "flow_state": "booking",
                "customer_info": {"name": "John Doe"},
                "context": {"intent": "appointment"},
                "message_count": 5,
                "created_at": "2025-10-19T12:00:00+00:00",
                "updated_at": "2025-10-19T12:05:00+00:00",
                "expires_at": "2025-10-20T12:00:00+00:00",
                "is_active": True
            }
        }


class ConversationListResponse(BaseModel):
    """Response schema for paginated conversations list."""
    total: int
    page: int
    page_size: int
    pages: int
    items: List[ConversationResponse]


class ConversationStatsResponse(BaseModel):
    """Response schema for conversation statistics."""
    total_conversations: int
    active_conversations: int
    completed_conversations: int
    expired_conversations: int
    avg_message_count: float
    total_messages: int
    unique_customers: int
    unique_businesses: int
    conversations_by_status: dict
    conversations_by_flow_state: dict
    conversations_last_24h: int
    conversations_last_7d: int
    conversations_last_30d: int

    class Config:
        json_schema_extra = {
            "example": {
                "total_conversations": 500,
                "active_conversations": 150,
                "completed_conversations": 300,
                "expired_conversations": 50,
                "avg_message_count": 8.5,
                "total_messages": 4250,
                "unique_customers": 350,
                "unique_businesses": 45,
                "conversations_by_status": {"active": 150, "completed": 300, "expired": 50},
                "conversations_by_flow_state": {"greeting": 50, "booking": 100, "confirmation": 200},
                "conversations_last_24h": 25,
                "conversations_last_7d": 150,
                "conversations_last_30d": 400
            }
        }


class ConversationsByBusinessResponse(BaseModel):
    """Response schema for conversations grouped by business."""
    business_id: str
    total_conversations: int
    active_conversations: int
    completed_conversations: int
    avg_message_count: float
    total_messages: int
    last_conversation_at: str


class UpdateConversationRequest(BaseModel):
    """Request schema for updating conversation."""
    status: Optional[str] = Field(None, description="Update conversation status")
    flow_state: Optional[str] = Field(None, description="Update flow state")
    is_active: Optional[bool] = Field(None, description="Update active status")
    customer_info: Optional[dict] = Field(None, description="Update customer info")
    context: Optional[dict] = Field(None, description="Update context")


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    details: Optional[dict] = None