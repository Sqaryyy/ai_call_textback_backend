# app/config/celery_config.py
"""Celery configuration and task routing"""
from celery import Celery
from kombu import Queue

from app.config.settings import get_settings

settings = get_settings()


def create_celery_app() -> Celery:
    """Create and configure Celery application"""

    celery_app = Celery(
        "afterhours_service",
        broker=settings.CELERY_BROKER_URL,
        backend=settings.CELERY_RESULT_BACKEND,
    )

    # Configure Celery
    celery_app.conf.update(
        task_serializer=settings.CELERY_TASK_SERIALIZER,
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,

        # Task routing
        task_routes={
            "app.tasks.conversation_tasks.process_sms_message": {"queue": "conversations"},
            "app.tasks.call_tasks.process_incoming_call": {"queue": "calls"},
            "app.tasks.appointment_tasks.*": {"queue": "appointments"},
            "app.tasks.calendar_tasks.*": {"queue": "appointments"},
            "app.tasks.maintenance_tasks.*": {"queue": "maintenance"},
            "app.tasks.knowledge_tasks.*": {"queue": "knowledge"},  # ADD THIS LINE
        },

        # Queue definitions
        task_queues=(
            Queue("conversations", routing_key="conversations"),
            Queue("calls", routing_key="calls"),
            Queue("appointments", routing_key="appointments"),
            Queue("maintenance", routing_key="maintenance"),
            Queue("knowledge", routing_key="knowledge"),  # ADD THIS LINE
        ),

        # Worker settings
        worker_max_tasks_per_child=1000,
        worker_prefetch_multiplier=1,
        task_acks_late=True,

        # Retry settings
        task_retry_max_retries=3,
        task_retry_delay=60,  # 1 minute

        # Fix deprecation warning for Celery 6+
        broker_connection_retry_on_startup=True,
    )

    # Auto-discover tasks
    celery_app.autodiscover_tasks([
        "app.tasks.call_tasks",
        "app.tasks.conversation_tasks",
        "app.tasks.appointment_tasks",
        "app.tasks.calendar_tasks",
        "app.tasks.maintenance_tasks",
        "app.tasks.knowledge_tasks",  # ADD THIS LINE
    ])

    return celery_app


# Create the Celery app instance
celery_app = create_celery_app()