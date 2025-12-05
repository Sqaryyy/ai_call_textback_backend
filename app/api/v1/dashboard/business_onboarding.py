# New file: app/api/v1/business_onboarding.py
"""
Onboarding endpoints for businesses
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
from uuid import UUID

from app.api.dependencies import get_db, get_current_active_user
from app.services.business.business_service import BusinessService
from app.models.auth.user import User

router = APIRouter(tags=["Business Onboarding"])


# ============================================================================
# Pydantic Schemas
# ============================================================================

class OnboardingStepResponse(BaseModel):
    """Represents a single onboarding step"""
    id: str
    label: str
    description: str
    order: int
    completed: bool


class OnboardingStatusResponse(BaseModel):
    """Response for onboarding status"""
    completed_steps: List[str]
    current_step: str
    progress_percentage: int
    is_completed: bool
    started_at: str | None
    completed_at: str | None
    steps: List[OnboardingStepResponse]


class MarkStepCompleteRequest(BaseModel):
    """Request to mark an onboarding step as complete"""
    step_id: str


class MessageResponse(BaseModel):
    """Generic message response"""
    message: str
    details: dict | None = None


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
    # Verify user has access to this business
    from app.models.auth.user import user_business_association
    user_business = db.query(user_business_association).filter(
        user_business_association.c.user_id == current_user.id,
        user_business_association.c.business_id == business_id
    ).first()

    if not user_business:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this business"
        )

    onboarding_status = BusinessService.get_onboarding_status(db, business_id)

    if not onboarding_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business not found"
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
    # Verify user has access to this business
    from app.models.auth.user import user_business_association
    user_business = db.query(user_business_association).filter(
        user_business_association.c.user_id == current_user.id,
        user_business_association.c.business_id == business_id
    ).first()

    if not user_business:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this business"
        )

    try:
        updated_status = BusinessService.mark_onboarding_step_complete(
            db=db,
            business_id=business_id,
            step_id=request.step_id
        )
        return updated_status
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


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
    # Verify user has access to this business
    from app.models.auth.user import user_business_association
    user_business = db.query(user_business_association).filter(
        user_business_association.c.user_id == current_user.id,
        user_business_association.c.business_id == business_id
    ).first()

    if not user_business:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this business"
        )

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

    return {
        "steps": steps
    }