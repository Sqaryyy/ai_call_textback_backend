# ============================================================================
# FILE: app/api/v1/admin/invites.py
# Platform admin endpoints for creating invites for new business owners
# ============================================================================
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from uuid import UUID

from app.api.dependencies import get_db, require_platform_admin
from app.services.invite.platform_invite_service import PlatformInviteService
from app.models.user import User
from app.models.invite import Invite
from app.config.settings import settings

router = APIRouter(prefix="/admin/invites", tags=["Admin - Platform Invites"])


# ============================================================================
# Pydantic Schemas
# ============================================================================

class CreatePlatformInviteRequest(BaseModel):
    """Request body for creating a platform invite."""
    email: Optional[EmailStr] = Field(
        None,
        description="Specific email (optional, if None anyone can use the invite)"
    )
    max_uses: int = Field(
        1,
        ge=1,
        le=100,
        description="Maximum number of times the invite can be used"
    )
    expires_in_days: Optional[int] = Field(
        7,
        ge=1,
        le=365,
        description="Days until expiration (null = never expires)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "email": "newowner@example.com",
                "max_uses": 1,
                "expires_in_days": 7
            }
        }


class PlatformInviteResponse(BaseModel):
    """Response with platform invite details."""
    id: str
    token: str
    email: Optional[str]
    role: str
    max_uses: int
    used_count: int
    is_active: bool
    is_valid: bool
    expires_at: Optional[str]
    created_at: str
    used_at: Optional[str]
    invite_url: str

    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "token": "abc123xyz789def456ghi012",
                "email": "newowner@example.com",
                "role": "owner",
                "max_uses": 1,
                "used_count": 0,
                "is_active": True,
                "is_valid": True,
                "expires_at": "2025-10-26T12:00:00+00:00",
                "created_at": "2025-10-19T12:00:00+00:00",
                "used_at": None,
                "invite_url": "http://localhost:3000/register?invite=abc123xyz789def456ghi012"
            }
        }


class PlatformInviteStatsResponse(BaseModel):
    """Response with platform invite statistics."""
    total_invites: int
    active_invites: int
    valid_invites: int
    used_invites: int
    expired_invites: int
    total_uses: int

    class Config:
        json_schema_extra = {
            "example": {
                "total_invites": 25,
                "active_invites": 18,
                "valid_invites": 15,
                "used_invites": 10,
                "expired_invites": 7,
                "total_uses": 12
            }
        }


class ExtendInviteRequest(BaseModel):
    """Request body for extending invite expiration."""
    additional_days: int = Field(
        ...,
        ge=1,
        le=365,
        description="Number of days to add to expiration"
    )


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    details: Optional[dict] = None


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
    invites_data = PlatformInviteService.list_platform_invites(
        db=db,
        include_inactive=include_inactive
    )

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
    stats = PlatformInviteService.get_platform_invite_stats(db=db)

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
    from app.models.invite import InviteType

    invite = db.query(Invite).filter(
        Invite.id == invite_id,
        Invite.invite_type == InviteType.PLATFORM
    ).first()

    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Platform invite not found"
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
    from app.models.invite import InviteType

    invite = db.query(Invite).filter(
        Invite.id == invite_id,
        Invite.invite_type == InviteType.PLATFORM
    ).first()

    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Platform invite not found"
        )

    if not invite.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invite is already revoked"
        )

    success = PlatformInviteService.revoke_platform_invite(db, invite_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke platform invite"
        )

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
    from app.models.invite import InviteType

    invite = db.query(Invite).filter(
        Invite.id == invite_id,
        Invite.invite_type == InviteType.PLATFORM
    ).first()

    if not invite:
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to extend platform invite expiration"
        )

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
    from app.models.invite import InviteType

    invite = db.query(Invite).filter(
        Invite.id == invite_id,
        Invite.invite_type == InviteType.PLATFORM
    ).first()

    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Platform invite not found"
        )

    success = PlatformInviteService.delete_platform_invite(db, invite_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete platform invite"
        )

    return MessageResponse(
        message="Platform invite deleted successfully",
        details={
            "invite_id": str(invite_id),
            "token": invite.token
        }
    )