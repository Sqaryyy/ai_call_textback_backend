# app/api/routes/document_routes.py
"""
Document Management API Endpoints
Handles CRUD operations for documents and document indexing
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel, Field
import uuid
import logging

from app.database import get_db
from app.models.document import Document, DocumentType, IndexingStatus
from app.models.service import Service
from app.services.document_indexer import DocumentIndexer
from app.services.rag_service import RAGService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])


# ============================================================================
# Request/Response Models
# ============================================================================

class DocumentCreate(BaseModel):
    """Request model for creating a text document"""
    business_id: str
    title: str
    type: DocumentType
    content: str
    related_service_id: Optional[str] = None


class DocumentUpdate(BaseModel):
    """Request model for updating a document"""
    title: Optional[str] = None
    content: Optional[str] = None
    related_service_id: Optional[str] = None


class DocumentResponse(BaseModel):
    """Response model for document data"""
    id: str
    business_id: str
    title: str
    type: str
    indexing_status: str
    original_filename: Optional[str]
    file_size: Optional[int]
    related_service_id: Optional[str]
    previous_version_id: Optional[str]
    is_active: bool
    created_at: str
    updated_at: str
    indexed_at: Optional[str]
    chunk_count: int
    indexing_error: Optional[str] = None


class DocumentListResponse(BaseModel):
    """Response model for document list"""
    total: int
    documents: List[DocumentResponse]


class DocumentIndexResponse(BaseModel):
    """Response model for indexing operations"""
    success: bool
    message: str
    document_id: str
    indexed_chunks: int


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/", response_model=DocumentResponse)
async def create_text_document(
        document: DocumentCreate,
        db: Session = Depends(get_db)
):
    """
    Create a new text-based document (NOTE, POLICY, FAQ, etc.)
    """
    try:
        indexer = DocumentIndexer()

        # Validate business exists
        from app.models.business import Business
        business = db.query(Business).filter(Business.id == document.business_id).first()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")

        # Validate service if provided
        service_id = None
        if document.related_service_id:
            service = db.query(Service).filter(
                Service.id == document.related_service_id,
                Service.business_id == document.business_id
            ).first()
            if not service:
                raise HTTPException(status_code=404, detail="Service not found")
            service_id = uuid.UUID(document.related_service_id)

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
            raise HTTPException(status_code=500, detail=result["message"])

        # Fetch and return created document
        doc = db.query(Document).filter(Document.id == result["document_id"]).first()
        return DocumentResponse(**doc.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload", response_model=DocumentResponse)
async def upload_pdf_document(
        business_id: str = Form(...),
        title: str = Form(...),
        related_service_id: Optional[str] = Form(None),
        file: UploadFile = File(...),
        db: Session = Depends(get_db)
):
    """
    Upload and index a PDF document
    """
    try:
        # Validate file type
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")

        indexer = DocumentIndexer()

        # Validate business exists
        from app.models.business import Business
        business = db.query(Business).filter(Business.id == business_id).first()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")

        # Validate service if provided
        service_id = None
        if related_service_id:
            service = db.query(Service).filter(
                Service.id == related_service_id,
                Service.business_id == business_id
            ).first()
            if not service:
                raise HTTPException(status_code=404, detail="Service not found")
            service_id = uuid.UUID(related_service_id)

        # Read file content
        file_content = await file.read()
        file_size = len(file_content)

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
            raise HTTPException(status_code=500, detail=result["message"])

        # Fetch and return created document
        doc = db.query(Document).filter(Document.id == result["document_id"]).first()
        return DocumentResponse(**doc.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading PDF: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
        document_id: str,
        db: Session = Depends(get_db)
):
    """
    Get document by ID
    """
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        return DocumentResponse(**document.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/business/{business_id}", response_model=DocumentListResponse)
def list_business_documents(
        business_id: str,
        document_type: Optional[DocumentType] = None,
        service_id: Optional[str] = None,
        active_only: bool = True,
        db: Session = Depends(get_db)
):
    """
    List all documents for a business with optional filters
    """
    try:
        query = db.query(Document).filter(Document.business_id == business_id)

        if active_only:
            query = query.filter(Document.is_active == True)

        if document_type:
            query = query.filter(Document.type == document_type)

        if service_id:
            query = query.filter(Document.related_service_id == service_id)

        documents = query.order_by(Document.created_at.desc()).all()

        return DocumentListResponse(
            total=len(documents),
            documents=[DocumentResponse(**doc.to_dict()) for doc in documents]
        )

    except Exception as e:
        logger.error(f"Error listing documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{document_id}", response_model=DocumentResponse)
async def update_document(
        document_id: str,
        update_data: DocumentUpdate,
        create_version: bool = False,
        db: Session = Depends(get_db)
):
    """
    Update a document

    Args:
        document_id: Document to update
        update_data: Fields to update
        create_version: If True, create a new version instead of updating in place
    """
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        indexer = DocumentIndexer()

        if create_version:
            # Create new version
            result = await indexer.update_document_version(
                document_id=uuid.UUID(document_id),
                new_content=update_data.content or document.original_content,
                db=db,
                new_title=update_data.title
            )

            if not result["success"]:
                raise HTTPException(status_code=500, detail=result["message"])

            # Return new version
            new_doc = db.query(Document).filter(
                Document.id == result["new_document_id"]
            ).first()
            return DocumentResponse(**new_doc.to_dict())

        else:
            # Update in place
            if update_data.title:
                document.title = update_data.title

            if update_data.content:
                document.original_content = update_data.content
                # Reindex with new content
                await indexer.reindex_document(
                    document_id=uuid.UUID(document_id),
                    db=db
                )

            if update_data.related_service_id:
                document.related_service_id = uuid.UUID(update_data.related_service_id)

            db.commit()
            db.refresh(document)

            return DocumentResponse(**document.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{document_id}/revert", response_model=DocumentResponse)
async def revert_document_version(
        document_id: str,
        db: Session = Depends(get_db)
):
    """
    Revert document to its previous version
    """
    try:
        indexer = DocumentIndexer()

        result = await indexer.revert_document_version(
            document_id=uuid.UUID(document_id),
            db=db
        )

        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])

        # Return the reverted document
        reverted_doc = db.query(Document).filter(
            Document.id == result["reverted_to_document_id"]
        ).first()

        return DocumentResponse(**reverted_doc.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reverting document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{document_id}/reindex", response_model=DocumentIndexResponse)
async def reindex_document(
        document_id: str,
        db: Session = Depends(get_db)
):
    """
    Reindex a document (regenerate chunks and embeddings)
    """
    try:
        indexer = DocumentIndexer()

        result = await indexer.reindex_document(
            document_id=uuid.UUID(document_id),
            db=db
        )

        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["message"])

        return DocumentIndexResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reindexing document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{document_id}")
def delete_document(
        document_id: str,
        hard_delete: bool = False,
        db: Session = Depends(get_db)
):
    """
    Delete a document

    Args:
        document_id: Document to delete
        hard_delete: If True, permanently delete. If False, soft delete (set is_active=False)
    """
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        if hard_delete:
            # Hard delete (cascades to chunks automatically)
            db.delete(document)
            db.commit()
            return {"success": True, "message": "Document permanently deleted"}
        else:
            # Soft delete
            document.is_active = False

            # Also deactivate chunks
            from app.models.document import DocumentChunk
            db.query(DocumentChunk).filter(
                DocumentChunk.document_id == document_id
            ).update({"is_active": False})

            db.commit()
            return {"success": True, "message": "Document deactivated"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{document_id}/chunks")
def get_document_chunks(
        document_id: str,
        active_only: bool = True,
        db: Session = Depends(get_db)
):
    """
    Get all chunks for a document (for debugging/inspection)
    """
    try:
        from app.models.document import DocumentChunk

        query = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id)

        if active_only:
            query = query.filter(DocumentChunk.is_active == True)

        chunks = query.order_by(DocumentChunk.chunk_index).all()

        return {
            "document_id": document_id,
            "total_chunks": len(chunks),
            "chunks": [chunk.to_dict() for chunk in chunks]
        }

    except Exception as e:
        logger.error(f"Error fetching chunks: {e}")
        raise HTTPException(status_code=500, detail=str(e))