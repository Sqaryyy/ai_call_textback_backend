# app/tasks/call_tasks.py - WITH METRICS TRACKING
"""Call processing tasks"""
import logging
import uuid
from datetime import datetime, timezone, timedelta

from app.config.celery_config import celery_app
from app.config.database import get_db
from app.models.call_event import CallEvent
from app.models.conversation import Conversation
from app.services.business.business_service import BusinessService
from app.services.twilio.sms_service import sms_service
from app.services.conversation.conversation_metrics_service import ConversationMetricsService

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def process_incoming_call(
        self, call_sid: str, caller_phone: str, business_phone: str,
        call_status: str, caller_location: dict, correlation_id: str
):
    """Process incoming call - create conversation and send SMS"""
    try:
        logger.info(f"Processing missed call {call_sid} from {caller_phone}")

        db = next(get_db())
        try:
            # 1. Find business
            business = BusinessService.get_business_by_phone(db, business_phone)

            # 2. Log call event
            call_event = CallEvent(
                id=uuid.uuid4(),
                twilio_call_sid=call_sid,
                business_id=business.id,
                caller_phone=caller_phone,
                business_phone=business_phone,
                call_status=call_status,
                direction="inbound",
                caller_location=caller_location,
                call_metadata={"correlation_id": correlation_id}
            )
            db.add(call_event)
            db.flush()  # Get call_event.id before creating metrics

            # 3. Create conversation
            conversation_id = uuid.uuid4()
            expires_at = datetime.now(timezone.utc) + timedelta(hours=2)

            conversation = Conversation(
                id=conversation_id,
                customer_phone=caller_phone,
                business_phone=business_phone,
                business_id=business.id,
                status="active",
                flow_state="greeting",
                context={
                    "call_sid": call_sid,
                    "initiated_by": "missed_call",
                    "correlation_id": correlation_id
                },
                expires_at=expires_at
            )
            db.add(conversation)
            db.flush()  # Get conversation.id before creating metrics

            # 4. Create metrics tracking
            ConversationMetricsService.create_metrics(
                db=db,
                conversation_id=str(conversation_id),
                call_event_id=str(call_event.id),
                business_id=str(business.id)
            )

            # 5. Send SMS via service
            message_body = (
                f"Hi! You recently called {business.name} but we weren't able to answer. "
                f"I'm here to help you right now! What can I assist you with today?"
            )

            sms_result = sms_service.send_sms(
                to_phone=caller_phone,
                from_phone=business_phone,
                message_body=message_body,
                conversation_id=conversation_id,
                correlation_id=correlation_id,
                db=db
            )

            # 6. Update metrics - increment bot message count for initial outreach
            ConversationMetricsService.increment_message_count(
                db=db,
                conversation_id=str(conversation_id),
                is_customer_message=False
            )

            db.commit()

            logger.info(f"Completed processing call {call_sid} with metrics tracking")
            return {
                "status": "completed",
                "call_sid": call_sid,
                "conversation_id": conversation_id,
                "sms_sent": sms_result["success"]
            }

        finally:
            db.close()

    except Exception as exc:
        logger.error(f"Error processing call {call_sid}: {str(exc)}")
        raise self.retry(countdown=60 * (self.request.retries + 1))