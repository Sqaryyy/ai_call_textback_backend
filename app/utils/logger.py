# app/utils/logger.py
"""
Unified application logger - use this everywhere instead of print()
"""
import logging
from typing import Any, Dict, Optional


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a module."""
    return logging.getLogger(name)


def sanitize_for_logging(data: Any) -> Any:
    """
    Remove sensitive fields from data before logging.

    CRITICAL: This prevents accidentally logging passwords, tokens, etc.
    """
    if not isinstance(data, dict):
        return data

    # Fields that should NEVER appear in logs
    SENSITIVE_FIELDS = {
        'password', 'hashed_password', 'token', 'access_token', 'refresh_token',
        'api_key', 'secret', 'authorization', 'cookie', 'session',
        'verification_token', 'reset_token', 'invite_token'
    }

    sanitized = {}
    for key, value in data.items():
        lower_key = key.lower()

        # Redact sensitive fields
        if any(sensitive in lower_key for sensitive in SENSITIVE_FIELDS):
            sanitized[key] = "***REDACTED***"
        # Recursively sanitize nested dicts
        elif isinstance(value, dict):
            sanitized[key] = sanitize_for_logging(value)
        else:
            sanitized[key] = value

    return sanitized


def log_request(logger: logging.Logger, method: str, path: str, user_id: Optional[str] = None):
    """Log an incoming request (safe for production)."""
    logger.info(f"Request: {method} {path}", extra={
        "method": method,
        "path": path,
        "user_id": user_id
    })


def log_error(logger: logging.Logger, message: str, error: Exception, context: Optional[Dict] = None):
    """Log an error with context (automatically sanitizes)."""
    safe_context = sanitize_for_logging(context) if context else {}
    logger.error(f"{message}: {str(error)}", extra={
        "error_type": type(error).__name__,
        "context": safe_context
    })