# ============================================================================
# FILE: app/api/v1/admin/call_events.py
# Platform admin endpoints for managing call events
# CRITICAL: Contains sensitive PII (phone numbers, recordings, caller info)
# ============================================================================
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Optional, List
from uuid import UUID
from datetime import datetime

from app.api.dependencies import get_db, require_platform_admin
from app.models.auth.user import User
from app.models.conversation.call_event import CallEvent
from app.utils.logger import get_logger
from app.schemas.admin.call_events import (
    MessageResponse,
    CallEventResponse,
    CallEventStatsResponse,
    CallEventListResponse,
    CallEventsByBusinessResponse
)
logger = get_logger(__name__)

router = APIRouter(prefix="/call-events", tags=["Admin - Call Events"])


# ============================================================================
# Admin Call Event Endpoints
# ============================================================================

@router.get("/", response_model=CallEventListResponse)
async def list_call_events(
        page: int = Query(1, ge=1, description="Page number"),
        page_size: int = Query(50, ge=1, le=100, description="Items per page"),
        business_id: Optional[UUID] = Query(None, description="Filter by business ID"),
        call_status: Optional[str] = Query(None, description="Filter by call status"),
        direction: Optional[str] = Query(None, description="Filter by direction (inbound/outbound)"),
        caller_phone: Optional[str] = Query(None, description="Filter by caller phone"),
        twilio_call_sid: Optional[str] = Query(None, description="Filter by Twilio Call SID"),
        from_date: Optional[datetime] = Query(None, description="Filter from date"),
        to_date: Optional[datetime] = Query(None, description="Filter to date"),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    List all call events with filtering and pagination.

    Requires platform admin role.
    """
    # Log admin access WITHOUT phone numbers
    logger.info(f"Admin listing call events - User ID: {current_user.id}, Page: {page}")

    query = db.query(CallEvent)

    # Apply filters
    if business_id:
        query = query.filter(CallEvent.business_id == business_id)
    if call_status:
        query = query.filter(CallEvent.call_status == call_status)
    if direction:
        query = query.filter(CallEvent.direction == direction)
    if caller_phone:
        # Filter by phone but don't log the actual number
        query = query.filter(CallEvent.caller_phone == caller_phone)
        logger.debug("Filtering by specific caller phone number")
    if twilio_call_sid:
        query = query.filter(CallEvent.twilio_call_sid == twilio_call_sid)
    if from_date:
        query = query.filter(CallEvent.created_at >= from_date)
    if to_date:
        query = query.filter(CallEvent.created_at <= to_date)

    # Get total count
    total = query.count()

    # Calculate pagination
    pages = (total + page_size - 1) // page_size
    offset = (page - 1) * page_size

    # Get paginated results
    call_events = query.order_by(desc(CallEvent.created_at)).offset(offset).limit(page_size).all()

    items = [
        CallEventResponse(
            id=str(event.id),
            business_id=str(event.business_id),
            twilio_call_sid=event.twilio_call_sid,
            caller_phone=event.caller_phone,
            business_phone=event.business_phone,
            call_status=event.call_status,
            direction=event.direction,
            caller_location=event.caller_location or {},
            caller_name=event.caller_name,
            duration=event.duration,
            recording_url=event.recording_url,
            call_metadata=event.call_metadata or {},
            created_at=event.created_at.isoformat(),
            updated_at=event.updated_at.isoformat()
        )
        for event in call_events
    ]

    # Log counts WITHOUT any PII
    logger.debug(f"Retrieved {len(items)} call events (total: {total})")

    return CallEventListResponse(
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        items=items
    )


@router.get("/stats", response_model=CallEventStatsResponse)
async def get_call_event_stats(
        business_id: Optional[UUID] = Query(None, description="Filter stats by business ID"),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Get comprehensive statistics about call events.

    Requires platform admin role.
    """
    from datetime import timedelta

    logger.info(f"Admin requesting call event stats - User ID: {current_user.id}")

    query = db.query(CallEvent)
    if business_id:
        query = query.filter(CallEvent.business_id == business_id)

    # Total calls
    total_calls = query.count()

    # Direction breakdown
    inbound_calls = query.filter(CallEvent.direction == "inbound").count()
    outbound_calls = query.filter(CallEvent.direction == "outbound").count()

    # Status breakdown
    completed_calls = query.filter(CallEvent.call_status == "completed").count()
    failed_calls = query.filter(CallEvent.call_status == "failed").count()

    # Duration stats (convert string duration to int)
    calls_with_duration = query.filter(CallEvent.duration.isnot(None)).all()
    total_duration = sum(int(call.duration) for call in calls_with_duration if call.duration.isdigit())
    avg_duration = total_duration / len(calls_with_duration) if calls_with_duration else 0

    # Recordings
    calls_with_recordings = query.filter(CallEvent.recording_url.isnot(None)).count()

    # Unique businesses
    unique_businesses = db.query(func.count(func.distinct(CallEvent.business_id))).scalar()

    # Time-based stats
    now = datetime.utcnow()
    calls_last_24h = query.filter(CallEvent.created_at >= now - timedelta(hours=24)).count()
    calls_last_7d = query.filter(CallEvent.created_at >= now - timedelta(days=7)).count()
    calls_last_30d = query.filter(CallEvent.created_at >= now - timedelta(days=30)).count()

    logger.debug(f"Call stats - Total: {total_calls}, Completed: {completed_calls}, Failed: {failed_calls}")

    return CallEventStatsResponse(
        total_calls=total_calls,
        inbound_calls=inbound_calls,
        outbound_calls=outbound_calls,
        completed_calls=completed_calls,
        failed_calls=failed_calls,
        total_duration_seconds=total_duration,
        avg_duration_seconds=round(avg_duration, 2),
        calls_with_recordings=calls_with_recordings,
        unique_businesses=unique_businesses,
        calls_last_24h=calls_last_24h,
        calls_last_7d=calls_last_7d,
        calls_last_30d=calls_last_30d
    )


@router.get("/by-business", response_model=List[CallEventsByBusinessResponse])
async def get_call_events_by_business(
        from_date: Optional[datetime] = Query(None, description="Filter from date"),
        to_date: Optional[datetime] = Query(None, description="Filter to date"),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Get call event statistics grouped by business.

    Requires platform admin role.
    """
    logger.info(f"Admin requesting call events by business - User ID: {current_user.id}")

    query = db.query(
        CallEvent.business_id,
        func.count(CallEvent.id).label('total_calls'),
        func.sum(func.case((CallEvent.direction == 'inbound', 1), else_=0)).label('inbound_calls'),
        func.sum(func.case((CallEvent.direction == 'outbound', 1), else_=0)).label('outbound_calls'),
        func.sum(func.case((CallEvent.call_status == 'completed', 1), else_=0)).label('completed_calls'),
        func.sum(func.case((CallEvent.call_status == 'failed', 1), else_=0)).label('failed_calls'),
        func.max(CallEvent.created_at).label('last_call_at')
    )

    if from_date:
        query = query.filter(CallEvent.created_at >= from_date)
    if to_date:
        query = query.filter(CallEvent.created_at <= to_date)

    results = query.group_by(CallEvent.business_id).all()

    logger.debug(f"Retrieved call stats for {len(results)} businesses")

    return [
        CallEventsByBusinessResponse(
            business_id=str(result.business_id),
            total_calls=result.total_calls,
            inbound_calls=result.inbound_calls,
            outbound_calls=result.outbound_calls,
            completed_calls=result.completed_calls,
            failed_calls=result.failed_calls,
            total_duration_seconds=0,  # Can be calculated if needed
            last_call_at=result.last_call_at.isoformat()
        )
        for result in results
    ]


@router.get("/{call_event_id}", response_model=CallEventResponse)
async def get_call_event(
        call_event_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Get details of a specific call event.

    Requires platform admin role.
    """
    # Log access with event ID only (not phone numbers)
    logger.info(f"Admin viewing call event - User ID: {current_user.id}, Call Event ID: {call_event_id}")

    call_event = db.query(CallEvent).filter(CallEvent.id == call_event_id).first()

    if not call_event:
        logger.warning(f"Call event not found - Call Event ID: {call_event_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Call event not found"
        )

    return CallEventResponse(
        id=str(call_event.id),
        business_id=str(call_event.business_id),
        twilio_call_sid=call_event.twilio_call_sid,
        caller_phone=call_event.caller_phone,
        business_phone=call_event.business_phone,
        call_status=call_event.call_status,
        direction=call_event.direction,
        caller_location=call_event.caller_location or {},
        caller_name=call_event.caller_name,
        duration=call_event.duration,
        recording_url=call_event.recording_url,
        call_metadata=call_event.call_metadata or {},
        created_at=call_event.created_at.isoformat(),
        updated_at=call_event.updated_at.isoformat()
    )


@router.delete("/{call_event_id}", response_model=MessageResponse)
async def delete_call_event(
        call_event_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Permanently delete a call event.

    Requires platform admin role. This action cannot be undone.
    WARNING: Deletes sensitive PII (phone numbers, recordings, caller info).
    """
    logger.warning(
        f"Admin deleting call event (PERMANENT) - User ID: {current_user.id}, Call Event ID: {call_event_id}")

    call_event = db.query(CallEvent).filter(CallEvent.id == call_event_id).first()

    if not call_event:
        logger.warning(f"Call event deletion failed - Not found: {call_event_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Call event not found"
        )

    # Store Twilio SID for audit (not phone number)
    twilio_sid = call_event.twilio_call_sid

    db.delete(call_event)
    db.commit()

    # Log deletion WITHOUT phone numbers
    logger.warning(
        f"Call event DELETED permanently - Call Event ID: {call_event_id}, Twilio SID: {twilio_sid}, Deleted by: {current_user.id}")

    return MessageResponse(
        message="Call event deleted successfully",
        details={
            "call_event_id": str(call_event_id),
            "twilio_call_sid": twilio_sid
        }
    )