"""Conversation processing tasks"""
import json
import re
import asyncio
import logging
from datetime import datetime

from app.config.celery_config import celery_app
from app.config.database import get_db
from app.services.conversation.conversation_service import ConversationService
from app.services.conversation.conversation_state_service import ConversationStateService
from app.services.conversation.conversation_metrics_service import ConversationMetricsService
from app.services.message.message_service import MessageService
from app.models.conversation_metrics import ConversationMetrics
from app.services.business.business_service import BusinessService
from app.services.appointment.appointment_service import AppointmentService
from app.services.ai.ai_service import AIService
from app.services.twilio.sms_service import SMSService
from app.tasks.calendar_tasks import sync_appointment_to_calendar

logger = logging.getLogger(__name__)


def extract_customer_info(messages):
    """Extract customer info from conversation history"""
    customer_info = {}

    for msg in reversed(messages[-20:]):  # Check last 20 messages
        if not hasattr(msg, 'content') or not msg.content:
            continue

        content_lower = msg.content.lower()

        # Extract name
        if not customer_info.get("name") and "name is" in content_lower:
            name_part = content_lower.split("name is")[-1].strip()
            name = name_part.split()[0].strip(',.!?')
            if name and len(name) > 1:
                customer_info["name"] = name.title()

        # Also check for "I'm [name]" or "my name's [name]"
        if not customer_info.get("name"):
            if "i'm " in content_lower or "my name" in content_lower:
                patterns = [r"i'?m ([a-zA-Z]+)", r"my name'?s? ([a-zA-Z]+)"]
                for pattern in patterns:
                    match = re.search(pattern, content_lower)
                    if match:
                        name = match.group(1).strip()
                        if len(name) > 1:
                            customer_info["name"] = name.title()
                            break

        # Extract email
        if not customer_info.get("email") and "@" in msg.content:
            email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', msg.content)
            if email_match:
                customer_info["email"] = email_match.group(0)

    return customer_info


@celery_app.task(bind=True, max_retries=3)
def process_sms_message(
        self, message_sid: str, sender_phone: str, business_phone: str,
        message_body: str, media_urls: list, correlation_id: str
):
    """Process incoming SMS message with stateful conversation"""
    try:
        logger.info(f"Processing SMS {message_sid} from {sender_phone}")

        db = next(get_db())

        try:
            # 1. Get business
            business = BusinessService.get_business_by_phone(db, business_phone)
            if not business:
                logger.error(f"Business not found for phone: {business_phone}")
                return {"status": "failed", "reason": "business_not_found"}

            # 2. Find or create conversation
            conversation = ConversationService.find_or_create_conversation(
                db, sender_phone, business_phone, business.id
            )

            # Store conversation ID immediately as string to avoid session detachment issues
            conversation_id = str(conversation.id)
            logger.info(f"Found existing conversation: {conversation_id}")

            # 3. METRICS: Mark customer responded on first message
            ConversationMetricsService.mark_customer_responded(db, conversation_id)

            # Check if conversation went cold and mark as dropped off
            messages = MessageService.get_conversation_messages(db, conversation_id)
            if len(messages) > 0:
                last_message = messages[-1]
                time_since_last = (datetime.now() - last_message.created_at).total_seconds()

                # If more than 2 hours since last message, previous conversation dropped off
                if time_since_last > 7200:  # 2 hours
                    metrics = db.query(ConversationMetrics).filter(
                        ConversationMetrics.conversation_id == conversation_id
                    ).first()

                    # Only mark as dropped if conversation wasn't already completed
                    if metrics and not metrics.conversation_completed and not metrics.booking_created:
                        ConversationMetricsService.mark_conversation_completed(
                            db=db,
                            conversation_id=conversation_id,
                            last_flow_state=conversation.flow_state,
                            dropped_off=True
                        )
                        logger.info(f"Marked previous conversation as dropped off (inactive for {time_since_last/3600:.1f} hours)")

            # 4. Get or create conversation state
            conv_state = ConversationStateService.get_or_create_state(
                db=db,
                conversation_id=conversation_id
            )

            # Reset state if previous action completed
            if conv_state.flow_state == "action_completed":
                logger.info("Resetting conversation state (previous action completed)")
                ConversationStateService.update_state(
                    db=db,
                    conversation_id=conversation_id,
                    flow_state="gathering_info"
                )
                conv_state = ConversationStateService.get_or_create_state(db, conversation_id)

            # 5. Add customer message
            MessageService.create_message(
                db=db,
                message_sid=message_sid,
                conversation_id=conversation_id,
                sender_phone=sender_phone,
                recipient_phone=business_phone,
                role="customer",
                content=message_body,
                is_inbound=True,
                media_urls=media_urls
            )
            ConversationService.increment_message_count(db, conversation_id)

            # METRICS: Track customer message
            ConversationMetricsService.increment_message_count(
                db=db,
                conversation_id=conversation_id,
                is_customer_message=True
            )

            # 6. Get messages and extract customer info
            messages = MessageService.get_conversation_messages(db, conversation_id)

            # Extract customer info from conversation history
            customer_info = extract_customer_info(messages)
            if customer_info:
                existing_info = conv_state.state_data.get("customer_info", {})
                updated_info = {**existing_info, **customer_info}
                ConversationStateService.update_state(
                    db=db,
                    conversation_id=conversation_id,
                    state_data={"customer_info": updated_info}
                )
                conv_state = ConversationStateService.get_or_create_state(db, conversation_id)

            # 7. Get context and format messages
            business_context = BusinessService.get_business_context(db, business.id)
            business_context["business_id"] = str(business.id)

            formatted_messages = MessageService.format_messages_for_ai(messages)

            # 8. Initialize AI service and get response
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

            # 9. Handle function calls in a loop
            while ai_response.get("function_call"):
                function_name = ai_response['function_call']['name']
                function_args = ai_response['function_call']['arguments']

                logger.info(f"Executing function: {function_name} with args: {function_args}")

                # Execute function based on name
                if function_name == "book_appointment":
                    try:
                        appointment = AppointmentService.create_appointment(
                            db=db,
                            conversation_id=conversation_id,
                            business_id=str(business.id),
                            customer_phone=sender_phone,
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

                        # Queue calendar sync
                        sync_appointment_to_calendar.delay(str(appointment.id))

                        # METRICS: Track successful booking
                        service_price = business_context.get("service_catalog", {}).get(
                            function_args.get("service_type", ""), {}
                        ).get("price")

                        ConversationMetricsService.mark_booking_created(
                            db=db,
                            conversation_id=conversation_id,
                            appointment_id=str(appointment.id),
                            estimated_revenue=service_price
                        )

                        # Mark conversation as completed successfully
                        ConversationMetricsService.mark_conversation_completed(
                            db=db,
                            conversation_id=conversation_id,
                            last_flow_state="booking_completed",
                            dropped_off=False
                        )

                        function_result = {
                            "success": True,
                            "appointment_id": str(appointment.id),
                            "message": "Appointment booked successfully",
                            "action_completed": True
                        }

                        # Update conversation state
                        ConversationStateService.update_state(
                            db=db,
                            conversation_id=conversation_id,
                            flow_state="action_completed"
                        )
                        logger.info("State updated: action_completed")

                    except Exception as e:
                        db.rollback()
                        function_result = {"success": False, "error": str(e)}
                        logger.error(f"Error booking appointment: {str(e)}")

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
                            limit=60
                        ))
                        function_result = {"slots": slots, "count": len(slots)}
                        logger.info(f"Found {len(slots)} available slots")
                    except Exception as e:
                        db.rollback()
                        function_result = {"slots": [], "count": 0, "error": str(e)}
                        logger.error(f"Error getting slots: {str(e)}")

                elif function_name == "get_customer_appointments":
                    try:
                        appointments = asyncio.run(ai_service.get_customer_appointments(
                            db=db,
                            customer_phone=sender_phone,
                            business_id=str(business.id),
                            include_past=function_args.get("include_past", False)
                        ))
                        function_result = {"success": True, "appointments": appointments}
                    except Exception as e:
                        function_result = {"success": False, "appointments": [], "error": str(e)}
                        logger.error(f"Error getting appointments: {str(e)}")

                elif function_name == "cancel_appointment":
                    try:
                        result = asyncio.run(ai_service.cancel_appointment(
                            db=db,
                            appointment_id=function_args["appointment_id"],
                            customer_phone=sender_phone,
                            reason=function_args.get("reason")
                        ))
                        function_result = result

                        # Update conversation state after cancellation
                        if result.get("success") and result.get("action_completed"):
                            ConversationStateService.update_state(
                                db=db,
                                conversation_id=conversation_id,
                                flow_state="action_completed"
                            )
                            logger.info("State updated: action_completed")

                    except Exception as e:
                        db.rollback()
                        function_result = {"success": False, "message": str(e)}
                        logger.error(f"Error canceling appointment: {str(e)}")

                elif function_name == "reschedule_appointment":
                    try:
                        result = asyncio.run(ai_service.reschedule_appointment(
                            db=db,
                            appointment_id=function_args["appointment_id"],
                            customer_phone=sender_phone,
                            new_datetime=function_args["new_datetime"],
                            reason=function_args.get("reason")
                        ))
                        function_result = result

                        # Update conversation state after rescheduling
                        if result.get("success") and result.get("action_completed"):
                            ConversationStateService.update_state(
                                db=db,
                                conversation_id=conversation_id,
                                flow_state="action_completed"
                            )
                            logger.info("State updated: action_completed")

                    except Exception as e:
                        db.rollback()
                        function_result = {"success": False, "message": str(e)}
                        logger.error(f"Error rescheduling appointment: {str(e)}")

                else:
                    function_result = {"success": False, "message": f"Unknown function: {function_name}"}
                    logger.warning(f"Unknown function called: {function_name}")

                # Add function call and result to message history
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

            # 10. Send final AI response via SMS
            if ai_response.get("content"):
                sms_service = SMSService()
                result = sms_service.send_sms(
                    to_phone=sender_phone,
                    from_phone=business_phone,
                    message_body=ai_response["content"],
                    conversation_id=conversation_id,
                    correlation_id=correlation_id,
                    db=db
                )

                # METRICS: Track bot message
                if result["success"]:
                    ConversationMetricsService.increment_message_count(
                        db=db,
                        conversation_id=conversation_id,
                        is_customer_message=False
                    )
                    logger.info(f"SMS sent successfully: {result['message_sid']}")
                else:
                    logger.error(f"SMS failed to send: {result.get('error')}")

            logger.info(f"Successfully processed SMS {message_sid}")
            return {"status": "completed", "message_sid": message_sid}

        finally:
            db.close()

    except Exception as exc:
        logger.error(f"Error processing SMS {message_sid}: {str(exc)}", exc_info=True)
        raise self.retry(countdown=60 * (self.request.retries + 1))
