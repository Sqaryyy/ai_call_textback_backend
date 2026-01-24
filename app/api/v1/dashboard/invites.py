"""
Business owner endpoints for inviting team members to their business
UPDATED: Added comprehensive logging with user audit trail
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from app.api.dependencies import get_db, require_business_owner
from app.services.invite.business_invite_service import BusinessInviteService
from app.models.auth.user import User, BusinessRole
from app.models.invite import Invite, InviteType
from app.models.business.business import Business
from app.config.settings import settings
from app.schemas.business_invites import (
    CreateBusinessInviteRequest,
    BusinessInviteResponse,
    BusinessInviteStatsResponse,
    ExtendInviteRequest,
    MessageResponse,
    BusinessUserResponse,
    BusinessUsersListResponse
)
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["Business - Team Invites"])


# ============================================================================
# Helper Functions
# ============================================================================

def _verify_business_access(db: Session, user: User, business_id: UUID) -> Business:
    """Verify user is owner of the business and return business object."""
    from app.services.user.user_service import UserService

    # Check if business exists
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        logger.warning(
            f"Business access verification failed: Business {business_id} not found - "
            f"User: {user.id}"
        )
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
        logger.warning(
            f"User {user.id} attempted to manage invites for business {business_id} - "
            f"Current role: {role}, Required: OWNER"
        )
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
    # Mask email for logging (show only domain)
    email_parts = request.email.split('@') if request.email else ['', '']
    masked_email = f"***@{email_parts[1]}" if len(email_parts) == 2 else "***"

    logger.info(
        f"User {current_user.id} creating business invite - "
        f"Business: {business_id}, Role: {request.role}, Email: {masked_email}, "
        f"Max uses: {request.max_uses}, Expires in: {request.expires_in_days} days"
    )

    # Verify user is owner of this business
    business = _verify_business_access(db, current_user, business_id)

    # Validate role
    if request.role not in ["owner", "member"]:
        logger.warning(
            f"Invalid role '{request.role}' specified for invite - "
            f"User: {current_user.id}, Business: {business_id}"
        )
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

        logger.info(
            f"Business invite created successfully - "
            f"Invite ID: {invite.id}, Business: {business_id}, Role: {request.role}, "
            f"Email: {masked_email}, Created by: {current_user.id}"
        )

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
        logger.warning(
            f"Business invite creation failed - Validation error: {str(e)} - "
            f"User: {current_user.id}, Business: {business_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(
            f"Error creating business invite - "
            f"User: {current_user.id}, Business: {business_id}: {e}",
            exc_info=True
        )
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
    logger.info(
        f"User {current_user.id} listing business invites - "
        f"Business: {business_id}, Include inactive: {include_inactive}"
    )

    # Verify user is owner of this business
    business = _verify_business_access(db, current_user, business_id)

    invites_data = BusinessInviteService.list_business_invites(
        db=db,
        business_id=business_id,
        include_inactive=include_inactive
    )

    logger.info(
        f"Returned {len(invites_data)} business invites for business {business_id}"
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
    logger.info(
        f"User {current_user.id} requesting invite statistics for business {business_id}"
    )

    # Verify user is owner of this business
    _verify_business_access(db, current_user, business_id)

    stats = BusinessInviteService.get_business_invite_stats(
        db=db,
        business_id=business_id
    )

    logger.info(
        f"Invite statistics retrieved - Business: {business_id}, "
        f"Total: {stats.get('total_invites', 0)}, Active: {stats.get('active_invites', 0)}, "
        f"Used: {stats.get('used_invites', 0)}"
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
    logger.info(
        f"User {current_user.id} requesting invite details - "
        f"Invite: {invite_id}, Business: {business_id}"
    )

    # Verify user is owner of this business
    business = _verify_business_access(db, current_user, business_id)

    invite = db.query(Invite).filter(
        Invite.id == invite_id,
        Invite.business_id == business_id,
        Invite.invite_type == InviteType.BUSINESS
    ).first()

    if not invite:
        logger.warning(
            f"Business invite {invite_id} not found - "
            f"Business: {business_id}, User: {current_user.id}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business invite not found"
        )

    invite_url = BusinessInviteService.get_invite_url(invite, settings.FRONTEND_URL)

    logger.info(
        f"Invite details retrieved - Invite: {invite_id}, "
        f"Role: {invite.role}, Active: {invite.is_active}, Used: {invite.used_count}/{invite.max_uses}"
    )

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
    logger.warning(
        f"User {current_user.id} REVOKING business invite - "
        f"Invite: {invite_id}, Business: {business_id}"
    )

    # Verify user is owner of this business
    _verify_business_access(db, current_user, business_id)

    invite = db.query(Invite).filter(
        Invite.id == invite_id,
        Invite.business_id == business_id,
        Invite.invite_type == InviteType.BUSINESS
    ).first()

    if not invite:
        logger.warning(
            f"Invite revocation failed: Invite {invite_id} not found - "
            f"Business: {business_id}, User: {current_user.id}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business invite not found"
        )

    if not invite.is_active:
        logger.warning(
            f"Invite revocation failed: Invite {invite_id} already revoked - "
            f"User: {current_user.id}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invite is already revoked"
        )

    success = BusinessInviteService.revoke_business_invite(db, invite_id)

    if not success:
        logger.error(
            f"Failed to revoke invite {invite_id} - Business: {business_id}, User: {current_user.id}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke business invite"
        )

    logger.warning(
        f"Business invite REVOKED - "
        f"Invite: {invite_id}, Role: {invite.role}, Business: {business_id}, "
        f"Revoked by: {current_user.id}"
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
    logger.info(
        f"User {current_user.id} extending invite expiration - "
        f"Invite: {invite_id}, Business: {business_id}, Additional days: {request.additional_days}"
    )

    # Verify user is owner of this business
    business = _verify_business_access(db, current_user, business_id)

    invite = db.query(Invite).filter(
        Invite.id == invite_id,
        Invite.business_id == business_id,
        Invite.invite_type == InviteType.BUSINESS
    ).first()

    if not invite:
        logger.warning(
            f"Invite extension failed: Invite {invite_id} not found - "
            f"Business: {business_id}, User: {current_user.id}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business invite not found"
        )

    old_expiry = invite.expires_at

    updated_invite = BusinessInviteService.extend_business_invite_expiration(
        db=db,
        invite_id=invite_id,
        additional_days=request.additional_days
    )

    if not updated_invite:
        logger.error(
            f"Failed to extend invite {invite_id} - Business: {business_id}, User: {current_user.id}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to extend business invite expiration"
        )

    invite_url = BusinessInviteService.get_invite_url(updated_invite, settings.FRONTEND_URL)

    logger.info(
        f"Invite expiration extended - "
        f"Invite: {invite_id}, Old expiry: {old_expiry}, New expiry: {updated_invite.expires_at}, "
        f"Extended by: {current_user.id}"
    )

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
    logger.warning(
        f"User {current_user.id} DELETING business invite - "
        f"Invite: {invite_id}, Business: {business_id}"
    )

    # Verify user is owner of this business
    _verify_business_access(db, current_user, business_id)

    invite = db.query(Invite).filter(
        Invite.id == invite_id,
        Invite.business_id == business_id,
        Invite.invite_type == InviteType.BUSINESS
    ).first()

    if not invite:
        logger.warning(
            f"Invite deletion failed: Invite {invite_id} not found - "
            f"Business: {business_id}, User: {current_user.id}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business invite not found"
        )

    invite_role = invite.role
    invite_email = invite.email

    success = BusinessInviteService.delete_business_invite(db, invite_id)

    if not success:
        logger.error(
            f"Failed to delete invite {invite_id} - Business: {business_id}, User: {current_user.id}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete business invite"
        )

    logger.warning(
        f"Business invite PERMANENTLY DELETED - "
        f"Invite: {invite_id}, Role: {invite_role}, Email: {invite_email}, "
        f"Business: {business_id}, Deleted by: {current_user.id}"
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
    logger.warning(
        f"User {current_user.id} initiating CLEANUP of expired invites for business {business_id}"
    )

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

    logger.warning(
        f"Expired invites CLEANUP completed - "
        f"Business: {business_id}, Deleted: {count} invites, "
        f"Initiated by: {current_user.id}"
    )

    return MessageResponse(
        message=f"Cleanup completed for business",
        details={
            "business_id": str(business_id),
            "expired_invites_deleted": count
        }
    )


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
    logger.info(
        f"User {current_user.id} requesting business users list - "
        f"Business: {business_id}, Include inactive: {include_inactive}"
    )

    # Verify user is owner of this business
    business = _verify_business_access(db, current_user, business_id)

    # Query users associated with this business through the user_business_association table
    from app.models.auth.user import user_business_association
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
    role_counts = {}
    for user, role, joined_at in results:
        role_str = role.value if hasattr(role, 'value') else role
        role_counts[role_str] = role_counts.get(role_str, 0) + 1

        users.append(BusinessUserResponse(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            role=role_str,
            joined_at=joined_at.isoformat(),
            is_active=user.is_active
        ))

    # Format role distribution for logging
    role_dist = ", ".join([f"{role}: {count}" for role, count in role_counts.items()])

    logger.info(
        f"Business users list retrieved - "
        f"Business: {business_id}, Total users: {len(users)}, "
        f"Roles: [{role_dist}]"
    )

    return BusinessUsersListResponse(
        business_id=str(business_id),
        business_name=business.name,
        total_users=len(users),
        users=users
    )