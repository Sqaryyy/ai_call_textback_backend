# ============================================================================
# FILE: app/services/invite/business_invite_service.py
# Business invite service - for inviting team members to a business
# ============================================================================
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any, List, cast
from uuid import UUID
from datetime import datetime, timedelta, timezone

from app.models.invite import Invite, InviteType


class BusinessInviteService:
    """Service layer for business invite operations (owners invite team members)."""

    @staticmethod
    def create_business_invite(
            db: Session,
            business_id: UUID,
            created_by: UUID,
            role: str = "member",
            email: Optional[str] = None,
            max_uses: int = 1,
            expires_in_days: Optional[int] = 7
    ) -> Invite:
        """
        Create a new invite for a business team member.

        Args:
            db: Database session
            business_id: Business the invite is for
            created_by: User ID who created the invite (must be business owner)
            role: Role to assign (owner or member)
            email: Optional specific email (if None, anyone can use)
            max_uses: How many times the invite can be used
            expires_in_days: Days until expiration (None = never expires)

        Returns:
            Created invite object
        """
        # Validate role
        if role not in ["owner", "member"]:
            raise ValueError(f"Invalid role '{role}'. Must be 'owner' or 'member'")

        expires_at = None
        if expires_in_days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

        invite = Invite(
            token=Invite.generate_token(),
            invite_type=InviteType.BUSINESS,
            business_id=business_id,
            created_by=created_by,
            role=role,
            email=email.lower().strip() if email else None,
            max_uses=max_uses,
            expires_at=expires_at,
            is_active=True
        )

        db.add(invite)
        db.commit()
        db.refresh(invite)

        return invite

    @staticmethod
    def validate_business_invite(
            db: Session,
            token: str,
            email: Optional[str] = None
    ) -> tuple[bool, Optional[str], Optional[Invite]]:
        """
        Validate a business invite token.

        Returns:
            (is_valid, error_message, invite)
        """
        invite = db.query(Invite).filter(
            Invite.token == token,
            Invite.invite_type == InviteType.BUSINESS
        ).first()

        if not invite:
            return False, "Business invite not found", None

        if not invite.is_valid():
            if not invite.is_active:
                return False, "Invite has been deactivated", invite
            elif invite.used_count >= invite.max_uses:
                return False, "Invite has reached maximum uses", invite
            elif invite.expires_at and datetime.now(timezone.utc) > invite.expires_at:
                return False, "Invite has expired", invite
            else:
                return False, "Invite is invalid", invite

        # If invite is email-specific, verify the email matches
        if invite.email and email:
            if invite.email.lower() != email.lower():
                return False, "This invite is for a different email address", invite

        return True, None, invite

    @staticmethod
    def use_business_invite(
            db: Session,
            invite_id: UUID
    ) -> bool:
        """
        Mark a business invite as used (increment usage count).
        Returns True if successful, False if invite is no longer valid.
        """
        invite: Optional[Invite] = db.query(Invite).filter(
            Invite.id == invite_id,
            Invite.invite_type == InviteType.BUSINESS
        ).first()

        if not invite:
            return False

        invite.increment_usage()
        db.commit()

        return True

    @staticmethod
    def revoke_business_invite(
            db: Session,
            invite_id: UUID
    ) -> bool:
        """
        Deactivate a business invite (cannot be used anymore).
        Returns True if successful, False if invite not found.
        """
        invite = db.query(Invite).filter(
            Invite.id == invite_id,
            Invite.invite_type == InviteType.BUSINESS
        ).first()

        if not invite:
            return False

        invite.is_active = False
        db.commit()

        return True

    @staticmethod
    def list_business_invites(
            db: Session,
            business_id: UUID,
            include_inactive: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get all invites for a specific business.

        Args:
            db: Database session
            business_id: Business to get invites for
            include_inactive: Whether to include inactive/expired invites
        """
        query = db.query(Invite).filter(
            Invite.business_id == business_id,
            Invite.invite_type == InviteType.BUSINESS
        )

        if not include_inactive:
            query = query.filter(Invite.is_active == True)

        invites: List[Invite] = cast(
            List[Invite],
            query.order_by(Invite.created_at.desc()).all()
        )

        return [
            {
                "id": str(invite.id),
                "token": invite.token,
                "email": invite.email,
                "role": invite.role,
                "max_uses": invite.max_uses,
                "used_count": invite.used_count,
                "is_active": invite.is_active,
                "is_valid": invite.is_valid(),
                "expires_at": invite.expires_at.isoformat() if invite.expires_at else None,
                "created_at": invite.created_at.isoformat(),
                "used_at": invite.used_at.isoformat() if invite.used_at else None
            }
            for invite in invites
        ]

    @staticmethod
    def get_business_invite_stats(
            db: Session,
            business_id: UUID
    ) -> Dict[str, Any]:
        """Get statistics about invites for a specific business."""
        invites: List[Invite] = cast(
            List[Invite],
            db.query(Invite).filter(
                Invite.business_id == business_id,
                Invite.invite_type == InviteType.BUSINESS
            ).all()
        )

        total = len(invites)
        active = sum(1 for inv in invites if inv.is_active)
        used = sum(1 for inv in invites if inv.used_count > 0)
        expired = sum(
            1
            for inv in invites
            if inv.expires_at and datetime.now(timezone.utc) > inv.expires_at
        )
        valid = sum(1 for inv in invites if inv.is_valid())

        return {
            "total_invites": total,
            "active_invites": active,
            "valid_invites": valid,
            "used_invites": used,
            "expired_invites": expired,
            "total_uses": sum(inv.used_count for inv in invites),
        }

    @staticmethod
    def delete_business_invite(
            db: Session,
            invite_id: UUID
    ) -> bool:
        """
        Permanently delete a business invite.
        Returns True if successful, False if invite not found.
        """
        invite = db.query(Invite).filter(
            Invite.id == invite_id,
            Invite.invite_type == InviteType.BUSINESS
        ).first()

        if not invite:
            return False

        db.delete(invite)
        db.commit()

        return True

    @staticmethod
    def extend_business_invite_expiration(
            db: Session,
            invite_id: UUID,
            additional_days: int
    ) -> Optional[Invite]:
        """
        Extend a business invite's expiration date.
        Returns updated invite or None if not found.
        """
        invite: Optional[Invite] = cast(
            Optional[Invite],
            db.query(Invite).filter(
                Invite.id == invite_id,
                Invite.invite_type == InviteType.BUSINESS
            ).first()
        )

        if not invite:
            return None

        if invite.expires_at:
            invite.expires_at = invite.expires_at + timedelta(days=additional_days)
        else:
            invite.expires_at = datetime.now(timezone.utc) + timedelta(days=additional_days)

        db.commit()
        db.refresh(invite)

        return invite

    @staticmethod
    def get_invite_url(invite: Invite, base_url: str) -> str:
        """
        Generate the full invite URL for frontend.

        Args:
            invite: The invite object
            base_url: Base URL of your frontend (e.g., "https://yourdomain.com")

        Returns:
            Full invite URL like: https://yourdomain.com/register?invite=TOKEN
        """
        return f"{base_url.rstrip('/')}/register?invite={invite.token}"