"""
Admin Appointments API
CRUD operations for appointments - requires PLATFORM ADMIN access
Platform admins can manage appointments for ANY business
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional
from datetime import datetime, timezone, timedelta
from uuid import UUID

from app.config.database import get_db
from app.models.auth.user import User
from app.models.business.business import Business
from app.models.appointment.appointment import Appointment
from app.api.dependencies import require_platform_admin
from app.utils.logger import get_logger
from app.schemas.admin.appointments import (
    AppointmentResponse,
    AppointmentListResponse,
    AppointmentStatsResponse,
    MessageResponse,
    AppointmentsByBusinessResponse,
    CancelAppointmentRequest,
    AppointmentCreate,
    AppointmentUpdate
    )
logger = get_logger(__name__)

# ============================================================================
# Router
# ============================================================================

router = APIRouter(
    prefix="/appointments",
    tags=["Admin - Appointments"]
)


# ============================================================================
# CRUD Endpoints
# ============================================================================

@router.get("/", response_model=AppointmentListResponse)
async def list_appointments(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    business_id: Optional[UUID] = Query(None, description="Filter by business ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    booking_source: Optional[str] = Query(None, description="Filter by booking source"),
    customer_phone: Optional[str] = Query(None, description="Filter by customer phone"),
    start_date: Optional[datetime] = Query(None, description="Filter appointments from this date"),
    end_date: Optional[datetime] = Query(None, description="Filter appointments until this date"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    List all appointments with filtering and pagination.

    Requires platform admin role.
    """
    logger.info(f"Admin listing appointments - User ID: {current_user.id}, Page: {page}")

    query = db.query(Appointment)

    # Apply filters
    if business_id:
        query = query.filter(Appointment.business_id == business_id)
    if status:
        query = query.filter(Appointment.status == status)
    if booking_source:
        query = query.filter(Appointment.booking_source == booking_source)
    if customer_phone:
        query = query.filter(Appointment.customer_phone.ilike(f"%{customer_phone}%"))
    if start_date:
        query = query.filter(Appointment.appointment_datetime >= start_date)
    if end_date:
        query = query.filter(Appointment.appointment_datetime <= end_date)

    # Get total count
    total = query.count()

    # Calculate pagination
    pages = (total + page_size - 1) // page_size
    offset = (page - 1) * page_size

    # Get paginated results
    appointments = query.order_by(desc(Appointment.appointment_datetime)).offset(offset).limit(page_size).all()

    items = [AppointmentResponse.model_validate(apt) for apt in appointments]

    logger.debug(f"Retrieved {len(items)} appointments (total: {total})")

    return AppointmentListResponse(
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        items=items
    )


@router.get("/stats", response_model=AppointmentStatsResponse)
async def get_appointment_stats(
    business_id: Optional[UUID] = Query(None, description="Filter stats by business ID"),
    start_date: Optional[datetime] = Query(None, description="Filter from date"),
    end_date: Optional[datetime] = Query(None, description="Filter to date"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    Get comprehensive statistics about appointments.

    Requires platform admin role.
    """
    logger.info(f"Admin requesting appointment stats - User ID: {current_user.id}")

    query = db.query(Appointment)
    if business_id:
        query = query.filter(Appointment.business_id == business_id)
    if start_date:
        query = query.filter(Appointment.appointment_datetime >= start_date)
    if end_date:
        query = query.filter(Appointment.appointment_datetime <= end_date)

    # Total appointments
    total_appointments = query.count()

    # Status breakdown
    scheduled_appointments = query.filter(Appointment.status == "scheduled").count()
    confirmed_appointments = query.filter(Appointment.status == "confirmed").count()
    cancelled_appointments = query.filter(Appointment.status == "cancelled").count()
    completed_appointments = query.filter(Appointment.status == "completed").count()
    no_show_appointments = query.filter(Appointment.status == "no_show").count()

    # Detailed breakdowns
    all_appointments = query.all()
    appointments_by_status = {}
    appointments_by_source = {}

    for apt in all_appointments:
        appointments_by_status[apt.status] = appointments_by_status.get(apt.status, 0) + 1
        appointments_by_source[apt.booking_source] = appointments_by_source.get(apt.booking_source, 0) + 1

    # Unique counts
    unique_businesses = db.query(func.count(func.distinct(Appointment.business_id))).scalar()
    unique_customers = query.with_entities(func.count(func.distinct(Appointment.customer_phone))).scalar()

    # Average duration
    avg_duration = query.with_entities(func.avg(Appointment.duration_minutes)).scalar() or 0

    # Time-based stats
    now = datetime.now(timezone.utc)
    appointments_last_24h = query.filter(Appointment.created_at >= now - timedelta(hours=24)).count()
    appointments_last_7d = query.filter(Appointment.created_at >= now - timedelta(days=7)).count()
    appointments_last_30d = query.filter(Appointment.created_at >= now - timedelta(days=30)).count()

    # Upcoming appointments
    upcoming_appointments = query.filter(
        Appointment.appointment_datetime >= now,
        Appointment.status.in_(["scheduled", "confirmed"])
    ).count()

    logger.debug(f"Stats computed - Total: {total_appointments}, Upcoming: {upcoming_appointments}")

    return AppointmentStatsResponse(
        total_appointments=total_appointments,
        scheduled_appointments=scheduled_appointments,
        confirmed_appointments=confirmed_appointments,
        cancelled_appointments=cancelled_appointments,
        completed_appointments=completed_appointments,
        no_show_appointments=no_show_appointments,
        appointments_by_status=appointments_by_status,
        appointments_by_source=appointments_by_source,
        unique_businesses=unique_businesses,
        unique_customers=unique_customers,
        avg_duration_minutes=round(float(avg_duration), 2),
        appointments_last_24h=appointments_last_24h,
        appointments_last_7d=appointments_last_7d,
        appointments_last_30d=appointments_last_30d,
        upcoming_appointments=upcoming_appointments
    )


@router.get("/by-business", response_model=List[AppointmentsByBusinessResponse])
async def get_appointments_by_business(
    start_date: Optional[datetime] = Query(None, description="Filter from date"),
    end_date: Optional[datetime] = Query(None, description="Filter to date"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    Get appointment statistics grouped by business.

    Requires platform admin role.
    """
    logger.info(f"Admin requesting appointments by business - User ID: {current_user.id}")

    query = db.query(
        Appointment.business_id,
        func.count(Appointment.id).label('total_appointments'),
        func.sum(func.case((Appointment.status == 'scheduled', 1), else_=0)).label('scheduled_appointments'),
        func.sum(func.case((Appointment.status == 'confirmed', 1), else_=0)).label('confirmed_appointments'),
        func.sum(func.case((Appointment.status == 'cancelled', 1), else_=0)).label('cancelled_appointments'),
        func.sum(func.case((Appointment.status == 'completed', 1), else_=0)).label('completed_appointments'),
        func.max(Appointment.appointment_datetime).label('last_appointment_at')
    )

    if start_date:
        query = query.filter(Appointment.appointment_datetime >= start_date)
    if end_date:
        query = query.filter(Appointment.appointment_datetime <= end_date)

    results = query.group_by(Appointment.business_id).all()

    logger.debug(f"Retrieved stats for {len(results)} businesses")

    return [
        AppointmentsByBusinessResponse(
            business_id=str(result.business_id),
            total_appointments=result.total_appointments,
            scheduled_appointments=result.scheduled_appointments,
            confirmed_appointments=result.confirmed_appointments,
            cancelled_appointments=result.cancelled_appointments,
            completed_appointments=result.completed_appointments,
            last_appointment_at=result.last_appointment_at.isoformat() if result.last_appointment_at else None
        )
        for result in results
    ]


@router.get("/{appointment_id}", response_model=AppointmentResponse)
async def get_appointment(
    appointment_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    Get details of a specific appointment.

    Requires platform admin role.
    """
    logger.info(f"Admin viewing appointment - User ID: {current_user.id}, Appointment ID: {appointment_id}")

    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()

    if not appointment:
        logger.warning(f"Appointment not found - Appointment ID: {appointment_id}")
        raise HTTPException(status_code=404, detail="Appointment not found")

    return AppointmentResponse.model_validate(appointment)


@router.post("/", response_model=AppointmentResponse, status_code=201)
async def create_appointment(
    appointment_data: AppointmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    Create a new appointment.

    Requires platform admin role.
    """
    logger.info(f"Admin creating appointment - User ID: {current_user.id}, Business ID: {appointment_data.business_id}")

    # Verify business exists
    business = db.query(Business).filter(Business.id == appointment_data.business_id).first()
    if not business:
        logger.warning(f"Appointment creation failed - Business not found: {appointment_data.business_id}")
        raise HTTPException(status_code=404, detail="Business not found")

    # Validate status
    valid_statuses = ["scheduled", "confirmed", "cancelled", "completed", "no_show"]
    if appointment_data.status not in valid_statuses:
        logger.warning(f"Appointment creation failed - Invalid status: {appointment_data.status}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )

    appointment = Appointment(
        conversation_id=appointment_data.conversation_id,
        business_id=appointment_data.business_id,
        calendar_integration_id=appointment_data.calendar_integration_id,
        customer_phone=appointment_data.customer_phone,
        customer_name=appointment_data.customer_name,
        customer_email=appointment_data.customer_email,
        service_type=appointment_data.service_type,
        appointment_datetime=appointment_data.appointment_datetime,
        duration_minutes=appointment_data.duration_minutes,
        notes=appointment_data.notes,
        status=appointment_data.status,
        booking_source=appointment_data.booking_source,
    )

    db.add(appointment)
    db.commit()
    db.refresh(appointment)

    logger.info(f"Appointment created - Appointment ID: {appointment.id}, Business ID: {appointment_data.business_id}, Created by: {current_user.id}")

    return AppointmentResponse.model_validate(appointment)


@router.put("/{appointment_id}", response_model=AppointmentResponse)
async def update_appointment(
    appointment_id: UUID,
    appointment_data: AppointmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    Update an existing appointment.

    Requires platform admin role.
    """
    logger.info(f"Admin updating appointment - User ID: {current_user.id}, Appointment ID: {appointment_id}")

    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()

    if not appointment:
        logger.warning(f"Appointment update failed - Not found: {appointment_id}")
        raise HTTPException(status_code=404, detail="Appointment not found")

    # Track status change for audit log
    old_status = appointment.status
    new_status = appointment_data.status

    # Validate status if provided
    if appointment_data.status:
        valid_statuses = ["scheduled", "confirmed", "cancelled", "completed", "no_show"]
        if appointment_data.status not in valid_statuses:
            logger.warning(f"Appointment update failed - Invalid status: {appointment_data.status}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
            )

    # Update fields
    update_data = appointment_data.model_dump(exclude_unset=True)

    # Handle cancellation
    if appointment_data.status == "cancelled" and appointment.status != "cancelled":
        update_data["cancelled_at"] = datetime.now(timezone.utc)

    for field, value in update_data.items():
        setattr(appointment, field, value)

    db.commit()
    db.refresh(appointment)

    # Log status change if applicable
    if new_status and old_status != new_status:
        logger.info(f"Appointment status changed - Appointment ID: {appointment_id}, {old_status} → {new_status}, Updated by: {current_user.id}")
    else:
        logger.info(f"Appointment updated - Appointment ID: {appointment_id}, Updated by: {current_user.id}")

    return AppointmentResponse.model_validate(appointment)


@router.delete("/{appointment_id}", response_model=MessageResponse)
async def delete_appointment(
    appointment_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    Permanently delete an appointment.

    Requires platform admin role. This action cannot be undone.
    Note: Cancelling is recommended over deletion.
    """
    logger.warning(f"Admin deleting appointment (PERMANENT) - User ID: {current_user.id}, Appointment ID: {appointment_id}")

    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()

    if not appointment:
        logger.warning(f"Appointment deletion failed - Not found: {appointment_id}")
        raise HTTPException(status_code=404, detail="Appointment not found")

    # Store info for audit log before deletion
    business_id = str(appointment.business_id)

    db.delete(appointment)
    db.commit()

    logger.warning(f"Appointment DELETED permanently - Appointment ID: {appointment_id}, Business ID: {business_id}, Deleted by: {current_user.id}")

    return MessageResponse(
        message="Appointment deleted successfully",
        details={
            "appointment_id": str(appointment_id),
            "business_id": business_id,
            "customer_phone": appointment.customer_phone
        }
    )


@router.post("/{appointment_id}/cancel", response_model=AppointmentResponse)
async def cancel_appointment(
    appointment_id: UUID,
    cancel_request: CancelAppointmentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    Cancel an appointment (soft delete).

    Requires platform admin role.
    """
    logger.info(f"Admin cancelling appointment - User ID: {current_user.id}, Appointment ID: {appointment_id}")

    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()

    if not appointment:
        logger.warning(f"Appointment cancellation failed - Not found: {appointment_id}")
        raise HTTPException(status_code=404, detail="Appointment not found")

    old_status = appointment.status
    appointment.status = "cancelled"
    appointment.cancelled_at = datetime.now(timezone.utc)
    appointment.cancellation_reason = cancel_request.cancellation_reason

    db.commit()
    db.refresh(appointment)

    logger.info(f"Appointment cancelled - Appointment ID: {appointment_id}, Previous status: {old_status}, Cancelled by: {current_user.id}")

    return AppointmentResponse.model_validate(appointment)