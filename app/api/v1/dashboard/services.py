"""
Service Management API Endpoints
Handles CRUD operations for business services
UPDATED: Added comprehensive logging with user audit trail
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from decimal import Decimal
import uuid

from app.config.database import get_db
from app.models.auth.user import User
from app.api.dependencies import get_current_user
from app.models.business.service import Service, BookingType
from app.models.business.business import Business
from app.schemas.service import (
    BookingTypeEnum,
    RequiredFieldSchema,
    ServiceCreate,
    ServiceUpdate,
    ServiceResponse,
    ServiceListResponse,
    ServiceBulkCreate
)
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["services"])


# ============================================================================
# Helper Functions
# ============================================================================

def _service_to_response(service: Service, db: Session) -> ServiceResponse:
    """Convert Service model to ServiceResponse with computed fields"""
    from app.models.business.document import Document

    # Count linked documents
    linked_docs_count = db.query(Document).filter(
        Document.related_service_id == service.id,
        Document.is_active == True
    ).count()

    data = service.to_dict()
    data["formatted_price"] = service.formatted_price
    data["formatted_duration"] = service.formatted_duration
    data["formatted_consultation_duration"] = service.formatted_consultation_duration
    data["linked_documents_count"] = linked_docs_count

    return ServiceResponse(**data)


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/", response_model=ServiceResponse)
def create_service(
        service_data: ServiceCreate,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Create a new service
    Requires authenticated session.
    """
    logger.info(
        f"User {current_user.id} creating service - "
        f"Business: {service_data.business_id}, Name: '{service_data.name}', "
        f"Type: {service_data.booking_type.value}"
    )

    try:
        # Validate business exists
        business = db.query(Business).filter(
            Business.id == service_data.business_id
        ).first()
        if not business:
            logger.warning(
                f"Service creation failed: Business {service_data.business_id} not found - "
                f"User: {current_user.id}"
            )
            raise HTTPException(status_code=404, detail="Business not found")

        # Validation: consultation_required needs consultation_duration
        if service_data.booking_type == BookingTypeEnum.CONSULTATION_REQUIRED:
            if not service_data.consultation_duration:
                logger.warning(
                    f"Service creation failed: Missing consultation_duration for CONSULTATION_REQUIRED - "
                    f"Service: '{service_data.name}', User: {current_user.id}"
                )
                raise HTTPException(
                    status_code=400,
                    detail="consultation_duration is required when booking_type is consultation_required"
                )

        # Convert required_fields to dict format
        required_fields_data = [field.dict() for field in service_data.required_fields]

        # Create service
        service = Service(
            id=uuid.uuid4(),
            business_id=uuid.UUID(service_data.business_id),
            name=service_data.name,
            description=service_data.description,
            price=Decimal(str(service_data.price)) if service_data.price is not None else None,
            price_display=service_data.price_display,
            duration=service_data.duration,
            booking_type=BookingType[service_data.booking_type.name],
            consultation_duration=service_data.consultation_duration,
            consultation_price=Decimal(
                str(service_data.consultation_price)) if service_data.consultation_price is not None else None,
            required_fields=required_fields_data,
            display_order=service_data.display_order,
            is_active=True
        )

        db.add(service)
        db.commit()
        db.refresh(service)

        logger.info(
            f"Service created successfully - "
            f"Service ID: {service.id}, Name: '{service.name}', "
            f"Type: {service.booking_type.value}, Duration: {service.duration}min, "
            f"Required fields: {len(required_fields_data)}, Business: {service_data.business_id}, "
            f"Created by: {current_user.id}"
        )

        return _service_to_response(service, db)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error creating service - Business: {service_data.business_id}, "
            f"User: {current_user.id}: {e}",
            exc_info=True
        )
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk", response_model=ServiceListResponse)
def create_services_bulk(
        bulk_data: ServiceBulkCreate,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Create multiple services at once (useful for initial setup)
    Requires authenticated session.
    """
    logger.info(
        f"User {current_user.id} bulk creating services - "
        f"Business: {bulk_data.business_id}, Count: {len(bulk_data.services)}"
    )

    try:
        # Validate business exists
        business = db.query(Business).filter(
            Business.id == bulk_data.business_id
        ).first()
        if not business:
            logger.warning(
                f"Bulk service creation failed: Business {bulk_data.business_id} not found - "
                f"User: {current_user.id}"
            )
            raise HTTPException(status_code=404, detail="Business not found")

        created_services = []

        for idx, service_data in enumerate(bulk_data.services):
            # Validation
            if service_data.booking_type == BookingTypeEnum.CONSULTATION_REQUIRED:
                if not service_data.consultation_duration:
                    logger.warning(
                        f"Bulk creation failed: Missing consultation_duration for '{service_data.name}' - "
                        f"User: {current_user.id}"
                    )
                    raise HTTPException(
                        status_code=400,
                        detail=f"consultation_duration required for service '{service_data.name}'"
                    )

            required_fields_data = [field.dict() for field in service_data.required_fields]

            service = Service(
                id=uuid.uuid4(),
                business_id=uuid.UUID(bulk_data.business_id),
                name=service_data.name,
                description=service_data.description,
                price=Decimal(str(service_data.price)) if service_data.price is not None else None,
                price_display=service_data.price_display,
                duration=service_data.duration,
                booking_type=BookingType[service_data.booking_type.name],
                consultation_duration=service_data.consultation_duration,
                consultation_price=Decimal(
                    str(service_data.consultation_price)) if service_data.consultation_price is not None else None,
                required_fields=required_fields_data,
                display_order=service_data.display_order if service_data.display_order else idx,
                is_active=True
            )

            db.add(service)
            created_services.append(service)

        db.commit()

        # Log each service name for audit
        service_names = [s.name for s in created_services]
        logger.info(
            f"Bulk created {len(created_services)} services - "
            f"Business: {bulk_data.business_id}, "
            f"Services: {', '.join(service_names[:5])}{'...' if len(service_names) > 5 else ''}, "
            f"Created by: {current_user.id}"
        )

        # Refresh all services
        for service in created_services:
            db.refresh(service)

        return ServiceListResponse(
            total=len(created_services),
            services=[_service_to_response(s, db) for s in created_services]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error in bulk service creation - Business: {bulk_data.business_id}, "
            f"User: {current_user.id}: {e}",
            exc_info=True
        )
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{service_id}", response_model=ServiceResponse)
def get_service(
        service_id: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Get service by ID
    Requires authenticated session.
    """
    logger.info(f"User {current_user.id} requesting service {service_id}")

    try:
        service = db.query(Service).filter(Service.id == service_id).first()
        if not service:
            logger.warning(
                f"Service {service_id} not found - User: {current_user.id}"
            )
            raise HTTPException(status_code=404, detail="Service not found")

        logger.info(
            f"Service retrieved - Service: {service_id}, Name: '{service.name}', "
            f"Type: {service.booking_type.value}"
        )

        return _service_to_response(service, db)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error fetching service {service_id} - User: {current_user.id}: {e}",
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/business/{business_id}", response_model=ServiceListResponse)
def list_business_services(
        business_id: str,
        active_only: bool = True,
        include_inactive: bool = False,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    List all services for a business
    Requires authenticated session.
    """
    logger.info(
        f"User {current_user.id} listing services for business {business_id} - "
        f"Active only: {active_only}, Include inactive: {include_inactive}"
    )

    try:
        query = db.query(Service).filter(Service.business_id == business_id)

        if active_only and not include_inactive:
            query = query.filter(Service.is_active == True)

        services = query.order_by(Service.display_order, Service.created_at).all()

        logger.info(
            f"Returned {len(services)} services for business {business_id}"
        )

        return ServiceListResponse(
            total=len(services),
            services=[_service_to_response(s, db) for s in services]
        )

    except Exception as e:
        logger.error(
            f"Error listing services - Business: {business_id}, User: {current_user.id}: {e}",
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{service_id}", response_model=ServiceResponse)
def update_service(
        service_id: str,
        update_data: ServiceUpdate,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Update a service
    Requires authenticated session.
    """
    logger.info(f"User {current_user.id} updating service {service_id}")

    try:
        service = db.query(Service).filter(Service.id == service_id).first()
        if not service:
            logger.warning(
                f"Service update failed: Service {service_id} not found - User: {current_user.id}"
            )
            raise HTTPException(status_code=404, detail="Service not found")

        # Track changes
        changes = []

        # Update fields if provided
        if update_data.name is not None:
            changes.append(f"name: '{service.name}' -> '{update_data.name}'")
            service.name = update_data.name

        if update_data.description is not None:
            changes.append("description updated")
            service.description = update_data.description

        if update_data.price is not None:
            changes.append(f"price: {service.price} -> {update_data.price}")
            service.price = Decimal(str(update_data.price))

        if update_data.price_display is not None:
            service.price_display = update_data.price_display

        if update_data.duration is not None:
            changes.append(f"duration: {service.duration}min -> {update_data.duration}min")
            service.duration = update_data.duration

        if update_data.booking_type is not None:
            changes.append(f"booking_type: {service.booking_type.value} -> {update_data.booking_type.value}")
            service.booking_type = BookingType[update_data.booking_type.name]

            # Validate consultation_duration when switching to consultation_required
            if update_data.booking_type == BookingTypeEnum.CONSULTATION_REQUIRED:
                if not service.consultation_duration and not update_data.consultation_duration:
                    logger.warning(
                        f"Service update failed: Missing consultation_duration for CONSULTATION_REQUIRED - "
                        f"Service: {service_id}, User: {current_user.id}"
                    )
                    raise HTTPException(
                        status_code=400,
                        detail="consultation_duration required when booking_type is consultation_required"
                    )

        if update_data.consultation_duration is not None:
            changes.append(f"consultation_duration: {service.consultation_duration}min -> {update_data.consultation_duration}min")
            service.consultation_duration = update_data.consultation_duration

        if update_data.consultation_price is not None:
            service.consultation_price = Decimal(str(update_data.consultation_price))

        if update_data.required_fields is not None:
            changes.append(f"required_fields: {len(update_data.required_fields)} fields")
            service.required_fields = [field.dict() for field in update_data.required_fields]

        if update_data.display_order is not None:
            changes.append(f"display_order: {service.display_order} -> {update_data.display_order}")
            service.display_order = update_data.display_order

        if update_data.is_active is not None:
            changes.append(f"is_active: {service.is_active} -> {update_data.is_active}")
            service.is_active = update_data.is_active

        db.commit()
        db.refresh(service)

        logger.info(
            f"Service updated - Service: {service_id}, "
            f"Changes: [{', '.join(changes) if changes else 'no changes'}], "
            f"Updated by: {current_user.id}"
        )

        return _service_to_response(service, db)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error updating service {service_id} - User: {current_user.id}: {e}",
            exc_info=True
        )
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{service_id}")
def delete_service(
        service_id: str,
        hard_delete: bool = False,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Delete a service
    Requires authenticated session.

    Args:
        service_id: Service to delete
        hard_delete: If True, permanently delete. If False, soft delete (set is_active=False)
    """
    delete_type = "HARD DELETE" if hard_delete else "soft delete"
    logger.warning(
        f"User {current_user.id} performing {delete_type} on service {service_id}"
    )

    try:
        service = db.query(Service).filter(Service.id == service_id).first()
        if not service:
            logger.warning(
                f"Service deletion failed: Service {service_id} not found - User: {current_user.id}"
            )
            raise HTTPException(status_code=404, detail="Service not found")

        # Check if service has linked documents
        from app.models.business.document import Document
        linked_docs_count = db.query(Document).filter(
            Document.related_service_id == service_id,
            Document.is_active == True
        ).count()

        service_name = service.name
        business_id = service.business_id

        if hard_delete:
            if linked_docs_count > 0:
                logger.warning(
                    f"Hard delete blocked: Service {service_id} has {linked_docs_count} linked documents - "
                    f"User: {current_user.id}"
                )
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot hard delete service with {linked_docs_count} linked documents. "
                           "Delete or unlink documents first, or use soft delete."
                )

            # Hard delete (will set related_service_id to NULL in documents due to ON DELETE SET NULL)
            db.delete(service)
            db.commit()

            logger.warning(
                f"Service PERMANENTLY DELETED - "
                f"Service ID: {service_id}, Name: '{service_name}', "
                f"Business: {business_id}, Deleted by: {current_user.id}"
            )

            return {
                "success": True,
                "message": "Service permanently deleted"
            }
        else:
            # Soft delete
            service.is_active = False
            db.commit()

            logger.warning(
                f"Service DEACTIVATED - "
                f"Service ID: {service_id}, Name: '{service_name}', "
                f"Business: {business_id}, Linked documents: {linked_docs_count}, "
                f"Deactivated by: {current_user.id}"
            )

            return {
                "success": True,
                "message": "Service deactivated",
                "linked_documents": linked_docs_count
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error deleting service {service_id} - User: {current_user.id}: {e}",
            exc_info=True
        )
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{service_id}/reorder")
def reorder_service(
        service_id: str,
        new_order: int,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Update the display order of a service
    Requires authenticated session.
    """
    logger.info(
        f"User {current_user.id} reordering service {service_id} to position {new_order}"
    )

    try:
        service = db.query(Service).filter(Service.id == service_id).first()
        if not service:
            logger.warning(
                f"Service reorder failed: Service {service_id} not found - User: {current_user.id}"
            )
            raise HTTPException(status_code=404, detail="Service not found")

        old_order = service.display_order
        service.display_order = new_order
        db.commit()

        logger.info(
            f"Service reordered - Service: {service_id}, Name: '{service.name}', "
            f"Order: {old_order} -> {new_order}, Updated by: {current_user.id}"
        )

        return {
            "success": True,
            "service_id": service_id,
            "old_order": old_order,
            "new_order": new_order
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error reordering service {service_id} - User: {current_user.id}: {e}",
            exc_info=True
        )
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{service_id}/documents")
def get_service_documents(
        service_id: str,
        active_only: bool = True,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Get all documents linked to a service
    Requires authenticated session.
    """
    logger.info(
        f"User {current_user.id} requesting documents for service {service_id} - "
        f"Active only: {active_only}"
    )

    try:
        from app.models.business.document import Document

        # Verify service exists
        service = db.query(Service).filter(Service.id == service_id).first()
        if not service:
            logger.warning(
                f"Service {service_id} not found - User: {current_user.id}"
            )
            raise HTTPException(status_code=404, detail="Service not found")

        query = db.query(Document).filter(Document.related_service_id == service_id)

        if active_only:
            query = query.filter(Document.is_active == True)

        documents = query.order_by(Document.created_at.desc()).all()

        logger.info(
            f"Retrieved {len(documents)} documents for service {service_id}"
        )

        return {
            "service_id": service_id,
            "service_name": service.name,
            "total_documents": len(documents),
            "documents": [doc.to_dict() for doc in documents]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error fetching service documents - Service: {service_id}, User: {current_user.id}: {e}",
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/migrate-from-catalog/{business_id}")
def migrate_from_service_catalog(
        business_id: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Migrate services from old Business.service_catalog JSON to Services table
    (Helper endpoint for manual migration if needed)
    Requires authenticated session.
    """
    logger.warning(
        f"User {current_user.id} initiating service catalog MIGRATION for business {business_id}"
    )

    try:
        business = db.query(Business).filter(Business.id == business_id).first()
        if not business:
            logger.warning(
                f"Migration failed: Business {business_id} not found - User: {current_user.id}"
            )
            raise HTTPException(status_code=404, detail="Business not found")

        if not business.service_catalog:
            logger.info(
                f"No service catalog to migrate for business {business_id}"
            )
            return {
                "success": True,
                "message": "No service_catalog to migrate",
                "migrated_count": 0
            }

        # Check if services already exist
        existing_count = db.query(Service).filter(
            Service.business_id == business_id
        ).count()

        if existing_count > 0:
            logger.warning(
                f"Migration blocked: Business {business_id} already has {existing_count} services - "
                f"User: {current_user.id}"
            )
            raise HTTPException(
                status_code=400,
                detail=f"Business already has {existing_count} services. Delete them first if you want to re-migrate."
            )

        migrated_count = 0

        for idx, (service_name, service_info) in enumerate(business.service_catalog.items()):
            # Parse price
            price = None
            price_display = None
            if 'price' in service_info:
                price_val = service_info['price']
                if price_val == 'Free' or price_val == 'free':
                    price_display = 'Free'
                else:
                    try:
                        price = Decimal(str(price_val).replace('$', '').replace(',', ''))
                    except:
                        price_display = str(price_val)

            # Default to DIRECT booking with basic name field requirement
            service = Service(
                id=uuid.uuid4(),
                business_id=uuid.UUID(business_id),
                name=service_name,
                description=service_info.get('description'),
                price=price,
                price_display=price_display,
                duration=service_info.get('duration'),
                booking_type=BookingType.DIRECT,
                required_fields=[{"field": "name", "label": "Name", "type": "text", "required": True}],
                display_order=idx,
                is_active=True
            )

            db.add(service)
            migrated_count += 1

        db.commit()

        logger.warning(
            f"Service catalog MIGRATED - Business: {business_id}, "
            f"Services migrated: {migrated_count}, Migrated by: {current_user.id}"
        )

        return {
            "success": True,
            "message": f"Successfully migrated {migrated_count} services",
            "migrated_count": migrated_count
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error migrating services - Business: {business_id}, User: {current_user.id}: {e}",
            exc_info=True
        )
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=ServiceListResponse)
def list_all_services(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    List all active services
    Requires authenticated session.
    """
    logger.info(f"User {current_user.id} listing all active services")

    try:
        services = db.query(Service).filter(
            Service.is_active == True
        ).order_by(Service.display_order, Service.created_at).all()

        logger.info(f"Returned {len(services)} active services")

        return ServiceListResponse(
            total=len(services),
            services=[_service_to_response(s, db) for s in services]
        )

    except Exception as e:
        logger.error(
            f"Error listing all services - User: {current_user.id}: {e}",
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))