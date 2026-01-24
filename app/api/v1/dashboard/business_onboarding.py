"""
Onboarding endpoints for businesses
UPDATED: Added comprehensive logging for onboarding actions
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from app.api.dependencies import get_db, get_current_active_user
from app.services.business.business_service import BusinessService
from app.models.auth.user import User
from app.schemas.business_onboarding import (
    OnboardingStatusResponse,
    MarkStepCompleteRequest,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["Business Onboarding"])


# ============================================================================
# Helper Functions
# ============================================================================

def verify_business_access(user_id: UUID, business_id: UUID, db: Session) -> bool:
    """
    Verify user has access to business.
    Returns True if access granted, raises HTTPException otherwise.
    """
    from app.models.auth.user import user_business_association
    user_business = db.query(user_business_association).filter(
        user_business_association.c.user_id == user_id,
        user_business_association.c.business_id == business_id
    ).first()

    if not user_business:
        logger.warning(
            f"User {user_id} attempted to access business {business_id} without permission"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this business"
        )

    return True


# ============================================================================
# Onboarding Endpoints
# ============================================================================

@router.get("/{business_id}/onboarding", response_model=OnboardingStatusResponse)
async def get_onboarding_status(
        business_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_active_user)
):
    """
    Get the current onboarding status for a business.

    Returns detailed information about:
    - Completed steps
    - Current step
    - Progress percentage
    - All available steps with completion status
    """
    logger.info(
        f"User {current_user.id} requesting onboarding status for business {business_id}"
    )

    # Verify user has access to this business
    verify_business_access(current_user.id, business_id, db)

    onboarding_status = BusinessService.get_onboarding_status(db, business_id)

    if not onboarding_status:
        logger.warning(
            f"Business {business_id} not found for onboarding status request by user {current_user.id}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business not found"
        )

    # Log progress summary (safe metadata)
    progress = onboarding_status.get('progress_percentage', 0)
    completed_count = len(onboarding_status.get('completed_steps', []))
    total_steps = len(onboarding_status.get('steps', []))

    logger.info(
        f"Onboarding status retrieved for business {business_id} - "
        f"Progress: {progress}%, Completed: {completed_count}/{total_steps} steps"
    )

    return onboarding_status


@router.post("/{business_id}/onboarding/complete", response_model=OnboardingStatusResponse)
async def mark_onboarding_step_complete(
        business_id: UUID,
        request: MarkStepCompleteRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_active_user)
):
    """
    Mark an onboarding step as complete.

    Valid step IDs:
    - business_info
    - calendar_connection
    - business_knowledge

    Returns updated onboarding status.
    """
    logger.info(
        f"User {current_user.id} marking onboarding step '{request.step_id}' as complete "
        f"for business {business_id}"
    )

    # Verify user has access to this business
    verify_business_access(current_user.id, business_id, db)

    try:
        updated_status = BusinessService.mark_onboarding_step_complete(
            db=db,
            business_id=business_id,
            step_id=request.step_id
        )

        # Log successful completion
        progress = updated_status.get('progress_percentage', 0)
        is_complete = updated_status.get('is_complete', False)

        logger.info(
            f"Onboarding step '{request.step_id}' marked complete for business {business_id} - "
            f"Progress: {progress}%, Onboarding complete: {is_complete}"
        )

        # Log if onboarding is now fully complete
        if is_complete:
            logger.info(
                f"Business {business_id} has COMPLETED full onboarding - "
                f"User: {current_user.id}"
            )

        return updated_status

    except ValueError as e:
        logger.warning(
            f"Invalid onboarding step '{request.step_id}' for business {business_id} - "
            f"User: {current_user.id}, Error: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(
            f"Error marking onboarding step complete for business {business_id}: {e}",
            exc_info=True
        )
        raise


@router.get("/{business_id}/onboarding/steps")
async def get_available_steps(
        business_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_active_user)
):
    """
    Get list of all available onboarding steps.

    This is useful for the frontend to know what steps are available.
    """
    logger.info(
        f"User {current_user.id} requesting available onboarding steps for business {business_id}"
    )

    # Verify user has access to this business
    verify_business_access(current_user.id, business_id, db)

    steps = []
    for step_id, step_info in sorted(
            BusinessService.ONBOARDING_STEPS.items(),
            key=lambda x: x[1]["order"]
    ):
        steps.append({
            "id": step_id,
            "label": step_info["label"],
            "description": step_info["description"],
            "order": step_info["order"]
        })

    logger.info(
        f"Returned {len(steps)} available onboarding steps for business {business_id}"
    )

    return {
        "steps": steps
    }