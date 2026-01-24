# app/services/rag_service.py
"""
RAG (Retrieval-Augmented Generation) Service - NEW ARCHITECTURE
Handles embedding generation, vector storage, and similarity search
Works with Documents, DocumentChunks, and Services tables
"""
import logging
from typing import List, Dict, Optional, Tuple, Union
from datetime import datetime, timezone
from openai import OpenAI
from sqlalchemy.orm import Session
from sqlalchemy import text, or_, func
import uuid

from app.models.business.document import Document, DocumentChunk, DocumentType, IndexingStatus
from app.models.business.service import Service
from app.config.settings import Settings
from app.services.ai.document_indexer import DocumentIndexer

logger = logging.getLogger(__name__)
settings = Settings()


class RAGService:
    """Handles RAG operations: embedding, indexing, and retrieval with new architecture"""

    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.embedding_model = "text-embedding-3-small"
        self.embedding_dimension = 1536
        self.similarity_threshold = 0.0
        self.max_context_chunks = 5
        self.indexer = DocumentIndexer()  # ✅ Add this

    async def index_business_knowledge(
            self,
            business_id: str,
            db: Session,
            force_reindex: bool = False
    ) -> Dict:
        """
        Index or re-index all documents for a business
        Delegates to DocumentIndexer for actual processing
        """
        try:
            from uuid import UUID
            business_id_uuid = UUID(business_id) if isinstance(business_id, str) else business_id

            # Get documents that need indexing
            query = db.query(Document).filter(
                Document.business_id == business_id_uuid,
                Document.is_active == True
            )

            if not force_reindex:
                query = query.filter(
                    or_(
                        Document.indexing_status == IndexingStatus.PENDING,
                        Document.indexing_status == IndexingStatus.FAILED
                    )
                )

            documents = query.all()

            if not documents:
                logger.info(f"No documents to index for business {business_id}")
                return {
                    "success": True,
                    "documents_processed": 0,
                    "chunks_created": 0
                }

            logger.info(f"Indexing {len(documents)} documents for business {business_id}")

            total_chunks = 0
            successful = 0
            failed = 0

            for document in documents:
                try:
                    if force_reindex:
                        # Reindex existing document
                        result = await self.indexer.reindex_document(
                            document_id=document.id,
                            db=db
                        )
                    else:
                        # Index new document
                        result = await self.indexer.index_document(
                            document_id=document.id,
                            db=db
                        )

                    if result["success"]:
                        successful += 1
                        total_chunks += result.get("indexed_chunks", 0)
                    else:
                        failed += 1
                        logger.error(f"Failed to index document {document.id}: {result.get('message')}")

                except Exception as e:
                    logger.error(f"Error indexing document {document.id}: {e}")
                    failed += 1

            logger.info(
                f"Indexing complete for business {business_id}: "
                f"{successful} successful, {failed} failed, {total_chunks} chunks created"
            )

            return {
                "success": True,
                "documents_processed": len(documents),
                "successful": successful,
                "failed": failed,
                "chunks_created": total_chunks
            }

        except Exception as e:
            logger.error(f"Error in index_business_knowledge: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "documents_processed": 0,
                "chunks_created": 0
            }