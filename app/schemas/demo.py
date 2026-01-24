"""
Pydantic schemas for demo API endpoints
"""
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime


class StartDemoRequest(BaseModel):
    business_id: Optional[str] = None


class StartDemoResponse(BaseModel):
    session_id: str
    customer_phone: str
    greeting: str
    business_name: str


class SendMessageRequest(BaseModel):
    session_id: str
    message: str


class SendMessageResponse(BaseModel):
    ai_response: str
    conversation_state: str


class ConversationMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime


class GetConversationResponse(BaseModel):
    messages: List[ConversationMessage]
    state: Dict[str, Any]