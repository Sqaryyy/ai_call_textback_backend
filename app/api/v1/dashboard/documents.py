"""
Document Management API Endpoints
Handles CRUD operations for documents and document indexing
UPDATED: Added comprehensive logging with user audit trail
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import Optional
import uuid

from app.config.database import get_db
from app.models.auth.user import User
from app.api.dependencies import get_current_user
from app.models.business.document import Document, DocumentType
from app.models.business.service import Service
from app.services.ai.document_indexer import DocumentIndexer
from app.schemas.documents import (
    DocumentCreate,
    DocumentUpdate,
    DocumentResponse,
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentIndexResponse
)
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["documents"])


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/", response_model=DocumentResponse)
async def create_text_document(
        document: DocumentCreate,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Create a new text-based document (NOTE, POLICY, FAQ, etc.)
    Requires authenticated session.
    """
    logger.info(
        f"User {current_user.id} creating {document.type} document - "
        f"Business: {document.business_id}, Title: '{document.title}'"
    )

    try:
        indexer = DocumentIndexer()

        # Validate business exists
        from app.models.business.business import Business
        business = db.query(Business).filter(Business.id == document.business_id).first()
        if not business:
            logger.warning(
                f"Document creation failed: Business {document.business_id} not found - "
                f"User: {current_user.id}"
            )
            raise HTTPException(status_code=404, detail="Business not found")

        # Validate service if provided
        service_id = None
        if document.related_service_id:
            service = db.query(Service).filter(
                Service.id == document.related_service_id,
                Service.business_id == document.business_id
            ).first()
            if not service:
                logger.warning(
                    f"Document creation failed: Service {document.related_service_id} not found - "
                    f"Business: {document.business_id}, User: {current_user.id}"
                )
                raise HTTPException(status_code=404, detail="Service not found")
            service_id = uuid.UUID(document.related_service_id)
            logger.debug(f"Document linked to service {service_id}")

        content_length = len(document.content) if document.content else 0
        logger.debug(f"Document content length: {content_length} characters")

        # Create and index document
        result = await indexer.create_and_index_document(
            business_id=uuid.UUID(document.business_id),
            title=document.title,
            doc_type=document.type,
            content=document.content,
            db=db,
            related_service_id=service_id
        )

        if not result["success"]:
            logger.error(
                f"Document indexing failed - Business: {document.business_id}, "
                f"Title: '{document.title}', Error: {result['message']}"
            )
            raise HTTPException(status_code=500, detail=result["message"])

        # Fetch and return created document
        doc = db.query(Document).filter(Document.id == result["document_id"]).first()

        logger.info(
            f"Document created successfully - "
            f"Document ID: {result['document_id']}, Type: {document.type}, "
            f"Business: {document.business_id}, Chunks: {result.get('chunks_created', 0)}, "
            f"User: {current_user.id}"
        )

        return DocumentResponse(**doc.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error creating document - Business: {document.business_id}, "
            f"User: {current_user.id}: {e}",
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload", response_model=DocumentResponse)
async def upload_pdf_document(
        business_id: str = Form(...),
        title: str = Form(...),
        related_service_id: Optional[str] = Form(None),
        file: UploadFile = File(...),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Upload and index a PDF document
    Requires authenticated session.
    """
    logger.info(
        f"User {current_user.id} uploading PDF document - "
        f"Business: {business_id}, Title: '{title}', Filename: '{file.filename}'"
    )

    try:
        # Validate file type
        if not file.filename.lower().endswith('.pdf'):
            logger.warning(
                f"PDF upload failed: Invalid file type '{file.filename}' - User: {current_user.id}"
            )
            raise HTTPException(status_code=400, detail="Only PDF files are supported")

        indexer = DocumentIndexer()

        # Validate business exists
        from app.models.business.business import Business
        business = db.query(Business).filter(Business.id == business_id).first()
        if not business:
            logger.warning(
                f"PDF upload failed: Business {business_id} not found - User: {current_user.id}"
            )
            raise HTTPException(status_code=404, detail="Business not found")

        # Validate service if provided
        service_id = None
        if related_service_id:
            service = db.query(Service).filter(
                Service.id == related_service_id,
                Service.business_id == business_id
            ).first()
            if not service:
                logger.warning(
                    f"PDF upload failed: Service {related_service_id} not found - "
                    f"Business: {business_id}, User: {current_user.id}"
                )
                raise HTTPException(status_code=404, detail="Service not found")
            service_id = uuid.UUID(related_service_id)
            logger.debug(f"PDF linked to service {service_id}")

        # Read file content
        file_content = await file.read()
        file_size = len(file_content)

        logger.debug(f"PDF file read - Size: {file_size} bytes ({file_size / 1024:.2f} KB)")

        # Create and index document
        result = await indexer.create_and_index_document(
            business_id=uuid.UUID(business_id),
            title=title,
            doc_type=DocumentType.PDF,
            content="",  # Will be extracted from PDF
            db=db,
            file_content=file_content,
            original_filename=file.filename,
            file_size=file_size,
            related_service_id=service_id
        )

        if not result["success"]:
            logger.error(
                f"PDF indexing failed - Business: {business_id}, "
                f"Filename: '{file.filename}', Error: {result['message']}"
            )
            raise HTTPException(status_code=500, detail=result["message"])

        # Fetch and return created document
        doc = db.query(Document).filter(Document.id == result["document_id"]).first()

        logger.info(
            f"PDF document uploaded successfully - "
            f"Document ID: {result['document_id']}, Filename: '{file.filename}', "
            f"Size: {file_size / 1024:.2f} KB, Business: {business_id}, "
            f"Chunks: {result.get('chunks_created', 0)}, User: {current_user.id}"
        )

        return DocumentResponse(**doc.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error uploading PDF - Business: {business_id}, "
            f"Filename: '{file.filename}', User: {current_user.id}: {e}",
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{document_id}", response_model=DocumentDetailResponse)
def get_document(
        document_id: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Get document by ID with full content
    Requires authenticated session.
    """
    logger.info(f"User {current_user.id} requesting document {document_id}")

    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            logger.warning(
                f"Document {document_id} not found - User: {current_user.id}"
            )
            raise HTTPException(status_code=404, detail="Document not found")

        # Use to_dict with include_content=True to get original_content
        doc_dict = document.to_dict(include_content=True)

        logger.info(
            f"Document retrieved - "
            f"Document ID: {document_id}, Type: {document.type}, "
            f"Title: '{document.title}', Business: {document.business_id}"
        )

        return DocumentDetailResponse(**doc_dict)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error fetching document {document_id} - User: {current_user.id}: {e}",
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/business/{business_id}", response_model=DocumentListResponse)
def list_business_documents(
        business_id: str,
        document_type: Optional[DocumentType] = None,
        service_id: Optional[str] = None,
        active_only: bool = True,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    List all documents for a business with optional filters
    Requires authenticated session.
    """
    # Build filter description for logging
    filters = []
    if document_type:
        filters.append(f"type={document_type}")
    if service_id:
        filters.append(f"service={service_id}")
    if active_only:
        filters.append("active_only=True")

    filter_str = ", ".join(filters) if filters else "no filters"

    logger.info(
        f"User {current_user.id} listing documents for business {business_id} - "
        f"Filters: {filter_str}"
    )

    try:
        query = db.query(Document).filter(Document.business_id == business_id)

        if active_only:
            query = query.filter(Document.is_active == True)

        if document_type:
            query = query.filter(Document.type == document_type)

        if service_id:
            query = query.filter(Document.related_service_id == service_id)

        documents = query.order_by(Document.created_at.desc()).all()

        logger.info(
            f"Returned {len(documents)} documents for business {business_id}"
        )

        return DocumentListResponse(
            total=len(documents),
            documents=[DocumentResponse(**doc.to_dict()) for doc in documents]
        )

    except Exception as e:
        logger.error(
            f"Error listing documents - Business: {business_id}, User: {current_user.id}: {e}",
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{document_id}", response_model=DocumentResponse)
async def update_document(
        document_id: str,
        update_data: DocumentUpdate,
        create_version: bool = False,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Update a document
    Requires authenticated session.

    Args:
        document_id: Document to update
        update_data: Fields to update
        create_version: If True, create a new version instead of updating in place
    """
    logger.info(
        f"User {current_user.id} updating document {document_id} - "
        f"Create version: {create_version}"
    )

    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            logger.warning(
                f"Document update failed: Document {document_id} not found - "
                f"User: {current_user.id}"
            )
            raise HTTPException(status_code=404, detail="Document not found")

        indexer = DocumentIndexer()

        if create_version:
            logger.debug(f"Creating new version of document {document_id}")

            # Create new version
            result = await indexer.update_document_version(
                document_id=uuid.UUID(document_id),
                new_content=update_data.content or document.original_content,
                db=db,
                new_title=update_data.title
            )

            if not result["success"]:
                logger.error(
                    f"Document version creation failed - "
                    f"Document: {document_id}, Error: {result['message']}"
                )
                raise HTTPException(status_code=500, detail=result["message"])

            # Return new version
            new_doc = db.query(Document).filter(
                Document.id == result["new_document_id"]
            ).first()

            logger.info(
                f"Document version created - "
                f"Original: {document_id}, New: {result['new_document_id']}, "
                f"User: {current_user.id}"
            )

            return DocumentResponse(**new_doc.to_dict())

        else:
            logger.debug(f"Updating document {document_id} in place")

            changes = []
            if update_data.title:
                changes.append(f"title: '{document.title}' -> '{update_data.title}'")
                document.title = update_data.title

            if update_data.content:
                content_length = len(update_data.content)
                changes.append(f"content: {content_length} chars")
                document.original_content = update_data.content
                # Reindex with new content
                await indexer.reindex_document(
                    document_id=uuid.UUID(document_id),
                    db=db
                )

            if update_data.related_service_id:
                changes.append(f"service: {update_data.related_service_id}")
                document.related_service_id = uuid.UUID(update_data.related_service_id)

            db.commit()
            db.refresh(document)

            logger.info(
                f"Document updated in place - "
                f"Document: {document_id}, Changes: [{', '.join(changes)}], "
                f"User: {current_user.id}"
            )

            return DocumentResponse(**document.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error updating document {document_id} - User: {current_user.id}: {e}",
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{document_id}/revert", response_model=DocumentResponse)
async def revert_document_version(
        document_id: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Revert document to its previous version
    Requires authenticated session.
    """
    logger.warning(
        f"User {current_user.id} REVERTING document {document_id} to previous version"
    )

    try:
        indexer = DocumentIndexer()

        result = await indexer.revert_document_version(
            document_id=uuid.UUID(document_id),
            db=db
        )

        if not result["success"]:
            logger.warning(
                f"Document revert failed - Document: {document_id}, "
                f"Error: {result['message']}, User: {current_user.id}"
            )
            raise HTTPException(status_code=400, detail=result["message"])

        # Return the reverted document
        reverted_doc = db.query(Document).filter(
            Document.id == result["reverted_to_document_id"]
        ).first()

        logger.warning(
            f"Document REVERTED - "
            f"Original: {document_id}, Reverted to: {result['reverted_to_document_id']}, "
            f"User: {current_user.id}"
        )

        return DocumentResponse(**reverted_doc.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error reverting document {document_id} - User: {current_user.id}: {e}",
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{document_id}/reindex", response_model=DocumentIndexResponse)
async def reindex_document(
        document_id: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Reindex a document (regenerate chunks and embeddings)
    Requires authenticated session.
    """
    logger.info(f"User {current_user.id} reindexing document {document_id}")

    try:
        indexer = DocumentIndexer()

        result = await indexer.reindex_document(
            document_id=uuid.UUID(document_id),
            db=db
        )

        if not result["success"]:
            logger.error(
                f"Document reindexing failed - "
                f"Document: {document_id}, Error: {result['message']}"
            )
            raise HTTPException(status_code=500, detail=result["message"])

        logger.info(
            f"Document reindexed successfully - "
            f"Document: {document_id}, Chunks: {result.get('chunks_created', 0)}, "
            f"User: {current_user.id}"
        )

        return DocumentIndexResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error reindexing document {document_id} - User: {current_user.id}: {e}",
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{document_id}")
def delete_document(
        document_id: str,
        hard_delete: bool = False,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Delete a document
    Requires authenticated session.

    Args:
        document_id: Document to delete
        hard_delete: If True, permanently delete. If False, soft delete (set is_active=False)
    """
    delete_type = "HARD DELETE" if hard_delete else "soft delete"
    logger.warning(
        f"User {current_user.id} performing {delete_type} on document {document_id}"
    )

    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            logger.warning(
                f"Document deletion failed: Document {document_id} not found - "
                f"User: {current_user.id}"
            )
            raise HTTPException(status_code=404, detail="Document not found")

        doc_type = document.type
        doc_title = document.title
        business_id = document.business_id

        if hard_delete:
            # Hard delete (cascades to chunks automatically)
            db.delete(document)
            db.commit()

            logger.warning(
                f"Document PERMANENTLY DELETED - "
                f"Document ID: {document_id}, Type: {doc_type}, Title: '{doc_title}', "
                f"Business: {business_id}, User: {current_user.id}"
            )

            return {"success": True, "message": "Document permanently deleted"}
        else:
            # Soft delete
            document.is_active = False

            # Also deactivate chunks
            from app.models.business.document import DocumentChunk
            chunk_count = db.query(DocumentChunk).filter(
                DocumentChunk.document_id == document_id
            ).update({"is_active": False})

            db.commit()

            logger.warning(
                f"Document DEACTIVATED - "
                f"Document ID: {document_id}, Type: {doc_type}, Title: '{doc_title}', "
                f"Business: {business_id}, Chunks deactivated: {chunk_count}, "
                f"User: {current_user.id}"
            )

            return {"success": True, "message": "Document deactivated"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error deleting document {document_id} - User: {current_user.id}: {e}",
            exc_info=True
        )
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{document_id}/chunks")
def get_document_chunks(
        document_id: str,
        active_only: bool = True,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Get all chunks for a document (for debugging/inspection)
    Requires authenticated session.
    """
    logger.info(
        f"User {current_user.id} requesting chunks for document {document_id} - "
        f"Active only: {active_only}"
    )

    try:
        from app.models.business.document import DocumentChunk

        query = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id)

        if active_only:
            query = query.filter(DocumentChunk.is_active == True)

        chunks = query.order_by(DocumentChunk.chunk_index).all()

        logger.info(
            f"Retrieved {len(chunks)} chunks for document {document_id}"
        )

        return {
            "document_id": document_id,
            "total_chunks": len(chunks),
            "chunks": [chunk.to_dict() for chunk in chunks]
        }

    except Exception as e:
        logger.error(
            f"Error fetching chunks for document {document_id} - User: {current_user.id}: {e}",
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=DocumentListResponse)
def list_all_documents(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    List all active documents
    Requires authenticated session.
    """
    logger.info(f"User {current_user.id} listing all active documents")

    try:
        documents = db.query(Document).filter(
            Document.is_active == True
        ).order_by(Document.created_at.desc()).all()

        logger.info(f"Returned {len(documents)} active documents")

        return DocumentListResponse(
            total=len(documents),
            documents=[doc.to_dict() for doc in documents]
        )

    except Exception as e:
        logger.error(
            f"Error listing all documents - User: {current_user.id}: {e}",
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))