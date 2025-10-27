
# ============================================================================
# FILE 3: app/api/v1/dashboard/calls.py
# Session authenticated endpoints - thin HTTP layer
# ============================================================================
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
from uuid import UUID

from app.config.database import get_db
from app.models.user import User
from app.api.dependencies import get_current_user
from app.services.call.call_service import CallService

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
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    return CallService.list_calls(
        db=db,
        business_id=current_user.business_id,
        start_date=start_date,
        end_date=end_date,
        call_status=call_status,
        caller_phone=caller_phone,
        skip=skip,
        limit=limit
    )


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
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    result = CallService.get_call_by_id(
        db=db,
        business_id=current_user.business_id,
        call_id=call_id
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail="Call event not found or you don't have access to it"
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
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    return CallService.get_call_stats(
        db=db,
        business_id=current_user.business_id,
        start_date=start_date,
        end_date=end_date
    )


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
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    return CallService.search_calls_by_phone(
        db=db,
        business_id=current_user.business_id,
        phone=phone,
        skip=skip,
        limit=limit
    )