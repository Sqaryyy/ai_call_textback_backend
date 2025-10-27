# ============================================================================
# FILE: app/models/email_verification.py
# Email verification token model for user registration
# ============================================================================
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime, timedelta, timezone
import uuid
import secrets

from app.models.business import Base


class EmailVerification(Base):
    """
    Model for storing email verification tokens.
    Used during user registration to verify email addresses.
    """
    __tablename__ = "email_verifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Verification token - sent via email
    token = Column(String(64), unique=True, nullable=False, index=True)

    # User relationship
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)

    # Token metadata
    is_used = Column(Boolean, default=False, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    verified_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", backref="email_verifications", lazy="joined")

    @staticmethod
    def generate_token() -> str:
        """Generate a secure random token for email verification."""
        return secrets.token_urlsafe(32)

    @staticmethod
    def create_for_user(user_id: UUID, expiry_hours: int = 24) -> 'EmailVerification':
        """
        Create a new email verification token for a user.

        Args:
            user_id: User ID to create token for
            expiry_hours: Hours until token expires (default 24)

        Returns:
            New EmailVerification instance (not yet added to session)
        """
        token = EmailVerification.generate_token()
        expires_at = datetime.now(timezone.utc) + timedelta(hours=expiry_hours)

        return EmailVerification(
            token=token,
            user_id=user_id,
            expires_at=expires_at,
            is_used=False
        )

    def is_valid(self) -> bool:
        """
        Check if the verification token is still valid.

        Returns:
            True if token is not used and not expired, False otherwise
        """
        if self.is_used:
            return False

        if datetime.now(timezone.utc) > self.expires_at:
            return False

        return True

    def mark_as_used(self):
        """Mark the verification token as used."""
        self.is_used = True
        self.verified_at = datetime.now(timezone.utc)

    def __repr__(self):
        return f"<EmailVerification {self.token[:8]}... user={self.user_id}>"