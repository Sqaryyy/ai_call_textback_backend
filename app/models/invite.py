# ============================================================================
# FILE: app/models/invite.py
# UPDATED: Supports both platform and business invites
# ============================================================================
from sqlalchemy import Column, String, Boolean, DateTime, Integer, Enum as SQLEnum, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from datetime import datetime, timezone
import uuid
import secrets
import enum

from app.models.business import Base


class InviteType(str, enum.Enum):
    """Type of invite - platform or business."""
    PLATFORM = "platform"  # Platform admin creates for new business owners
    BUSINESS = "business"  # Business owners create for team members


class Invite(Base):
    __tablename__ = "invites"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Invite type - determines the flow
    invite_type = Column(
        SQLEnum('business', 'platform', name='invitetype', create_type=False),
        nullable=False,
        default='platform',  # Use string directly
        index=True
    )

    # Invite token - unique code for registration link
    token = Column(String(64), unique=True, nullable=False, index=True)

    # Who can use this invite
    email = Column(String(255), nullable=True)  # If None, anyone with link can use it

    # Business association (NULL for platform invites, required for business invites)
    business_id = Column(UUID(as_uuid=True), nullable=True)

    # Role they'll get
    # - Platform invites: Always "owner" (they become business owners)
    # - Business invites: "owner" or "member" (role in specific business)
    role = Column(String(20), default="member", nullable=False)

    # Invite metadata
    created_by = Column(UUID(as_uuid=True), nullable=True)  # User who created the invite
    max_uses = Column(Integer, default=1, nullable=False)  # How many times it can be used
    used_count = Column(Integer, default=0, nullable=False)  # How many times it's been used

    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)  # Last time it was used

    # Constraint: business invites MUST have business_id, platform invites MUST NOT
    __table_args__ = (
        CheckConstraint(
            "(invite_type = 'platform' AND business_id IS NULL) OR "
            "(invite_type = 'business' AND business_id IS NOT NULL)",
            name="check_business_invite_has_business_id"
        ),
    )

    @staticmethod
    def generate_token() -> str:
        """Generate a secure random token for the invite."""
        return secrets.token_urlsafe(32)

    def is_valid(self) -> bool:
        """Check if the invite is still valid and can be used."""
        if not self.is_active:
            return False

        if self.used_count >= self.max_uses:
            return False

        if self.expires_at and datetime.now(timezone.utc) > self.expires_at:
            return False

        return True

    def increment_usage(self):
        """Increment the usage count and update used_at timestamp."""
        self.used_count += 1
        self.used_at = datetime.now(timezone.utc)

        # Auto-deactivate if max uses reached
        if self.used_count >= self.max_uses:
            self.is_active = False

    def is_platform_invite(self) -> bool:
        """Check if this is a platform invite."""
        return self.invite_type == InviteType.PLATFORM

    def is_business_invite(self) -> bool:
        """Check if this is a business invite."""
        return self.invite_type == InviteType.BUSINESS

    def __repr__(self):
        invite_for = f"business {self.business_id}" if self.business_id else "platform"
        return f"<Invite {self.token[:8]}... for {self.email or 'anyone'} ({invite_for})>"

