# ============================================================================
# FILE: app/api/v1/admin/invites.py
# Platform admin endpoints for creating invites for business owners
# CRITICAL: Contains PII (email addresses)
# ============================================================================
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from app.api.dependencies import get_db, require_platform_admin
from app.services.invite.platform_invite_service import PlatformInviteService
from app.models.auth.user import User
from app.models.invite import Invite
from app.config.settings import settings
from app.utils.logger import get_logger
from app.schemas.admin.invites import (
    MessageResponse,
    ExtendInviteRequest,
    PlatformInviteResponse,
    PlatformInviteStatsResponse,
    CreatePlatformInviteRequest
)
logger = get_logger(__name__)
router = APIRouter(prefix="/invites", tags=["Admin - Platform Invites"])

# ============================================================================
# Platform Invite Management Endpoints
# ============================================================================

@router.post("/", response_model=PlatformInviteResponse, status_code=status.HTTP_201_CREATED)
async def create_platform_invite(
        request: CreatePlatformInviteRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Create a new platform invite for onboarding business owners.

    Requires platform admin role. The invite will allow someone to register
    as a business owner on the platform.
    """
    # Log action without email (PII)
    invite_type = "email-specific" if request.email else "open"
    logger.info(
        f"Admin {current_user.id} creating platform invite - "
        f"Type: {invite_type}, Max uses: {request.max_uses}, Expires in: {request.expires_in_days} days"
    )

    try:
        invite = PlatformInviteService.create_platform_invite(
            db=db,
            created_by=current_user.id,
            email=request.email,
            max_uses=request.max_uses,
            expires_in_days=request.expires_in_days
        )

        # Generate the invite URL
        invite_url = PlatformInviteService.get_invite_url(invite, settings.FRONTEND_URL)

        logger.info(f"Platform invite {invite.id} created successfully by admin {current_user.id}")

        return PlatformInviteResponse(
            id=str(invite.id),
            token=invite.token,
            email=invite.email,
            role=invite.role,
            max_uses=invite.max_uses,
            used_count=invite.used_count,
            is_active=invite.is_active,
            is_valid=invite.is_valid(),
            expires_at=invite.expires_at.isoformat() if invite.expires_at else None,
            created_at=invite.created_at.isoformat(),
            used_at=invite.used_at.isoformat() if invite.used_at else None,
            invite_url=invite_url
        )

    except Exception as e:
        logger.error(f"Error creating platform invite: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create platform invite: {str(e)}"
        )


@router.get("/", response_model=List[PlatformInviteResponse])
async def list_platform_invites(
        include_inactive: bool = Query(
            False,
            description="Include inactive/expired invites"
        ),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    List all platform invites.

    Requires platform admin role.
    """
    filter_str = " (including inactive)" if include_inactive else " (active only)"
    logger.info(f"Admin {current_user.id} listing platform invites{filter_str}")

    invites_data = PlatformInviteService.list_platform_invites(
        db=db,
        include_inactive=include_inactive
    )

    logger.info(f"Returning {len(invites_data)} platform invites")

    return [
        PlatformInviteResponse(
            **invite,
            invite_url=f"{settings.FRONTEND_URL}/register?invite={invite['token']}"
        )
        for invite in invites_data
    ]


@router.get("/stats", response_model=PlatformInviteStatsResponse)
async def get_platform_invite_stats(
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Get statistics about platform invites.

    Requires platform admin role.
    """
    logger.info(f"Admin {current_user.id} requesting platform invite stats")

    stats = PlatformInviteService.get_platform_invite_stats(db=db)

    logger.info(
        f"Invite stats: {stats['total_invites']} total, {stats['active_invites']} active, "
        f"{stats['used_invites']} used, {stats['expired_invites']} expired"
    )

    return PlatformInviteStatsResponse(**stats)


@router.get("/{invite_id}", response_model=PlatformInviteResponse)
async def get_platform_invite(
        invite_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Get details of a specific platform invite.

    Requires platform admin role.
    """
    logger.info(f"Admin {current_user.id} viewing platform invite {invite_id}")

    from app.models.invite import InviteType

    invite = db.query(Invite).filter(
        Invite.id == invite_id,
        Invite.invite_type == InviteType.PLATFORM
    ).first()

    if not invite:
        logger.warning(f"Platform invite {invite_id} not found - requested by admin {current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Platform invite not found"
        )

    logger.debug(
        f"Retrieved invite - Role: {invite.role}, Active: {invite.is_active}, "
        f"Used: {invite.used_count}/{invite.max_uses}"
    )

    invite_url = PlatformInviteService.get_invite_url(invite, settings.FRONTEND_URL)

    return PlatformInviteResponse(
        id=str(invite.id),
        token=invite.token,
        email=invite.email,
        role=invite.role,
        max_uses=invite.max_uses,
        used_count=invite.used_count,
        is_active=invite.is_active,
        is_valid=invite.is_valid(),
        expires_at=invite.expires_at.isoformat() if invite.expires_at else None,
        created_at=invite.created_at.isoformat(),
        used_at=invite.used_at.isoformat() if invite.used_at else None,
        invite_url=invite_url
    )


@router.patch("/{invite_id}/revoke", response_model=MessageResponse)
async def revoke_platform_invite(
        invite_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Revoke (deactivate) a platform invite so it can no longer be used.

    Requires platform admin role.
    """
    logger.info(f"Admin {current_user.id} revoking platform invite {invite_id}")

    from app.models.invite import InviteType

    invite = db.query(Invite).filter(
        Invite.id == invite_id,
        Invite.invite_type == InviteType.PLATFORM
    ).first()

    if not invite:
        logger.warning(f"Revoke failed - platform invite {invite_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Platform invite not found"
        )

    if not invite.is_active:
        logger.warning(f"Revoke failed - invite {invite_id} already revoked")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invite is already revoked"
        )

    success = PlatformInviteService.revoke_platform_invite(db, invite_id)

    if not success:
        logger.error(f"Failed to revoke platform invite {invite_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke platform invite"
        )

    logger.info(f"Platform invite {invite_id} revoked successfully by admin {current_user.id}")

    return MessageResponse(
        message="Platform invite revoked successfully",
        details={
            "invite_id": str(invite_id),
            "token": invite.token
        }
    )


@router.patch("/{invite_id}/extend", response_model=PlatformInviteResponse)
async def extend_platform_invite_expiration(
        invite_id: UUID,
        request: ExtendInviteRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Extend the expiration date of a platform invite.

    Requires platform admin role.
    """
    logger.info(
        f"Admin {current_user.id} extending platform invite {invite_id} expiration by {request.additional_days} days"
    )

    from app.models.invite import InviteType

    invite = db.query(Invite).filter(
        Invite.id == invite_id,
        Invite.invite_type == InviteType.PLATFORM
    ).first()

    if not invite:
        logger.warning(f"Extend failed - platform invite {invite_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Platform invite not found"
        )

    updated_invite = PlatformInviteService.extend_platform_invite_expiration(
        db=db,
        invite_id=invite_id,
        additional_days=request.additional_days
    )

    if not updated_invite:
        logger.error(f"Failed to extend platform invite {invite_id} expiration")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to extend platform invite expiration"
        )

    logger.info(f"Platform invite {invite_id} expiration extended successfully")

    invite_url = PlatformInviteService.get_invite_url(updated_invite, settings.FRONTEND_URL)

    return PlatformInviteResponse(
        id=str(updated_invite.id),
        token=updated_invite.token,
        email=updated_invite.email,
        role=updated_invite.role,
        max_uses=updated_invite.max_uses,
        used_count=updated_invite.used_count,
        is_active=updated_invite.is_active,
        is_valid=updated_invite.is_valid(),
        expires_at=updated_invite.expires_at.isoformat() if updated_invite.expires_at else None,
        created_at=updated_invite.created_at.isoformat(),
        used_at=updated_invite.used_at.isoformat() if updated_invite.used_at else None,
        invite_url=invite_url
    )


@router.delete("/{invite_id}", response_model=MessageResponse)
async def delete_platform_invite(
        invite_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Permanently delete a platform invite.

    Requires platform admin role. This action cannot be undone.
    """
    logger.warning(f"Admin {current_user.id} attempting to DELETE platform invite {invite_id}")

    from app.models.invite import InviteType

    invite = db.query(Invite).filter(
        Invite.id == invite_id,
        Invite.invite_type == InviteType.PLATFORM
    ).first()

    if not invite:
        logger.warning(f"Delete failed - platform invite {invite_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Platform invite not found"
        )

    invite_token = invite.token
    invite_role = invite.role

    success = PlatformInviteService.delete_platform_invite(db, invite_id)

    if not success:
        logger.error(f"Failed to delete platform invite {invite_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete platform invite"
        )

    logger.warning(
        f"Platform invite DELETED permanently - "
        f"Invite ID: {invite_id}, Role: {invite_role}, Token: {invite_token}, "
        f"Deleted by: {current_user.id}"
    )

    return MessageResponse(
        message="Platform invite deleted successfully",
        details={
            "invite_id": str(invite_id),
            "token": invite.token
        }
    )