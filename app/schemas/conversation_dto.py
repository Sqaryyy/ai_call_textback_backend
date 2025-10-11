# app/schemas/conversation_dto.py
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from enum import Enum

class ConversationStatus(str, Enum):
    ACTIVE = "active"
    WAITING = "waiting"
    COMPLETED = "completed"
    EXPIRED = "expired"
    ESCALATED = "escalated"

class MessageRole(str, Enum):
    CUSTOMER = "customer"
    ASSISTANT = "assistant"
    SYSTEM = "system"

class ConversationFlowState(str, Enum):
    GREETING = "greeting"
    COLLECTING_INFO = "collecting_info"
    CHECKING_AVAILABILITY = "checking_availability"
    BOOKING_APPOINTMENT = "booking_appointment"
    CONFIRMING_DETAILS = "confirming_details"
    COMPLETED = "completed"
    ESCALATED = "escalated"

class MessageDTO(BaseModel):
    """Individual message in a conversation"""
    id: Optional[str] = Field(None, description="Message ID")
    role: MessageRole = Field(..., description="Message sender role")
    content: str = Field(..., description="Message content")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional message data")

class ConversationDTO(BaseModel):
    """Complete conversation data transfer object"""
    id: str = Field(..., description="Conversation ID")
    customer_phone: str = Field(..., description="Customer phone number")
    business_phone: str = Field(..., description="Business phone number")
    business_id: str = Field(..., description="Business identifier")
    status: ConversationStatus = Field(ConversationStatus.ACTIVE)
    flow_state: ConversationFlowState = Field(ConversationFlowState.GREETING)
    messages: List[MessageDTO] = Field(default_factory=list)
    customer_info: Dict[str, Any] = Field(default_factory=dict, description="Collected customer information")
    context: Dict[str, Any] = Field(default_factory=dict, description="Conversation context and state")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = Field(None, description="Conversation expiration time")

class ConversationStateUpdate(BaseModel):
    """Update conversation state"""
    conversation_id: str = Field(..., description="Conversation ID")
    new_state: ConversationFlowState = Field(..., description="New flow state")
    context_updates: Dict[str, Any] = Field(default_factory=dict, description="Context updates")
    customer_info_updates: Dict[str, Any] = Field(default_factory=dict, description="Customer info updates")