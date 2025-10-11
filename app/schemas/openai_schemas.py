# app/schemas/openai_schemas.py
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List, Union
from enum import Enum

class OpenAIRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION = "function"

class FunctionCallType(str, Enum):
    CHECK_AVAILABILITY = "check_availability"
    BOOK_APPOINTMENT = "book_appointment"
    GET_BUSINESS_INFO = "get_business_info"
    TRANSFER_TO_HUMAN = "transfer_to_human"

class OpenAIMessage(BaseModel):
    """OpenAI chat message format"""
    role: OpenAIRole = Field(..., description="Message role")
    content: Optional[str] = Field(None, description="Message content")
    name: Optional[str] = Field(None, description="Function name (for function role)")
    function_call: Optional[Dict[str, Any]] = Field(None, description="Function call details")

class OpenAIChatRequest(BaseModel):
    """OpenAI chat completion request"""
    messages: List[OpenAIMessage] = Field(..., description="Conversation messages")
    model: str = Field("gpt-4", description="OpenAI model to use")
    temperature: float = Field(0.7, description="Response randomness")
    max_tokens: int = Field(500, description="Maximum response length")
    functions: Optional[List[Dict[str, Any]]] = Field(None, description="Available functions")
    function_call: Optional[Union[str, Dict[str, str]]] = Field(None, description="Function call preference")

class OpenAIChatResponse(BaseModel):
    """OpenAI chat completion response"""
    id: str = Field(..., description="Response ID")
    object: str = Field(..., description="Response object type")
    created: int = Field(..., description="Creation timestamp")
    model: str = Field(..., description="Model used")
    choices: List[Dict[str, Any]] = Field(..., description="Response choices")
    usage: Dict[str, int] = Field(..., description="Token usage statistics")

class BusinessContext(BaseModel):
    """Business-specific context for OpenAI prompts"""
    business_id: str = Field(..., description="Business identifier")
    business_name: str = Field(..., description="Business name")
    business_type: str = Field(..., description="Type of business")
    services: List[str] = Field(default_factory=list, description="Available services")
    operating_hours: Dict[str, Any] = Field(default_factory=dict, description="Business hours")
    booking_instructions: str = Field("", description="Special booking instructions")
    contact_info: Dict[str, str] = Field(default_factory=dict, description="Business contact information")

class AvailabilityRequest(BaseModel):
    """Request for checking appointment availability"""
    business_id: str = Field(..., description="Business identifier")
    service_type: Optional[str] = Field(None, description="Requested service type")
    preferred_date: Optional[str] = Field(None, description="Preferred date (YYYY-MM-DD)")
    preferred_time: Optional[str] = Field(None, description="Preferred time (HH:MM)")
    duration_minutes: int = Field(60, description="Appointment duration in minutes")