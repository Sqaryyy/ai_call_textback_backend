from sqlalchemy import Column, String, Boolean, DateTime, Integer, Text, ForeignKey, Enum as SQLAEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
import uuid
import enum

from app.models.business import Base


class KnowledgeCategory(str, enum.Enum):
    """Categories for business knowledge chunks"""
    SERVICE_INFO = "service_info"
    PRICING = "pricing"
    POLICIES = "policies"
    FAQ = "faq"
    BUSINESS_HOURS = "business_hours"
    CONTACT_INFO = "contact_info"
    GENERAL = "general"


class BusinessKnowledge(Base):
    """
    Stores business knowledge chunks with embeddings for semantic search.
    Each row represents a piece of information about the business.
    """
    __tablename__ = "business_knowledge"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Content and embedding
    content = Column(Text, nullable=False)
    embedding = Column(Vector(1536), nullable=False)

    # Metadata
    extra_metadata = Column(JSONB, default=dict)
    category = Column(
        SQLAEnum(
            KnowledgeCategory,
            name="knowledge_category",
            values_callable=lambda obj: [e.value for e in obj]  # Use values, not names
        ),
        nullable=False,
        index=True
    )
    source_field = Column(String(100), nullable=True)
    chunk_index = Column(Integer, default=0)

    # Timestamps and status
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    is_active = Column(Boolean, default=True, index=True)

    # Relationship
    business = relationship("Business", backref="knowledge_chunks")

    def __repr__(self):
        return f"<BusinessKnowledge(id={self.id}, business_id={self.business_id}, category={self.category})>"

    def to_dict(self):
        """Convert to dictionary for easy serialization"""
        return {
            "id": str(self.id),
            "business_id": str(self.business_id),
            "content": self.content,
            "category": self.category.value if isinstance(self.category, KnowledgeCategory) else self.category,
            "extra_metadata": self.extra_metadata,
            "source_field": self.source_field,
            "chunk_index": self.chunk_index,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "is_active": self.is_active
        }

    @classmethod
    def create_chunk(
        cls,
        business_id: uuid.UUID,
        content: str,
        embedding: list,
        category: KnowledgeCategory,
        source_field: str = None,
        chunk_index: int = 0,
        extra_metadata: dict = None
    ):
        """Factory method to create a knowledge chunk"""
        return cls(
            business_id=business_id,
            content=content,
            embedding=embedding,
            category=category,  # SQLAlchemy will handle the conversion now
            source_field=source_field,
            chunk_index=chunk_index,
            extra_metadata=extra_metadata or {},
            is_active=True
        )