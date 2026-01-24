"""
Admin Availability API
CRUD operations for availability rules and overrides - requires PLATFORM ADMIN access
Platform admins can manage availability for ANY business
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from datetime import date as date_type,timedelta
from uuid import UUID

from app.config.database import get_db
from app.models.auth.user import User
from app.models.business.business import Business
from app.models.appointment.availability import AvailabilityRule, AvailabilityOverride
from app.api.dependencies import require_platform_admin
from app.utils.logger import get_logger
from app.schemas.admin.availability import (
    MessageResponse,
    AvailabilityRuleListResponse,
    AvailabilityRuleResponse,
    AvailabilityRuleStatsResponse,
    AvailabilityRuleCreate,
    AvailabilityRuleUpdate,
    AvailabilityOverrideResponse,
    AvailabilityOverrideStatsResponse,
    AvailabilityOverrideListResponse,
    AvailabilityOverrideCreate,
    AvailabilityOverrideUpdate,
)
logger = get_logger(__name__)


# ============================================================================
# Routers
# ============================================================================

availability_rules_router = APIRouter(
    prefix="/availability-rules",
    tags=["Admin - Availability Rules"]
)

availability_overrides_router = APIRouter(
    prefix="/availability-overrides",
    tags=["Admin - Availability Overrides"]
)


# ============================================================================
# AVAILABILITY RULES ENDPOINTS
# ============================================================================

@availability_rules_router.get("/", response_model=AvailabilityRuleListResponse)
async def list_availability_rules(
        page: int = Query(1, ge=1, description="Page number"),
        page_size: int = Query(50, ge=1, le=100, description="Items per page"),
        business_id: Optional[UUID] = Query(None, description="Filter by business ID"),
        day_of_week: Optional[int] = Query(None, ge=0, le=6, description="Filter by day of week"),
        is_active: Optional[bool] = Query(None, description="Filter by active status"),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    List all availability rules with filtering and pagination.

    Requires platform admin role.
    """
    logger.info(f"Admin listing availability rules - User ID: {current_user.id}")

    query = db.query(AvailabilityRule)

    # Apply filters
    if business_id:
        query = query.filter(AvailabilityRule.business_id == business_id)
    if day_of_week is not None:
        query = query.filter(AvailabilityRule.day_of_week == day_of_week)
    if is_active is not None:
        query = query.filter(AvailabilityRule.is_active == is_active)

    # Get total count
    total = query.count()

    # Calculate pagination
    pages = (total + page_size - 1) // page_size
    offset = (page - 1) * page_size

    # Get paginated results
    rules = query.order_by(
        AvailabilityRule.business_id,
        AvailabilityRule.day_of_week
    ).offset(offset).limit(page_size).all()

    items = [AvailabilityRuleResponse.model_validate(rule) for rule in rules]

    logger.debug(f"Retrieved {len(items)} availability rules (total: {total})")

    return AvailabilityRuleListResponse(
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        items=items
    )


@availability_rules_router.get("/stats", response_model=AvailabilityRuleStatsResponse)
async def get_availability_rule_stats(
        business_id: Optional[UUID] = Query(None, description="Filter stats by business ID"),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Get comprehensive statistics about availability rules.

    Requires platform admin role.
    """
    logger.info(f"Admin requesting availability rule stats - User ID: {current_user.id}")

    query = db.query(AvailabilityRule)
    if business_id:
        query = query.filter(AvailabilityRule.business_id == business_id)

    # Total rules
    total_rules = query.count()

    # Active/Inactive breakdown
    active_rules = query.filter(AvailabilityRule.is_active == True).count()
    inactive_rules = query.filter(AvailabilityRule.is_active == False).count()

    # Day of week breakdown
    rules_by_day = {}
    all_rules = query.all()
    for rule in all_rules:
        day_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][rule.day_of_week]
        rules_by_day[day_name] = rules_by_day.get(day_name, 0) + 1

    # Unique businesses
    unique_businesses = db.query(func.count(func.distinct(AvailabilityRule.business_id))).scalar()

    # Average durations
    avg_slot = db.query(func.avg(AvailabilityRule.slot_duration_minutes)).scalar() or 0
    avg_buffer = db.query(func.avg(AvailabilityRule.buffer_time_minutes)).scalar() or 0

    return AvailabilityRuleStatsResponse(
        total_rules=total_rules,
        active_rules=active_rules,
        inactive_rules=inactive_rules,
        rules_by_day=rules_by_day,
        unique_businesses=unique_businesses,
        avg_slot_duration_minutes=round(float(avg_slot), 2),
        avg_buffer_time_minutes=round(float(avg_buffer), 2)
    )


@availability_rules_router.get("/{rule_id}", response_model=AvailabilityRuleResponse)
async def get_availability_rule(
        rule_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Get details of a specific availability rule.

    Requires platform admin role.
    """
    rule = db.query(AvailabilityRule).filter(AvailabilityRule.id == rule_id).first()

    if not rule:
        logger.warning(f"Availability rule not found - Rule ID: {rule_id}")
        raise HTTPException(status_code=404, detail="Availability rule not found")

    return AvailabilityRuleResponse.model_validate(rule)


@availability_rules_router.post("/", response_model=AvailabilityRuleResponse, status_code=201)
async def create_availability_rule(
        rule_data: AvailabilityRuleCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Create a new availability rule.

    Requires platform admin role.
    """
    logger.info(f"Admin creating availability rule - User ID: {current_user.id}, Business ID: {rule_data.business_id}, Day: {rule_data.day_of_week}")

    # Verify business exists
    business = db.query(Business).filter(Business.id == rule_data.business_id).first()
    if not business:
        logger.warning(f"Availability rule creation failed - Business not found: {rule_data.business_id}")
        raise HTTPException(status_code=404, detail="Business not found")

    # Validate time range
    if rule_data.start_time >= rule_data.end_time:
        logger.warning(f"Availability rule creation failed - Invalid time range: {rule_data.start_time} >= {rule_data.end_time}")
        raise HTTPException(
            status_code=400,
            detail="Start time must be before end time"
        )

    rule = AvailabilityRule(
        business_id=rule_data.business_id,
        day_of_week=rule_data.day_of_week,
        start_time=rule_data.start_time,
        end_time=rule_data.end_time,
        slot_duration_minutes=rule_data.slot_duration_minutes,
        buffer_time_minutes=rule_data.buffer_time_minutes,
        is_active=rule_data.is_active
    )

    db.add(rule)
    db.commit()
    db.refresh(rule)

    logger.info(f"Availability rule created - Rule ID: {rule.id}, Business ID: {rule_data.business_id}, Created by: {current_user.id}")

    return AvailabilityRuleResponse.model_validate(rule)


@availability_rules_router.put("/{rule_id}", response_model=AvailabilityRuleResponse)
async def update_availability_rule(
        rule_id: UUID,
        rule_data: AvailabilityRuleUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Update an existing availability rule.

    Requires platform admin role.
    """
    logger.info(f"Admin updating availability rule - User ID: {current_user.id}, Rule ID: {rule_id}")

    rule = db.query(AvailabilityRule).filter(AvailabilityRule.id == rule_id).first()

    if not rule:
        logger.warning(f"Availability rule update failed - Not found: {rule_id}")
        raise HTTPException(status_code=404, detail="Availability rule not found")

    # Update fields
    update_data = rule_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(rule, field, value)

    # Validate time range if both times are set
    if rule.start_time >= rule.end_time:
        logger.warning(f"Availability rule update failed - Invalid time range: {rule.start_time} >= {rule.end_time}")
        raise HTTPException(
            status_code=400,
            detail="Start time must be before end time"
        )

    db.commit()
    db.refresh(rule)

    logger.info(f"Availability rule updated - Rule ID: {rule_id}, Updated by: {current_user.id}")

    return AvailabilityRuleResponse.model_validate(rule)


@availability_rules_router.delete("/{rule_id}", response_model=MessageResponse)
async def delete_availability_rule(
        rule_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Permanently delete an availability rule.

    Requires platform admin role. This action cannot be undone.
    """
    logger.warning(f"Admin deleting availability rule (PERMANENT) - User ID: {current_user.id}, Rule ID: {rule_id}")

    rule = db.query(AvailabilityRule).filter(AvailabilityRule.id == rule_id).first()

    if not rule:
        logger.warning(f"Availability rule deletion failed - Not found: {rule_id}")
        raise HTTPException(status_code=404, detail="Availability rule not found")

    business_id = str(rule.business_id)
    day_of_week = rule.day_of_week

    db.delete(rule)
    db.commit()

    logger.warning(f"Availability rule DELETED permanently - Rule ID: {rule_id}, Business ID: {business_id}, Deleted by: {current_user.id}")

    return MessageResponse(
        message="Availability rule deleted successfully",
        details={
            "rule_id": str(rule_id),
            "business_id": business_id,
            "day_of_week": day_of_week
        }
    )


# ============================================================================
# AVAILABILITY OVERRIDES ENDPOINTS
# ============================================================================

@availability_overrides_router.get("/", response_model=AvailabilityOverrideListResponse)
async def list_availability_overrides(
        page: int = Query(1, ge=1, description="Page number"),
        page_size: int = Query(50, ge=1, le=100, description="Items per page"),
        business_id: Optional[UUID] = Query(None, description="Filter by business ID"),
        start_date: Optional[date_type] = Query(None, description="Filter from this date"),
        end_date: Optional[date_type] = Query(None, description="Filter until this date"),
        is_available: Optional[bool] = Query(None, description="Filter by availability status"),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    List all availability overrides with filtering and pagination.

    Requires platform admin role.
    """
    logger.info(f"Admin listing availability overrides - User ID: {current_user.id}")

    query = db.query(AvailabilityOverride)

    # Apply filters
    if business_id:
        query = query.filter(AvailabilityOverride.business_id == business_id)
    if start_date:
        query = query.filter(AvailabilityOverride.date >= start_date)
    if end_date:
        query = query.filter(AvailabilityOverride.date <= end_date)
    if is_available is not None:
        query = query.filter(AvailabilityOverride.is_available == is_available)

    # Get total count
    total = query.count()

    # Calculate pagination
    pages = (total + page_size - 1) // page_size
    offset = (page - 1) * page_size

    # Get paginated results
    overrides = query.order_by(
        AvailabilityOverride.business_id,
        AvailabilityOverride.date
    ).offset(offset).limit(page_size).all()

    items = [AvailabilityOverrideResponse.model_validate(override) for override in overrides]

    logger.debug(f"Retrieved {len(items)} availability overrides (total: {total})")

    return AvailabilityOverrideListResponse(
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        items=items
    )


@availability_overrides_router.get("/stats", response_model=AvailabilityOverrideStatsResponse)
async def get_availability_override_stats(
        business_id: Optional[UUID] = Query(None, description="Filter stats by business ID"),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Get comprehensive statistics about availability overrides.

    Requires platform admin role.
    """
    logger.info(f"Admin requesting availability override stats - User ID: {current_user.id}")

    query = db.query(AvailabilityOverride)
    if business_id:
        query = query.filter(AvailabilityOverride.business_id == business_id)

    # Total overrides
    total_overrides = query.count()

    # Available/Unavailable breakdown
    available_overrides = query.filter(AvailabilityOverride.is_available == True).count()
    unavailable_overrides = query.filter(AvailabilityOverride.is_available == False).count()

    # Unique businesses
    unique_businesses = db.query(func.count(func.distinct(AvailabilityOverride.business_id))).scalar()

    # Time-based stats
    today = date_type.today()
    overrides_last_30d = query.filter(
        AvailabilityOverride.date >= today - timedelta(days=30),
        AvailabilityOverride.date < today
    ).count()
    overrides_next_30d = query.filter(
        AvailabilityOverride.date >= today,
        AvailabilityOverride.date <= today + timedelta(days=30)
    ).count()

    return AvailabilityOverrideStatsResponse(
        total_overrides=total_overrides,
        available_overrides=available_overrides,
        unavailable_overrides=unavailable_overrides,
        unique_businesses=unique_businesses,
        overrides_last_30d=overrides_last_30d,
        overrides_next_30d=overrides_next_30d
    )


@availability_overrides_router.get("/{override_id}", response_model=AvailabilityOverrideResponse)
async def get_availability_override(
        override_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Get details of a specific availability override.

    Requires platform admin role.
    """
    override = db.query(AvailabilityOverride).filter(
        AvailabilityOverride.id == override_id
    ).first()

    if not override:
        logger.warning(f"Availability override not found - Override ID: {override_id}")
        raise HTTPException(status_code=404, detail="Availability override not found")

    return AvailabilityOverrideResponse.model_validate(override)


@availability_overrides_router.post("/", response_model=AvailabilityOverrideResponse, status_code=201)
async def create_availability_override(
        override_data: AvailabilityOverrideCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Create a new availability override.

    Requires platform admin role.
    """
    logger.info(f"Admin creating availability override - User ID: {current_user.id}, Business ID: {override_data.business_id}, Date: {override_data.date}")

    # Verify business exists
    business = db.query(Business).filter(Business.id == override_data.business_id).first()
    if not business:
        logger.warning(f"Availability override creation failed - Business not found: {override_data.business_id}")
        raise HTTPException(status_code=404, detail="Business not found")

    # Validate time range if both times provided
    if override_data.start_time and override_data.end_time:
        if override_data.start_time >= override_data.end_time:
            logger.warning(f"Availability override creation failed - Invalid time range")
            raise HTTPException(
                status_code=400,
                detail="Start time must be before end time"
            )

    # Check if override already exists for this business and date
    existing = db.query(AvailabilityOverride).filter(
        AvailabilityOverride.business_id == override_data.business_id,
        AvailabilityOverride.date == override_data.date
    ).first()

    if existing:
        logger.warning(f"Availability override creation failed - Duplicate for Business ID: {override_data.business_id}, Date: {override_data.date}")
        raise HTTPException(
            status_code=400,
            detail=f"Override already exists for this business on {override_data.date}"
        )

    override = AvailabilityOverride(
        business_id=override_data.business_id,
        date=override_data.date,
        is_available=override_data.is_available,
        start_time=override_data.start_time,
        end_time=override_data.end_time,
        reason=override_data.reason
    )

    db.add(override)
    db.commit()
    db.refresh(override)

    logger.info(f"Availability override created - Override ID: {override.id}, Business ID: {override_data.business_id}, Created by: {current_user.id}")

    return AvailabilityOverrideResponse.model_validate(override)


@availability_overrides_router.put("/{override_id}", response_model=AvailabilityOverrideResponse)
async def update_availability_override(
        override_id: UUID,
        override_data: AvailabilityOverrideUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Update an existing availability override.

    Requires platform admin role.
    """
    logger.info(f"Admin updating availability override - User ID: {current_user.id}, Override ID: {override_id}")

    override = db.query(AvailabilityOverride).filter(
        AvailabilityOverride.id == override_id
    ).first()

    if not override:
        logger.warning(f"Availability override update failed - Not found: {override_id}")
        raise HTTPException(status_code=404, detail="Availability override not found")

    # Update fields
    update_data = override_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(override, field, value)

    # Validate time range if both times are set
    if override.start_time and override.end_time:
        if override.start_time >= override.end_time:
            logger.warning(f"Availability override update failed - Invalid time range")
            raise HTTPException(
                status_code=400,
                detail="Start time must be before end time"
            )

    db.commit()
    db.refresh(override)

    logger.info(f"Availability override updated - Override ID: {override_id}, Updated by: {current_user.id}")

    return AvailabilityOverrideResponse.model_validate(override)


@availability_overrides_router.delete("/{override_id}", response_model=MessageResponse)
async def delete_availability_override(
        override_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Permanently delete an availability override.

    Requires platform admin role. This action cannot be undone.
    """
    logger.warning(f"Admin deleting availability override (PERMANENT) - User ID: {current_user.id}, Override ID: {override_id}")

    override = db.query(AvailabilityOverride).filter(
        AvailabilityOverride.id == override_id
    ).first()

    if not override:
        logger.warning(f"Availability override deletion failed - Not found: {override_id}")
        raise HTTPException(status_code=404, detail="Availability override not found")

    business_id = str(override.business_id)
    override_date = str(override.date)

    db.delete(override)
    db.commit()

    logger.warning(f"Availability override DELETED permanently - Override ID: {override_id}, Business ID: {business_id}, Deleted by: {current_user.id}")

    return MessageResponse(
        message="Availability override deleted successfully",
        details={
            "override_id": str(override_id),
            "business_id": business_id,
            "date": override_date
        }
    )