"""
Demo API - Interactive SMS conversation testing for potential customers
NOW WITH FULL CONTEXT LOGGING
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
import json

from app.config.database import get_db
from app.services.conversation.conversation_state_service import ConversationStateService
from app.services.business.business_service import BusinessService
from app.services.ai.ai_service import AIService
from app.models.business import Business

# NEW: Import demo storage service
from app.services.demo.demo_storage_service import DemoStorageService

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


# ============================================================================
# IN-MEMORY SESSION STORAGE (temporary demo sessions)
# ============================================================================
# Key: session_id -> Value: { demo_conversation_id, customer_phone, business_id }
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
    Creates a demo conversation with greeting message.
    """
    # Validate business exists
    business = db.query(Business).filter(Business.id == request.business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # Generate demo customer phone
    customer_phone = f"+1555DEMO{uuid.uuid4().hex[:4]}"
    business_phone = business.phone_number
    business_name = business.name or "our business"

    # Generate session ID
    session_id = str(uuid.uuid4())

    # NEW: Create demo conversation in demo tables
    demo_conversation = DemoStorageService.create_demo_conversation(
        db=db,
        session_id=session_id,
        business_id=str(business.id),
        customer_phone=customer_phone
    )

    # Store session in memory
    demo_sessions[session_id] = {
        "demo_conversation_id": str(demo_conversation.id),
        "customer_phone": customer_phone,
        "business_id": str(business.id),
        "business_overrides": {}
    }

    # Send initial greeting
    greeting = f"Hey, this is {business_name}. We have missed your call. How can we help?"

    # NEW: Log greeting message
    DemoStorageService.log_demo_message(
        db=db,
        demo_conversation_id=demo_conversation.id,
        role="assistant",
        content=greeting
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
    NOW LOGS ALL AI CONTEXT FOR ANALYTICS.
    """
    # Get session from memory
    session = demo_sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Demo session not found or expired")

    demo_conversation_id = session["demo_conversation_id"]
    customer_phone = session["customer_phone"]
    business_id = session["business_id"]

    # Get business
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    business_phone = business.phone_number

    # NEW: Log customer message
    customer_message = DemoStorageService.log_demo_message(
        db=db,
        demo_conversation_id=demo_conversation_id,
        role="customer",
        content=request.message
    )

    # Get or create conversation state (using in-memory state for demo)
    # We'll track this separately from production conversation_state table
    conv_state = {
        "flow_state": session.get("flow_state", "gathering_info"),
        "customer_info": session.get("customer_info", {})
    }

    # Get context
    business_context = BusinessService.get_business_context(db, business_id)
    business_context["business_id"] = business_id

    # Apply session-specific business overrides
    business_overrides = session.get("business_overrides", {})
    if business_overrides:
        business_context.update(business_overrides)

    # Get all previous demo messages for context
    demo_conversation = DemoStorageService.get_demo_conversation(db, request.session_id)
    all_messages = db.query(DemoStorageService.DemoMessage).filter(
        DemoStorageService.DemoMessage.demo_conversation_id == demo_conversation.id
    ).order_by(DemoStorageService.DemoMessage.created_at).all()

    # Format messages for AI
    formatted_messages = [
        {
            "role": msg.role if msg.role != "customer" else "user",
            "content": msg.content
        }
        for msg in all_messages
    ]

    # Initialize AI service
    ai_service = AIService()

    # Track what we're sending to AI for logging
    messages_sent_to_ai = formatted_messages.copy()

    ai_response = ai_service.generate_response(
        messages=formatted_messages,
        business_context=business_context,
        conversation_context=conv_state,
        db=db
    )

    # Track function calls for response and logging
    function_calls_log = []
    rag_context_captured = None  # Capture RAG if available

    # Handle function calls
    while ai_response.get("function_call"):
        function_name = ai_response['function_call']['name']
        function_args = ai_response['function_call']['arguments']

        # Inject required parameters
        if function_name in ["get_customer_appointments", "cancel_appointment", "reschedule_appointment"]:
            function_args["customer_phone"] = customer_phone

        if function_name in ["get_customer_info", "set_customer_info"]:
            # Use demo conversation ID for state
            function_args["conversation_id"] = demo_conversation_id

        # Execute function
        function_result = await execute_demo_function(
            db=db,
            function_name=function_name,
            function_args=function_args,
            business_id=business_id,
            business_context=business_context,
            demo_conversation_id=demo_conversation_id,
            customer_phone=customer_phone,
            ai_service=ai_service,
            session=session
        )

        # Log function call
        function_calls_log.append({
            "name": function_name,
            "arguments": function_args,
            "result": function_result
        })

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

        # Get next AI response
        ai_response = ai_service.generate_response(
            messages=formatted_messages,
            business_context=business_context,
            conversation_context=conv_state,
            db=db
        )

    # NEW: Log complete AI context
    DemoStorageService.log_ai_context(
        db=db,
        demo_conversation_id=demo_conversation_id,
        demo_message_id=str(customer_message.id),
        business_context=business_context,
        conversation_context=conv_state,
        messages_sent_to_ai=messages_sent_to_ai,
        rag_context=rag_context_captured,
        function_calls=function_calls_log,
        ai_response=ai_response.get("content"),
        finish_reason=ai_response.get("finish_reason")
    )

    # Save final AI response
    if ai_response.get("content"):
        DemoStorageService.log_demo_message(
            db=db,
            demo_conversation_id=demo_conversation_id,
            role="assistant",
            content=ai_response["content"]
        )

    # Update session state
    session["flow_state"] = conv_state["flow_state"]
    session["customer_info"] = conv_state["customer_info"]

    return SendMessageResponse(
        ai_response=ai_response.get("content", ""),
        function_calls=[
            FunctionCall(
                name=fc["name"],
                arguments=fc["arguments"],
                result=fc["result"]
            )
            for fc in function_calls_log
        ],
        conversation_state=conv_state["flow_state"]
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

    demo_conversation_id = session["demo_conversation_id"]

    # Get messages from demo tables
    messages = db.query(DemoStorageService.DemoMessage).filter(
        DemoStorageService.DemoMessage.demo_conversation_id == demo_conversation_id
    ).order_by(DemoStorageService.DemoMessage.created_at).all()

    # Get state from session
    conv_state = {
        "flow_state": session.get("flow_state", "gathering_info"),
        "customer_info": session.get("customer_info", {})
    }

    return GetConversationResponse(
        messages=[
            ConversationMessage(
                role=msg.role,
                content=msg.content,
                timestamp=msg.created_at
            )
            for msg in messages
        ],
        state=conv_state
    )


@router.get("/business/{session_id}")
async def get_business_data(
        session_id: str,
        db: Session = Depends(get_db)
):
    """
    Get comprehensive business data for a demo session.
    """
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


# NEW: Analytics endpoint
@router.get("/analytics/{session_id}")
async def get_demo_analytics(
        session_id: str,
        db: Session = Depends(get_db)
):
    """
    Get full conversation history with all AI context for analysis.
    Shows exactly what data was given to AI and how it responded.
    """
    history = DemoStorageService.get_conversation_history(db, session_id)
    if not history:
        raise HTTPException(status_code=404, detail="Demo session not found")

    return history


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def execute_demo_function(
        db: Session,
        function_name: str,
        function_args: Dict[str, Any],
        business_id: str,
        business_context: Dict[str, Any],
        demo_conversation_id: str,
        customer_phone: str,
        ai_service: AIService,
        session: Dict
) -> Dict[str, Any]:
    """
    Execute a function call in demo mode.
    For appointments: return fake success without actually booking.
    For customer info: store in session instead of DB.
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
        # DEMO MODE: Return empty list
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
        # Get from session instead of DB
        customer_info = session.get("customer_info", {})
        return {
            "success": True,
            "customer_info": customer_info,
            "has_name": bool(customer_info.get("name")),
            "has_email": bool(customer_info.get("email"))
        }

    elif function_name == "set_customer_info":
        # Store in session instead of DB
        customer_info = session.get("customer_info", {})
        if function_args.get("customer_name"):
            customer_info["name"] = function_args["customer_name"]
        if function_args.get("customer_email"):
            customer_info["email"] = function_args["customer_email"]
        if function_args.get("customer_phone"):
            customer_info["phone"] = function_args["customer_phone"]

        session["customer_info"] = customer_info

        return {
            "success": True,
            "message": "Customer information stored successfully",
            "customer_info": customer_info
        }

    else:
        return {"success": False, "message": f"Unknown function: {function_name}"}