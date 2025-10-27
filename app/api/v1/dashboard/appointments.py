
# ============================================================================
# FILE 3: app/api/v1/dashboard/appointments.py
# Session authenticated endpoints - thin HTTP layer
# ============================================================================
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session
from datetime import date
from typing import Optional
from uuid import UUID

from app.config.database import get_db
from app.models.user import User
from app.api.dependencies import get_current_user
from app.services.appointment.appointment_query_service import AppointmentService

router = APIRouter(prefix="/appointments", tags=["dashboard-appointments"])


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
    if not current_user.business_id:
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    return AppointmentService.list_appointments(
        db=db,
        business_id=current_user.business_id,
        start_date=start_date,
        end_date=end_date,
        status=status,
        customer_phone=customer_phone,
        service_type=service_type,
        skip=skip,
        limit=limit
    )


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
    if not current_user.business_id:
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    result = AppointmentService.get_appointment_by_id(
        db=db,
        business_id=current_user.business_id,
        appointment_id=appointment_id
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail="Appointment not found or you don't have access to it"
        )

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
    if not current_user.business_id:
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    return AppointmentService.get_todays_appointments(
        db=db,
        business_id=current_user.business_id
    )


@router.get("/upcoming/week")
async def get_week_appointments(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Get all appointments scheduled for the next 7 days.
    Requires authenticated session.
    """
    if not current_user.business_id:
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    return AppointmentService.get_week_appointments(
        db=db,
        business_id=current_user.business_id
    )


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
    if not current_user.business_id:
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    return AppointmentService.search_appointments_by_phone(
        db=db,
        business_id=current_user.business_id,
        phone=phone,
        skip=skip,
        limit=limit
    )


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
    if not current_user.business_id:
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    return AppointmentService.get_appointment_stats(
        db=db,
        business_id=current_user.business_id,
        start_date=start_date,
        end_date=end_date
    )