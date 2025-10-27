# ============================================================================
# FILE 2: app/api/v1/api_key/appointments.py
# API key authenticated endpoints - thin HTTP layer
# ============================================================================
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session
from datetime import date
from typing import Optional
from uuid import UUID

from app.config.database import get_db
from app.models.api_key import APIKey
from app.api.dependencies import require_api_key, require_scope
from app.services.appointment.appointment_query_service import AppointmentService

router = APIRouter(prefix="/appointments", tags=["api-appointments"])


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
        api_key: APIKey = Depends(require_api_key),
        _: None = Depends(require_scope("read:appointments")),
        db: Session = Depends(get_db)
):
    """
    Get a list of all appointments for your business.
    Requires API key with 'read:appointments' scope.
    """
    return AppointmentService.list_appointments(
        db=db,
        business_id=api_key.business_id,
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
        api_key: APIKey = Depends(require_api_key),
        _: None = Depends(require_scope("read:appointments")),
        db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific appointment.
    Requires API key with 'read:appointments' scope.
    """
    result = AppointmentService.get_appointment_by_id(
        db=db,
        business_id=api_key.business_id,
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
        api_key: APIKey = Depends(require_api_key),
        _: None = Depends(require_scope("read:appointments")),
        db: Session = Depends(get_db)
):
    """
    Get all appointments scheduled for today.
    Requires API key with 'read:appointments' scope.
    """
    return AppointmentService.get_todays_appointments(
        db=db,
        business_id=api_key.business_id
    )


@router.get("/upcoming/week")
async def get_week_appointments(
        api_key: APIKey = Depends(require_api_key),
        _: None = Depends(require_scope("read:appointments")),
        db: Session = Depends(get_db)
):
    """
    Get all appointments scheduled for the next 7 days.
    Requires API key with 'read:appointments' scope.
    """
    return AppointmentService.get_week_appointments(
        db=db,
        business_id=api_key.business_id
    )


@router.get("/search/by-phone")
async def search_appointments_by_phone(
        phone: str = Query(..., description="Phone number to search for", min_length=10),
        skip: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        api_key: APIKey = Depends(require_api_key),
        _: None = Depends(require_scope("read:appointments")),
        db: Session = Depends(get_db)
):
    """
    Search for all appointments for a specific phone number.
    Requires API key with 'read:appointments' scope.
    """
    return AppointmentService.search_appointments_by_phone(
        db=db,
        business_id=api_key.business_id,
        phone=phone,
        skip=skip,
        limit=limit
    )


@router.get("/stats/summary")
async def get_appointment_stats(
        start_date: Optional[date] = Query(None, description="Stats from this date"),
        end_date: Optional[date] = Query(None, description="Stats until this date"),
        api_key: APIKey = Depends(require_api_key),
        _: None = Depends(require_scope("read:appointments")),
        db: Session = Depends(get_db)
):
    """
    Get summary statistics about your appointments.
    Requires API key with 'read:appointments' scope.
    """
    return AppointmentService.get_appointment_stats(
        db=db,
        business_id=api_key.business_id,
        start_date=start_date,
        end_date=end_date
    )

