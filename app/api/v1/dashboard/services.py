# app/api/routes/service_routes.py
"""
Service Management API Endpoints
Handles CRUD operations for business services
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel, Field
from decimal import Decimal
import uuid
import logging

from app.database import get_db
from app.models.service import Service
from app.models.business import Business

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/services", tags=["services"])


# ============================================================================
# Request/Response Models
# ============================================================================

class ServiceCreate(BaseModel):
    """Request model for creating a service"""
    business_id: str
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    price: Optional[float] = Field(None, ge=0)
    price_display: Optional[str] = Field(None, max_length=50)
    duration: Optional[int] = Field(None, ge=0, description="Duration in minutes")
    display_order: int = Field(default=0)


class ServiceUpdate(BaseModel):
    """Request model for updating a service"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    price: Optional[float] = Field(None, ge=0)
    price_display: Optional[str] = Field(None, max_length=50)
    duration: Optional[int] = Field(None, ge=0)
    display_order: Optional[int] = None
    is_active: Optional[bool] = None


class ServiceResponse(BaseModel):
    """Response model for service data"""
    id: str
    business_id: str
    name: str
    description: Optional[str]
    price: Optional[float]
    price_display: Optional[str]
    formatted_price: str
    duration: Optional[int]
    formatted_duration: str
    is_active: bool
    display_order: int
    created_at: str
    updated_at: str
    linked_documents_count: int = 0


class ServiceListResponse(BaseModel):
    """Response model for service list"""
    total: int
    services: List[ServiceResponse]


class ServiceBulkCreate(BaseModel):
    """Request model for bulk service creation"""
    business_id: str
    services: List[ServiceCreate]


# ============================================================================
# Helper Functions
# ============================================================================

def _service_to_response(service: Service, db: Session) -> ServiceResponse:
    """Convert Service model to ServiceResponse with computed fields"""
    from app.models.document import Document

    # Count linked documents
    linked_docs_count = db.query(Document).filter(
        Document.related_service_id == service.id,
        Document.is_active == True
    ).count()

    data = service.to_dict()
    data["formatted_price"] = service.formatted_price
    data["formatted_duration"] = service.formatted_duration
    data["linked_documents_count"] = linked_docs_count

    return ServiceResponse(**data)


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/", response_model=ServiceResponse)
def create_service(
        service_data: ServiceCreate,
        db: Session = Depends(get_db)
):
    """
    Create a new service
    """
    try:
        # Validate business exists
        business = db.query(Business).filter(
            Business.id == service_data.business_id
        ).first()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")

        # Create service
        service = Service(
            id=uuid.uuid4(),
            business_id=uuid.UUID(service_data.business_id),
            name=service_data.name,
            description=service_data.description,
            price=Decimal(str(service_data.price)) if service_data.price is not None else None,
            price_display=service_data.price_display,
            duration=service_data.duration,
            display_order=service_data.display_order,
            is_active=True
        )

        db.add(service)
        db.commit()
        db.refresh(service)

        logger.info(f"Created service {service.id}: {service.name}")

        return _service_to_response(service, db)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating service: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk", response_model=ServiceListResponse)
def create_services_bulk(
        bulk_data: ServiceBulkCreate,
        db: Session = Depends(get_db)
):
    """
    Create multiple services at once (useful for initial setup)
    """
    try:
        # Validate business exists
        business = db.query(Business).filter(
            Business.id == bulk_data.business_id
        ).first()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")

        created_services = []

        for idx, service_data in enumerate(bulk_data.services):
            service = Service(
                id=uuid.uuid4(),
                business_id=uuid.UUID(bulk_data.business_id),
                name=service_data.name,
                description=service_data.description,
                price=Decimal(str(service_data.price)) if service_data.price is not None else None,
                price_display=service_data.price_display,
                duration=service_data.duration,
                display_order=service_data.display_order if service_data.display_order else idx,
                is_active=True
            )

            db.add(service)
            created_services.append(service)

        db.commit()

        logger.info(f"Bulk created {len(created_services)} services for business {bulk_data.business_id}")

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
        logger.error(f"Error in bulk service creation: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{service_id}", response_model=ServiceResponse)
def get_service(
        service_id: str,
        db: Session = Depends(get_db)
):
    """
    Get service by ID
    """
    try:
        service = db.query(Service).filter(Service.id == service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")

        return _service_to_response(service, db)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching service: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/business/{business_id}", response_model=ServiceListResponse)
def list_business_services(
        business_id: str,
        active_only: bool = True,
        include_inactive: bool = False,
        db: Session = Depends(get_db)
):
    """
    List all services for a business
    """
    try:
        query = db.query(Service).filter(Service.business_id == business_id)

        if active_only and not include_inactive:
            query = query.filter(Service.is_active == True)

        services = query.order_by(Service.display_order, Service.created_at).all()

        return ServiceListResponse(
            total=len(services),
            services=[_service_to_response(s, db) for s in services]
        )

    except Exception as e:
        logger.error(f"Error listing services: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{service_id}", response_model=ServiceResponse)
def update_service(
        service_id: str,
        update_data: ServiceUpdate,
        db: Session = Depends(get_db)
):
    """
    Update a service
    """
    try:
        service = db.query(Service).filter(Service.id == service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")

        # Update fields if provided
        if update_data.name is not None:
            service.name = update_data.name

        if update_data.description is not None:
            service.description = update_data.description

        if update_data.price is not None:
            service.price = Decimal(str(update_data.price))

        if update_data.price_display is not None:
            service.price_display = update_data.price_display

        if update_data.duration is not None:
            service.duration = update_data.duration

        if update_data.display_order is not None:
            service.display_order = update_data.display_order

        if update_data.is_active is not None:
            service.is_active = update_data.is_active

        db.commit()
        db.refresh(service)

        logger.info(f"Updated service {service_id}")

        return _service_to_response(service, db)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating service: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{service_id}")
def delete_service(
        service_id: str,
        hard_delete: bool = False,
        db: Session = Depends(get_db)
):
    """
    Delete a service

    Args:
        service_id: Service to delete
        hard_delete: If True, permanently delete. If False, soft delete (set is_active=False)
    """
    try:
        service = db.query(Service).filter(Service.id == service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")

        # Check if service has linked documents
        from app.models.document import Document
        linked_docs_count = db.query(Document).filter(
            Document.related_service_id == service_id,
            Document.is_active == True
        ).count()

        if hard_delete:
            if linked_docs_count > 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot hard delete service with {linked_docs_count} linked documents. "
                           "Delete or unlink documents first, or use soft delete."
                )

            # Hard delete (will set related_service_id to NULL in documents due to ON DELETE SET NULL)
            db.delete(service)
            db.commit()

            logger.info(f"Hard deleted service {service_id}")
            return {
                "success": True,
                "message": "Service permanently deleted"
            }
        else:
            # Soft delete
            service.is_active = False
            db.commit()

            logger.info(f"Soft deleted service {service_id}")
            return {
                "success": True,
                "message": "Service deactivated",
                "linked_documents": linked_docs_count
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting service: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{service_id}/reorder")
def reorder_service(
        service_id: str,
        new_order: int = Field(..., ge=0),
        db: Session = Depends(get_db)
):
    """
    Update the display order of a service
    """
    try:
        service = db.query(Service).filter(Service.id == service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")

        old_order = service.display_order
        service.display_order = new_order
        db.commit()

        logger.info(f"Reordered service {service_id} from {old_order} to {new_order}")

        return {
            "success": True,
            "service_id": service_id,
            "old_order": old_order,
            "new_order": new_order
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reordering service: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{service_id}/documents")
def get_service_documents(
        service_id: str,
        active_only: bool = True,
        db: Session = Depends(get_db)
):
    """
    Get all documents linked to a service
    """
    try:
        from app.models.document import Document

        # Verify service exists
        service = db.query(Service).filter(Service.id == service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")

        query = db.query(Document).filter(Document.related_service_id == service_id)

        if active_only:
            query = query.filter(Document.is_active == True)

        documents = query.order_by(Document.created_at.desc()).all()

        return {
            "service_id": service_id,
            "service_name": service.name,
            "total_documents": len(documents),
            "documents": [doc.to_dict() for doc in documents]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching service documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/migrate-from-catalog/{business_id}")
def migrate_from_service_catalog(
        business_id: str,
        db: Session = Depends(get_db)
):
    """
    Migrate services from old Business.service_catalog JSON to Services table
    (Helper endpoint for manual migration if needed)
    """
    try:
        business = db.query(Business).filter(Business.id == business_id).first()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")

        if not business.service_catalog:
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

            service = Service(
                id=uuid.uuid4(),
                business_id=uuid.UUID(business_id),
                name=service_name,
                description=service_info.get('description'),
                price=price,
                price_display=price_display,
                duration=service_info.get('duration'),
                display_order=idx,
                is_active=True
            )

            db.add(service)
            migrated_count += 1

        db.commit()

        logger.info(f"Migrated {migrated_count} services from service_catalog for business {business_id}")

        return {
            "success": True,
            "message": f"Successfully migrated {migrated_count} services",
            "migrated_count": migrated_count
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error migrating services: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))