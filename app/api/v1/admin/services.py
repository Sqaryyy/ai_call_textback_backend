"""
Admin Services API
System admins can view and manage services for ANY business
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from app.config.database import get_db
from app.models.auth.user import User
from app.models.business.business import Business
from app.models.business.service import Service, BookingType
from app.api.dependencies import require_platform_admin  # System admin only!
from app.utils.logger import get_logger
from app.schemas.admin.services import (
    ServiceListResponse,
    ServiceResponse,
    ServiceCreate,
    ServiceUpdate,
)

logger = get_logger(__name__)

# ============================================================================
# Router
# ============================================================================

admin_services_router = APIRouter(
    prefix="/services",
    tags=["admin-services"]
)


# ============================================================================
# ENDPOINTS
# ============================================================================

@admin_services_router.get("/", response_model=List[ServiceListResponse])
async def list_all_services(
        business_id: Optional[UUID] = Query(None, description="Filter by business ID"),
        active_only: bool = Query(True, description="Show only active services"),
        current_user: User = Depends(require_platform_admin),
        db: Session = Depends(get_db)
):
    """
    List all services across all businesses (admin only)
    Optionally filter by specific business
    """
    filter_str = ""
    if business_id:
        filter_str = f" for business {business_id}"
    if not active_only:
        filter_str += " (including inactive)"

    logger.info(f"Admin {current_user.id} listing services{filter_str}")

    query = db.query(Service).join(Business)

    if business_id:
        query = query.filter(Service.business_id == business_id)

    if active_only:
        query = query.filter(Service.is_active == True)

    services = query.order_by(
        Service.business_id,
        Service.display_order,
        Service.name
    ).all()

    logger.info(f"Returning {len(services)} services")

    # Include business context in response
    response = []
    for service in services:
        business = db.query(Business).filter(Business.id == service.business_id).first()
        service_dict = service.to_dict()
        service_dict['business_name'] = business.name if business else "Unknown"
        service_dict['formatted_price'] = service.formatted_price
        service_dict['formatted_duration'] = service.formatted_duration
        service_dict['formatted_consultation_duration'] = service.formatted_consultation_duration
        response.append(ServiceListResponse(**service_dict))

    return response


@admin_services_router.get("/{service_id}", response_model=ServiceResponse)
async def get_service(
        service_id: UUID,
        current_user: User = Depends(require_platform_admin),
        db: Session = Depends(get_db)
):
    """Get any service by ID (admin can view all)"""
    logger.info(f"Admin {current_user.id} viewing service {service_id}")

    service = db.query(Service).filter(Service.id == service_id).first()

    if not service:
        logger.warning(f"Service {service_id} not found - requested by admin {current_user.id}")
        raise HTTPException(status_code=404, detail="Service not found")

    logger.debug(
        f"Retrieved service - Business ID: {service.business_id}, "
        f"Name: '{service.name}', Type: {service.booking_type.value}, Active: {service.is_active}"
    )

    return ServiceResponse.from_orm(service)


@admin_services_router.post("/", response_model=ServiceResponse, status_code=201)
async def create_service(
        service_data: ServiceCreate,
        current_user: User = Depends(require_platform_admin),
        db: Session = Depends(get_db)
):
    """Create a new service for any business (admin only)"""
    logger.info(
        f"Admin {current_user.id} creating service for business {service_data.business_id} - "
        f"Name: '{service_data.name}', Type: {service_data.booking_type.value}"
    )

    # Verify business exists
    business = db.query(Business).filter(
        Business.id == service_data.business_id
    ).first()

    if not business:
        logger.warning(f"Create failed - business {service_data.business_id} not found")
        raise HTTPException(status_code=404, detail="Business not found")

    # Convert required_fields to dict format
    required_fields_list = [field.model_dump() for field in service_data.required_fields]

    service = Service(
        business_id=service_data.business_id,
        name=service_data.name,
        description=service_data.description,
        price=service_data.price,
        price_display=service_data.price_display,
        duration=service_data.duration,
        booking_type=service_data.booking_type,
        consultation_duration=service_data.consultation_duration,
        consultation_price=service_data.consultation_price,
        required_fields=required_fields_list,
        is_active=service_data.is_active,
        display_order=service_data.display_order
    )

    db.add(service)
    db.commit()
    db.refresh(service)

    logger.info(f"Service {service.id} created successfully for business {business.id}")

    return ServiceResponse.from_orm(service)


@admin_services_router.put("/{service_id}", response_model=ServiceResponse)
async def update_service(
        service_id: UUID,
        service_data: ServiceUpdate,
        current_user: User = Depends(require_platform_admin),
        db: Session = Depends(get_db)
):
    """Update any service (admin can modify all)"""
    # Build update description for logging
    updates = []
    update_data = service_data.model_dump(exclude_unset=True)
    for field in update_data.keys():
        if field == 'name':
            updates.append("name")
        elif field == 'description':
            updates.append("description")
        elif field == 'price' or field == 'price_display':
            updates.append("pricing")
        elif field == 'duration':
            updates.append("duration")
        elif field == 'booking_type':
            updates.append(f"booking_type={update_data[field].value}")
        elif field == 'is_active':
            updates.append(f"is_active={update_data[field]}")
        elif field == 'required_fields':
            updates.append("required_fields")
        else:
            updates.append(field)

    update_str = ', '.join(list(dict.fromkeys(updates))) if updates else "no changes"
    logger.info(f"Admin {current_user.id} updating service {service_id} - Updates: {update_str}")

    service = db.query(Service).filter(Service.id == service_id).first()

    if not service:
        logger.warning(f"Update failed - service {service_id} not found")
        raise HTTPException(status_code=404, detail="Service not found")

    # Update fields
    update_data = service_data.model_dump(exclude_unset=True)

    # Convert required_fields if present
    if 'required_fields' in update_data and update_data['required_fields'] is not None:
        update_data['required_fields'] = [
            field if isinstance(field, dict) else field.model_dump()
            for field in update_data['required_fields']
        ]

    for field, value in update_data.items():
        setattr(service, field, value)

    # Validate consultation settings if booking type changed
    if service.booking_type == BookingType.CONSULTATION_REQUIRED:
        if not service.consultation_duration:
            logger.warning(f"Update failed - consultation_duration required for service {service_id}")
            raise HTTPException(
                status_code=400,
                detail="consultation_duration is required for CONSULTATION_REQUIRED booking type"
            )

    db.commit()
    db.refresh(service)

    logger.info(f"Service {service_id} updated successfully")

    return ServiceResponse.from_orm(service)


@admin_services_router.delete("/{service_id}", status_code=204)
async def delete_service(
        service_id: UUID,
        current_user: User = Depends(require_platform_admin),
        db: Session = Depends(get_db)
):
    """Delete any service (admin can delete all)"""
    logger.warning(f"Admin {current_user.id} attempting to DELETE service {service_id}")

    service = db.query(Service).filter(Service.id == service_id).first()

    if not service:
        logger.warning(f"Delete failed - service {service_id} not found")
        raise HTTPException(status_code=404, detail="Service not found")

    service_name = service.name
    business_id = service.business_id

    db.delete(service)
    db.commit()

    logger.warning(
        f"Service DELETED permanently - "
        f"Service ID: {service_id}, Name: '{service_name}', "
        f"Business ID: {business_id}, Deleted by: {current_user.id}"
    )

    return None


@admin_services_router.post("/{service_id}/toggle", response_model=ServiceResponse)
async def toggle_service_active(
        service_id: UUID,
        current_user: User = Depends(require_platform_admin),
        db: Session = Depends(get_db)
):
    """Toggle service active status"""
    logger.info(f"Admin {current_user.id} toggling active status for service {service_id}")

    service = db.query(Service).filter(Service.id == service_id).first()

    if not service:
        logger.warning(f"Toggle failed - service {service_id} not found")
        raise HTTPException(status_code=404, detail="Service not found")

    old_status = service.is_active
    service.is_active = not service.is_active
    db.commit()
    db.refresh(service)

    logger.info(f"Service {service_id} active status toggled: {old_status} -> {service.is_active}")

    return ServiceResponse.from_orm(service)


@admin_services_router.post("/{service_id}/reorder", response_model=ServiceResponse)
async def reorder_service(
        service_id: UUID,
        new_order: int = Query(..., ge=0, description="New display order"),
        current_user: User = Depends(require_platform_admin),
        db: Session = Depends(get_db)
):
    """Update service display order"""
    logger.info(f"Admin {current_user.id} reordering service {service_id} to position {new_order}")

    service = db.query(Service).filter(Service.id == service_id).first()

    if not service:
        logger.warning(f"Reorder failed - service {service_id} not found")
        raise HTTPException(status_code=404, detail="Service not found")

    old_order = service.display_order
    service.display_order = new_order
    db.commit()
    db.refresh(service)

    logger.info(f"Service {service_id} reordered: {old_order} -> {new_order}")

    return ServiceResponse.from_orm(service)


@admin_services_router.get("/business/{business_id}/stats")
async def get_business_service_stats(
        business_id: UUID,
        current_user: User = Depends(require_platform_admin),
        db: Session = Depends(get_db)
):
    """Get service statistics for a specific business"""
    logger.info(f"Admin {current_user.id} requesting service stats for business {business_id}")

    business = db.query(Business).filter(Business.id == business_id).first()

    if not business:
        logger.warning(f"Business {business_id} not found - requested by admin {current_user.id}")
        raise HTTPException(status_code=404, detail="Business not found")

    total_services = db.query(Service).filter(
        Service.business_id == business_id
    ).count()

    active_services = db.query(Service).filter(
        Service.business_id == business_id,
        Service.is_active == True
    ).count()

    services_by_type = db.query(
        Service.booking_type,
        db.func.count(Service.id)
    ).filter(
        Service.business_id == business_id
    ).group_by(Service.booking_type).all()

    type_distribution = {
        booking_type.value: count
        for booking_type, count in services_by_type
    }

    logger.info(
        f"Business service stats: {total_services} total, {active_services} active, "
        f"type distribution: {type_distribution}"
    )

    return {
        "business_id": str(business_id),
        "business_name": business.name,
        "total_services": total_services,
        "active_services": active_services,
        "inactive_services": total_services - active_services,
        "services_by_type": type_distribution
    }


@admin_services_router.get("/stats/overview")
async def get_services_overview(
        current_user: User = Depends(require_platform_admin),
        db: Session = Depends(get_db)
):
    """Get platform-wide service statistics"""
    logger.info(f"Admin {current_user.id} requesting platform-wide service stats")

    total_services = db.query(Service).count()

    active_services = db.query(Service).filter(
        Service.is_active == True
    ).count()

    businesses_with_services = db.query(Service.business_id).distinct().count()

    services_by_type = db.query(
        Service.booking_type,
        db.func.count(Service.id)
    ).group_by(Service.booking_type).all()

    type_distribution = {
        booking_type.value: count
        for booking_type, count in services_by_type
    }

    avg_services_per_business = db.query(
        db.func.count(Service.id)
    ).join(Business).group_by(Business.id).subquery()

    avg_count = db.query(db.func.avg(avg_services_per_business.c.count_1)).scalar()

    logger.info(
        f"Platform service stats: {total_services} total, {active_services} active, "
        f"{businesses_with_services} businesses, type distribution: {type_distribution}"
    )

    return {
        "total_services": total_services,
        "active_services": active_services,
        "inactive_services": total_services - active_services,
        "businesses_with_services": businesses_with_services,
        "avg_services_per_business": float(avg_count) if avg_count else 0,
        "services_by_type": type_distribution
    }