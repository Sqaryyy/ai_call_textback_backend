from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from app.models.business.document import DocumentType
# ============================================================================
# Request/Response Models
# ============================================================================

class DocumentCreate(BaseModel):
    business_id: UUID = Field(..., description="Business ID this document belongs to")
    title: str = Field(..., min_length=1, max_length=500, description="Document title")
    type: DocumentType = Field(..., description="Document type")
    original_content: str = Field(..., min_length=1, description="Document text content")
    related_service_id: Optional[UUID] = Field(None, description="Related service ID")


class DocumentUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    type: Optional[DocumentType] = None
    original_content: Optional[str] = Field(None, min_length=1)
    related_service_id: Optional[UUID] = None
    is_active: Optional[bool] = None


class DocumentResponse(BaseModel):
    id: UUID
    business_id: UUID
    business_name: Optional[str]
    title: str
    type: str
    indexing_status: str
    original_filename: Optional[str]
    file_size: Optional[int]
    related_service_id: Optional[UUID]
    related_service_name: Optional[str]
    previous_version_id: Optional[UUID]
    is_active: bool
    created_at: str
    updated_at: str
    indexed_at: Optional[str]
    chunk_count: int
    indexing_error: Optional[str] = None

    class Config:
        from_attributes = True


class DocumentDetailResponse(DocumentResponse):
    original_content: str


class DocumentChunkResponse(BaseModel):
    id: UUID
    document_id: UUID
    content: str
    chunk_index: int
    extra_metadata: dict
    is_active: bool
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class ReindexRequest(BaseModel):
    document_ids: List[UUID] = Field(..., description="List of document IDs to reindex")


class BusinessDocumentStatsResponse(BaseModel):
    business_id: str
    business_name: str
    total_documents: int
    active_documents: int
    documents_by_type: dict
    documents_by_status: dict
    total_chunks: int
    failed_documents: int