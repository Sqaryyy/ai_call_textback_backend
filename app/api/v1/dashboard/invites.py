# ============================================================================
# FILE: app/api/v1/business/invites.py
# Business owner endpoints for inviting team members to their business
# ============================================================================
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from uuid import UUID

from app.api.dependencies import get_db, require_business_owner
from app.services.invite.business_invite_service import BusinessInviteService
from app.models.user import User, BusinessRole
from app.models.invite import Invite, InviteType
from app.models.business import Business
from app.config.settings import settings

router = APIRouter(tags=["Business - Team Invites"])


# ============================================================================
# Pydantic Schemas
# ============================================================================

class CreateBusinessInviteRequest(BaseModel):
    """Request body for creating a business invite."""
    email: Optional[EmailStr] = Field(
        None,
        description="Specific email (optional, if None anyone can use the invite)"
    )
    role: str = Field(
        "member",
        description="Role to assign: owner or member"
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
                "email": "teammember@example.com",
                "role": "member",
                "max_uses": 1,
                "expires_in_days": 7
            }
        }


class BusinessInviteResponse(BaseModel):
    """Response with business invite details."""
    id: str
    token: str
    email: Optional[str]
    role: str
    business_id: str
    business_name: Optional[str]
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
                "email": "teammember@example.com",
                "role": "member",
                "business_id": "660e8400-e29b-41d4-a716-446655440001",
                "business_name": "Acme Corp",
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


class BusinessInviteStatsResponse(BaseModel):
    """Response with business invite statistics."""
    total_invites: int
    active_invites: int
    valid_invites: int
    used_invites: int
    expired_invites: int
    total_uses: int

    class Config:
        json_schema_extra = {
            "example": {
                "total_invites": 15,
                "active_invites": 10,
                "valid_invites": 8,
                "used_invites": 5,
                "expired_invites": 5,
                "total_uses": 7
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
# Helper Functions
# ============================================================================

def _verify_business_access(db: Session, user: User, business_id: UUID) -> Business:
    """Verify user is owner of the business and return business object."""
    from app.services.user.user_service import UserService

    # Check if business exists
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business not found"
        )

    # Check if user is owner of this business
    role = UserService.get_user_role_in_business(
        db=db,
        user_id=user.id,
        business_id=business_id
    )

    if role != BusinessRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only business owners can manage invites"
        )

    return business


# ============================================================================
# Business Invite Management Endpoints
# ============================================================================

@router.post("/{business_id}/invites", response_model=BusinessInviteResponse, status_code=status.HTTP_201_CREATED)
async def create_business_invite(
        business_id: UUID = Path(..., description="Business ID"),
        request: CreateBusinessInviteRequest = ...,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_business_owner)
):
    """
    Create a new invite for a business team member.

    Requires business owner role. The invite will allow someone to join
    this specific business as a team member.
    """
    # Verify user is owner of this business
    business = _verify_business_access(db, current_user, business_id)

    # Validate role
    if request.role not in ["owner", "member"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role. Must be 'owner' or 'member'"
        )

    try:
        invite = BusinessInviteService.create_business_invite(
            db=db,
            business_id=business_id,
            created_by=current_user.id,
            role=request.role,
            email=request.email,
            max_uses=request.max_uses,
            expires_in_days=request.expires_in_days
        )

        # Generate the invite URL
        invite_url = BusinessInviteService.get_invite_url(invite, settings.FRONTEND_URL)

        return BusinessInviteResponse(
            id=str(invite.id),
            token=invite.token,
            email=invite.email,
            role=invite.role,
            business_id=str(business_id),
            business_name=business.name,
            max_uses=invite.max_uses,
            used_count=invite.used_count,
            is_active=invite.is_active,
            is_valid=invite.is_valid(),
            expires_at=invite.expires_at.isoformat() if invite.expires_at else None,
            created_at=invite.created_at.isoformat(),
            used_at=invite.used_at.isoformat() if invite.used_at else None,
            invite_url=invite_url
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create business invite: {str(e)}"
        )


@router.get("/{business_id}/invites", response_model=List[BusinessInviteResponse])
async def list_business_invites(
        business_id: UUID = Path(..., description="Business ID"),
        include_inactive: bool = Query(
            False,
            description="Include inactive/expired invites"
        ),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_business_owner)
):
    """
    List all invites for a specific business.

    Requires business owner role.
    """
    # Verify user is owner of this business
    business = _verify_business_access(db, current_user, business_id)

    invites_data = BusinessInviteService.list_business_invites(
        db=db,
        business_id=business_id,
        include_inactive=include_inactive
    )

    return [
        BusinessInviteResponse(
            **invite,
            business_id=str(business_id),
            business_name=business.name,
            invite_url=f"{settings.FRONTEND_URL}/register?invite={invite['token']}"
        )
        for invite in invites_data
    ]


@router.get("/{business_id}/invites/stats", response_model=BusinessInviteStatsResponse)
async def get_business_invite_stats(
        business_id: UUID = Path(..., description="Business ID"),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_business_owner)
):
    """
    Get statistics about invites for a specific business.

    Requires business owner role.
    """
    # Verify user is owner of this business
    _verify_business_access(db, current_user, business_id)

    stats = BusinessInviteService.get_business_invite_stats(
        db=db,
        business_id=business_id
    )

    return BusinessInviteStatsResponse(**stats)


@router.get("/{business_id}/invites/{invite_id}", response_model=BusinessInviteResponse)
async def get_business_invite(
        business_id: UUID = Path(..., description="Business ID"),
        invite_id: UUID = Path(..., description="Invite ID"),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_business_owner)
):
    """
    Get details of a specific business invite.

    Requires business owner role.
    """
    # Verify user is owner of this business
    business = _verify_business_access(db, current_user, business_id)

    invite = db.query(Invite).filter(
        Invite.id == invite_id,
        Invite.business_id == business_id,
        Invite.invite_type == InviteType.BUSINESS
    ).first()

    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business invite not found"
        )

    invite_url = BusinessInviteService.get_invite_url(invite, settings.FRONTEND_URL)

    return BusinessInviteResponse(
        id=str(invite.id),
        token=invite.token,
        email=invite.email,
        role=invite.role,
        business_id=str(business_id),
        business_name=business.name,
        max_uses=invite.max_uses,
        used_count=invite.used_count,
        is_active=invite.is_active,
        is_valid=invite.is_valid(),
        expires_at=invite.expires_at.isoformat() if invite.expires_at else None,
        created_at=invite.created_at.isoformat(),
        used_at=invite.used_at.isoformat() if invite.used_at else None,
        invite_url=invite_url
    )


@router.patch("/{business_id}/invites/{invite_id}/revoke", response_model=MessageResponse)
async def revoke_business_invite(
        business_id: UUID = Path(..., description="Business ID"),
        invite_id: UUID = Path(..., description="Invite ID"),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_business_owner)
):
    """
    Revoke (deactivate) a business invite so it can no longer be used.

    Requires business owner role.
    """
    # Verify user is owner of this business
    _verify_business_access(db, current_user, business_id)

    invite = db.query(Invite).filter(
        Invite.id == invite_id,
        Invite.business_id == business_id,
        Invite.invite_type == InviteType.BUSINESS
    ).first()

    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business invite not found"
        )

    if not invite.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invite is already revoked"
        )

    success = BusinessInviteService.revoke_business_invite(db, invite_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke business invite"
        )

    return MessageResponse(
        message="Business invite revoked successfully",
        details={
            "invite_id": str(invite_id),
            "token": invite.token,
            "business_id": str(business_id)
        }
    )


@router.patch("/{business_id}/invites/{invite_id}/extend", response_model=BusinessInviteResponse)
async def extend_business_invite_expiration(
        business_id: UUID = Path(..., description="Business ID"),
        invite_id: UUID = Path(..., description="Invite ID"),
        request: ExtendInviteRequest = ...,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_business_owner)
):
    """
    Extend the expiration date of a business invite.

    Requires business owner role.
    """
    # Verify user is owner of this business
    business = _verify_business_access(db, current_user, business_id)

    invite = db.query(Invite).filter(
        Invite.id == invite_id,
        Invite.business_id == business_id,
        Invite.invite_type == InviteType.BUSINESS
    ).first()

    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business invite not found"
        )

    updated_invite = BusinessInviteService.extend_business_invite_expiration(
        db=db,
        invite_id=invite_id,
        additional_days=request.additional_days
    )

    if not updated_invite:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to extend business invite expiration"
        )

    invite_url = BusinessInviteService.get_invite_url(updated_invite, settings.FRONTEND_URL)

    return BusinessInviteResponse(
        id=str(updated_invite.id),
        token=updated_invite.token,
        email=updated_invite.email,
        role=updated_invite.role,
        business_id=str(business_id),
        business_name=business.name,
        max_uses=updated_invite.max_uses,
        used_count=updated_invite.used_count,
        is_active=updated_invite.is_active,
        is_valid=updated_invite.is_valid(),
        expires_at=updated_invite.expires_at.isoformat() if updated_invite.expires_at else None,
        created_at=updated_invite.created_at.isoformat(),
        used_at=updated_invite.used_at.isoformat() if updated_invite.used_at else None,
        invite_url=invite_url
    )


@router.delete("/{business_id}/invites/{invite_id}", response_model=MessageResponse)
async def delete_business_invite(
        business_id: UUID = Path(..., description="Business ID"),
        invite_id: UUID = Path(..., description="Invite ID"),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_business_owner)
):
    """
    Permanently delete a business invite.

    Requires business owner role. This action cannot be undone.
    """
    # Verify user is owner of this business
    _verify_business_access(db, current_user, business_id)

    invite = db.query(Invite).filter(
        Invite.id == invite_id,
        Invite.business_id == business_id,
        Invite.invite_type == InviteType.BUSINESS
    ).first()

    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business invite not found"
        )

    success = BusinessInviteService.delete_business_invite(db, invite_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete business invite"
        )

    return MessageResponse(
        message="Business invite deleted successfully",
        details={
            "invite_id": str(invite_id),
            "token": invite.token,
            "business_id": str(business_id)
        }
    )


@router.post("/{business_id}/invites/cleanup-expired", response_model=MessageResponse)
async def cleanup_expired_business_invites(
        business_id: UUID = Path(..., description="Business ID"),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_business_owner)
):
    """
    Delete all expired invites for this business.

    Requires business owner role. This helps keep the database clean.
    """
    # Verify user is owner of this business
    _verify_business_access(db, current_user, business_id)

    from sqlalchemy import and_, func

    query = db.query(Invite).filter(
        and_(
            Invite.business_id == business_id,
            Invite.invite_type == InviteType.BUSINESS,
            Invite.expires_at.is_not(None),
            Invite.expires_at < func.now()
        )
    )

    count = query.count()
    query.delete(synchronize_session=False)
    db.commit()

    return MessageResponse(
        message=f"Cleanup completed for business",
        details={
            "business_id": str(business_id),
            "expired_invites_deleted": count
        }
    )

class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    details: Optional[dict] = None


class BusinessUserResponse(BaseModel):
    """Response with business user details."""
    id: str
    email: str
    full_name: Optional[str]
    role: str
    joined_at: str
    is_active: bool

    class Config:
        json_schema_extra = {
            "example": {
                "id": "770e8400-e29b-41d4-a716-446655440002",
                "email": "member@example.com",
                "full_name": "John Doe",
                "role": "member",
                "joined_at": "2025-10-15T12:00:00+00:00",
                "is_active": True
            }
        }


class BusinessUsersListResponse(BaseModel):
    """Response with list of business users."""
    business_id: str
    business_name: str
    total_users: int
    users: List[BusinessUserResponse]

    class Config:
        json_schema_extra = {
            "example": {
                "business_id": "660e8400-e29b-41d4-a716-446655440001",
                "business_name": "Acme Corp",
                "total_users": 3,
                "users": [
                    {
                        "id": "770e8400-e29b-41d4-a716-446655440002",
                        "email": "owner@example.com",
                        "full_name": "Jane Smith",
                        "role": "owner",
                        "joined_at": "2025-10-01T12:00:00+00:00",
                        "is_active": True
                    }
                ]
            }
        }


@router.get("/{business_id}/users", response_model=BusinessUsersListResponse)
async def get_business_users(
        business_id: UUID = Path(..., description="Business ID"),
        include_inactive: bool = Query(
            False,
            description="Include inactive users"
        ),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_business_owner)
):
    """
    Get all users (team members) in a specific business.

    Requires business owner role. Returns a list of all users who are
    members of this business along with their roles and status.
    """
    # Verify user is owner of this business
    business = _verify_business_access(db, current_user, business_id)

    # Query users associated with this business through the user_business_association table
    from app.models.user import user_business_association
    from sqlalchemy import select

    # Build the query to get users and their roles in this business
    query = (
        select(
            User,
            user_business_association.c.role,
            user_business_association.c.created_at
        )
        .join(
            user_business_association,
            User.id == user_business_association.c.user_id
        )
        .filter(user_business_association.c.business_id == business_id)
    )

    # Filter by active status if requested
    if not include_inactive:
        query = query.filter(User.is_active == True)

    # Order by role (owners first) then by joined date
    query = query.order_by(
        user_business_association.c.role.desc(),
        user_business_association.c.created_at.asc()
    )

    results = db.execute(query).all()

    # Build response
    users = []
    for user, role, joined_at in results:
        users.append(BusinessUserResponse(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            role=role.value if hasattr(role, 'value') else role,
            joined_at=joined_at.isoformat(),
            is_active=user.is_active
        ))

    return BusinessUsersListResponse(
        business_id=str(business_id),
        business_name=business.name,
        total_users=len(users),
        users=users
    )