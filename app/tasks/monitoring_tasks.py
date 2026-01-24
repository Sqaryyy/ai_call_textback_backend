# ============================================================================
# FILE: app/tasks/monitoring_tasks.py (NEW)
# Background tasks for monitoring Celery itself
# ============================================================================
from celery import shared_task
from app.config.email_config import email_service
from app.config.celery_config import celery_app
from app.utils.logger import get_logger

logger = get_logger(__name__)


@shared_task(name="app.tasks.monitoring_tasks.check_queue_health")
def check_queue_health():
    """
    Periodic task to check queue health and alert if backed up.

    Run this every 15 minutes via Celery Beat.
    """
    import asyncio
    from app.config.redis import get_redis

    async def _check():
        try:
            redis_client = await get_redis()

            queues = ["conversations", "calls", "appointments", "maintenance", "emails"]
            backed_up_queues = []

            for queue_name in queues:
                redis_key = f"celery:queue:{queue_name}"
                length = await redis_client.llen(redis_key)

                # Alert if queue has >100 tasks
                if length > 100:
                    backed_up_queues.append(f"{queue_name}: {length} tasks")
                    logger.warning(f"Queue backed up: {queue_name} - {length} tasks")

            await redis_client.close()

            # Send alert if any queue is backed up
            if backed_up_queues:
                await email_service.send_alert(
                    subject="Celery Queue Backup Detected",
                    body=f"""
Celery queues are backed up

Backed up queues:
{chr(10).join(backed_up_queues)}

Possible causes:
- Workers down or slow
- High task volume
- Tasks failing and retrying

Action: Check worker logs and restart if needed
""",
                    severity="warning"
                )

        except Exception as e:
            logger.error(f"Queue health check failed: {e}")

    # Run async code
    asyncio.run(_check())