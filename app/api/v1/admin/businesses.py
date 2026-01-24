"""
Admin Business API
CRUD operations for business management - requires PLATFORM ADMIN access
Platform admins can manage businesses for ANY business account
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timedelta

from app.config.database import get_db
from app.models.auth.user import User
from app.models.business.business import Business, BusinessHours
from app.api.dependencies import require_platform_admin
from app.utils.logger import get_logger
from app.schemas.admin.businesses import (
    MessageResponse,
    BusinessResponse,
    BusinessListResponse,
    BusinessStatsResponse,
    BusinessHoursResponse,
    PlatformBusinessStatsResponse,
    BusinessHoursCreate,
    BusinessHoursUpdate,
    BusinessProfileUpdate,
)

logger = get_logger(__name__)

# ============================================================================
# Routers
# ============================================================================

router = APIRouter(
    prefix="/businesses",
    tags=["Admin - Businesses"]
)

business_hours_router = APIRouter(
    prefix="/business-hours",
    tags=["Admin - Business Hours"]
)


# ============================================================================
# BUSINESS ENDPOINTS
# ============================================================================

@router.get("/", response_model=BusinessListResponse)
async def list_businesses(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    business_type: Optional[str] = Query(None, description="Filter by business type"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search by name or phone"),
    from_date: Optional[datetime] = Query(None, description="Filter from date"),
    to_date: Optional[datetime] = Query(None, description="Filter to date"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    List all businesses with filtering and pagination.

    Requires platform admin role.
    """
    logger.info(f"Admin listing businesses - User ID: {current_user.id}, Page: {page}")

    query = db.query(Business)

    # Apply filters
    if business_type:
        query = query.filter(Business.business_type == business_type)
    if is_active is not None:
        query = query.filter(Business.is_active == is_active)
    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            (Business.name.ilike(search_filter)) |
            (Business.phone_number.ilike(search_filter))
        )
    if from_date:
        query = query.filter(Business.created_at >= from_date)
    if to_date:
        query = query.filter(Business.created_at <= to_date)

    # Get total count
    total = query.count()

    # Calculate pagination
    pages = (total + page_size - 1) // page_size
    offset = (page - 1) * page_size

    # Get paginated results
    businesses = query.order_by(desc(Business.created_at)).offset(offset).limit(page_size).all()

    items = [
        BusinessResponse(**business.to_dict(include_deprecated=False))
        for business in businesses
    ]

    logger.debug(f"Retrieved {len(items)} businesses (total: {total})")

    return BusinessListResponse(
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        items=items
    )


@router.get("/stats", response_model=PlatformBusinessStatsResponse)
async def get_platform_business_stats(
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """Get platform-wide business statistics."""
    logger.info(f"Admin requesting platform business stats - User ID: {current_user.id}")

    # Change this to only count active businesses
    total_businesses = db.query(Business).filter(Business.is_active == True).count()

    # This stays the same
    active_businesses = db.query(Business).filter(Business.is_active == True).count()

    # Count inactive separately
    inactive_businesses = db.query(Business).filter(Business.is_active == False).count()

    # Business type breakdown
    businesses_by_type = {}
    all_businesses = db.query(Business).all()
    for business in all_businesses:
        businesses_by_type[business.business_type] = businesses_by_type.get(business.business_type, 0) + 1

    # Businesses with hours configured
    businesses_with_hours = db.query(func.count(func.distinct(BusinessHours.business_id))).scalar()

    # Businesses onboarded
    businesses_onboarded = sum(
        1 for b in all_businesses
        if b.onboarding_status and b.onboarding_status.get("completed", False)
    )

    # Time-based stats
    now = datetime.utcnow()
    businesses_last_24h = db.query(Business).filter(
        Business.created_at >= now - timedelta(hours=24)
    ).count()
    businesses_last_7d = db.query(Business).filter(
        Business.created_at >= now - timedelta(days=7)
    ).count()
    businesses_last_30d = db.query(Business).filter(
        Business.created_at >= now - timedelta(days=30)
    ).count()

    logger.debug(f"Platform stats - Total: {total_businesses}, Active: {active_businesses}, Onboarded: {businesses_onboarded}")

    return PlatformBusinessStatsResponse(
        total_businesses=total_businesses,
        active_businesses=active_businesses,
        inactive_businesses=inactive_businesses,
        businesses_by_type=businesses_by_type,
        businesses_with_hours_configured=businesses_with_hours,
        businesses_onboarded=businesses_onboarded,
        businesses_last_24h=businesses_last_24h,
        businesses_last_7d=businesses_last_7d,
        businesses_last_30d=businesses_last_30d
    )


@router.get("/{business_id}", response_model=BusinessResponse)
async def get_business(
    business_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    Get details of a specific business.

    Requires platform admin role.
    """
    business = db.query(Business).filter(Business.id == business_id).first()

    if not business:
        logger.warning(f"Business not found - Business ID: {business_id}")
        raise HTTPException(status_code=404, detail="Business not found")

    return BusinessResponse(**business.to_dict(include_deprecated=False))


@router.get("/{business_id}/stats", response_model=BusinessStatsResponse)
async def get_business_stats(
    business_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    Get statistics for a specific business.

    Requires platform admin role.
    """
    logger.info(f"Admin requesting business stats - User ID: {current_user.id}, Business ID: {business_id}")

    business = db.query(Business).filter(Business.id == business_id).first()

    if not business:
        logger.warning(f"Business stats failed - Not found: {business_id}")
        raise HTTPException(status_code=404, detail="Business not found")

    # Import here to avoid circular dependencies
    from app.models.business.service import Service
    from app.models.business.document import Document
    from app.models.appointment.availability import AvailabilityRule, AvailabilityOverride

    stats = BusinessStatsResponse(
        business_id=str(business.id),
        business_name=business.name,
        services_count=db.query(Service).filter(
            Service.business_id == business.id,
            Service.is_active == True
        ).count(),
        documents_count=db.query(Document).filter(
            Document.business_id == business.id,
            Document.is_active == True
        ).count(),
        availability_rules_count=db.query(AvailabilityRule).filter(
            AvailabilityRule.business_id == business.id,
            AvailabilityRule.is_active == True
        ).count(),
        availability_overrides_count=db.query(AvailabilityOverride).filter(
            AvailabilityOverride.business_id == business.id
        ).count(),
        business_hours_configured=db.query(BusinessHours).filter(
            BusinessHours.business_id == business.id
        ).count() > 0,
        onboarding_complete=business.onboarding_status.get("completed", False) if business.onboarding_status else False,
        timezone=business.timezone,
        is_active=business.is_active
    )

    return stats


@router.put("/{business_id}", response_model=BusinessResponse)
async def update_business(
    business_id: UUID,
    business_data: BusinessProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    Update a business profile.

    Requires platform admin role.
    """
    logger.info(f"Admin updating business - User ID: {current_user.id}, Business ID: {business_id}")

    business = db.query(Business).filter(Business.id == business_id).first()

    if not business:
        logger.warning(f"Business update failed - Not found: {business_id}")
        raise HTTPException(status_code=404, detail="Business not found")

    # Update fields
    update_data = business_data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        if hasattr(business, field):
            setattr(business, field, value)

    try:
        db.commit()
        db.refresh(business)
        logger.info(f"Business updated - Business ID: {business_id}, Updated by: {current_user.id}")

        return BusinessResponse(**business.to_dict(include_deprecated=False))

    except Exception as e:
        db.rollback()
        logger.error(f"Error updating business: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update business: {str(e)}")


@router.delete("/{business_id}", response_model=MessageResponse)
async def delete_business(
    business_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    Deactivate a business (soft delete).
    """
    logger.warning(f"Admin deactivating business - User ID: {current_user.id}, Business ID: {business_id}")

    business = db.query(Business).filter(Business.id == business_id).first()

    if not business:
        logger.warning(f"Business deactivation failed - Not found: {business_id}")
        raise HTTPException(status_code=404, detail="Business not found")

    try:
        business.is_active = False
        db.commit()
        logger.warning(f"Business deactivated - Business ID: {business_id}, Deactivated by: {current_user.id}")

        return MessageResponse(
            message="Business deactivated successfully",
            details={
                "business_id": str(business_id),
                "business_name": business.name
            }
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Error deactivating business: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to deactivate business: {str(e)}")


# ============================================================================
# BUSINESS HOURS ENDPOINTS
# ============================================================================

@business_hours_router.get("/", response_model=List[BusinessHoursResponse])
async def list_all_business_hours(
    business_id: Optional[UUID] = Query(None, description="Filter by business ID"),
    day_of_week: Optional[int] = Query(None, ge=0, le=6, description="Filter by day"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    List all business hours with optional filtering.

    Requires platform admin role.
    """
    logger.info(f"Admin listing business hours - User ID: {current_user.id}")

    query = db.query(BusinessHours)

    if business_id:
        query = query.filter(BusinessHours.business_id == business_id)
    if day_of_week is not None:
        query = query.filter(BusinessHours.day_of_week == day_of_week)

    hours = query.order_by(BusinessHours.business_id, BusinessHours.day_of_week).all()

    logger.debug(f"Retrieved {len(hours)} business hours records")

    return [BusinessHoursResponse.model_validate(h) for h in hours]


@business_hours_router.get("/{hours_id}", response_model=BusinessHoursResponse)
async def get_business_hours(
    hours_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    Get specific business hours by ID.

    Requires platform admin role.
    """
    hours = db.query(BusinessHours).filter(BusinessHours.id == hours_id).first()

    if not hours:
        logger.warning(f"Business hours not found - Hours ID: {hours_id}")
        raise HTTPException(status_code=404, detail="Business hours not found")

    return BusinessHoursResponse.model_validate(hours)


@business_hours_router.post("/", response_model=BusinessHoursResponse, status_code=201)
async def create_business_hours(
    hours_data: BusinessHoursCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    Create business hours for a specific business and day.

    Requires platform admin role.
    """
    logger.info(f"Admin creating business hours - User ID: {current_user.id}, Business ID: {hours_data.business_id}, Day: {hours_data.day_of_week}")

    # Verify business exists
    business = db.query(Business).filter(Business.id == hours_data.business_id).first()
    if not business:
        logger.warning(f"Business hours creation failed - Business not found: {hours_data.business_id}")
        raise HTTPException(status_code=404, detail="Business not found")

    # Check if hours already exist for this business and day
    existing = db.query(BusinessHours).filter(
        BusinessHours.business_id == hours_data.business_id,
        BusinessHours.day_of_week == hours_data.day_of_week
    ).first()

    if existing:
        logger.warning(f"Business hours creation failed - Duplicate for Business ID: {hours_data.business_id}, Day: {hours_data.day_of_week}")
        raise HTTPException(
            status_code=400,
            detail=f"Business hours already exist for this business on day {hours_data.day_of_week}. Use PUT to update."
        )

    hours = BusinessHours(
        business_id=hours_data.business_id,
        day_of_week=hours_data.day_of_week,
        open_time=hours_data.open_time,
        close_time=hours_data.close_time,
        is_closed=hours_data.is_closed
    )

    try:
        db.add(hours)
        db.commit()
        db.refresh(hours)
        logger.info(f"Business hours created - Hours ID: {hours.id}, Business ID: {hours_data.business_id}, Created by: {current_user.id}")

        return BusinessHoursResponse.model_validate(hours)

    except Exception as e:
        db.rollback()
        logger.error(f"Error creating business hours: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create business hours: {str(e)}")


@business_hours_router.put("/{hours_id}", response_model=BusinessHoursResponse)
async def update_business_hours(
    hours_id: int,
    hours_data: BusinessHoursUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    Update business hours by ID.

    Requires platform admin role.
    """
    logger.info(f"Admin updating business hours - User ID: {current_user.id}, Hours ID: {hours_id}")

    hours = db.query(BusinessHours).filter(BusinessHours.id == hours_id).first()

    if not hours:
        logger.warning(f"Business hours update failed - Not found: {hours_id}")
        raise HTTPException(status_code=404, detail="Business hours not found")

    # Update fields
    update_data = hours_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(hours, field, value)

    # Validate time range if both times are set
    if hours.open_time and hours.close_time and hours.close_time <= hours.open_time:
        logger.warning(f"Business hours update failed - Invalid time range")
        raise HTTPException(
            status_code=400,
            detail="close_time must be after open_time"
        )

    try:
        db.commit()
        db.refresh(hours)
        logger.info(f"Business hours updated - Hours ID: {hours_id}, Updated by: {current_user.id}")

        return BusinessHoursResponse.model_validate(hours)

    except Exception as e:
        db.rollback()
        logger.error(f"Error updating business hours: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update business hours: {str(e)}")


@business_hours_router.delete("/{hours_id}", response_model=MessageResponse)
async def delete_business_hours(
    hours_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    Delete business hours by ID.

    Requires platform admin role.
    """
    logger.warning(f"Admin deleting business hours (PERMANENT) - User ID: {current_user.id}, Hours ID: {hours_id}")

    hours = db.query(BusinessHours).filter(BusinessHours.id == hours_id).first()

    if not hours:
        logger.warning(f"Business hours deletion failed - Not found: {hours_id}")
        raise HTTPException(status_code=404, detail="Business hours not found")

    try:
        db.delete(hours)
        db.commit()
        logger.warning(f"Business hours DELETED permanently - Hours ID: {hours_id}, Deleted by: {current_user.id}")

        return MessageResponse(
            message="Business hours deleted successfully",
            details={
                "hours_id": hours_id,
                "business_id": str(hours.business_id),
                "day_of_week": hours.day_of_week
            }
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting business hours: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete business hours: {str(e)}")