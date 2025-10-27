# ============================================================================
# FILE: app/models/refresh_token.py
# Refresh token model for JWT token management with auto-cleanup
# ============================================================================
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, event
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Session
from sqlalchemy.sql import func
from datetime import datetime, timezone
import uuid
import secrets

from app.models.business import Base


class RefreshToken(Base):
    """
    Model for storing refresh tokens in the database.
    Allows for token revocation and tracking token usage.
    """
    __tablename__ = "refresh_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Token value - stored hashed for security
    token = Column(String(255), unique=True, nullable=False, index=True)

    # User relationship
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)

    # Token metadata
    is_revoked = Column(Boolean, default=False, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", backref="refresh_tokens", lazy="joined")

    @staticmethod
    def generate_token() -> str:
        """Generate a secure random token for refresh."""
        return secrets.token_urlsafe(64)

    def is_valid(self) -> bool:
        """
        Check if the refresh token is still valid.

        Returns:
            True if token is not revoked and not expired, False otherwise
        """
        if self.is_revoked:
            return False

        if datetime.now(timezone.utc) > self.expires_at:
            return False

        return True

    def revoke(self):
        """Revoke this refresh token."""
        self.is_revoked = True

    def update_last_used(self):
        """Update the last used timestamp."""
        self.last_used_at = datetime.now(timezone.utc)

    def __repr__(self):
        return f"<RefreshToken {self.token[:8]}... user={self.user_id}>"


# ============================================================================
# Auto-cleanup: Delete expired tokens on session flush
# ============================================================================

@event.listens_for(Session, "after_flush")
def cleanup_expired_tokens(session, flush_context):
    """
    Automatically delete expired refresh tokens after each database flush.

    This runs periodically to keep the database clean without requiring
    a separate cleanup job.
    """
    try:
        # Only run cleanup occasionally (not every flush)
        # Use a simple random check to run ~10% of the time
        import random
        if random.random() > 0.1:
            return

        # Delete expired tokens
        deleted = session.query(RefreshToken).filter(
            RefreshToken.expires_at < datetime.now(timezone.utc)
        ).delete(synchronize_session=False)

        if deleted > 0:
            session.commit()

    except Exception:
        # Don't let cleanup errors break the main transaction
        session.rollback()