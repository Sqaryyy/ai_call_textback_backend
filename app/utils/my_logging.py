# app/utils/my_logging.py
"""Logging configuration"""
import logging
import sys
from app.config.settings import get_settings


def setup_logging(verbose=True):
    """Configure application logging"""
    settings = get_settings()

    if verbose:
        level = getattr(logging, settings.LOG_LEVEL)
    else:
        level = logging.WARNING

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )

    if not verbose:
        # Silence noisy loggers
        noisy_loggers = [
            "sqlalchemy",
            "sqlalchemy.engine",
            "sqlalchemy.pool",
            "sqlalchemy.orm",
            "sqlalchemy.dialects",
            "alembic",
            "httpx",
            "uvicorn",
            "uvicorn.error",
            "uvicorn.access",
        ]
        for name in noisy_loggers:
            logger = logging.getLogger(name)
            logger.setLevel(logging.ERROR)
            logger.propagate = False
