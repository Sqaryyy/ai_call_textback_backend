# ===== app/models/api_request_log.py =====
from sqlalchemy import Column, String, DateTime, Integer, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid
from app.models.base import Base


class APIRequestLog(Base):
    """Log API requests for analytics and debugging"""
    __tablename__ = "api_request_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    api_key_id = Column(UUID(as_uuid=True), ForeignKey("api_keys.id"), nullable=False)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False)

    # Request details
    method = Column(String(10), nullable=False)  # GET, POST, etc.
    path = Column(String(500), nullable=False)
    query_params = Column(JSONB)

    # Response details
    status_code = Column(Integer, nullable=False)
    response_time_ms = Column(Integer)

    # Client info
    ip_address = Column(String(45))  # IPv6 compatible
    user_agent = Column(String(500))

    # Error tracking
    error_message = Column(String(1000))

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('ix_api_logs_key_created', 'api_key_id', 'created_at'),
        Index('ix_api_logs_business_created', 'business_id', 'created_at'),
    )