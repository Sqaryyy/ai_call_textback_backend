"""
Services and Documents Management Endpoints
RESTful API for managing business services and documents separately
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import logging
import uuid

from app.config.database import get_db
from app.models.auth.user import User
from app.models.business.business import Business
from app.models.business.service import Service
from app.models.business.document import Document, DocumentType, IndexingStatus
from app.api.dependencies import get_current_user
from app.services.ai.rag_service import RAGService

logger = logging.getLogger(__name__)

# Create routers for different resources
services_router = APIRouter(prefix="/services", tags=["services"])
documents_router = APIRouter(prefix="/documents", tags=["documents"])


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_business_or_404(user: User, db: Session) -> Business:
    """Get current user's business or raise 404"""
    if not user.active_business_id:
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    business = db.query(Business).filter(
        Business.id == user.active_business_id
    ).first()

    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    return business


def get_rag_service() -> RAGService:
    """Lazy initialization of RAG service"""
    return RAGService()


# ============================================================================
# SERVICES ENDPOINTS
# ============================================================================

@services_router.get("", response_model=List[dict])
async def list_services(
        include_inactive: bool = Query(False, description="Include inactive services"),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    List all services for the business.

    Query Parameters:
    - include_inactive: If False (default), only returns active services
    """
    business = get_business_or_404(current_user, db)

    query = db.query(Service).filter(Service.business_id == business.id)

    if not include_inactive:
        query = query.filter(Service.is_active == True)

    services = query.order_by(Service.display_order).all()

    return [service.to_dict() for service in services]


@services_router.post("", response_model=dict)
async def create_service(
        name: str = Query(..., min_length=1, max_length=200),
        description: Optional[str] = Query(None, max_length=2000),
        price: Optional[float] = Query(None, ge=0),
        price_display: Optional[str] = Query(None, max_length=50),
        duration: Optional[int] = Query(None, ge=1, description="Duration in minutes"),
        display_order: int = Query(0, ge=0),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Create a new service for the business.

    Parameters:
    - name: Service name (required)
    - description: Service description
    - price: Numeric price (e.g., 99.99)
    - price_display: Custom price text (e.g., "Starting at $99")
    - duration: Service duration in minutes
    - display_order: Order for UI display
    """
    business = get_business_or_404(current_user, db)

    # Create new service
    service = Service(
        business_id=business.id,
        name=name,
        description=description,
        price=price,
        price_display=price_display,
        duration=duration,
        display_order=display_order,
        is_active=True
    )

    try:
        db.add(service)
        db.commit()
        db.refresh(service)
        logger.info(f"Created service {service.id} for business {business.id}")

        # Trigger reindexing since services are part of knowledge base
        rag_service = get_rag_service()
        await rag_service.index_business_knowledge(
            business_id=str(business.id),
            db=db,
            force_reindex=False
        )

        return service.to_dict()

    except Exception as e:
        db.rollback()
        logger.error(f"Error creating service: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create service: {str(e)}")


@services_router.get("/{service_id}", response_model=dict)
async def get_service(
        service_id: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Get a specific service"""
    business = get_business_or_404(current_user, db)

    try:
        service_uuid = uuid.UUID(service_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid service ID format")

    service = db.query(Service).filter(
        Service.id == service_uuid,
        Service.business_id == business.id
    ).first()

    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    return service.to_dict()


@services_router.put("/{service_id}", response_model=dict)
async def update_service(
        service_id: str,
        name: Optional[str] = Query(None, min_length=1, max_length=200),
        description: Optional[str] = Query(None, max_length=2000),
        price: Optional[float] = Query(None, ge=0),
        price_display: Optional[str] = Query(None, max_length=50),
        duration: Optional[int] = Query(None, ge=1),
        display_order: Optional[int] = Query(None, ge=0),
        is_active: Optional[bool] = Query(None),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Update a service. Only provide fields you want to change.
    """
    business = get_business_or_404(current_user, db)

    try:
        service_uuid = uuid.UUID(service_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid service ID format")

    service = db.query(Service).filter(
        Service.id == service_uuid,
        Service.business_id == business.id
    ).first()

    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    # Update only provided fields
    updates = {
        "name": name,
        "description": description,
        "price": price,
        "price_display": price_display,
        "duration": duration,
        "display_order": display_order,
        "is_active": is_active
    }

    changed = False
    for field, value in updates.items():
        if value is not None:
            setattr(service, field, value)
            changed = True

    if not changed:
        return service.to_dict()

    try:
        db.commit()
        db.refresh(service)
        logger.info(f"Updated service {service.id}")

        # Trigger reindexing
        rag_service = get_rag_service()
        await rag_service.index_business_knowledge(
            business_id=str(business.id),
            db=db,
            force_reindex=False
        )

        return service.to_dict()

    except Exception as e:
        db.rollback()
        logger.error(f"Error updating service: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update service: {str(e)}")


@services_router.delete("/{service_id}")
async def delete_service(
        service_id: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Delete a service (soft delete - marks as inactive).
    """
    business = get_business_or_404(current_user, db)

    try:
        service_uuid = uuid.UUID(service_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid service ID format")

    service = db.query(Service).filter(
        Service.id == service_uuid,
        Service.business_id == business.id
    ).first()

    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    try:
        service.is_active = False
        db.commit()
        logger.info(f"Deleted (deactivated) service {service.id}")

        # Trigger reindexing
        rag_service = get_rag_service()
        await rag_service.index_business_knowledge(
            business_id=str(business.id),
            db=db,
            force_reindex=False
        )

        return {"success": True, "message": "Service deleted"}

    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting service: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete service: {str(e)}")


# ============================================================================
# DOCUMENTS ENDPOINTS
# ============================================================================

@documents_router.get("", response_model=List[dict])
async def list_documents(
        doc_type: Optional[str] = Query(None, description="Filter by document type"),
        include_inactive: bool = Query(False),
        related_service_id: Optional[str] = Query(None, description="Filter by related service"),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    List all documents for the business.

    Query Parameters:
    - doc_type: Filter by type (pdf, note, policy, faq, guide, general)
    - include_inactive: Include inactive documents
    - related_service_id: Filter by related service
    """
    business = get_business_or_404(current_user, db)

    query = db.query(Document).filter(Document.business_id == business.id)

    if not include_inactive:
        query = query.filter(Document.is_active == True)

    if doc_type:
        try:
            doc_type_enum = DocumentType(doc_type)
            query = query.filter(Document.type == doc_type_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid document type: {doc_type}")

    if related_service_id:
        try:
            service_uuid = uuid.UUID(related_service_id)
            query = query.filter(Document.related_service_id == service_uuid)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid service ID format")

    documents = query.order_by(Document.created_at.desc()).all()

    return [doc.to_dict() for doc in documents]


@documents_router.post("", response_model=dict)
async def create_document(
        title: str = Query(..., min_length=1, max_length=500),
        doc_type: str = Query(..., description="Document type: pdf, note, policy, faq, guide, general"),
        original_content: str = Query(..., description="Text content of the document"),
        related_service_id: Optional[str] = Query(None),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Create a new document for the business.

    Parameters:
    - title: Document title
    - doc_type: Type of document (pdf, note, policy, faq, guide, general)
    - original_content: The actual text content
    - related_service_id: Optional service this document is related to
    """
    business = get_business_or_404(current_user, db)

    # Validate document type
    try:
        doc_type_enum = DocumentType(doc_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid document type. Must be one of: {', '.join([e.value for e in DocumentType])}"
        )

    # Validate service ID if provided
    related_service_uuid = None
    if related_service_id:
        try:
            related_service_uuid = uuid.UUID(related_service_id)
            # Verify service belongs to this business
            service = db.query(Service).filter(
                Service.id == related_service_uuid,
                Service.business_id == business.id
            ).first()
            if not service:
                raise HTTPException(status_code=404, detail="Related service not found")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid service ID format")

    # Create document
    document = Document(
        business_id=business.id,
        title=title,
        type=doc_type_enum,
        original_content=original_content,
        related_service_id=related_service_uuid,
        indexing_status=IndexingStatus.PENDING,
        is_active=True
    )

    try:
        db.add(document)
        db.commit()
        db.refresh(document)
        logger.info(f"Created document {document.id} for business {business.id}")

        # Trigger indexing
        rag_service = get_rag_service()
        await rag_service.index_business_knowledge(
            business_id=str(business.id),
            db=db,
            force_reindex=False
        )

        return document.to_dict()

    except Exception as e:
        db.rollback()
        logger.error(f"Error creating document: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create document: {str(e)}")


@documents_router.get("/{document_id}", response_model=dict)
async def get_document(
        document_id: str,
        include_content: bool = Query(True),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Get a specific document.

    Parameters:
    - include_content: Whether to include the full original_content field
    """
    business = get_business_or_404(current_user, db)

    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID format")

    document = db.query(Document).filter(
        Document.id == doc_uuid,
        Document.business_id == business.id
    ).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return document.to_dict(include_content=include_content)


@documents_router.put("/{document_id}", response_model=dict)
async def update_document(
        document_id: str,
        title: Optional[str] = Query(None, min_length=1, max_length=500),
        original_content: Optional[str] = Query(None),
        related_service_id: Optional[str] = Query(None),
        is_active: Optional[bool] = Query(None),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Update a document. Only provide fields you want to change.
    Updating content will trigger reindexing.
    """
    business = get_business_or_404(current_user, db)

    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID format")

    document = db.query(Document).filter(
        Document.id == doc_uuid,
        Document.business_id == business.id
    ).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Update fields
    changed = False
    if title is not None:
        document.title = title
        changed = True

    if original_content is not None:
        document.original_content = original_content
        document.indexing_status = IndexingStatus.PENDING
        changed = True

    if related_service_id is not None:
        try:
            service_uuid = uuid.UUID(related_service_id)
            service = db.query(Service).filter(
                Service.id == service_uuid,
                Service.business_id == business.id
            ).first()
            if not service:
                raise HTTPException(status_code=404, detail="Related service not found")
            document.related_service_id = service_uuid
            changed = True
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid service ID format")

    if is_active is not None:
        document.is_active = is_active
        changed = True

    if not changed:
        return document.to_dict()

    try:
        db.commit()
        db.refresh(document)
        logger.info(f"Updated document {document.id}")

        # Trigger reindexing
        rag_service = get_rag_service()
        await rag_service.index_business_knowledge(
            business_id=str(business.id),
            db=db,
            force_reindex=False
        )

        return document.to_dict()

    except Exception as e:
        db.rollback()
        logger.error(f"Error updating document: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update document: {str(e)}")


@documents_router.delete("/{document_id}")
async def delete_document(
        document_id: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Delete a document (soft delete - marks as inactive).
    """
    business = get_business_or_404(current_user, db)

    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID format")

    document = db.query(Document).filter(
        Document.id == doc_uuid,
        Document.business_id == business.id
    ).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        document.is_active = False
        db.commit()
        logger.info(f"Deleted (deactivated) document {document.id}")

        # Trigger reindexing
        rag_service = get_rag_service()
        await rag_service.index_business_knowledge(
            business_id=str(business.id),
            db=db,
            force_reindex=False
        )

        return {"success": True, "message": "Document deleted"}

    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting document: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")