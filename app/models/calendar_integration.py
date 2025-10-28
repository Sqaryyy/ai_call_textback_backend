# ===== app/models/calendar_integration.py =====
from sqlalchemy import Column, String, Boolean, DateTime, LargeBinary, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
from app.models.base import Base
import uuid


class CalendarIntegration(Base):
    __tablename__ = "calendar_integrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"))

    provider = Column(String)  # 'google', 'calendly', 'outlook', 'cal.com'
    is_active = Column(Boolean, default=True)
    is_primary = Column(Boolean, default=False)  # For businesses with multiple calendars

    # OAuth tokens (use encryption library like cryptography.fernet)
    access_token_encrypted = Column(LargeBinary)
    refresh_token_encrypted = Column(LargeBinary)
    token_expires_at = Column(DateTime(timezone=True))

    # Provider-specific config (stored as JSON for flexibility)
    provider_config = Column(JSON)  # calendar_id, event_type_uri, etc.

    # Sync settings
    sync_direction = Column(String, default="bidirectional")  # 'read_only', 'write_only', 'bidirectional'
    auto_sync_enabled = Column(Boolean, default=True)
    last_sync_at = Column(DateTime(timezone=True))
    last_sync_status = Column(String)  # 'success', 'failed', 'partial'

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), onupdate=datetime.utcnow)
