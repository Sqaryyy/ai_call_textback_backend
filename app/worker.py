"""
Celery worker entry point
Handles all background task processing
"""
import logging
from celery.signals import worker_ready, worker_shutdown

from app.config.celery_config import create_celery_app
from app.config.settings import get_settings
from app.utils.my_logging import setup_logging

# Setup logging first
setup_logging()
logger = logging.getLogger(__name__)

# Create Celery app
settings = get_settings()
celery_app = create_celery_app()

@worker_ready.connect
def worker_ready_handler(sender=None, **kwargs):
    """Handle worker startup"""
    logger.info("🚀 Celery worker ready!")
    logger.info(f"📋 Registered tasks: {list(celery_app.tasks.keys())}")
    logger.info("📱 Ready to process calls and conversations...")

@worker_shutdown.connect
def worker_shutdown_handler(sender=None, **kwargs):
    """Handle worker shutdown"""
    logger.info("🛑 Celery worker shutting down...")

if __name__ == "__main__":
    # Run worker directly
    celery_app.start([
        'worker',
        '--loglevel=info',
        '--concurrency=4',
        '--max-tasks-per-child=1000'
    ])