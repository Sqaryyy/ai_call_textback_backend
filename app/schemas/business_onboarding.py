"""
Pydantic schemas for business onboarding endpoints
"""
from pydantic import BaseModel
from typing import List


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