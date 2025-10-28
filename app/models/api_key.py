# ===== app/models/api_key.py =====
from sqlalchemy import Column, String, DateTime, Boolean, JSON, Integer, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.models.base import Base


class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False)

    # API Key identification
    key_prefix = Column(String(12), nullable=False)  # e.g., "mctb_live_abc"
    key_hash = Column(String(128), nullable=False, unique=True, index=True)  # SHA256 hash

    # Metadata
    name = Column(String(100), nullable=False)  # "Production API", "Zapier Integration"
    description = Column(String(500))

    # Permissions
    scopes = Column(JSON, default=list)  # ["read:metrics", "read:conversations", "write:webhooks"]

    # Status & lifecycle
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Usage tracking
    last_used_at = Column(DateTime(timezone=True))
    usage_count = Column(Integer, default=0)

    # Rate limiting (requests per hour)
    rate_limit = Column(Integer, default=1000)

    # IP restrictions (optional security)
    allowed_ips = Column(JSON, default=list)  # ["192.168.1.1", "10.0.0.0/24"]

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    revoked_at = Column(DateTime(timezone=True))
    revoked_reason = Column(String(500))

    __table_args__ = (
        Index('ix_api_keys_business_active', 'business_id', 'is_active'),
    )
