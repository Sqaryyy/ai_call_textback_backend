"""
Admin Calendar Integration API
CRUD operations for calendar integrations - requires PLATFORM ADMIN access
Platform admins can manage calendar integrations for ANY business
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional
from datetime import datetime
from uuid import UUID

from app.config.database import get_db
from app.models.auth.user import User
from app.models.business.business import Business
from app.models.appointment.calendar_integration import CalendarIntegration
from app.api.dependencies import require_platform_admin
from app.utils.logger import get_logger
from app.schemas.admin.calendar_integrations import (
    MessageResponse,
    CalendarSyncResponse,
    CalendarSyncRequest,
    CalendarIntegrationListResponse,
    CalendarIntegrationResponse,
    CalendarIntegrationStatsResponse,
    CalendarIntegrationsByBusinessResponse,
    CalendarIntegrationUpdate,
    CalendarIntegrationCreate,
)

logger = get_logger(__name__)

# ============================================================================
# Router
# ============================================================================

router = APIRouter(
    prefix="/calendar-integrations",
    tags=["Admin - Calendar Integrations"]
)


# ============================================================================
# Helper Functions
# ============================================================================

def check_token_validity(integration: CalendarIntegration) -> bool:
    """Check if access token exists and hasn't expired"""
    if not integration.access_token_encrypted:
        return False
    if not integration.token_expires_at:
        return True  # No expiry set, assume valid
    return integration.token_expires_at > datetime.now()


# ============================================================================
# CRUD Endpoints
# ============================================================================

@router.get("/", response_model=CalendarIntegrationListResponse)
async def list_calendar_integrations(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    business_id: Optional[UUID] = Query(None, description="Filter by business ID"),
    provider: Optional[str] = Query(None, description="Filter by provider"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    is_primary: Optional[bool] = Query(None, description="Filter by primary status"),
    has_valid_token: Optional[bool] = Query(None, description="Filter by token validity"),
    from_date: Optional[datetime] = Query(None, description="Filter from date"),
    to_date: Optional[datetime] = Query(None, description="Filter to date"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    List all calendar integrations with filtering and pagination.

    Requires platform admin role.
    """
    logger.info(f"Admin listing calendar integrations - User ID: {current_user.id}")

    query = db.query(CalendarIntegration)

    # Apply filters
    if business_id:
        query = query.filter(CalendarIntegration.business_id == business_id)
    if provider:
        query = query.filter(CalendarIntegration.provider == provider)
    if is_active is not None:
        query = query.filter(CalendarIntegration.is_active == is_active)
    if is_primary is not None:
        query = query.filter(CalendarIntegration.is_primary == is_primary)
    if from_date:
        query = query.filter(CalendarIntegration.created_at >= from_date)
    if to_date:
        query = query.filter(CalendarIntegration.created_at <= to_date)

    # Get all results for token validity filter if needed
    if has_valid_token is not None:
        all_integrations = query.all()
        filtered_integrations = [
            integration for integration in all_integrations
            if check_token_validity(integration) == has_valid_token
        ]
        total = len(filtered_integrations)

        # Calculate pagination
        pages = (total + page_size - 1) // page_size
        offset = (page - 1) * page_size

        integrations = filtered_integrations[offset:offset + page_size]
    else:
        # Get total count
        total = query.count()

        # Calculate pagination
        pages = (total + page_size - 1) // page_size
        offset = (page - 1) * page_size

        # Get paginated results
        integrations = query.order_by(desc(CalendarIntegration.created_at)).offset(offset).limit(page_size).all()

    items = [
        CalendarIntegrationResponse(
            id=integration.id,
            business_id=integration.business_id,
            provider=integration.provider,
            is_active=integration.is_active,
            is_primary=integration.is_primary,
            sync_direction=integration.sync_direction,
            auto_sync_enabled=integration.auto_sync_enabled,
            provider_config=integration.provider_config,
            last_sync_at=integration.last_sync_at,
            last_sync_status=integration.last_sync_status,
            token_expires_at=integration.token_expires_at,
            has_valid_token=check_token_validity(integration),
            created_at=integration.created_at,
            updated_at=integration.updated_at
        )
        for integration in integrations
    ]

    logger.debug(f"Retrieved {len(items)} calendar integrations (total: {total})")

    return CalendarIntegrationListResponse(
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        items=items
    )


@router.get("/stats", response_model=CalendarIntegrationStatsResponse)
async def get_calendar_integration_stats(
    business_id: Optional[UUID] = Query(None, description="Filter stats by business ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    Get comprehensive statistics about calendar integrations.

    Requires platform admin role.
    """
    from datetime import timedelta

    logger.info(f"Admin requesting calendar integration stats - User ID: {current_user.id}")

    query = db.query(CalendarIntegration)
    if business_id:
        query = query.filter(CalendarIntegration.business_id == business_id)

    # Total integrations
    total_integrations = query.count()

    # Active/Inactive breakdown
    active_integrations = query.filter(CalendarIntegration.is_active == True).count()
    inactive_integrations = query.filter(CalendarIntegration.is_active == False).count()

    # Provider breakdown
    provider_counts = {}
    all_integrations = query.all()
    for integration in all_integrations:
        provider_counts[integration.provider] = provider_counts.get(integration.provider, 0) + 1

    # Valid tokens
    integrations_with_valid_tokens = sum(1 for i in all_integrations if check_token_validity(i))

    # Unique businesses
    unique_businesses = db.query(func.count(func.distinct(CalendarIntegration.business_id))).scalar()

    # Time-based stats
    now = datetime.utcnow()
    integrations_last_24h = query.filter(CalendarIntegration.created_at >= now - timedelta(hours=24)).count()
    integrations_last_7d = query.filter(CalendarIntegration.created_at >= now - timedelta(days=7)).count()
    integrations_last_30d = query.filter(CalendarIntegration.created_at >= now - timedelta(days=30)).count()

    logger.debug(f"Calendar stats - Total: {total_integrations}, Valid tokens: {integrations_with_valid_tokens}")

    return CalendarIntegrationStatsResponse(
        total_integrations=total_integrations,
        active_integrations=active_integrations,
        inactive_integrations=inactive_integrations,
        integrations_by_provider=provider_counts,
        integrations_with_valid_tokens=integrations_with_valid_tokens,
        integrations_last_24h=integrations_last_24h,
        integrations_last_7d=integrations_last_7d,
        integrations_last_30d=integrations_last_30d,
        unique_businesses=unique_businesses
    )


@router.get("/by-business", response_model=List[CalendarIntegrationsByBusinessResponse])
async def get_calendar_integrations_by_business(
    from_date: Optional[datetime] = Query(None, description="Filter from date"),
    to_date: Optional[datetime] = Query(None, description="Filter to date"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    Get calendar integration statistics grouped by business.

    Requires platform admin role.
    """
    logger.info(f"Admin requesting calendar integrations by business - User ID: {current_user.id}")

    query = db.query(
        CalendarIntegration.business_id,
        func.count(CalendarIntegration.id).label('total_integrations'),
        func.sum(func.case((CalendarIntegration.is_active == True, 1), else_=0)).label('active_integrations'),
        func.max(CalendarIntegration.last_sync_at).label('last_sync_at')
    )

    if from_date:
        query = query.filter(CalendarIntegration.created_at >= from_date)
    if to_date:
        query = query.filter(CalendarIntegration.created_at <= to_date)

    results = query.group_by(CalendarIntegration.business_id).all()

    response_list = []
    for result in results:
        # Get provider breakdown and other details for this business
        business_integrations = db.query(CalendarIntegration).filter(
            CalendarIntegration.business_id == result.business_id
        ).all()

        provider_counts = {}
        valid_tokens = 0
        primary_provider = None

        for integration in business_integrations:
            provider_counts[integration.provider] = provider_counts.get(integration.provider, 0) + 1
            if check_token_validity(integration):
                valid_tokens += 1
            if integration.is_primary:
                primary_provider = integration.provider

        response_list.append(
            CalendarIntegrationsByBusinessResponse(
                business_id=str(result.business_id),
                total_integrations=result.total_integrations,
                active_integrations=result.active_integrations,
                integrations_by_provider=provider_counts,
                valid_tokens=valid_tokens,
                primary_calendar_provider=primary_provider,
                last_sync_at=result.last_sync_at.isoformat() if result.last_sync_at else None
            )
        )

    logger.debug(f"Retrieved stats for {len(response_list)} businesses")

    return response_list


@router.get("/{integration_id}", response_model=CalendarIntegrationResponse)
async def get_calendar_integration(
    integration_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    Get details of a specific calendar integration.

    Requires platform admin role.
    """
    integration = db.query(CalendarIntegration).filter(
        CalendarIntegration.id == integration_id
    ).first()

    if not integration:
        logger.warning(f"Calendar integration not found - Integration ID: {integration_id}")
        raise HTTPException(status_code=404, detail="Calendar integration not found")

    return CalendarIntegrationResponse(
        id=integration.id,
        business_id=integration.business_id,
        provider=integration.provider,
        is_active=integration.is_active,
        is_primary=integration.is_primary,
        sync_direction=integration.sync_direction,
        auto_sync_enabled=integration.auto_sync_enabled,
        provider_config=integration.provider_config,
        last_sync_at=integration.last_sync_at,
        last_sync_status=integration.last_sync_status,
        token_expires_at=integration.token_expires_at,
        has_valid_token=check_token_validity(integration),
        created_at=integration.created_at,
        updated_at=integration.updated_at
    )


@router.post("/", response_model=CalendarIntegrationResponse, status_code=201)
async def create_calendar_integration(
    integration_data: CalendarIntegrationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    Create a new calendar integration.

    Requires platform admin role.
    Note: This creates the record. OAuth flow must be handled separately.
    """
    logger.info(f"Admin creating calendar integration - User ID: {current_user.id}, Business ID: {integration_data.business_id}, Provider: {integration_data.provider}")

    # Verify business exists
    business = db.query(Business).filter(Business.id == integration_data.business_id).first()
    if not business:
        logger.warning(f"Calendar integration creation failed - Business not found: {integration_data.business_id}")
        raise HTTPException(status_code=404, detail="Business not found")

    # Validate provider
    valid_providers = ["google", "calendly", "outlook", "cal.com"]
    if integration_data.provider not in valid_providers:
        logger.warning(f"Calendar integration creation failed - Invalid provider: {integration_data.provider}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid provider. Must be one of: {', '.join(valid_providers)}"
        )

    # Validate sync_direction
    valid_directions = ["read_only", "write_only", "bidirectional"]
    if integration_data.sync_direction not in valid_directions:
        logger.warning(f"Calendar integration creation failed - Invalid sync direction: {integration_data.sync_direction}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sync_direction. Must be one of: {', '.join(valid_directions)}"
        )

    # If this is set as primary, unset other primary integrations for this business
    if integration_data.is_primary:
        db.query(CalendarIntegration).filter(
            CalendarIntegration.business_id == integration_data.business_id,
            CalendarIntegration.is_primary == True
        ).update({"is_primary": False})
        logger.debug(f"Unset other primary calendars for business {integration_data.business_id}")

    integration = CalendarIntegration(
        business_id=integration_data.business_id,
        provider=integration_data.provider,
        is_active=integration_data.is_active,
        is_primary=integration_data.is_primary,
        sync_direction=integration_data.sync_direction,
        auto_sync_enabled=integration_data.auto_sync_enabled,
        provider_config=integration_data.provider_config or {}
    )

    db.add(integration)
    db.commit()
    db.refresh(integration)

    logger.info(f"Calendar integration created - Integration ID: {integration.id}, Provider: {integration_data.provider}, Created by: {current_user.id}")

    return CalendarIntegrationResponse(
        id=integration.id,
        business_id=integration.business_id,
        provider=integration.provider,
        is_active=integration.is_active,
        is_primary=integration.is_primary,
        sync_direction=integration.sync_direction,
        auto_sync_enabled=integration.auto_sync_enabled,
        provider_config=integration.provider_config,
        last_sync_at=integration.last_sync_at,
        last_sync_status=integration.last_sync_status,
        token_expires_at=integration.token_expires_at,
        has_valid_token=check_token_validity(integration),
        created_at=integration.created_at,
        updated_at=integration.updated_at
    )


@router.put("/{integration_id}", response_model=CalendarIntegrationResponse)
async def update_calendar_integration(
    integration_id: UUID,
    integration_data: CalendarIntegrationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    Update an existing calendar integration.

    Requires platform admin role.
    """
    logger.info(f"Admin updating calendar integration - User ID: {current_user.id}, Integration ID: {integration_id}")

    integration = db.query(CalendarIntegration).filter(
        CalendarIntegration.id == integration_id
    ).first()

    if not integration:
        logger.warning(f"Calendar integration update failed - Not found: {integration_id}")
        raise HTTPException(status_code=404, detail="Calendar integration not found")

    # Validate sync_direction if provided
    if integration_data.sync_direction:
        valid_directions = ["read_only", "write_only", "bidirectional"]
        if integration_data.sync_direction not in valid_directions:
            logger.warning(f"Calendar integration update failed - Invalid sync direction: {integration_data.sync_direction}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid sync_direction. Must be one of: {', '.join(valid_directions)}"
            )

    # If setting as primary, unset other primary integrations for this business
    if integration_data.is_primary:
        db.query(CalendarIntegration).filter(
            CalendarIntegration.business_id == integration.business_id,
            CalendarIntegration.is_primary == True,
            CalendarIntegration.id != integration_id
        ).update({"is_primary": False})
        logger.debug(f"Set as primary calendar for business {integration.business_id}")

    # Update fields
    update_data = integration_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(integration, field, value)

    integration.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(integration)

    logger.info(f"Calendar integration updated - Integration ID: {integration_id}, Updated by: {current_user.id}")

    return CalendarIntegrationResponse(
        id=integration.id,
        business_id=integration.business_id,
        provider=integration.provider,
        is_active=integration.is_active,
        is_primary=integration.is_primary,
        sync_direction=integration.sync_direction,
        auto_sync_enabled=integration.auto_sync_enabled,
        provider_config=integration.provider_config,
        last_sync_at=integration.last_sync_at,
        last_sync_status=integration.last_sync_status,
        token_expires_at=integration.token_expires_at,
        has_valid_token=check_token_validity(integration),
        created_at=integration.created_at,
        updated_at=integration.updated_at
    )


@router.delete("/{integration_id}", response_model=MessageResponse)
async def delete_calendar_integration(
    integration_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    Permanently delete a calendar integration.

    Requires platform admin role. This action cannot be undone.
    """
    logger.warning(f"Admin deleting calendar integration (PERMANENT) - User ID: {current_user.id}, Integration ID: {integration_id}")

    integration = db.query(CalendarIntegration).filter(
        CalendarIntegration.id == integration_id
    ).first()

    if not integration:
        logger.warning(f"Calendar integration deletion failed - Not found: {integration_id}")
        raise HTTPException(status_code=404, detail="Calendar integration not found")

    provider = integration.provider
    business_id = str(integration.business_id)

    db.delete(integration)
    db.commit()

    logger.warning(f"Calendar integration DELETED permanently - Integration ID: {integration_id}, Provider: {provider}, Deleted by: {current_user.id}")

    return MessageResponse(
        message="Calendar integration deleted successfully",
        details={
            "integration_id": str(integration_id),
            "business_id": business_id,
            "provider": provider
        }
    )


@router.post("/{integration_id}/toggle", response_model=CalendarIntegrationResponse)
async def toggle_calendar_integration(
    integration_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    Toggle active status of a calendar integration.

    Requires platform admin role.
    """
    logger.info(f"Admin toggling calendar integration - User ID: {current_user.id}, Integration ID: {integration_id}")

    integration = db.query(CalendarIntegration).filter(
        CalendarIntegration.id == integration_id
    ).first()

    if not integration:
        logger.warning(f"Calendar integration toggle failed - Not found: {integration_id}")
        raise HTTPException(status_code=404, detail="Calendar integration not found")

    old_status = integration.is_active
    integration.is_active = not integration.is_active
    integration.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(integration)

    logger.info(f"Calendar integration toggled - Integration ID: {integration_id}, {old_status} → {integration.is_active}, By: {current_user.id}")

    return CalendarIntegrationResponse(
        id=integration.id,
        business_id=integration.business_id,
        provider=integration.provider,
        is_active=integration.is_active,
        is_primary=integration.is_primary,
        sync_direction=integration.sync_direction,
        auto_sync_enabled=integration.auto_sync_enabled,
        provider_config=integration.provider_config,
        last_sync_at=integration.last_sync_at,
        last_sync_status=integration.last_sync_status,
        token_expires_at=integration.token_expires_at,
        has_valid_token=check_token_validity(integration),
        created_at=integration.created_at,
        updated_at=integration.updated_at
    )


@router.post("/{integration_id}/set-primary", response_model=CalendarIntegrationResponse)
async def set_primary_calendar(
    integration_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    Set this integration as the primary calendar for its business.

    Requires platform admin role.
    """
    logger.info(f"Admin setting primary calendar - User ID: {current_user.id}, Integration ID: {integration_id}")

    integration = db.query(CalendarIntegration).filter(
        CalendarIntegration.id == integration_id
    ).first()

    if not integration:
        logger.warning(f"Set primary calendar failed - Not found: {integration_id}")
        raise HTTPException(status_code=404, detail="Calendar integration not found")

    # Unset all other primary calendars for this business
    db.query(CalendarIntegration).filter(
        CalendarIntegration.business_id == integration.business_id,
        CalendarIntegration.is_primary == True
    ).update({"is_primary": False})

    # Set this as primary
    integration.is_primary = True
    integration.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(integration)

    logger.info(f"Primary calendar set - Integration ID: {integration_id}, Provider: {integration.provider}, By: {current_user.id}")

    return CalendarIntegrationResponse(
        id=integration.id,
        business_id=integration.business_id,
        provider=integration.provider,
        is_active=integration.is_active,
        is_primary=integration.is_primary,
        sync_direction=integration.sync_direction,
        auto_sync_enabled=integration.auto_sync_enabled,
        provider_config=integration.provider_config,
        last_sync_at=integration.last_sync_at,
        last_sync_status=integration.last_sync_status,
        token_expires_at=integration.token_expires_at,
        has_valid_token=check_token_validity(integration),
        created_at=integration.created_at,
        updated_at=integration.updated_at
    )


@router.post("/{integration_id}/sync", response_model=CalendarSyncResponse)
async def trigger_calendar_sync(
    integration_id: UUID,
    sync_request: CalendarSyncRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    Trigger a manual sync for this calendar integration.

    Requires platform admin role.
    Note: Actual sync logic should be implemented in a background task/service.
    """
    logger.info(f"Admin triggering calendar sync - User ID: {current_user.id}, Integration ID: {integration_id}, Force full: {sync_request.force_full_sync}")

    integration = db.query(CalendarIntegration).filter(
        CalendarIntegration.id == integration_id
    ).first()

    if not integration:
        logger.warning(f"Calendar sync failed - Integration not found: {integration_id}")
        raise HTTPException(status_code=404, detail="Calendar integration not found")

    if not integration.is_active:
        logger.warning(f"Calendar sync failed - Integration inactive: {integration_id}")
        raise HTTPException(status_code=400, detail="Calendar integration is not active")

    if not check_token_validity(integration):
        logger.warning(f"Calendar sync failed - Invalid token: {integration_id}")
        raise HTTPException(
            status_code=400,
            detail="Calendar integration has invalid or expired token. Please re-authenticate."
        )

    # TODO: Implement actual sync logic here or trigger background task
    # For now, just update the sync timestamp
    sync_started = datetime.utcnow()
    integration.last_sync_at = sync_started
    integration.last_sync_status = "success"
    integration.updated_at = datetime.utcnow()

    db.commit()

    logger.info(f"Calendar sync completed - Integration ID: {integration_id}, Status: success, Triggered by: {current_user.id}")

    return CalendarSyncResponse(
        integration_id=integration.id,
        sync_status="success",
        events_synced=0,  # TODO: Return actual count from sync
        errors=[],
        sync_started_at=sync_started,
        sync_completed_at=datetime.utcnow()
    )