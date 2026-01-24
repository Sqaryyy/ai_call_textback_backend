"""SMS sending tasks with retry logic"""
import logging
from app.config.celery_config import celery_app
from app.config.database import get_db
from app.services.twilio.sms_service import SMSService
from app.services.conversation.conversation_metrics_service import ConversationMetricsService

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=5, default_retry_delay=60)
def send_sms_reply(
        self,
        to_phone: str,
        from_phone: str,
        message_body: str,
        conversation_id: str,
        correlation_id: str,
        conversation_signal: str = "active"
):
    """
    Send SMS reply with automatic retries.

    Separated from main processing to ensure AI-generated replies
    don't get lost if Twilio is temporarily unavailable.

    Args:
        to_phone: Customer phone number
        from_phone: Business phone number
        message_body: AI-generated message to send
        conversation_id: Conversation UUID
        correlation_id: Request correlation ID
        conversation_signal: Conversation state signal (active/soft_close/hard_close)

    Retries:
        - Max 5 attempts
        - Exponential backoff: 60s, 120s, 180s, 240s, 300s
        - Total retry window: ~15 minutes
    """
    db = next(get_db())

    try:
        sms_service = SMSService()

        # Attempt to send SMS
        result = sms_service.send_sms(
            to_phone=to_phone,
            from_phone=from_phone,
            message_body=message_body,
            conversation_id=conversation_id,
            correlation_id=correlation_id,
            db=db
        )

        if not result["success"]:
            # SMS failed - retry
            error_msg = result.get('error', 'Unknown error')
            logger.warning(
                f"SMS send attempt {self.request.retries + 1}/{self.max_retries} failed: {error_msg}. "
                f"Will retry in {60 * (self.request.retries + 1)}s"
            )
            raise Exception(f"SMS send failed: {error_msg}")

        # SMS sent successfully - track metrics
        ConversationMetricsService.increment_message_count(
            db=db,
            conversation_id=conversation_id,
            is_customer_message=False
        )

        # Handle conversation signal transitions
        if conversation_signal == "soft_close":
            logger.info(f"🔔 Conversation signal: soft_close detected for {conversation_id}")
            ConversationMetricsService.mark_soft_close(
                db=db,
                conversation_id=conversation_id
            )
        elif conversation_signal == "hard_close":
            logger.info(f"🔔 Conversation signal: hard_close detected for {conversation_id}")
            # Already handled by booking completion or action completion
            pass

        logger.info(f"✅ SMS reply sent successfully: {result['message_sid']}")
        return {
            "status": "success",
            "message_sid": result['message_sid'],
            "conversation_id": conversation_id
        }

    except Exception as e:
        # Log retry attempt
        logger.error(
            f"❌ SMS send attempt {self.request.retries + 1}/{self.max_retries} failed: {str(e)}"
        )

        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            countdown = 60 * (self.request.retries + 1)
            logger.info(f"⏰ Retrying SMS send in {countdown}s...")
            raise self.retry(exc=e, countdown=countdown)
        else:
            # Max retries exhausted
            logger.error(
                f"🚨 SMS send FAILED after {self.max_retries} attempts. "
                f"Message lost: {message_body[:100]}"
            )
            # Could send alert to admin here
            raise

    finally:
        db.close()