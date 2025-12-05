# app/models/document.py
"""
Document and DocumentChunk Models
Handles unstructured knowledge storage with versioning support.
"""
from sqlalchemy import (
    Column, String, Text, ForeignKey, Boolean, DateTime, Integer,
    Enum as SQLAEnum, BigInteger
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
import uuid
import enum
from app.models.base import Base


class DocumentType(str, enum.Enum):
    """Types of documents that can be stored"""
    PDF = "pdf"
    NOTE = "note"
    POLICY = "policy"
    FAQ = "faq"
    GUIDE = "guide"
    GENERAL = "general"


class IndexingStatus(str, enum.Enum):
    """Status of document indexing process"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"


class Document(Base):
    """
    Source of truth for all unstructured business knowledge.
    Supports versioning and linking to specific services.
    """
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Document metadata
    title = Column(String(500), nullable=False)
    type = Column(
        SQLAEnum(
            DocumentType,
            name="document_type",
            values_callable=lambda obj: [e.value for e in obj]
        ),
        nullable=False,
        index=True
    )

    # Content storage
    original_content = Column(Text, nullable=False)  # Extracted text from PDF or raw text

    # File metadata (nullable for text-only documents)
    file_path = Column(String(1000), nullable=True)  # S3 key or local path
    original_filename = Column(String(500), nullable=True)
    file_size = Column(BigInteger, nullable=True)  # Size in bytes

    # Indexing status
    indexing_status = Column(
        SQLAEnum(
            IndexingStatus,
            name="indexing_status",
            values_callable=lambda obj: [e.value for e in obj]
        ),
        nullable=False,
        default=IndexingStatus.PENDING,
        index=True
    )
    indexing_error = Column(Text, nullable=True)  # Store error message if indexing fails
    indexed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    related_service_id = Column(
        UUID(as_uuid=True),
        ForeignKey("services.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # Versioning (1-level undo support)
    previous_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True
    )

    # Status
    is_active = Column(Boolean, default=True, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # Relationships
    business = relationship("Business", backref="documents")
    service = relationship(
        "Service",
        back_populates="documents",
        foreign_keys=[related_service_id]
    )
    chunks = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        foreign_keys="DocumentChunk.document_id"
    )

    # Self-referential for versioning
    previous_version = relationship(
        "Document",
        remote_side=[id],
        backref="newer_version",
        foreign_keys=[previous_version_id]
    )

    def __repr__(self):
        return f"<Document(id={self.id}, title={self.title}, type={self.type}, status={self.indexing_status})>"

    def to_dict(self, include_content=False):
        """Convert to dictionary for API responses"""
        result = {
            "id": str(self.id),
            "business_id": str(self.business_id),
            "title": self.title,
            "type": self.type.value,
            "indexing_status": self.indexing_status.value,
            "original_filename": self.original_filename,
            "file_size": self.file_size,
            "related_service_id": str(self.related_service_id) if self.related_service_id else None,
            "previous_version_id": str(self.previous_version_id) if self.previous_version_id else None,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "indexed_at": self.indexed_at.isoformat() if self.indexed_at else None,
            "chunk_count": len(self.chunks) if self.chunks else 0,
        }

        if include_content:
            result["original_content"] = self.original_content

        if self.indexing_error:
            result["indexing_error"] = self.indexing_error

        return result


class DocumentChunk(Base):
    """
    Stores vector chunks extracted from documents.
    Replaces BusinessKnowledge table with cleaner structure.
    """
    __tablename__ = "document_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Content and embedding
    content = Column(Text, nullable=False)
    embedding = Column(Vector(1536), nullable=False)

    # Position tracking
    chunk_index = Column(Integer, nullable=False, default=0)

    # Dynamic metadata (page numbers, sections, etc.)
    extra_metadata = Column(JSONB, default=dict)

    # Status (for versioning support)
    is_active = Column(Boolean, default=True, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # Relationship
    document = relationship("Document", back_populates="chunks")

    def __repr__(self):
        return f"<DocumentChunk(id={self.id}, document_id={self.document_id}, chunk_index={self.chunk_index})>"

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": str(self.id),
            "document_id": str(self.document_id),
            "content": self.content,
            "chunk_index": self.chunk_index,
            "extra_metadata": self.extra_metadata,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def create_chunk(
            cls,
            document_id: uuid.UUID,
            content: str,
            embedding: list,
            chunk_index: int = 0,
            extra_metadata: dict = None
    ):
        """Factory method to create a document chunk"""
        return cls(
            document_id=document_id,
            content=content,
            embedding=embedding,
            chunk_index=chunk_index,
            extra_metadata=extra_metadata or {},
            is_active=True
        )