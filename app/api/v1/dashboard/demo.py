"""
Demo API - Interactive SMS conversation testing for authenticated business owners
Dashboard authenticated endpoints - requires active business
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid
import json as json_module

from app.config.database import get_db
from app.models.auth.user import User
from app.api.dependencies import get_current_user
from app.services.business.business_service import BusinessService
from app.services.ai.ai_service import AIService
from app.models.business.business import Business
from app.services.demo.demo_storage_service import DemoStorageService
from app.models.demo import DemoMessage
from datetime import datetime, timezone, timedelta

router = APIRouter(tags=["dashboard-demo"])


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

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


class FunctionCall(BaseModel):
    name: str
    arguments: Dict[str, Any]
    result: Dict[str, Any]


class SendMessageResponse(BaseModel):
    ai_response: str
    function_calls: List[FunctionCall]
    conversation_state: str


class ConversationMessage(BaseModel):
    role: str  # Will be "user" or "assistant" for frontend consistency
    content: str
    timestamp: datetime


class GetConversationResponse(BaseModel):
    messages: List[ConversationMessage]
    state: Dict[str, Any]


# ============================================================================
# IN-MEMORY SESSION STORAGE
# ============================================================================
demo_sessions = {}


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/start", response_model=StartDemoResponse)
async def start_demo(
    request: StartDemoRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Start a new demo conversation session."""
    business_id = request.business_id or str(current_user.active_business_id)

    if not business_id:
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    # Validate business exists and user has access
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    if str(business.id) != str(current_user.active_business_id):
        raise HTTPException(
            status_code=403,
            detail="You don't have access to this business"
        )

    # Generate demo customer phone and session ID
    customer_phone = f"+1555DEMO{uuid.uuid4().hex[:4]}"
    session_id = str(uuid.uuid4())
    business_name = business.name or "our business"

    # Create demo conversation in database
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
        "user_id": str(current_user.id),
        "business_overrides": {},
        "flow_state": "gathering_info",
        "customer_info": {}
    }

    # Send initial greeting
    greeting = f"Hey, this is {business_name}. We have missed your call. How can we help?"

    # Log greeting message with "assistant" role
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
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Send a customer message and get AI response."""
    print("\n" + "=" * 80)
    print(f"📨 NEW MESSAGE REQUEST")
    print(f"Session ID: {request.session_id}")
    print(f"User Message: {request.message}")
    print("=" * 80 + "\n")

    # Get session from memory
    session = demo_sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Demo session not found or expired")

    # Verify user owns this demo session
    if str(session.get("user_id")) != str(current_user.id):
        raise HTTPException(
            status_code=403,
            detail="You don't have access to this demo session"
        )

    demo_conversation_id = session["demo_conversation_id"]
    customer_phone = session["customer_phone"]
    business_id = session["business_id"]

    # Get business
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # Log customer message with "user" role for consistency
    try:
        customer_message = DemoStorageService.log_demo_message(
            db=db,
            demo_conversation_id=demo_conversation_id,
            role="user",
            content=request.message
        )
    except Exception as e:
        print(f"Error logging customer message: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to log message: {str(e)}")

    # Get conversation state
    conv_state = {
        "flow_state": session.get("flow_state", "gathering_info"),
        "customer_info": session.get("customer_info", {})
    }

    # Get business context
    business_context = BusinessService.get_business_context(db, business_id)
    business_context["business_id"] = business_id

    # Apply session-specific overrides
    business_overrides = session.get("business_overrides", {})
    if business_overrides:
        business_context.update(business_overrides)

    # Get all previous messages
    try:
        demo_conversation = DemoStorageService.get_demo_conversation(db, request.session_id)
        all_messages = db.query(DemoMessage).filter(
            DemoMessage.demo_conversation_id == demo_conversation.id
        ).order_by(DemoMessage.created_at).all()
    except Exception as e:
        print(f"Error fetching demo conversation: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to fetch conversation: {str(e)}")

    # Format messages for AI - ensure all roles are "user" or "assistant"
    formatted_messages = []
    for msg in all_messages:
        role = msg.role
        # Normalize role names
        if role == "customer":
            role = "user"
        formatted_messages.append({
            "role": role,
            "content": msg.content
        })

    print(f"📝 Conversation history: {len(formatted_messages)} messages")

    # Initialize AI service
    ai_service = AIService()

    # Track for logging
    messages_sent_to_ai = formatted_messages.copy()

    # Get AI response
    print(f"🤖 Calling AI service for initial response...")
    ai_response = ai_service.generate_response(
        messages=formatted_messages,
        business_context=business_context,
        conversation_context=conv_state,
        db=db
    )

    print(f"\n{'=' * 80}")
    print(f"🤖 INITIAL AI RESPONSE:")
    print(f"Content: {ai_response.get('content')}")
    print(f"Function Call: {ai_response.get('function_call')}")
    print(f"Finish Reason: {ai_response.get('finish_reason')}")
    print(f"{'=' * 80}\n")

    # Track function calls
    function_calls_log = []
    function_call_count = 0

    # Handle function calls
    while ai_response.get("function_call"):
        function_call_count += 1
        function_name = ai_response['function_call']['name']
        function_args = ai_response['function_call']['arguments']

        print(f"\n{'=' * 80}")
        print(f"🔧 FUNCTION CALL #{function_call_count}")
        print(f"Function: {function_name}")
        print(f"Arguments: {json_module.dumps(function_args, indent=2)}")
        print(f"{'=' * 80}\n")

        # Inject required parameters
        if function_name in ["get_customer_appointments", "cancel_appointment", "reschedule_appointment"]:
            function_args["customer_phone"] = customer_phone

        if function_name in ["get_customer_info", "set_customer_info"]:
            function_args["conversation_id"] = demo_conversation_id

        # Execute function
        print(f"⚙️  Executing {function_name}...")
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

        print(f"\n{'=' * 80}")
        print(f"✅ FUNCTION RESULT #{function_call_count}")
        print(f"Result: {json_module.dumps(function_result, indent=2, default=str)}")
        print(f"{'=' * 80}\n")

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
            "function_call": {
                "name": function_name,
                "arguments": json_module.dumps(function_args)
            }
        })
        formatted_messages.append({
            "role": "function",
            "name": function_name,
            "content": json_module.dumps(function_result)
        })

        # Get next AI response
        print(f"🤖 Calling AI service after function result...")
        ai_response = ai_service.generate_response(
            messages=formatted_messages,
            business_context=business_context,
            conversation_context=conv_state,
            db=db
        )

        print(f"\n{'=' * 80}")
        print(f"🤖 AI RESPONSE AFTER FUNCTION #{function_call_count}:")
        print(f"Content: {ai_response.get('content')}")
        print(f"Function Call: {ai_response.get('function_call')}")
        print(f"Finish Reason: {ai_response.get('finish_reason')}")
        print(f"{'=' * 80}\n")

    print(f"\n{'=' * 80}")
    print(f"✨ FINAL RESPONSE TO USER:")
    print(f"Message: {ai_response.get('content', '')}")
    print(f"Total Function Calls: {function_call_count}")
    print(f"{'=' * 80}\n")

    # Log AI context
    try:
        DemoStorageService.log_ai_context(
            db=db,
            demo_conversation_id=demo_conversation_id,
            demo_message_id=str(customer_message.id),
            business_context=business_context,
            conversation_context=conv_state,
            messages_sent_to_ai=messages_sent_to_ai,
            rag_context=None,
            function_calls=function_calls_log,
            ai_response=ai_response.get("content"),
            finish_reason=ai_response.get("finish_reason")
        )
    except Exception as e:
        print(f"Error logging AI context: {e}")
        db.rollback()

    # Save final AI response
    if ai_response.get("content"):
        try:
            DemoStorageService.log_demo_message(
                db=db,
                demo_conversation_id=demo_conversation_id,
                role="assistant",
                content=ai_response["content"]
            )
        except Exception as e:
            print(f"Error logging assistant message: {e}")
            db.rollback()
            raise HTTPException(status_code=500, detail="Failed to save AI response")

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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get full conversation history for a demo session."""
    session = demo_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Demo session not found or expired")

    # Verify user owns this demo session
    if str(session.get("user_id")) != str(current_user.id):
        raise HTTPException(
            status_code=403,
            detail="You don't have access to this demo session"
        )

    demo_conversation_id = session["demo_conversation_id"]

    # Get messages from database
    messages = db.query(DemoMessage).filter(
        DemoMessage.demo_conversation_id == demo_conversation_id
    ).order_by(DemoMessage.created_at).all()

    # Get state from session
    conv_state = {
        "flow_state": session.get("flow_state", "gathering_info"),
        "customer_info": session.get("customer_info", {})
    }

    # Normalize roles for frontend
    normalized_messages = []
    for msg in messages:
        role = msg.role
        if role == "customer":
            role = "user"
        normalized_messages.append(
            ConversationMessage(
                role=role,
                content=msg.content,
                timestamp=msg.created_at
            )
        )

    return GetConversationResponse(
        messages=normalized_messages,
        state=conv_state
    )


@router.get("/sessions")
async def list_demo_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all demo sessions for the current user."""
    if not current_user.active_business_id:
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    # Filter sessions by user
    user_sessions = [
        {
            "session_id": session_id,
            "business_id": session_data["business_id"],
            "customer_phone": session_data["customer_phone"],
            "demo_conversation_id": session_data["demo_conversation_id"]
        }
        for session_id, session_data in demo_sessions.items()
        if str(session_data.get("user_id")) == str(current_user.id)
    ]

    return {
        "sessions": user_sessions,
        "total": len(user_sessions)
    }


@router.delete("/sessions/{session_id}")
async def delete_demo_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a demo session."""
    session = demo_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Demo session not found")

    # Verify user owns this demo session
    if str(session.get("user_id")) != str(current_user.id):
        raise HTTPException(
            status_code=403,
            detail="You don't have access to this demo session"
        )

    # Remove from memory
    del demo_sessions[session_id]

    return {"success": True, "message": "Demo session deleted"}


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
    """Execute a function call in demo mode."""

    if function_name == "book_appointment":
        print("📅 Booking appointment in demo mode")

        # Generate appointment ID
        appointment_id = f"demo-{uuid.uuid4().hex[:8]}"

        # Store the appointment in session for later retrieval
        if "appointments" not in session:
            session["appointments"] = []

        # Create appointment record
        appointment = {
            "id": appointment_id,
            "service": function_args.get("service_type"),
            "start_time": function_args.get("appointment_datetime"),
            "customer_name": function_args.get("customer_name"),
            "status": "scheduled",
            "notes": function_args.get("notes", ""),
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        session["appointments"].append(appointment)
        print(f"✅ Appointment stored in session: {appointment}")

        return {
            "success": True,
            "appointment_id": appointment_id,
            "message": "✨ Demo: Appointment booked successfully",
            "action_completed": True,
            "demo_mode": True
        }

    elif function_name == "get_services":
        services = await ai_service.get_services(
            db=db,
            business_id=business_id
        )
        # Return service names for the AI
        return {
            "services": [
                {
                    "name": s["name"],
                    "price": s["price"],
                    "duration_minutes": s["duration_minutes"],
                    "description": s.get("description", "")
                }
                for s in services
            ]
        }

    elif function_name == "get_available_slots":
        print(f"📅 Generating fake demo slots for {function_args.get('service')}...")

        # Generate fake slots for demo mode
        def generate_fake_demo_slots(
                service: str,
                duration_minutes: int,
                start_date: Optional[str] = None,
                limit: int = 12
        ) -> List[Dict]:
            """Generate predictable fake available slots for demo mode"""
            slots = []
            # Start from tomorrow at 9 AM
            now = datetime.now(timezone.utc)
            tomorrow = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)

            # Generate slots: 9 AM, 10 AM, 11 AM, 2 PM, 3 PM, 4 PM for next 3 days
            time_slots = [9, 10, 11, 14, 15, 16]  # hours

            for day_offset in range(3):  # Next 3 days
                day = tomorrow + timedelta(days=day_offset)
                for hour in time_slots:
                    slot_time = day.replace(hour=hour)
                    end_time = slot_time + timedelta(minutes=duration_minutes)

                    slots.append({
                        "start_time": slot_time.isoformat(),
                        "end_time": end_time.isoformat(),
                        "display_time": slot_time.strftime("%A, %B %d at %I:%M %p")
                    })

                    if len(slots) >= limit:
                        return slots

            return slots

        # Generate fake slots
        slots = generate_fake_demo_slots(
            service=function_args.get("service", "haircut"),
            duration_minutes=function_args.get("duration_minutes", 30),
            start_date=function_args.get("start_date"),
            limit=function_args.get("limit", 12)
        )

        print(f"✅ Generated {len(slots)} fake demo slots")
        if slots:
            print(f"First few slots: {[s['display_time'] for s in slots[:3]]}")

        return {
            "slots": slots,
            "count": len(slots),
            "demo_mode": True
        }

    elif function_name == "get_customer_appointments":
        print("🔍 Retrieving customer appointments from demo session...")

        # Get appointments from session
        appointments = session.get("appointments", [])

        # Filter by status if not including past
        include_past = function_args.get("include_past", False)
        if not include_past:
            appointments = [
                apt for apt in appointments
                if apt.get("status") in ["scheduled", "confirmed"]
            ]

        # Format appointments for AI
        formatted_appointments = []
        for apt in appointments:
            try:
                start_dt = datetime.fromisoformat(apt["start_time"])
                # Calculate end time (assume 30 min if not specified)
                duration = 123 if apt["service"] == "Hair service" else 30
                end_dt = start_dt + timedelta(minutes=duration)

                formatted_appointments.append({
                    "id": apt["id"],
                    "service": apt["service"],
                    "start_time": apt["start_time"],
                    "end_time": end_dt.isoformat(),
                    "status": apt.get("status", "scheduled"),
                    "customer_name": apt.get("customer_name"),
                    "display_time": start_dt.strftime("%A, %B %d at %I:%M %p")
                })
            except Exception as e:
                print(f"⚠️ Error formatting appointment: {e}")
                continue

        print(f"✅ Found {len(formatted_appointments)} appointments")
        if formatted_appointments:
            appt_list = [f"{a['service']} - {a['display_time']}" for a in formatted_appointments]
            print(f"Appointments: {appt_list}")

        return {
            "success": True,
            "appointments": formatted_appointments,
            "demo_mode": True
        }

    elif function_name == "cancel_appointment":
        print(f"❌ Cancelling appointment {function_args.get('appointment_id')}...")
        appointment_id = function_args.get("appointment_id")
        appointments = session.get("appointments", [])

        # Find and cancel the appointment
        appointment_found = False
        for apt in appointments:
            if apt["id"] == appointment_id:
                apt["status"] = "cancelled"
                apt["cancelled_at"] = datetime.now(timezone.utc).isoformat()
                if function_args.get("reason"):
                    apt["cancellation_reason"] = function_args.get("reason")

                appointment_found = True
                print(f"✅ Appointment cancelled: {apt['service']} - {apt['start_time']}")

                # Parse the start time for display
                try:
                    start_dt = datetime.fromisoformat(apt["start_time"])
                    display_time = start_dt.strftime("%A, %B %d at %I:%M %p")
                except:
                    display_time = apt["start_time"]

                return {
                    "success": True,
                    "message": f"Your {apt['service']} appointment on {display_time} has been cancelled.",
                    "action_completed": True,
                    "demo_mode": True
                }

        if not appointment_found:
            print(f"⚠️ Appointment not found: {appointment_id}")
            return {
                "success": False,
                "message": "Appointment not found or doesn't belong to this phone number",
                "demo_mode": True
            }

    elif function_name == "reschedule_appointment":
        print(f"🔄 Rescheduling appointment {function_args.get('appointment_id')}...")
        appointment_id = function_args.get("appointment_id")
        new_datetime = function_args.get("new_datetime")
        appointments = session.get("appointments", [])

        # Find and reschedule the appointment
        for apt in appointments:
            if apt["id"] == appointment_id:
                old_time = apt["start_time"]
                apt["start_time"] = new_datetime
                apt["rescheduled_at"] = datetime.now(timezone.utc).isoformat()
                if function_args.get("reason"):
                    apt["reschedule_reason"] = function_args.get("reason")

                print(f"✅ Appointment rescheduled from {old_time} to {new_datetime}")

                # Parse times for display
                try:
                    old_dt = datetime.fromisoformat(old_time)
                    new_dt = datetime.fromisoformat(new_datetime)
                    old_display = old_dt.strftime("%A, %B %d at %I:%M %p")
                    new_display = new_dt.strftime("%A, %B %d at %I:%M %p")
                except:
                    old_display = old_time
                    new_display = new_datetime

                return {
                    "success": True,
                    "message": f"Your appointment has been rescheduled from {old_display} to {new_display}.",
                    "action_completed": True,
                    "demo_mode": True
                }

        return {
            "success": False,
            "message": "Appointment not found or doesn't belong to this phone number",
            "demo_mode": True
        }

    elif function_name == "get_customer_info":
        customer_info = session.get("customer_info", {})
        return {
            "success": True,
            "customer_info": customer_info,
            "has_name": bool(customer_info.get("name")),
            "has_email": bool(customer_info.get("email"))
        }

    elif function_name == "set_customer_info":
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