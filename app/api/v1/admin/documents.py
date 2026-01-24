"""
Admin Documents API
System admins can view and manage documents across all businesses
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from app.config.database import get_db
from app.models.auth.user import User
from app.models.business.business import Business
from app.models.business.document import Document, DocumentChunk, DocumentType, IndexingStatus
from app.models.business.service import Service
from app.api.dependencies import require_platform_admin
from app.services.ai.rag_service import RAGService
from app.utils.logger import get_logger
from app.schemas.admin.documents import (
    ReindexRequest,
    DocumentResponse,
    DocumentDetailResponse,
    DocumentChunkResponse,
    BusinessDocumentStatsResponse,
    DocumentCreate,
    DocumentUpdate
)

logger = get_logger(__name__)


# ============================================================================
# Router
# ============================================================================

admin_documents_router = APIRouter(
    prefix="/documents",
    tags=["admin-documents"]
)


# ============================================================================
# Helper Functions
# ============================================================================

def get_rag_service() -> RAGService:
    """Lazy initialization of RAG service"""
    return RAGService()


def _document_to_response(document: Document, db: Session) -> DocumentResponse:
    """Convert Document to response with business context"""
    business = db.query(Business).filter(Business.id == document.business_id).first()
    business_name = business.name if business else "Unknown"

    service_name = None
    if document.related_service_id:
        service = db.query(Service).filter(Service.id == document.related_service_id).first()
        service_name = service.name if service else None

    doc_dict = document.to_dict()
    doc_dict['business_name'] = business_name
    doc_dict['related_service_name'] = service_name

    return DocumentResponse(**doc_dict)


# ============================================================================
# DOCUMENT ENDPOINTS
# ============================================================================

@admin_documents_router.get("/", response_model=List[DocumentResponse])
async def list_all_documents(
    business_id: Optional[UUID] = Query(None, description="Filter by business ID"),
    type: Optional[DocumentType] = Query(None, description="Filter by document type"),
    active_only: bool = Query(True, description="Show only active documents"),
    service_id: Optional[UUID] = Query(None, description="Filter by related service"),
    indexing_status: Optional[IndexingStatus] = Query(None, description="Filter by indexing status"),
    current_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db)
):
    """List all documents across all businesses (admin can see all)"""
    # Build filter description for logging
    filters_applied = []
    if business_id:
        filters_applied.append("business_id")
    if type:
        filters_applied.append(f"type={type.value}")
    if not active_only:
        filters_applied.append("including_inactive")
    if service_id:
        filters_applied.append("service_id")
    if indexing_status:
        filters_applied.append(f"status={indexing_status.value}")

    filter_str = f" with filters: {', '.join(filters_applied)}" if filters_applied else ""
    logger.info(f"Admin {current_user.id} listing documents{filter_str}")

    query = db.query(Document)

    if business_id:
        query = query.filter(Document.business_id == business_id)

    if active_only:
        query = query.filter(Document.is_active == True)

    if type:
        query = query.filter(Document.type == type)

    if service_id:
        query = query.filter(Document.related_service_id == service_id)

    if indexing_status:
        query = query.filter(Document.indexing_status == indexing_status)

    documents = query.order_by(Document.created_at.desc()).all()

    logger.info(f"Returning {len(documents)} documents")

    return [_document_to_response(doc, db) for doc in documents]


@admin_documents_router.get("/stats", response_model=dict)
async def get_platform_document_stats(
    business_id: Optional[UUID] = Query(None, description="Filter by business ID"),
    current_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db)
):
    """Get platform-wide document statistics"""
    filter_info = f" for business {business_id}" if business_id else " (platform-wide)"
    logger.info(f"Admin {current_user.id} requesting document stats{filter_info}")

    query = db.query(Document)

    if business_id:
        query = query.filter(Document.business_id == business_id)

    total_documents = query.count()
    active_documents = query.filter(Document.is_active == True).count()

    # By type
    type_counts = db.query(
        Document.type,
        db.func.count(Document.id)
    )
    if business_id:
        type_counts = type_counts.filter(Document.business_id == business_id)
    type_counts = type_counts.group_by(Document.type).all()
    documents_by_type = {doc_type.value: count for doc_type, count in type_counts}

    # By status
    status_counts = db.query(
        Document.indexing_status,
        db.func.count(Document.id)
    )
    if business_id:
        status_counts = status_counts.filter(Document.business_id == business_id)
    status_counts = status_counts.group_by(Document.indexing_status).all()
    documents_by_status = {status.value: count for status, count in status_counts}

    failed_documents = query.filter(
        Document.indexing_status == IndexingStatus.FAILED
    ).count()

    # Chunk count
    chunk_query = db.query(db.func.count(DocumentChunk.id))
    if business_id:
        chunk_query = chunk_query.join(Document).filter(Document.business_id == business_id)
    total_chunks = chunk_query.scalar()

    logger.info(
        f"Stats calculated: {total_documents} total docs, {active_documents} active, "
        f"{failed_documents} failed, type distribution: {documents_by_type}"
    )

    return {
        "total_documents": total_documents,
        "active_documents": active_documents,
        "inactive_documents": total_documents - active_documents,
        "documents_by_type": documents_by_type,
        "documents_by_status": documents_by_status,
        "failed_documents": failed_documents,
        "total_chunks": total_chunks
    }


@admin_documents_router.get("/business/{business_id}/stats", response_model=BusinessDocumentStatsResponse)
async def get_business_document_stats(
    business_id: UUID,
    current_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db)
):
    """Get document statistics for a specific business"""
    logger.info(f"Admin {current_user.id} requesting document stats for business {business_id}")

    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        logger.warning(f"Business {business_id} not found - requested by admin {current_user.id}")
        raise HTTPException(status_code=404, detail="Business not found")

    query = db.query(Document).filter(Document.business_id == business_id)

    total_documents = query.count()
    active_documents = query.filter(Document.is_active == True).count()

    # By type
    type_counts = db.query(
        Document.type,
        db.func.count(Document.id)
    ).filter(Document.business_id == business_id).group_by(Document.type).all()
    documents_by_type = {doc_type.value: count for doc_type, count in type_counts}

    # By status
    status_counts = db.query(
        Document.indexing_status,
        db.func.count(Document.id)
    ).filter(Document.business_id == business_id).group_by(Document.indexing_status).all()
    documents_by_status = {status.value: count for status, count in status_counts}

    failed_documents = query.filter(
        Document.indexing_status == IndexingStatus.FAILED
    ).count()

    total_chunks = db.query(db.func.count(DocumentChunk.id)).join(
        Document
    ).filter(Document.business_id == business_id).scalar()

    logger.info(f"Business stats: {total_documents} docs, {total_chunks} chunks, {failed_documents} failed")

    return BusinessDocumentStatsResponse(
        business_id=str(business_id),
        business_name=business.name,
        total_documents=total_documents,
        active_documents=active_documents,
        documents_by_type=documents_by_type,
        documents_by_status=documents_by_status,
        total_chunks=total_chunks,
        failed_documents=failed_documents
    )


@admin_documents_router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: UUID,
    current_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db)
):
    """Get any document by ID with full content (admin can view all)"""
    logger.info(f"Admin {current_user.id} viewing document {document_id}")

    document = db.query(Document).filter(Document.id == document_id).first()

    if not document:
        logger.warning(f"Document {document_id} not found - requested by admin {current_user.id}")
        raise HTTPException(status_code=404, detail="Document not found")

    logger.debug(
        f"Retrieved document - Business ID: {document.business_id}, "
        f"Type: {document.type.value}, Status: {document.indexing_status.value}"
    )

    doc_dict = document.to_dict(include_content=True)

    business = db.query(Business).filter(Business.id == document.business_id).first()
    doc_dict['business_name'] = business.name if business else "Unknown"

    service_name = None
    if document.related_service_id:
        service = db.query(Service).filter(Service.id == document.related_service_id).first()
        service_name = service.name if service else None
    doc_dict['related_service_name'] = service_name

    return DocumentDetailResponse(**doc_dict)


@admin_documents_router.post("/", response_model=DocumentResponse, status_code=201)
async def create_document(
    document_data: DocumentCreate,
    current_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db)
):
    """Create a new text document for any business (admin only)"""
    logger.info(
        f"Admin {current_user.id} creating document for business {document_data.business_id} - "
        f"Type: {document_data.type.value}, Title: '{document_data.title}'"
    )

    # Verify business exists
    business = db.query(Business).filter(
        Business.id == document_data.business_id
    ).first()
    if not business:
        logger.warning(f"Create failed - business {document_data.business_id} not found")
        raise HTTPException(status_code=404, detail="Business not found")

    # Validate service exists if provided
    if document_data.related_service_id:
        service = db.query(Service).filter(
            Service.id == document_data.related_service_id,
            Service.business_id == document_data.business_id
        ).first()
        if not service:
            logger.warning(f"Create failed - service {document_data.related_service_id} not found")
            raise HTTPException(status_code=404, detail="Related service not found")

    document = Document(
        business_id=document_data.business_id,
        title=document_data.title,
        type=document_data.type,
        original_content=document_data.original_content,
        related_service_id=document_data.related_service_id,
        indexing_status=IndexingStatus.PENDING,
        is_active=True
    )

    try:
        db.add(document)
        db.commit()
        db.refresh(document)
        logger.info(f"Document {document.id} created successfully for business {business.id}")

        # Trigger indexing
        rag_service = get_rag_service()
        await rag_service.index_business_knowledge(
            business_id=str(business.id),
            db=db,
            force_reindex=False
        )

        return _document_to_response(document, db)

    except Exception as e:
        db.rollback()
        logger.error(f"Error creating document: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create document: {str(e)}")


@admin_documents_router.put("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: UUID,
    document_data: DocumentUpdate,
    current_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db)
):
    """Update any document (admin can modify all)"""
    # Build update description for logging
    updates = []
    if document_data.title is not None:
        updates.append("title")
    if document_data.type is not None:
        updates.append(f"type={document_data.type.value}")
    if document_data.original_content is not None:
        updates.append("content")
    if document_data.related_service_id is not None:
        updates.append("related_service_id")
    if document_data.is_active is not None:
        updates.append(f"is_active={document_data.is_active}")

    update_str = ', '.join(updates) if updates else "no changes"
    logger.info(f"Admin {current_user.id} updating document {document_id} - Updates: {update_str}")

    document = db.query(Document).filter(Document.id == document_id).first()

    if not document:
        logger.warning(f"Update failed - document {document_id} not found")
        raise HTTPException(status_code=404, detail="Document not found")

    # Validate service exists if provided
    if document_data.related_service_id:
        service = db.query(Service).filter(
            Service.id == document_data.related_service_id,
            Service.business_id == document.business_id
        ).first()
        if not service:
            logger.warning(f"Update failed - service {document_data.related_service_id} not found")
            raise HTTPException(status_code=404, detail="Related service not found")

    # Check if content is being updated (versioning logic)
    content_changed = (
        document_data.original_content is not None
        and document_data.original_content != document.original_content
    )

    if content_changed:
        logger.info(f"Content changed for document {document_id} - creating new version")

        # Create new version
        new_document = Document(
            business_id=document.business_id,
            title=document_data.title or document.title,
            type=document_data.type or document.type,
            original_content=document_data.original_content,
            related_service_id=document_data.related_service_id or document.related_service_id,
            previous_version_id=document.id,
            indexing_status=IndexingStatus.PENDING,
            is_active=True
        )

        # Deactivate old version
        document.is_active = False

        try:
            db.add(new_document)
            db.commit()
            db.refresh(new_document)
            logger.info(f"New document version created: {document.id} -> {new_document.id}")

            # Trigger indexing
            rag_service = get_rag_service()
            await rag_service.index_business_knowledge(
                business_id=str(document.business_id),
                db=db,
                force_reindex=False
            )

            return _document_to_response(new_document, db)

        except Exception as e:
            db.rollback()
            logger.error(f"Error creating document version: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to update document: {str(e)}")
    else:
        # Just update metadata
        update_data = document_data.model_dump(exclude_unset=True, exclude={'original_content'})
        for field, value in update_data.items():
            setattr(document, field, value)

        try:
            db.commit()
            db.refresh(document)
            logger.info(f"Document {document.id} metadata updated successfully")

            return _document_to_response(document, db)

        except Exception as e:
            db.rollback()
            logger.error(f"Error updating document: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to update document: {str(e)}")


@admin_documents_router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: UUID,
    current_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db)
):
    """Soft delete any document (admin can delete all)"""
    logger.info(f"Admin {current_user.id} soft deleting document {document_id}")

    document = db.query(Document).filter(Document.id == document_id).first()

    if not document:
        logger.warning(f"Delete failed - document {document_id} not found")
        raise HTTPException(status_code=404, detail="Document not found")

    business_id = document.business_id

    try:
        document.is_active = False
        db.commit()
        logger.info(f"Document {document_id} soft deleted - Business ID: {business_id}")

        # Trigger reindexing
        rag_service = get_rag_service()
        await rag_service.index_business_knowledge(
            business_id=str(business_id),
            db=db,
            force_reindex=False
        )

        return None

    except Exception as e:
        db.rollback()
        logger.error(f"Error soft deleting document: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")


@admin_documents_router.delete("/{document_id}/hard", status_code=204)
async def hard_delete_document(
    document_id: UUID,
    current_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db)
):
    """Permanently delete any document and all its chunks (admin only)"""
    logger.warning(f"Admin {current_user.id} attempting to HARD DELETE document {document_id}")

    document = db.query(Document).filter(Document.id == document_id).first()

    if not document:
        logger.warning(f"Hard delete failed - document {document_id} not found")
        raise HTTPException(status_code=404, detail="Document not found")

    business_id = document.business_id
    document_title = document.title
    document_type = document.type.value

    try:
        db.delete(document)
        db.commit()
        logger.warning(
            f"Document HARD DELETED permanently - "
            f"Document ID: {document_id}, Title: '{document_title}', Type: {document_type}, "
            f"Business ID: {business_id}, Deleted by: {current_user.id}"
        )

        # Trigger reindexing
        rag_service = get_rag_service()
        await rag_service.index_business_knowledge(
            business_id=str(business_id),
            db=db,
            force_reindex=False
        )

        return None

    except Exception as e:
        db.rollback()
        logger.error(f"Error hard deleting document: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")


@admin_documents_router.post("/{document_id}/reindex", response_model=DocumentResponse)
async def reindex_document(
    document_id: UUID,
    current_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db)
):
    """Trigger re-indexing of any document (admin only)"""
    logger.info(f"Admin {current_user.id} triggering reindex for document {document_id}")

    document = db.query(Document).filter(Document.id == document_id).first()

    if not document:
        logger.warning(f"Reindex failed - document {document_id} not found")
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        # Reset indexing status
        document.indexing_status = IndexingStatus.PENDING
        document.indexing_error = None
        document.indexed_at = None

        # Deactivate existing chunks
        chunks_deactivated = db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        ).update({"is_active": False})

        db.commit()
        db.refresh(document)
        logger.info(f"Reindex initiated for document {document_id} - {chunks_deactivated} chunks deactivated")

        # Trigger indexing
        rag_service = get_rag_service()
        await rag_service.index_business_knowledge(
            business_id=str(document.business_id),
            db=db,
            force_reindex=True
        )

        return _document_to_response(document, db)

    except Exception as e:
        db.rollback()
        logger.error(f"Error reindexing document: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reindex document: {str(e)}")


@admin_documents_router.post("/reindex-batch", response_model=dict)
async def reindex_documents_batch(
    request: ReindexRequest,
    current_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db)
):
    """Trigger re-indexing for multiple documents (admin only)"""
    logger.info(f"Admin {current_user.id} triggering batch reindex for {len(request.document_ids)} documents")

    documents = db.query(Document).filter(
        Document.id.in_(request.document_ids)
    ).all()

    if len(documents) != len(request.document_ids):
        logger.warning(f"Batch reindex failed - some documents not found")
        raise HTTPException(
            status_code=404,
            detail="One or more documents not found"
        )

    try:
        reindexed_count = 0
        businesses_to_reindex = set()

        for document in documents:
            document.indexing_status = IndexingStatus.PENDING
            document.indexing_error = None
            document.indexed_at = None
            businesses_to_reindex.add(str(document.business_id))

            # Deactivate existing chunks
            db.query(DocumentChunk).filter(
                DocumentChunk.document_id == document.id
            ).update({"is_active": False})

            reindexed_count += 1

        db.commit()
        logger.info(
            f"Batch reindex initiated - {reindexed_count} documents, "
            f"{len(businesses_to_reindex)} businesses affected"
        )

        # Trigger indexing for affected businesses
        rag_service = get_rag_service()
        for business_id in businesses_to_reindex:
            await rag_service.index_business_knowledge(
                business_id=business_id,
                db=db,
                force_reindex=True
            )

        return {
            "message": f"Re-indexing triggered for {reindexed_count} documents",
            "document_ids": [str(doc.id) for doc in documents],
            "businesses_affected": len(businesses_to_reindex)
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error batch reindexing documents: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reindex documents: {str(e)}")


@admin_documents_router.get("/{document_id}/chunks", response_model=List[DocumentChunkResponse])
async def get_document_chunks(
    document_id: UUID,
    active_only: bool = Query(True, description="Show only active chunks"),
    current_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db)
):
    """Get all chunks for any document (admin can view all)"""
    logger.info(f"Admin {current_user.id} viewing chunks for document {document_id}")

    document = db.query(Document).filter(Document.id == document_id).first()

    if not document:
        logger.warning(f"Document {document_id} not found - requested by admin {current_user.id}")
        raise HTTPException(status_code=404, detail="Document not found")

    query = db.query(DocumentChunk).filter(
        DocumentChunk.document_id == document_id
    )

    if active_only:
        query = query.filter(DocumentChunk.is_active == True)

    chunks = query.order_by(DocumentChunk.chunk_index).all()

    logger.info(f"Returning {len(chunks)} chunks for document {document_id}")

    return [DocumentChunkResponse(**chunk.to_dict()) for chunk in chunks]


@admin_documents_router.get("/{document_id}/versions", response_model=List[DocumentResponse])
async def get_document_versions(
    document_id: UUID,
    current_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db)
):
    """Get version history for any document (admin only)"""
    logger.info(f"Admin {current_user.id} viewing version history for document {document_id}")

    document = db.query(Document).filter(Document.id == document_id).first()

    if not document:
        logger.warning(f"Document {document_id} not found - requested by admin {current_user.id}")
        raise HTTPException(status_code=404, detail="Document not found")

    versions = [document]

    # Walk back through previous versions
    current = document
    while current.previous_version_id:
        previous = db.query(Document).filter(
            Document.id == current.previous_version_id
        ).first()
        if previous:
            versions.append(previous)
            current = previous
        else:
            break

    logger.info(f"Returning {len(versions)} versions for document {document_id}")

    return [_document_to_response(doc, db) for doc in versions]


@admin_documents_router.post("/{document_id}/restore/{version_id}", response_model=DocumentResponse)
async def restore_document_version(
    document_id: UUID,
    version_id: UUID,
    current_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db)
):
    """Restore a previous version of any document (admin only)"""
    logger.info(f"Admin {current_user.id} restoring document {document_id} to version {version_id}")

    current_doc = db.query(Document).filter(Document.id == document_id).first()
    version_doc = db.query(Document).filter(Document.id == version_id).first()

    if not current_doc or not version_doc:
        logger.warning(f"Restore failed - document {document_id} or version {version_id} not found")
        raise HTTPException(status_code=404, detail="Document or version not found")

    try:
        # Create new version based on old content
        restored_document = Document(
            business_id=version_doc.business_id,
            title=version_doc.title,
            type=version_doc.type,
            original_content=version_doc.original_content,
            related_service_id=version_doc.related_service_id,
            previous_version_id=current_doc.id,
            indexing_status=IndexingStatus.PENDING,
            is_active=True
        )

        # Deactivate current version
        current_doc.is_active = False

        db.add(restored_document)
        db.commit()
        db.refresh(restored_document)
        logger.info(f"Document version restored: {version_id} -> {restored_document.id}")

        # Trigger indexing
        rag_service = get_rag_service()
        await rag_service.index_business_knowledge(
            business_id=str(version_doc.business_id),
            db=db,
            force_reindex=False
        )

        return _document_to_response(restored_document, db)

    except Exception as e:
        db.rollback()
        logger.error(f"Error restoring document version: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to restore document: {str(e)}")