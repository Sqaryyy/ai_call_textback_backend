from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
# ============================================================================
# Pydantic Schemas
# ============================================================================

class ConversationStateResponse(BaseModel):
    """Response schema for conversation state."""
    id: str
    state_data: dict
    flow_state: str
    last_message_at: Optional[str]
    expires_at: Optional[str]
    is_waiting_for_response: bool
    retry_count: int
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "state_data": {
                    "current_step": "date_selection",
                    "collected_info": {
                        "service": "haircut",
                        "stylist": "John"
                    }
                },
                "flow_state": "booking",
                "last_message_at": "2025-10-19T12:30:00+00:00",
                "expires_at": "2025-10-20T12:00:00+00:00",
                "is_waiting_for_response": True,
                "retry_count": 0,
                "created_at": "2025-10-19T12:00:00+00:00",
                "updated_at": "2025-10-19T12:30:00+00:00"
            }
        }


class ConversationStateListResponse(BaseModel):
    """Response schema for paginated conversation states list."""
    total: int
    page: int
    page_size: int
    pages: int
    items: List[ConversationStateResponse]


class ConversationStateStatsResponse(BaseModel):
    """Response schema for conversation state statistics."""
    total_states: int
    waiting_for_response_count: int
    waiting_for_response_rate: float
    expired_states_count: int
    states_by_flow_state: dict
    avg_retry_count: float
    max_retry_count: int
    states_with_retries: int
    states_last_24h: int
    states_last_7d: int
    states_last_30d: int

    class Config:
        json_schema_extra = {
            "example": {
                "total_states": 300,
                "waiting_for_response_count": 75,
                "waiting_for_response_rate": 25.0,
                "expired_states_count": 20,
                "states_by_flow_state": {
                    "greeting": 50,
                    "booking": 150,
                    "confirmation": 100
                },
                "avg_retry_count": 0.5,
                "max_retry_count": 3,
                "states_with_retries": 50,
                "states_last_24h": 30,
                "states_last_7d": 120,
                "states_last_30d": 250
            }
        }


class UpdateConversationStateRequest(BaseModel):
    """Request schema for updating conversation state."""
    state_data: Optional[dict] = Field(None, description="Update state data")
    flow_state: Optional[str] = Field(None, description="Update flow state")
    is_waiting_for_response: Optional[bool] = Field(None, description="Update waiting status")
    retry_count: Optional[int] = Field(None, ge=0, description="Update retry count")
    expires_at: Optional[datetime] = Field(None, description="Update expiration time")


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    details: Optional[dict] = None
