# app/api/v1/onboarding.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.models.business import Business, BusinessHours
from app.models import CalendarIntegration
from app.config.database import get_db
from app.services.calendar.google_calendar_service import GoogleCalendarService
from app.services.calendar.outlook_service import OutlookCalendarService

router = APIRouter(tags=["onboarding"])


# ========== TEST ENDPOINT ==========
@router.get("/test")
async def test_onboarding_api():
    """Test endpoint to verify the onboarding API is working"""
    return {
        "success": True,
        "message": "Onboarding API is running",
        "timestamp": datetime.utcnow().isoformat(),
        "available_endpoints": [
            "POST /business/create",
            "POST /business/{business_id}/calendar/authorize",
            "POST /business/{business_id}/calendar/connect",
            "PATCH /business/{business_id}/calendar/{integration_id}/select-primary",
            "GET /business/{business_id}/status",
            "GET /test"
        ]
    }


# ========== REQUEST MODELS ==========
class BusinessHoursInput(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6, description="0=Monday, 6=Sunday")
    open_time: str = Field(..., pattern="^([0-1][0-9]|2[0-3]):[0-5][0-9]$", description="HH:MM format")
    close_time: str = Field(..., pattern="^([0-1][0-9]|2[0-3]):[0-5][0-9]$", description="HH:MM format")
    is_closed: bool = Field(default=False)


class CreateBusinessRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    phone_number: str = Field(..., pattern="^\\+?[1-9]\\d{1,14}$")
    business_type: str = Field(..., min_length=1, max_length=100)
    timezone: str = Field(default="UTC")
    services: Optional[List[str]] = Field(default_factory=list)
    business_hours: List[BusinessHoursInput] = Field(..., min_items=7, max_items=7)


# ========== STEP 1: Create Business + Hours ==========
@router.post("/business/create")
async def create_business(
        request: CreateBusinessRequest,
        db: Session = Depends(get_db)
):
    """
    Step 1: Create business profile and business hours
    Returns business_id for next steps
    """
    try:
        # Check if phone number already exists
        existing = db.query(Business).filter_by(phone_number=request.phone_number).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Business with phone number {request.phone_number} already exists"
            )

        # Create business
        business = Business(
            name=request.name,
            phone_number=request.phone_number,
            business_type=request.business_type,
            timezone=request.timezone,
            services=request.services,
            onboarding_status={
                "completed": False,
                "started_at": datetime.utcnow().isoformat(),
                "current_step": "business_created",
                "steps_completed": ["business_created"]
            }
        )

        db.add(business)
        db.flush()

        business_id = str(business.id)

        # Validate we have exactly 7 days
        days_provided = {h.day_of_week for h in request.business_hours}
        if days_provided != {0, 1, 2, 3, 4, 5, 6}:
            raise HTTPException(
                status_code=400,
                detail="Must provide business hours for all 7 days (0-6)"
            )

        # Create business hours
        for hours_input in request.business_hours:
            business_hour = BusinessHours(
                business_id=business.id,
                day_of_week=hours_input.day_of_week,
                open_time=hours_input.open_time,
                close_time=hours_input.close_time,
                is_closed=hours_input.is_closed
            )
            db.add(business_hour)

        # Update onboarding status
        business.onboarding_status["steps_completed"].append("business_hours_set")
        business.onboarding_status["current_step"] = "awaiting_calendar"

        db.commit()

        return {
            "success": True,
            "business_id": business_id,
            "business_name": request.name,
            "message": "Business created successfully. Proceed to calendar integration.",
            "next_step": "get_authorization_url"
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create business: {str(e)}")


# ========== STEP 2: Get Authorization URL ==========
@router.post("/business/{business_id}/calendar/authorize")
async def get_calendar_authorization_url(
        business_id: str,
        provider: str = Query(..., description="google or outlook"),
        db: Session = Depends(get_db)
):
    """
    Step 2: Get authorization URL for calendar provider
    """
    business = db.query(Business).filter_by(id=business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    try:
        if provider.lower() == "google":
            service = GoogleCalendarService()
            auth_url = service.generate_authorization_url(business_id)
        elif provider.lower() == "outlook":
            service = OutlookCalendarService()
            auth_url = service.generate_authorization_url(business_id)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported provider: {provider}. Use 'google' or 'outlook'"
            )

        # Update onboarding status
        business.onboarding_status["current_step"] = "awaiting_oauth"
        db.commit()

        return {
            "success": True,
            "authorization_url": auth_url,
            "provider": provider,
            "instructions": "Visit the URL to authorize, then use the code from the callback URL"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate auth URL: {str(e)}")

@router.get("/business/{business_id}/calendar/check-status")
async def check_calendar_oauth_status(
        business_id: str,
        db: Session = Depends(get_db)
):
    """
    Check if OAuth has been completed for this business
    Returns integration details if found
    """
    business = db.query(Business).filter_by(id=business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    try:
        # Look for active calendar integration
        integration = db.query(CalendarIntegration).filter_by(
            business_id=business_id,
            is_active=True
        ).order_by(CalendarIntegration.created_at.desc()).first()

        if integration:
            # OAuth completed
            business.onboarding_status["steps_completed"].append("calendar_connected")
            business.onboarding_status["current_step"] = "awaiting_calendar_selection"
            db.commit()

            return {
                "success": True,
                "integration_found": True,
                "integration_id": str(integration.id),
                "provider": integration.provider,
                "available_calendars": integration.provider_config.get('calendar_list', []),
                "message": "Calendar connected. Select which calendar to use.",
                "next_step": "select_primary_calendar"
            }
        else:
            # OAuth not yet completed
            return {
                "success": True,
                "integration_found": False,
                "message": "OAuth authorization not yet completed. Please complete the authorization flow.",
                "current_step": business.onboarding_status.get("current_step", "awaiting_oauth")
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check OAuth status: {str(e)}")


# ========== STEP 3: Complete OAuth with Code ==========
@router.post("/business/{business_id}/calendar/connect")
async def connect_calendar(
        business_id: str,
        provider: str,
        authorization_code: str,
        db: Session = Depends(get_db)
):
    """
    Step 3: Connect calendar using authorization code from OAuth
    Returns available calendars to choose from
    """
    business = db.query(Business).filter_by(id=business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    try:
        if provider.lower() == "google":
            service = GoogleCalendarService()
            integration = service.handle_oauth_callback(
                code=authorization_code,
                state=business_id,
                db=db
            )
        elif provider.lower() == "outlook":
            service = OutlookCalendarService()
            integration = service.handle_oauth_callback(
                code=authorization_code,
                state=business_id,
                db=db
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

        # Update onboarding status
        business.onboarding_status["steps_completed"].append("calendar_connected")
        business.onboarding_status["current_step"] = "awaiting_calendar_selection"
        db.commit()

        return {
            "success": True,
            "integration_id": str(integration.id),
            "provider": provider,
            "available_calendars": integration.provider_config.get('calendar_list', []),
            "message": "Calendar connected. Select which calendar to use.",
            "next_step": "select_primary_calendar"
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to connect calendar: {str(e)}")


# ========== STEP 4: Select Primary Calendar ==========
@router.patch("/business/{business_id}/calendar/{integration_id}/select-primary")
async def select_primary_calendar(
        business_id: str,
        integration_id: str,
        calendar_id: str,
        db: Session = Depends(get_db)
):
    """
    Step 4: Select which calendar to use and set as primary
    Completes onboarding
    """
    business = db.query(Business).filter_by(id=business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    integration = db.query(CalendarIntegration).filter_by(
        id=integration_id,
        business_id=business_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Calendar integration not found")

    try:
        # Set selected calendar
        integration.provider_config['selected_calendar_id'] = calendar_id

        # Unset other primary calendars for this business
        db.query(CalendarIntegration).filter_by(
            business_id=business_id
        ).update({"is_primary": False})

        # Set this as primary
        integration.is_primary = True

        # Complete onboarding
        business.onboarding_status = {
            "completed": True,
            "started_at": business.onboarding_status["started_at"],
            "completed_at": datetime.utcnow().isoformat(),
            "steps_completed": [
                "business_created",
                "business_hours_set",
                "calendar_connected",
                "calendar_selected"
            ]
        }

        db.commit()

        return {
            "success": True,
            "message": "Onboarding completed successfully!",
            "business_id": business_id,
            "business_name": business.name,
            "calendar_provider": integration.provider,
            "selected_calendar_id": calendar_id,
            "next_steps": [
                "Test your calendar integration",
                "Configure AI instructions",
                "Start accepting appointments"
            ]
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to set primary calendar: {str(e)}")


# ========== HELPER: Get Onboarding Status ==========
@router.get("/business/{business_id}/status")
async def get_onboarding_status(
        business_id: str,
        db: Session = Depends(get_db)
):
    """Check the onboarding status of a business"""
    business = db.query(Business).filter_by(id=business_id).first()

    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    has_hours = db.query(BusinessHours).filter_by(business_id=business_id).count() == 7
    has_integration = db.query(CalendarIntegration).filter_by(
        business_id=business_id,
        is_active=True
    ).first() is not None

    return {
        "business_id": business_id,
        "business_name": business.name,
        "onboarding_status": business.onboarding_status,
        "checks": {
            "business_created": True,
            "business_hours_set": has_hours,
            "calendar_integrated": has_integration,
            "fully_onboarded": business.onboarding_status.get('completed', False)
        }
    }