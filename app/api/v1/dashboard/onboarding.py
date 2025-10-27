# app/api/v1/onboarding.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, timezone
import uuid

from app.config.database import get_db
from app.models.business import Business, BusinessHours
from app.models.calendar_integration import CalendarIntegration
from app.models.user import User, BusinessRole, user_business_association
from app.api.dependencies import get_current_active_user

router = APIRouter(tags=["onboarding"])


# ========== HELPER FUNCTIONS ==========

def verify_business_access(
        db: Session,
        user: User,
        business_id: str,
        require_owner: bool = True
) -> Business:
    """
    Verify that the user has access to the business and return it.

    Args:
        db: Database session
        user: Current authenticated user
        business_id: Business UUID as string
        require_owner: If True, requires OWNER role; if False, any role is acceptable

    Returns:
        Business object if access is granted

    Raises:
        HTTPException: If business not found or user lacks access
    """
    try:
        business_uuid = uuid.UUID(business_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid business ID format"
        )

    # Get business
    business = db.query(Business).filter(
        Business.id == business_uuid,
        Business.is_active.is_(True)
    ).first()

    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business not found"
        )

    # Check user has access to this business
    association = db.query(user_business_association).filter(
        user_business_association.c.user_id == user.id,
        user_business_association.c.business_id == business_uuid
    ).first()

    if not association:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this business"
        )

    # Check role if required
    if require_owner and association.role != BusinessRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only business owners can perform this action"
        )

    return business


def link_user_to_business(
        db: Session,
        user_id: uuid.UUID,
        business_id: uuid.UUID,
        role: BusinessRole = BusinessRole.OWNER
):
    """
    Create a user-business association.

    Args:
        db: Database session
        user_id: User UUID
        business_id: Business UUID
        role: BusinessRole (default: OWNER)
    """
    # Check if association already exists
    existing = db.query(user_business_association).filter(
        user_business_association.c.user_id == user_id,
        user_business_association.c.business_id == business_id
    ).first()

    if existing:
        return  # Already linked

    # Create new association
    stmt = user_business_association.insert().values(
        id=uuid.uuid4(),
        user_id=user_id,
        business_id=business_id,
        role=role
    )
    db.execute(stmt)
    db.commit()


# ========== PYDANTIC MODELS ==========

class BusinessHourInput(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6, description="0=Monday, 6=Sunday")
    open_time: str = Field(..., pattern=r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$", description="HH:MM format")
    close_time: str = Field(..., pattern=r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$", description="HH:MM format")
    is_closed: bool = False

    @field_validator('close_time')
    @classmethod
    def validate_time_range(cls, v: str, info) -> str:
        if 'open_time' in info.data and not info.data.get('is_closed', False):
            open_h, open_m = map(int, info.data['open_time'].split(':'))
            close_h, close_m = map(int, v.split(':'))
            if (close_h * 60 + close_m) <= (open_h * 60 + open_m):
                raise ValueError('close_time must be after open_time')
        return v


class BusinessCreateInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    phone_number: str = Field(..., pattern=r"^\+?1?\d{10,15}$")
    business_type: str = Field(..., min_length=1, max_length=100)
    timezone: str = Field(default="UTC")

    # Optional fields
    services: Optional[List[str]] = []
    contact_info: Optional[dict] = {}
    ai_instructions: Optional[str] = ""

    # New structured fields
    business_profile: Optional[dict] = {}
    service_catalog: Optional[dict] = {}
    conversation_policies: Optional[dict] = {}
    quick_responses: Optional[dict] = {}


class BusinessUpdateInput(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    phone_number: Optional[str] = Field(None, pattern=r"^\+?1?\d{10,15}$")
    business_type: Optional[str] = Field(None, min_length=1, max_length=100)
    timezone: Optional[str] = None
    services: Optional[List[str]] = None
    contact_info: Optional[dict] = None
    ai_instructions: Optional[str] = None
    business_profile: Optional[dict] = None
    service_catalog: Optional[dict] = None
    conversation_policies: Optional[dict] = None
    quick_responses: Optional[dict] = None


class OnboardingStatusResponse(BaseModel):
    business_created: bool
    business_hours_configured: bool
    calendar_connected: bool
    primary_calendar_set: bool
    onboarding_complete: bool
    next_step: str

@router.get("/my-businesses")
async def get_my_businesses(
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    """
    Get all businesses the current user has access to

    🔒 Authentication Required: JWT token
    📋 Returns: List of businesses with user's role in each
    """
    print(f"\n{'=' * 60}")
    print(f"📊 GET /my-businesses called")
    print(f"{'=' * 60}")
    print(f"👤 Current User ID: {current_user.id}")
    print(f"📧 Current User Email: {current_user.email}")

    # Get all business associations for this user
    associations = db.query(user_business_association).filter(
        user_business_association.c.user_id == current_user.id
    ).all()

    print(f"\n🔗 Found {len(associations)} business associations")
    for idx, assoc in enumerate(associations, 1):
        print(f"  Association {idx}:")
        print(f"    - Business ID: {assoc.business_id}")
        print(f"    - Role: {assoc.role}")

    businesses = []
    for assoc in associations:
        business = db.query(Business).filter(
            Business.id == assoc.business_id,
            Business.is_active.is_(True)
        ).first()

        if business:
            print(f"\n✅ Found active business: {business.name}")
            print(f"   ID: {business.id}")
            print(f"   Type: {business.business_type}")
            print(f"   Phone: {business.phone_number}")
            print(f"   User Role: {assoc.role.value}")

            businesses.append({
                "id": str(business.id),
                "name": business.name,
                "business_type": business.business_type,
                "phone_number": business.phone_number,
                "role": assoc.role.value,
                "is_active_business": str(business.id) == str(current_user.active_business_id),
                "onboarding_complete": business.onboarding_status.get("completed_at") is not None,
                "created_at": business.created_at.isoformat() if business.created_at else None
            })
        else:
            print(f"\n❌ Business {assoc.business_id} not found or inactive")

    print(f"\n📦 Returning {len(businesses)} businesses")
    print(f"{'=' * 60}\n")

    return {
        "businesses": businesses,
        "total": len(businesses)
    }
# ========== STEP 1: CREATE BUSINESS (SECURED) ==========

@router.post("/business", status_code=status.HTTP_201_CREATED)
async def create_business(
        business_data: BusinessCreateInput,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    """
    Step 1: Create a new business account

    🔒 Authentication Required: JWT token
    👤 Creates business owned by the authenticated user
    """
    # Check if phone number already exists
    existing = db.query(Business).filter(
        Business.phone_number == business_data.phone_number,
        Business.is_active.is_(True)
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A business with this phone number already exists"
        )

    # Create business
    business = Business(
        id=uuid.uuid4(),
        name=business_data.name,
        phone_number=business_data.phone_number,
        business_type=business_data.business_type,
        timezone=business_data.timezone,
        services=business_data.services,
        contact_info=business_data.contact_info,
        ai_instructions=business_data.ai_instructions,
        business_profile=business_data.business_profile,
        service_catalog=business_data.service_catalog,
        conversation_policies=business_data.conversation_policies,
        quick_responses=business_data.quick_responses,
        onboarding_status={
            "business_created": True,
            "business_hours_configured": False,
            "calendar_connected": False,
            "primary_calendar_set": False,
            "completed_at": None
        }
    )

    db.add(business)
    db.flush()  # Get the business ID without committing

    # 🔑 KEY CHANGE: Link the business to the user as OWNER
    link_user_to_business(
        db=db,
        user_id=current_user.id,
        business_id=business.id,
        role=BusinessRole.OWNER
    )

    # Set as active business for the user if they don't have one
    if not current_user.active_business_id:
        current_user.active_business_id = business.id

    db.commit()
    db.refresh(business)

    return {
        "success": True,
        "business_id": str(business.id),
        "message": "Business created successfully",
        "next_step": "configure_business_hours"
    }


# ========== STEP 2: CONFIGURE BUSINESS HOURS (SECURED) ==========

@router.post("/{business_id}/business-hours")
async def set_business_hours(
        business_id: str,
        hours: List[BusinessHourInput],
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    """
    Step 2: Configure business hours for all days of the week

    🔒 Authentication Required: JWT token
    🔑 Authorization: Must be business owner
    """
    # Verify user owns this business
    business = verify_business_access(db, current_user, business_id, require_owner=True)

    # Validate we have hours for all 7 days
    days_provided = {h.day_of_week for h in hours}
    if len(days_provided) != 7:
        raise HTTPException(
            status_code=400,
            detail="Must provide hours for all 7 days (0-6)"
        )

    # Delete existing hours
    db.query(BusinessHours).filter(BusinessHours.business_id == business_id).delete()

    # Create new hours
    for hour_data in hours:
        business_hour = BusinessHours(
            business_id=business_id,
            day_of_week=hour_data.day_of_week,
            open_time=hour_data.open_time,
            close_time=hour_data.close_time,
            is_closed=hour_data.is_closed
        )
        db.add(business_hour)

    # Update onboarding status
    business.onboarding_status["business_hours_configured"] = True

    db.commit()

    return {
        "success": True,
        "message": "Business hours configured successfully",
        "next_step": "connect_calendar"
    }


@router.get("/{business_id}/business-hours")
async def get_business_hours(
        business_id: str,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    """
    Get configured business hours

    🔒 Authentication Required: JWT token
    🔑 Authorization: Must be business member (owner or member)
    """
    # Verify user has access (member or owner)
    business = verify_business_access(db, current_user, business_id, require_owner=False)

    hours = db.query(BusinessHours).filter(
        BusinessHours.business_id == business_id
    ).order_by(BusinessHours.day_of_week).all()

    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    return {
        "business_id": business_id,
        "hours": [
            {
                "day_of_week": h.day_of_week,
                "day_name": day_names[h.day_of_week],
                "open_time": h.open_time,
                "close_time": h.close_time,
                "is_closed": h.is_closed
            }
            for h in hours
        ]
    }


@router.patch("/{business_id}/business-hours/{day_of_week}")
async def update_business_hour(
        business_id: str,
        day_of_week: int,
        hour_data: BusinessHourInput,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    """
    Update business hours for a specific day

    🔒 Authentication Required: JWT token
    🔑 Authorization: Must be business owner
    """
    if day_of_week != hour_data.day_of_week:
        raise HTTPException(
            status_code=400,
            detail="day_of_week in URL must match day_of_week in body"
        )

    # Verify user owns this business
    business = verify_business_access(db, current_user, business_id, require_owner=True)

    hour = db.query(BusinessHours).filter(
        BusinessHours.business_id == business_id,
        BusinessHours.day_of_week == day_of_week
    ).first()

    if not hour:
        raise HTTPException(status_code=404, detail="Business hour not found for this day")

    hour.open_time = hour_data.open_time
    hour.close_time = hour_data.close_time
    hour.is_closed = hour_data.is_closed

    db.commit()

    return {
        "success": True,
        "message": f"Business hours updated for day {day_of_week}"
    }


# ========== STEP 3: CALENDAR INTEGRATION STATUS (SECURED) ==========

@router.get("/{business_id}/calendar-status")
async def get_calendar_status(
        business_id: str,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    """
    Step 3: Check calendar integration status

    🔒 Authentication Required: JWT token
    🔑 Authorization: Must be business member
    """
    # Verify user has access
    business = verify_business_access(db, current_user, business_id, require_owner=False)

    integrations = db.query(CalendarIntegration).filter(
        CalendarIntegration.business_id == business_id,
        CalendarIntegration.is_active.is_(True)
    ).all()

    primary_calendar = next((i for i in integrations if i.is_primary), None)

    return {
        "business_id": business_id,
        "has_integrations": len(integrations) > 0,
        "total_integrations": len(integrations),
        "has_primary": primary_calendar is not None,
        "integrations": [
            {
                "id": str(i.id),
                "provider": i.provider,
                "is_primary": i.is_primary,
                "created_at": i.created_at.isoformat() if i.created_at else None,
                "provider_config": i.provider_config
            }
            for i in integrations
        ],
        "available_providers": ["google", "outlook", "calendly"]
    }


# ========== STEP 3: SET PRIMARY CALENDAR (SECURED) ==========

@router.patch("/{business_id}/primary-calendar/{integration_id}")
async def set_primary_calendar(
        business_id: str,
        integration_id: str,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    """
    Step 3 (final): Set primary calendar after connecting and selecting calendar

    🔒 Authentication Required: JWT token
    🔑 Authorization: Must be business owner
    """
    # Verify user owns this business
    business = verify_business_access(db, current_user, business_id, require_owner=True)

    integration = db.query(CalendarIntegration).filter(
        CalendarIntegration.id == integration_id,
        CalendarIntegration.business_id == business_id,
        CalendarIntegration.is_active.is_(True)
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Calendar integration not found")

    # Unset all other primary calendars for this business
    db.query(CalendarIntegration).filter(
        CalendarIntegration.business_id == business_id
    ).update({"is_primary": False})

    # Set this one as primary
    integration.is_primary = True

    # Update onboarding status
    business.onboarding_status["calendar_connected"] = True
    business.onboarding_status["primary_calendar_set"] = True

    # Check if onboarding is complete
    if all([
        business.onboarding_status.get("business_created"),
        business.onboarding_status.get("business_hours_configured"),
        business.onboarding_status.get("calendar_connected"),
        business.onboarding_status.get("primary_calendar_set")
    ]):
        business.onboarding_status["completed_at"] = datetime.now(timezone.utc).isoformat()

    db.commit()

    return {
        "success": True,
        "message": "Primary calendar set successfully",
        "primary_calendar": {
            "id": str(integration.id),
            "provider": integration.provider
        },
        "onboarding_complete": business.onboarding_status.get("completed_at") is not None
    }


# ========== ONBOARDING STATUS CHECK (SECURED) ==========

@router.get("/{business_id}/status")
async def get_onboarding_status(
        business_id: str,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
) -> OnboardingStatusResponse:
    """
    Check overall onboarding progress

    🔒 Authentication Required: JWT token
    🔑 Authorization: Must be business member
    """
    # Verify user has access
    business = verify_business_access(db, current_user, business_id, require_owner=False)

    status_data = business.onboarding_status or {}

    business_created = status_data.get("business_created", True)
    business_hours_configured = status_data.get("business_hours_configured", False)
    calendar_connected = status_data.get("calendar_connected", False)
    primary_calendar_set = status_data.get("primary_calendar_set", False)

    # Verify business hours actually exist
    if business_hours_configured:
        hours_count = db.query(BusinessHours).filter(
            BusinessHours.business_id == business_id
        ).count()
        business_hours_configured = hours_count == 7

    # Verify calendar integration exists
    if calendar_connected:
        integration_count = db.query(CalendarIntegration).filter(
            CalendarIntegration.business_id == business_id,
            CalendarIntegration.is_active.is_(True)
        ).count()
        calendar_connected = integration_count > 0

    # Verify primary calendar is set
    if primary_calendar_set:
        primary_exists = db.query(CalendarIntegration).filter(
            CalendarIntegration.business_id == business_id,
            CalendarIntegration.is_active.is_(True),
            CalendarIntegration.is_primary.is_(True)
        ).first() is not None
        primary_calendar_set = primary_exists

    onboarding_complete = all([
        business_created,
        business_hours_configured,
        calendar_connected,
        primary_calendar_set
    ])

    # Determine next step
    if not business_hours_configured:
        next_step = "configure_business_hours"
    elif not calendar_connected:
        next_step = "connect_calendar"
    elif not primary_calendar_set:
        next_step = "set_primary_calendar"
    else:
        next_step = "complete"

    return OnboardingStatusResponse(
        business_created=business_created,
        business_hours_configured=business_hours_configured,
        calendar_connected=calendar_connected,
        primary_calendar_set=primary_calendar_set,
        onboarding_complete=onboarding_complete,
        next_step=next_step
    )


# ========== BUSINESS MANAGEMENT (SECURED) ==========

@router.get("/{business_id}")
async def get_business(
        business_id: str,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    """
    Get business details

    🔒 Authentication Required: JWT token
    🔑 Authorization: Must be business member
    """
    # Verify user has access
    business = verify_business_access(db, current_user, business_id, require_owner=False)

    return {
        "id": str(business.id),
        "name": business.name,
        "phone_number": business.phone_number,
        "business_type": business.business_type,
        "timezone": business.timezone,
        "services": business.services,
        "contact_info": business.contact_info,
        "ai_instructions": business.ai_instructions,
        "business_profile": business.business_profile,
        "service_catalog": business.service_catalog,
        "conversation_policies": business.conversation_policies,
        "quick_responses": business.quick_responses,
        "onboarding_status": business.onboarding_status,
        "created_at": business.created_at.isoformat() if business.created_at else None
    }


@router.patch("/{business_id}")
async def update_business(
        business_id: str,
        update_data: BusinessUpdateInput,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    """
    Update business details

    🔒 Authentication Required: JWT token
    🔑 Authorization: Must be business owner
    """
    # Verify user owns this business
    business = verify_business_access(db, current_user, business_id, require_owner=True)

    # Update only provided fields
    update_dict = update_data.model_dump(exclude_unset=True)

    # Check phone number uniqueness if being updated
    if "phone_number" in update_dict:
        existing = db.query(Business).filter(
            Business.phone_number == update_dict["phone_number"],
            Business.id != business.id,
            Business.is_active.is_(True)
        ).first()
        if existing:
            raise HTTPException(
                status_code=409,
                detail="Another business with this phone number already exists"
            )

    for key, value in update_dict.items():
        setattr(business, key, value)

    db.commit()
    db.refresh(business)

    return {
        "success": True,
        "message": "Business updated successfully",
        "business_id": str(business.id)
    }


@router.delete("/{business_id}")
async def deactivate_business(
        business_id: str,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    """
    Deactivate a business (soft delete)

    🔒 Authentication Required: JWT token
    🔑 Authorization: Must be business owner
    """
    # Verify user owns this business
    business = verify_business_access(db, current_user, business_id, require_owner=True)

    business.is_active = False

    # Also deactivate all calendar integrations
    db.query(CalendarIntegration).filter(
        CalendarIntegration.business_id == business_id
    ).update({"is_active": False})

    db.commit()

    return {
        "success": True,
        "message": "Business deactivated successfully"
    }


# ========== NEW: USER'S BUSINESSES ENDPOINT ==========
