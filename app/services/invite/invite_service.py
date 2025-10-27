# ============================================================================
# FILE: app/services/invite/invite_service.py
# Generic invite service - routes to platform or business services
# ============================================================================
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID

from app.models.invite import Invite, InviteType
from app.services.invite.platform_invite_service import PlatformInviteService
from app.services.invite.business_invite_service import BusinessInviteService


class InviteService:
    """
    Generic invite service that routes to appropriate service based on invite type.
    Use this for operations that work across both invite types.
    """

    @staticmethod
    def get_invite_by_token(
            db: Session,
            token: str
    ) -> Optional[Invite]:
        """Get an invite by its token (works for both platform and business invites)."""
        return db.query(Invite).filter(Invite.token == token).first()

    @staticmethod
    def validate_invite(
            db: Session,
            token: str,
            email: Optional[str] = None
    ) -> tuple[bool, Optional[str], Optional[Invite]]:
        """
        Validate an invite token (auto-detects type and routes to correct service).

        Returns:
            (is_valid, error_message, invite)
        """
        invite = InviteService.get_invite_by_token(db, token)

        if not invite:
            return False, "Invite not found", None

        # Route to appropriate service based on type
        if invite.invite_type == InviteType.PLATFORM:
            return PlatformInviteService.validate_platform_invite(db, token, email)
        else:
            return BusinessInviteService.validate_business_invite(db, token, email)

    @staticmethod
    def use_invite(
            db: Session,
            invite_id: UUID
    ) -> bool:
        """
        Mark an invite as used (auto-detects type and routes to correct service).
        Returns True if successful, False if invite is no longer valid.
        """
        invite = db.query(Invite).filter(Invite.id == invite_id).first()

        if not invite:
            return False

        # Route to appropriate service based on type
        if invite.invite_type == InviteType.PLATFORM:
            return PlatformInviteService.use_platform_invite(db, invite_id)
        else:
            return BusinessInviteService.use_business_invite(db, invite_id)

    @staticmethod
    def get_invite_url(invite: Invite, base_url: str) -> str:
        """
        Generate the full invite URL for frontend (works for both types).

        Args:
            invite: The invite object
            base_url: Base URL of your frontend (e.g., "https://yourdomain.com")

        Returns:
            Full invite URL like: https://yourdomain.com/register?invite=TOKEN
        """
        # Both types use same URL - frontend will detect invite type
        return f"{base_url.rstrip('/')}/register?invite={invite.token}"