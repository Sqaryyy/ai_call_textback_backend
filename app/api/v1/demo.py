"""
Demo API - Interactive SMS conversation testing for potential customers
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
import json

from app.config.database import get_db
from app.services.conversation.conversation_service import ConversationService
from app.services.conversation.conversation_state_service import ConversationStateService
from app.services.message.message_service import MessageService
from app.services.business.business_service import BusinessService
from app.services.ai.ai_service import AIService
from app.models.business import Business

router = APIRouter()


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class StartDemoRequest(BaseModel):
    business_id: str


class StartDemoResponse(BaseModel):
    session_id: str
    customer_phone: str
    greeting: str
    business_name: str


class SendMessageRequest(BaseModel):
    session_id: str
    message: str


class FunctionCall(BaseModel):
    name: str
    arguments: Dict[str, Any]
    result: Dict[str, Any]


class SendMessageResponse(BaseModel):
    ai_response: str
    function_calls: List[FunctionCall]
    conversation_state: str


class ConversationMessage(BaseModel):
    role: str
    content: str
    timestamp: datetime


class GetConversationResponse(BaseModel):
    messages: List[ConversationMessage]
    state: Dict[str, Any]


class BusinessContextResponse(BaseModel):
    business_id: str
    name: str
    phone_number: str
    business_hours: Dict[str, Any]
    service_catalog: Dict[str, Any]
    booking_policies: Dict[str, Any]
    business_info: str


class UpdateBusinessContextRequest(BaseModel):
    name: Optional[str] = None
    business_hours: Optional[Dict[str, Any]] = None
    service_catalog: Optional[Dict[str, Any]] = None
    booking_policies: Optional[Dict[str, Any]] = None
    business_info: Optional[str] = None


# ============================================================================
# IN-MEMORY SESSION STORAGE (temporary demo sessions)
# ============================================================================
# Key: session_id -> Value: { conversation_id, customer_phone, business_id }
demo_sessions = {}


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/start", response_model=StartDemoResponse)
async def start_demo(
    request: StartDemoRequest,
    db: Session = Depends(get_db)
):
    """
    Start a new demo conversation session.
    Creates a temporary conversation with greeting message.
    """
    # Validate business exists
    business = db.query(Business).filter(Business.id == request.business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # Generate demo customer phone
    customer_phone = f"+1555DEMO{uuid.uuid4().hex[:4]}"
    business_phone = business.phone_number
    business_name = business.name or "our business"

    # Create conversation (marked as demo)
    conversation = ConversationService.find_or_create_conversation(
        db, customer_phone, business_phone, business.id
    )

    # Mark as demo in conversation metadata if possible
    # (You might want to add an is_demo field to your Conversation model)

    # Generate session ID
    session_id = str(uuid.uuid4())

    # Store session in memory
    demo_sessions[session_id] = {
        "conversation_id": str(conversation.id),
        "customer_phone": customer_phone,
        "business_id": str(business.id),
        "business_overrides": {}  # Store custom business context edits
    }

    # Send initial greeting
    greeting = f"Hey, this is {business_name}. We have missed your call. How can we help?"

    MessageService.create_message(
        db=db,
        message_sid=str(uuid.uuid4()),
        conversation_id=conversation.id,
        sender_phone=business_phone,
        recipient_phone=customer_phone,
        role="assistant",
        content=greeting,
        is_inbound=False,
        message_status="sent"
    )

    return StartDemoResponse(
        session_id=session_id,
        customer_phone=customer_phone,
        greeting=greeting,
        business_name=business_name
    )


@router.post("/message", response_model=SendMessageResponse)
async def send_message(
    request: SendMessageRequest,
    db: Session = Depends(get_db)
):
    """
    Send a customer message and get AI response.
    Handles the full conversation flow including function calls.
    """
    # Get session from memory
    session = demo_sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Demo session not found or expired")

    conversation_id = session["conversation_id"]
    customer_phone = session["customer_phone"]
    business_id = session["business_id"]

    # Get business
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    business_phone = business.phone_number

    # Get or create conversation state
    conv_state = ConversationStateService.get_or_create_state(
        db=db,
        conversation_id=conversation_id
    )

    # Reset state if previous action completed
    if conv_state.flow_state == "action_completed":
        existing_customer_info = conv_state.state_data.get("customer_info", {})
        ConversationStateService.update_state(
            db=db,
            conversation_id=conversation_id,
            flow_state="gathering_info",
            state_data={"customer_info": existing_customer_info}
        )
        conv_state = ConversationStateService.get_or_create_state(db, conversation_id)

    # Add customer message
    MessageService.create_message(
        db=db,
        message_sid=str(uuid.uuid4()),
        conversation_id=conversation_id,
        sender_phone=customer_phone,
        recipient_phone=business_phone,
        role="customer",
        content=request.message,
        is_inbound=True,
        media_urls=[]
    )

    # Get context and messages
    business_context = BusinessService.get_business_context(db, business_id)
    business_context["business_id"] = business_id

    # Apply session-specific business overrides
    business_overrides = session.get("business_overrides", {})
    if business_overrides:
        business_context.update(business_overrides)

    messages = MessageService.get_conversation_messages(db, conversation_id)
    formatted_messages = MessageService.format_messages_for_ai(messages)

    # Initialize AI service
    ai_service = AIService()
    ai_response = ai_service.generate_response(
        messages=formatted_messages,
        business_context=business_context,
        conversation_context={
            "flow_state": conv_state.flow_state,
            "customer_info": conv_state.state_data.get("customer_info", {})
        },
        db=db
    )

    # Track function calls for response
    function_calls_log = []

    # Handle function calls
    while ai_response.get("function_call"):
        function_name = ai_response['function_call']['name']
        function_args = ai_response['function_call']['arguments']

        # Inject required parameters
        if function_name in ["get_customer_appointments", "cancel_appointment", "reschedule_appointment"]:
            function_args["customer_phone"] = customer_phone

        if function_name in ["get_customer_info", "set_customer_info"]:
            function_args["conversation_id"] = conversation_id

        # Execute function
        function_result = await execute_demo_function(
            db=db,
            function_name=function_name,
            function_args=function_args,
            business_id=business_id,
            business_context=business_context,
            conversation_id=conversation_id,
            customer_phone=customer_phone,
            ai_service=ai_service
        )

        # Log function call
        function_calls_log.append(FunctionCall(
            name=function_name,
            arguments=function_args,
            result=function_result
        ))

        # Add to message history
        formatted_messages.append({
            "role": "assistant",
            "content": None,
            "function_call": {"name": function_name, "arguments": json.dumps(function_args)}
        })
        formatted_messages.append({
            "role": "function",
            "name": function_name,
            "content": json.dumps(function_result)
        })

        # Refresh state
        conv_state = ConversationStateService.get_or_create_state(db, conversation_id)

        # Get next AI response
        ai_response = ai_service.generate_response(
            messages=formatted_messages,
            business_context=business_context,
            conversation_context={
                "flow_state": conv_state.flow_state,
                "customer_info": conv_state.state_data.get("customer_info", {})
            },
            db=db
        )

    # Save final AI response
    if ai_response.get("content"):
        MessageService.create_message(
            db=db,
            message_sid=str(uuid.uuid4()),
            conversation_id=conversation_id,
            sender_phone=business_phone,
            recipient_phone=customer_phone,
            role="assistant",
            content=ai_response["content"],
            is_inbound=False,
            message_status="sent"
        )

    return SendMessageResponse(
        ai_response=ai_response.get("content", ""),
        function_calls=function_calls_log,
        conversation_state=conv_state.flow_state
    )


@router.get("/conversation/{session_id}", response_model=GetConversationResponse)
async def get_conversation(
    session_id: str,
    db: Session = Depends(get_db)
):
    """
    Get full conversation history for a demo session.
    Useful for page refresh or reconnection.
    """
    session = demo_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Demo session not found or expired")

    conversation_id = session["conversation_id"]

    # Get messages
    messages = MessageService.get_conversation_messages(db, conversation_id)

    # Get state
    conv_state = ConversationStateService.get_or_create_state(db, conversation_id)

    return GetConversationResponse(
        messages=[
            ConversationMessage(
                role=msg.role,
                content=msg.content,
                timestamp=msg.created_at
            )
            for msg in messages
        ],
        state={
            "flow_state": conv_state.flow_state,
            "customer_info": conv_state.state_data.get("customer_info", {})
        }
    )


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def execute_demo_function(
    db: Session,
    function_name: str,
    function_args: Dict[str, Any],
    business_id: str,
    business_context: Dict[str, Any],
    conversation_id: str,
    customer_phone: str,
    ai_service: AIService
) -> Dict[str, Any]:
    """
    Execute a function call in demo mode.
    For appointments: return fake success without actually booking.
    For other functions: execute normally.
    """

    if function_name == "book_appointment":
        # DEMO MODE: Don't actually book, just return success
        return {
            "success": True,
            "appointment_id": f"demo-{uuid.uuid4().hex[:8]}",
            "message": "✨ Demo: Appointment would be booked successfully",
            "action_completed": True,
            "demo_mode": True
        }

    elif function_name == "get_services":
        return {
            "services": list(business_context.get("service_catalog", {}).keys())
        }

    elif function_name == "get_available_slots":
        try:
            slots = await ai_service.get_available_slots(
                db=db,
                business_id=business_id,
                service=function_args.get("service", "haircut"),
                duration_minutes=function_args.get("duration_minutes", 30),
                start_date=function_args.get("start_date"),
                end_date=function_args.get("end_date"),
                limit=function_args.get("limit", 12)
            )
            return {"slots": slots, "count": len(slots)}
        except Exception as e:
            return {"slots": [], "count": 0, "error": str(e)}

    elif function_name == "get_customer_appointments":
        # DEMO MODE: Return empty list (no real appointments for demo)
        return {
            "success": True,
            "appointments": [],
            "demo_mode": True
        }

    elif function_name == "cancel_appointment":
        # DEMO MODE: Fake cancellation
        return {
            "success": True,
            "message": "✨ Demo: Appointment would be cancelled",
            "action_completed": True,
            "demo_mode": True
        }

    elif function_name == "reschedule_appointment":
        # DEMO MODE: Fake reschedule
        return {
            "success": True,
            "message": "✨ Demo: Appointment would be rescheduled",
            "action_completed": True,
            "demo_mode": True
        }

    elif function_name == "get_customer_info":
        try:
            result = await ai_service.get_customer_info(
                db=db,
                conversation_id=conversation_id
            )
            return result
        except Exception as e:
            return {
                "success": False,
                "customer_info": {},
                "has_name": False,
                "has_email": False
            }

    elif function_name == "set_customer_info":
        try:
            result = await ai_service.set_customer_info(
                db=db,
                conversation_id=conversation_id,
                customer_name=function_args.get("customer_name"),
                customer_email=function_args.get("customer_email"),
                customer_phone=function_args.get("customer_phone")
            )
            return result
        except Exception as e:
            return {
                "success": False,
                "message": str(e)
            }

    else:
        return {"success": False, "message": f"Unknown function: {function_name}"}

@router.get("/business/{session_id}")
async def get_business_data(
    session_id: str,
    db: Session = Depends(get_db)
):
    """
    Get comprehensive business data for a demo session.
    This endpoint provides all business information including profile, services,
    policies, contact info, FAQs, and operational details for verification.
    """
    # Get session from memory
    session = demo_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Demo session not found or expired")

    business_id = session["business_id"]

    # Get business
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # Get full business context
    business_context = BusinessService.get_business_context(db, business_id)

    # Apply session-specific business overrides if any
    business_overrides = session.get("business_overrides", {})
    if business_overrides:
        business_context.update(business_overrides)

    return {
        "business_id": business_id,
        "name": business.name,
        "phone_number": business.phone_number,
        "business_type": business.business_type,
        "timezone": business.timezone,
        "business_profile": business.business_profile or {},
        "service_catalog": business.service_catalog or {},
        "conversation_policies": business.conversation_policies or {},
        "quick_responses": business.quick_responses or {},
        "contact_info": business.contact_info or {},
        "ai_instructions": business.ai_instructions or "",
        "business_hours": business_context.get("business_hours", {}),
        "booking_policies": business_context.get("booking_policies", {}),
        "business_info": business_context.get("business_info", "")
    }