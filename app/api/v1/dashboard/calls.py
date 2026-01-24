# ============================================================================
# FILE: app/api/v1/dashboard/calls.py
# Session authenticated endpoints - thin HTTP layer
# UPDATED: Added comprehensive logging with user audit trail
# ============================================================================
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
from uuid import UUID

from app.config.database import get_db
from app.models.auth.user import User
from app.api.dependencies import get_current_user
from app.services.call.call_service import CallService
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/calls", tags=["dashboard-calls"])


@router.get("")
async def list_call_events(
        start_date: Optional[datetime] = Query(None, description="Filter calls after this date (ISO 8601)"),
        end_date: Optional[datetime] = Query(None, description="Filter calls before this date (ISO 8601)"),
        call_status: Optional[str] = Query(None, description="Filter by call status"),
        caller_phone: Optional[str] = Query(None, description="Filter by caller phone number"),
        skip: int = Query(0, ge=0, description="Number of records to skip"),
        limit: int = Query(50, ge=1, le=100, description="Number of records to return"),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Get a list of all call events for your business.
    Requires authenticated session.
    """
    if not current_user.business_id:
        logger.warning(
            f"User {current_user.id} attempted to list calls without active business"
        )
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    # Build filter description for logging
    filters = []
    if start_date:
        filters.append(f"start_date={start_date.date()}")
    if end_date:
        filters.append(f"end_date={end_date.date()}")
    if call_status:
        filters.append(f"status={call_status}")
    if caller_phone:
        # Mask phone number for privacy (show only last 4 digits)
        masked_phone = f"***{caller_phone[-4:]}" if len(caller_phone) >= 4 else "***"
        filters.append(f"phone={masked_phone}")

    filter_str = ", ".join(filters) if filters else "no filters"

    logger.info(
        f"User {current_user.id} listing calls for business {current_user.business_id} - "
        f"Filters: {filter_str}, Skip: {skip}, Limit: {limit}"
    )

    result = CallService.list_calls(
        db=db,
        business_id=current_user.business_id,
        start_date=start_date,
        end_date=end_date,
        call_status=call_status,
        caller_phone=caller_phone,
        skip=skip,
        limit=limit
    )

    call_count = len(result.get('calls', []))
    total_count = result.get('total', 0)

    logger.info(
        f"Returned {call_count} calls (Total: {total_count}) for business {current_user.business_id}"
    )

    return result


@router.get("/{call_id}")
async def get_call_event(
        call_id: UUID = Path(..., description="The call event ID"),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific call event.
    Requires authenticated session.
    """
    if not current_user.business_id:
        logger.warning(
            f"User {current_user.id} attempted to get call details without active business"
        )
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    logger.info(
        f"User {current_user.id} requesting call details - "
        f"Call ID: {call_id}, Business: {current_user.business_id}"
    )

    result = CallService.get_call_by_id(
        db=db,
        business_id=current_user.business_id,
        call_id=call_id
    )

    if not result:
        logger.warning(
            f"Call {call_id} not found or access denied - "
            f"Business: {current_user.business_id}, User: {current_user.id}"
        )
        raise HTTPException(
            status_code=404,
            detail="Call event not found or you don't have access to it"
        )

    logger.info(
        f"Call details retrieved - "
        f"Call ID: {call_id}, Status: {result.get('call_status')}, "
        f"Duration: {result.get('duration_seconds')}s"
    )

    return result


@router.get("/stats/summary")
async def get_call_stats(
        start_date: Optional[datetime] = Query(None, description="Stats from this date"),
        end_date: Optional[datetime] = Query(None, description="Stats until this date"),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Get summary statistics about your call events.
    Requires authenticated session.
    """
    if not current_user.business_id:
        logger.warning(
            f"User {current_user.id} attempted to get call stats without active business"
        )
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    date_range = "all time"
    if start_date and end_date:
        date_range = f"{start_date.date()} to {end_date.date()}"
    elif start_date:
        date_range = f"from {start_date.date()}"
    elif end_date:
        date_range = f"until {end_date.date()}"

    logger.info(
        f"User {current_user.id} requesting call statistics for business {current_user.business_id} - "
        f"Date range: {date_range}"
    )

    result = CallService.get_call_stats(
        db=db,
        business_id=current_user.business_id,
        start_date=start_date,
        end_date=end_date
    )

    logger.info(
        f"Call statistics retrieved for business {current_user.business_id} - "
        f"Total calls: {result.get('total_calls', 0)}, "
        f"Avg duration: {result.get('avg_duration_seconds', 0)}s"
    )

    return result


@router.get("/search/by-phone")
async def search_calls_by_phone(
        phone: str = Query(..., description="Phone number to search for", min_length=10),
        skip: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Search for all calls from a specific phone number.
    Requires authenticated session.
    """
    if not current_user.business_id:
        logger.warning(
            f"User {current_user.id} attempted to search calls by phone without active business"
        )
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    # Mask phone number for privacy logging (show only last 4 digits)
    masked_phone = f"***{phone[-4:]}" if len(phone) >= 4 else "***"

    logger.info(
        f"User {current_user.id} searching calls by phone for business {current_user.business_id} - "
        f"Phone: {masked_phone}, Skip: {skip}, Limit: {limit}"
    )

    result = CallService.search_calls_by_phone(
        db=db,
        business_id=current_user.business_id,
        phone=phone,
        skip=skip,
        limit=limit
    )

    call_count = len(result.get('calls', []))
    total_count = result.get('total', 0)

    logger.info(
        f"Phone search completed - Found {call_count} calls (Total: {total_count}) "
        f"for phone {masked_phone} in business {current_user.business_id}"
    )

    return result