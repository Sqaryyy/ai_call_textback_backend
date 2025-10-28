# ============================================================================
# FILE: app/models/password_reset.py
# Password reset token model for forgot password flow
# ============================================================================
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime, timedelta, timezone
import uuid
import secrets
from app.models.base import Base


class PasswordReset(Base):
    """
    Model for storing password reset tokens.
    Used in the forgot password / reset password flow.
    """
    __tablename__ = "password_resets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Reset token - sent via email
    token = Column(String(64), unique=True, nullable=False, index=True)

    # User relationship
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)

    # Token metadata
    is_used = Column(Boolean, default=False, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", backref="password_resets", lazy="joined")

    @staticmethod
    def generate_token() -> str:
        """Generate a secure random token for password reset."""
        return secrets.token_urlsafe(32)

    @staticmethod
    def create_for_user(user_id: UUID, expiry_hours: int = 1) -> 'PasswordReset':
        """
        Create a new password reset token for a user.

        Args:
            user_id: User ID to create token for
            expiry_hours: Hours until token expires (default 1 hour for security)

        Returns:
            New PasswordReset instance (not yet added to session)
        """
        token = PasswordReset.generate_token()
        expires_at = datetime.now(timezone.utc) + timedelta(hours=expiry_hours)

        return PasswordReset(
            token=token,
            user_id=user_id,
            expires_at=expires_at,
            is_used=False
        )

    def is_valid(self) -> bool:
        """
        Check if the reset token is still valid.

        Returns:
            True if token is not used and not expired, False otherwise
        """
        if self.is_used:
            return False

        if datetime.now(timezone.utc) > self.expires_at:
            return False

        return True

    def mark_as_used(self):
        """Mark the reset token as used."""
        self.is_used = True
        self.used_at = datetime.now(timezone.utc)

    def __repr__(self):
        return f"<PasswordReset {self.token[:8]}... user={self.user_id}>"