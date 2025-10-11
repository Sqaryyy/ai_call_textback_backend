"""
Test the SMS conversation flow - minimal output version.
Shows only: Customer messages, AI responses, and function calls.
"""

import sys
from datetime import datetime
from pathlib import Path

# ⭐ SET TESTING MODE BEFORE ANY APP IMPORTS ⭐
from app.utils.my_logging import setup_logging

setup_logging(verbose=False)
# Now import app modules
from app.config.database import get_db
from app.services.conversation.conversation_service import ConversationService
from app.services.conversation.conversation_state_service import ConversationStateService
from app.services.message.message_service import MessageService
from app.services.business.business_service import BusinessService
from app.models.business import Business
from app.services.ai.ai_service import AIService
from app.tasks.calendar_tasks import sync_appointment_to_calendar
import uuid
import json
import asyncio
from app.services.appointment.appointment_service import AppointmentService

sys.path.append(str(Path(__file__).parent.parent))


def send_initial_greeting(db, business_id: str, customer_phone: str):
    """Send initial greeting message when conversation starts."""
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        print(f"❌ Business {business_id} not found")
        return None

    business_phone = business.phone_number
    business_name = business.name or "our business"

    # Create or get conversation
    conversation = ConversationService.find_or_create_conversation(
        db, customer_phone, business_phone, business.id
    )

    # Check if this is a new conversation (no messages yet)
    messages = MessageService.get_conversation_messages(db, conversation.id)
    if len(messages) == 0:
        # Send initial greeting
        greeting = f"Hey, this is {business_name}. We have missed your call. How can we help?"
        print(f"\n🤖 AI: {greeting}\n")

        # Save greeting to database
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

        return greeting

    return None


def simulate_customer_message(db, business_id: str, customer_phone: str, message_body: str):
    """Simulate a customer sending an SMS message and get AI response."""

    # Get business and conversation
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        print(f"❌ Business {business_id} not found")
        return None

    business_phone = business.phone_number
    conversation = ConversationService.find_or_create_conversation(
        db, customer_phone, business_phone, business.id
    )

    # ⭐ Get or create conversation state ⭐
    conv_state = ConversationStateService.get_or_create_state(
        db=db,
        conversation_id=str(conversation.id)
    )

    # ⭐ STATE MANAGEMENT: Reset state if previous action completed ⭐
    if conv_state.flow_state == "action_completed":
        print("🔄 Resetting conversation state (previous action completed)")
        # Preserve customer_info when resetting flow state
        existing_customer_info = conv_state.state_data.get("customer_info", {})
        ConversationStateService.update_state(
            db=db,
            conversation_id=str(conversation.id),
            flow_state="gathering_info",
            state_data={"customer_info": existing_customer_info}  # Keep customer info
        )
        conv_state = ConversationStateService.get_or_create_state(db, str(conversation.id))

    # Add customer message
    MessageService.create_message(
        db=db,
        message_sid=str(uuid.uuid4()),
        conversation_id=conversation.id,
        sender_phone=customer_phone,
        recipient_phone=business_phone,
        role="customer",
        content=message_body,
        is_inbound=True,
        media_urls=[]
    )
    ConversationService.increment_message_count(db, conversation.id)

    # Get context and messages
    business_context = BusinessService.get_business_context(db, business.id)
    business_context["business_id"] = str(business.id)
    messages = MessageService.get_conversation_messages(db, conversation.id)
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

    # Handle function calls
    while ai_response.get("function_call"):
        function_name = ai_response['function_call']['name']
        function_args = ai_response['function_call']['arguments']

        # ⭐ INJECT customer_phone for relevant functions BEFORE printing
        if function_name in ["get_customer_appointments", "cancel_appointment", "reschedule_appointment"]:
            function_args["customer_phone"] = customer_phone

        # ⭐ INJECT conversation_id for customer info functions
        if function_name in ["get_customer_info", "set_customer_info"]:
            function_args["conversation_id"] = str(conversation.id)

        print(f"\n⚡ Function: {function_name}")
        print(f"   Args: {json.dumps(function_args, indent=8)}")

        # Execute function
        if function_name == "book_appointment":
            try:
                appointment = AppointmentService.create_appointment(
                    db=db,
                    conversation_id=conversation.id,
                    business_id=str(business.id),
                    customer_phone=customer_phone,
                    customer_name=function_args.get("customer_name"),
                    service_type=function_args.get("service_type"),
                    appointment_datetime=datetime.fromisoformat(function_args["appointment_datetime"]),
                    duration_minutes=function_args.get("duration_minutes", 30),
                    customer_email=function_args.get("customer_email"),
                    notes=function_args.get("notes", "")
                )
                appointment.status = "scheduled"
                db.commit()
                db.refresh(appointment)
                sync_appointment_to_calendar.delay(str(appointment.id))

                function_result = {
                    "success": True,
                    "appointment_id": str(appointment.id),
                    "message": "Appointment booked successfully",
                    "action_completed": True
                }

                # ⭐ Update conversation state after booking ⭐
                ConversationStateService.update_state(
                    db=db,
                    conversation_id=str(conversation.id),
                    flow_state="action_completed"
                )
                print("✅ State updated: action_completed")

            except Exception as e:
                db.rollback()
                function_result = {"success": False, "error": str(e)}

        elif function_name == "get_services":
            function_result = {
                "services": list(business_context.get("service_catalog", {}).keys())
            }

        elif function_name == "get_available_slots":
            try:
                slots = asyncio.run(ai_service.get_available_slots(
                    db=db,
                    business_id=str(business.id),
                    service=function_args.get("service", "haircut"),
                    duration_minutes=function_args.get("duration_minutes", 30),
                    start_date=function_args.get("start_date"),
                    end_date=function_args.get("end_date"),
                    limit=function_args.get("limit", 12)
                ))
                function_result = {"slots": slots, "count": len(slots)}
                print(f"   Found {len(slots)} slots")
            except Exception as e:
                db.rollback()
                function_result = {"slots": [], "count": 0, "error": str(e)}

        elif function_name == "get_customer_appointments":
            try:
                appointments = asyncio.run(ai_service.get_customer_appointments(
                    db=db,
                    customer_phone=customer_phone,
                    business_id=str(business.id),
                    include_past=function_args.get("include_past", False)
                ))
                function_result = {"success": True, "appointments": appointments}
            except Exception as e:
                function_result = {"success": False, "appointments": []}

        elif function_name == "cancel_appointment":
            try:
                result = asyncio.run(ai_service.cancel_appointment(
                    db=db,
                    appointment_id=function_args["appointment_id"],
                    customer_phone=customer_phone,
                    reason=function_args.get("reason")
                ))
                function_result = result

                if result.get("success") and result.get("action_completed"):
                    ConversationStateService.update_state(
                        db=db,
                        conversation_id=str(conversation.id),
                        flow_state="action_completed"
                    )
                    print("✅ State updated: action_completed")

            except Exception as e:
                db.rollback()
                function_result = {"success": False, "message": str(e)}

        elif function_name == "reschedule_appointment":
            try:
                result = asyncio.run(ai_service.reschedule_appointment(
                    db=db,
                    appointment_id=function_args["appointment_id"],
                    customer_phone=customer_phone,
                    new_datetime=function_args["new_datetime"],
                    reason=function_args.get("reason")
                ))
                function_result = result

                if result.get("success") and result.get("action_completed"):
                    ConversationStateService.update_state(
                        db=db,
                        conversation_id=str(conversation.id),
                        flow_state="action_completed"
                    )
                    print("✅ State updated: action_completed")

            except Exception as e:
                db.rollback()
                function_result = {"success": False, "message": str(e)}

        elif function_name == "get_customer_info":
            try:
                result = asyncio.run(ai_service.get_customer_info(
                    db=db,
                    conversation_id=str(conversation.id)
                ))
                function_result = result
                print(f"   Customer info: {result.get('customer_info', {})}")
            except Exception as e:
                function_result = {
                    "success": False,
                    "customer_info": {},
                    "has_name": False,
                    "has_email": False
                }

        elif function_name == "set_customer_info":
            try:
                result = asyncio.run(ai_service.set_customer_info(
                    db=db,
                    conversation_id=str(conversation.id),
                    customer_name=function_args.get("customer_name"),
                    customer_email=function_args.get("customer_email"),
                    customer_phone=function_args.get("customer_phone")
                ))
                function_result = result
                print(f"   ✅ Stored: {result.get('customer_info', {})}")
            except Exception as e:
                function_result = {
                    "success": False,
                    "message": str(e)
                }

        else:
            function_result = {"success": False, "message": f"Unknown function: {function_name}"}

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

        # Refresh state for next iteration
        conv_state = ConversationStateService.get_or_create_state(db, str(conversation.id))

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

    # Print final AI response (after all function calls)
    if ai_response.get("content"):
        print(f"\n🤖 AI: {ai_response.get('content')}\n")

        # Save AI response to database
        MessageService.create_message(
            db=db,
            message_sid=str(uuid.uuid4()),
            conversation_id=conversation.id,
            sender_phone=business_phone,
            recipient_phone=customer_phone,
            role="assistant",
            content=ai_response["content"],
            is_inbound=False,
            message_status="sent"
        )

    return ai_response


def interactive_test(business_id: str):
    """Interactive testing - maintains conversation until 'new' command."""
    db = next(get_db())

    # Start with initial customer phone
    customer_phone = f"+1555555{uuid.uuid4().hex[:4]}"

    print("\n" + "=" * 60)
    print("INTERACTIVE SMS TESTING")
    print("Commands:")
    print("  'quit' - exit")
    print("  'new'  - start fresh conversation")
    print("=" * 60)
    print(f"\n🆕 Conversation started (Customer: {customer_phone})")

    # Send initial greeting for new conversation
    send_initial_greeting(db, business_id, customer_phone)

    while True:
        user_input = input("\n👤 Customer message: ").strip()

        if user_input.lower() == 'quit':
            break

        if user_input.lower() == 'new':
            # Generate new phone number for fresh conversation
            customer_phone = f"+1555555{uuid.uuid4().hex[:4]}"
            print(f"\n🆕 Fresh conversation started (Customer: {customer_phone})")
            # Send initial greeting for new conversation
            send_initial_greeting(db, business_id, customer_phone)
            continue

        if not user_input:
            continue

        simulate_customer_message(db, business_id, customer_phone, user_input)

    print("\n👋 Goodbye!")
    db.close()


if __name__ == "__main__":
    BUSINESS_ID = "455fa2cb-ba30-4f49-8cc0-188429d2ec33"
    interactive_test(BUSINESS_ID)