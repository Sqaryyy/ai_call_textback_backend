# ============================================================================
# FILE 3: app/api/v1/dashboard/appointments.py
# Session authenticated endpoints - thin HTTP layer
# UPDATED: Use active_business_id instead of business_id
# UPDATED: Added comprehensive logging with PII protection
# ============================================================================
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session
from datetime import date
from typing import Optional
from uuid import UUID

from app.config.database import get_db
from app.models.auth.user import User
from app.api.dependencies import get_current_user
from app.services.appointment.appointment_query_service import AppointmentService
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["dashboard-appointments"])


def mask_phone_number(phone: str) -> str:
    """
    Mask phone number for logging - only show last 4 digits.
    Example: "+1234567890" -> "****7890"
    """
    if not phone or len(phone) < 4:
        return "****"
    return f"****{phone[-4:]}"


@router.get("")
async def list_appointments(
        start_date: Optional[date] = Query(None, description="Filter appointments on or after this date"),
        end_date: Optional[date] = Query(None, description="Filter appointments on or before this date"),
        status: Optional[str] = Query(None,
                                      description="Filter by status (scheduled, confirmed, cancelled, completed, no_show)"),
        customer_phone: Optional[str] = Query(None, description="Filter by customer phone number"),
        service_type: Optional[str] = Query(None, description="Filter by service type"),
        skip: int = Query(0, ge=0, description="Number of records to skip"),
        limit: int = Query(50, ge=1, le=100, description="Number of records to return"),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Get a list of all appointments for your business.
    Requires authenticated session.
    """
    if not current_user.active_business_id:
        logger.warning(
            f"User {current_user.id} attempted to list appointments without active business"
        )
        raise HTTPException(
            status_code=403,
            detail="No active business selected. Please select a business first."
        )

    # Build filter description for logging
    filters = []
    if start_date:
        filters.append(f"start_date={start_date}")
    if end_date:
        filters.append(f"end_date={end_date}")
    if status:
        filters.append(f"status={status}")
    if customer_phone:
        filters.append(f"phone={mask_phone_number(customer_phone)}")
    if service_type:
        filters.append(f"service_type={service_type}")

    filter_str = f" with filters: {', '.join(filters)}" if filters else ""
    logger.info(
        f"User {current_user.id} listing appointments for business {current_user.active_business_id}"
        f"{filter_str} - Pagination: skip={skip}, limit={limit}"
    )

    result = AppointmentService.list_appointments(
        db=db,
        business_id=current_user.active_business_id,
        start_date=start_date,
        end_date=end_date,
        status=status,
        customer_phone=customer_phone,
        service_type=service_type,
        skip=skip,
        limit=limit
    )

    # Log result count (safe metadata)
    count = len(result) if isinstance(result, list) else result.get('count', 'unknown')
    logger.info(f"Returned {count} appointments")

    return result


@router.get("/upcoming/today")
async def get_todays_appointments(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Get all appointments scheduled for today.
    Requires authenticated session.
    """
    if not current_user.active_business_id:
        logger.warning(
            f"User {current_user.id} attempted to view today's appointments without active business"
        )
        raise HTTPException(
            status_code=403,
            detail="No active business selected. Please select a business first."
        )

    logger.info(
        f"User {current_user.id} viewing today's appointments for business {current_user.active_business_id}"
    )

    result = AppointmentService.get_todays_appointments(
        db=db,
        business_id=current_user.active_business_id
    )

    count = len(result) if isinstance(result, list) else result.get('count', 'unknown')
    logger.info(f"Returned {count} appointments for today")

    return result


@router.get("/upcoming/week")
async def get_week_appointments(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Get all appointments scheduled for the next 7 days.
    Requires authenticated session.
    """
    if not current_user.active_business_id:
        logger.warning(
            f"User {current_user.id} attempted to view week appointments without active business"
        )
        raise HTTPException(
            status_code=403,
            detail="No active business selected. Please select a business first."
        )

    logger.info(
        f"User {current_user.id} viewing week appointments for business {current_user.active_business_id}"
    )

    result = AppointmentService.get_week_appointments(
        db=db,
        business_id=current_user.active_business_id
    )

    count = len(result) if isinstance(result, list) else result.get('count', 'unknown')
    logger.info(f"Returned {count} appointments for the week")

    return result


@router.get("/search/by-phone")
async def search_appointments_by_phone(
        phone: str = Query(..., description="Phone number to search for", min_length=10),
        skip: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Search for all appointments for a specific phone number.
    Requires authenticated session.
    """
    if not current_user.active_business_id:
        logger.warning(
            f"User {current_user.id} attempted to search appointments by phone without active business"
        )
        raise HTTPException(
            status_code=403,
            detail="No active business selected. Please select a business first."
        )

    logger.info(
        f"User {current_user.id} searching appointments by phone {mask_phone_number(phone)} "
        f"for business {current_user.active_business_id} - Pagination: skip={skip}, limit={limit}"
    )

    result = AppointmentService.search_appointments_by_phone(
        db=db,
        business_id=current_user.active_business_id,
        phone=phone,
        skip=skip,
        limit=limit
    )

    count = len(result) if isinstance(result, list) else result.get('count', 'unknown')
    logger.info(f"Phone search returned {count} appointments")

    return result


@router.get("/stats/summary")
async def get_appointment_stats(
        start_date: Optional[date] = Query(None, description="Stats from this date"),
        end_date: Optional[date] = Query(None, description="Stats until this date"),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Get summary statistics about your appointments.
    Requires authenticated session.
    """
    if not current_user.active_business_id:
        logger.warning(
            f"User {current_user.id} attempted to view appointment stats without active business"
        )
        raise HTTPException(
            status_code=403,
            detail="No active business selected. Please select a business first."
        )

    date_range = ""
    if start_date or end_date:
        date_parts = []
        if start_date:
            date_parts.append(f"from {start_date}")
        if end_date:
            date_parts.append(f"to {end_date}")
        date_range = f" - Date range: {' '.join(date_parts)}"

    logger.info(
        f"User {current_user.id} requesting appointment statistics for business "
        f"{current_user.active_business_id}{date_range}"
    )

    result = AppointmentService.get_appointment_stats(
        db=db,
        business_id=current_user.active_business_id,
        start_date=start_date,
        end_date=end_date
    )

    # Log aggregated stats (safe metadata, no PII)
    if isinstance(result, dict):
        logger.info(
            f"Stats summary: {result.get('total', 0)} total appointments, "
            f"{result.get('scheduled', 0)} scheduled, "
            f"{result.get('completed', 0)} completed"
        )

    return result


@router.get("/{appointment_id}")
async def get_appointment(
        appointment_id: UUID = Path(..., description="The appointment ID"),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific appointment.
    Requires authenticated session.
    """
    if not current_user.active_business_id:
        logger.warning(
            f"User {current_user.id} attempted to view appointment {appointment_id} without active business"
        )
        raise HTTPException(
            status_code=403,
            detail="No active business selected. Please select a business first."
        )

    logger.info(
        f"User {current_user.id} viewing appointment {appointment_id} "
        f"for business {current_user.active_business_id}"
    )

    result = AppointmentService.get_appointment_by_id(
        db=db,
        business_id=current_user.active_business_id,
        appointment_id=appointment_id
    )

    if not result:
        logger.warning(
            f"Appointment {appointment_id} not found or user {current_user.id} lacks access - "
            f"Business ID: {current_user.active_business_id}"
        )
        raise HTTPException(
            status_code=404,
            detail="Appointment not found or you don't have access to it"
        )

    logger.debug(
        f"Retrieved appointment {appointment_id} - "
        f"Status: {result.get('status', 'unknown')}"
    )

    return result