"""
Pydantic schemas for document management endpoints
"""
from pydantic import BaseModel
from typing import Optional, List

from app.models.business.document import DocumentType


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


class DocumentDetailResponse(DocumentResponse):
    """Response model for document with full content"""
    original_content: str


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