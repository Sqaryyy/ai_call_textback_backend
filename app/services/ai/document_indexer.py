# app/services/document_indexer.py
"""
Document Indexer Service
Handles document ingestion, text extraction, chunking, and embedding generation.
"""
import logging
from typing import List, Dict, Optional
from datetime import datetime, timezone
from openai import OpenAI
from sqlalchemy.orm import Session
import uuid
import PyPDF2
import io

from app.models.document import Document, DocumentChunk, DocumentType, IndexingStatus
from app.config.settings import Settings

logger = logging.getLogger(__name__)
settings = Settings()


class DocumentIndexer:
    """Handles document processing and indexing"""

    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.embedding_model = "text-embedding-3-small"
        self.embedding_dimension = 1536
        self.chunk_size = 1000  # Characters per chunk
        self.chunk_overlap = 200  # Overlap between chunks

    async def extract_text_from_pdf(self, file_content: bytes) -> Dict:
        """
        Extract text from PDF file

        Returns:
            Dict with 'text' and 'metadata' (page_count, etc.)
        """
        try:
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))

            pages = []
            for page_num, page in enumerate(pdf_reader.pages, start=1):
                text = page.extract_text()
                if text.strip():
                    pages.append({
                        'page_number': page_num,
                        'text': text
                    })

            full_text = "\n\n".join([p['text'] for p in pages])

            return {
                'text': full_text,
                'metadata': {
                    'page_count': len(pdf_reader.pages),
                    'pages': pages
                }
            }

        except Exception as e:
            logger.error(f"Error extracting PDF text: {e}")
            raise ValueError(f"Failed to extract text from PDF: {str(e)}")

    def chunk_text(self, text: str, metadata: Optional[Dict] = None) -> List[Dict]:
        """
        Split text into overlapping chunks

        Args:
            text: Text to chunk
            metadata: Optional metadata (e.g., page info for PDFs)

        Returns:
            List of chunk dicts with 'content' and 'metadata'
        """
        if not text or not text.strip():
            return []

        chunks = []
        start = 0
        chunk_index = 0

        # For PDFs with page info, try to chunk by page first
        if metadata and 'pages' in metadata:
            for page_info in metadata['pages']:
                page_text = page_info['text']
                page_num = page_info['page_number']

                # If page is small enough, keep it as one chunk
                if len(page_text) <= self.chunk_size:
                    chunks.append({
                        'content': page_text,
                        'chunk_index': chunk_index,
                        'metadata': {'page_number': page_num}
                    })
                    chunk_index += 1
                else:
                    # Split large pages into sub-chunks
                    page_chunks = self._split_text(page_text)
                    for sub_chunk in page_chunks:
                        chunks.append({
                            'content': sub_chunk,
                            'chunk_index': chunk_index,
                            'metadata': {'page_number': page_num}
                        })
                        chunk_index += 1
        else:
            # Standard text chunking (for notes, FAQs, etc.)
            text_chunks = self._split_text(text)
            for idx, chunk_content in enumerate(text_chunks):
                chunks.append({
                    'content': chunk_content,
                    'chunk_index': idx,
                    'metadata': {}
                })

        logger.info(f"Created {len(chunks)} chunks from text")
        return chunks

    def _split_text(self, text: str) -> List[str]:
        """
        Split text into chunks with overlap
        Uses sentence boundaries when possible
        """
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0

        while start < len(text):
            end = start + self.chunk_size

            # If we're not at the end, try to break at sentence boundary
            if end < len(text):
                # Look for sentence endings near the chunk boundary
                for i in range(end, max(start + self.chunk_size - 200, start), -1):
                    if text[i] in '.!?\n':
                        end = i + 1
                        break

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            # Move start forward with overlap
            start = end - self.chunk_overlap

        return chunks

    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding vector for text using OpenAI"""
        try:
            text = text.replace("\n", " ").strip()
            if not text:
                raise ValueError("Cannot generate embedding for empty text")

            # Run sync API call in executor
            import asyncio
            loop = asyncio.get_event_loop()

            def _sync_call():
                return self.client.embeddings.create(
                    input=[text],
                    model=self.embedding_model
                )

            response = await asyncio.wait_for(
                loop.run_in_executor(None, _sync_call),
                timeout=30.0
            )

            embedding = response.data[0].embedding
            logger.info(f"Generated embedding with dimension: {len(embedding)}")
            return embedding

        except asyncio.TimeoutError:
            logger.error(f"Timeout generating embedding for: {text[:50]}...")
            raise
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise

    async def index_document(
            self,
            document_id: uuid.UUID,
            db: Session,
            file_content: Optional[bytes] = None
    ) -> Dict:
        """
        Index a document: extract text, chunk, generate embeddings, store chunks

        Args:
            document_id: Document to index
            db: Database session
            file_content: Optional file content (for PDFs)

        Returns:
            Dict with indexing results
        """
        try:
            # Fetch document
            document = db.query(Document).filter(Document.id == document_id).first()
            if not document:
                return {"success": False, "message": "Document not found"}

            # Update status to PROCESSING
            document.indexing_status = IndexingStatus.PROCESSING
            db.commit()

            logger.info(f"Starting indexing for document {document_id} ({document.title})")

            # Extract text based on document type
            text = document.original_content
            metadata = {}

            if document.type == DocumentType.PDF and file_content:
                logger.info("Extracting text from PDF...")
                extraction_result = await self.extract_text_from_pdf(file_content)
                text = extraction_result['text']
                metadata = extraction_result['metadata']

                # Update document content with extracted text
                document.original_content = text

            if not text or not text.strip():
                document.indexing_status = IndexingStatus.FAILED
                document.indexing_error = "No text content found"
                db.commit()
                return {
                    "success": False,
                    "message": "No text content to index"
                }

            # Chunk the text
            logger.info("Chunking text...")
            chunks_data = self.chunk_text(text, metadata)

            if not chunks_data:
                document.indexing_status = IndexingStatus.FAILED
                document.indexing_error = "No chunks created from text"
                db.commit()
                return {
                    "success": False,
                    "message": "No chunks created from text"
                }

            logger.info(f"Created {len(chunks_data)} chunks, generating embeddings...")

            # Generate embeddings and create DocumentChunk records
            indexed_chunks = 0
            for chunk_data in chunks_data:
                try:
                    embedding = await self.generate_embedding(chunk_data['content'])

                    chunk = DocumentChunk.create_chunk(
                        document_id=document.id,
                        content=chunk_data['content'],
                        embedding=embedding,
                        chunk_index=chunk_data['chunk_index'],
                        extra_metadata=chunk_data['metadata']
                    )

                    db.add(chunk)
                    indexed_chunks += 1

                    logger.info(f"Indexed chunk {indexed_chunks}/{len(chunks_data)}")

                except Exception as e:
                    logger.error(f"Error indexing chunk {chunk_data['chunk_index']}: {e}")
                    continue

            # Update document status
            document.indexing_status = IndexingStatus.COMPLETE
            document.indexed_at = datetime.now(timezone.utc)
            document.indexing_error = None
            db.commit()

            logger.info(f"✅ Successfully indexed document {document_id}: {indexed_chunks} chunks")

            return {
                "success": True,
                "message": f"Indexed {indexed_chunks} chunks",
                "indexed_chunks": indexed_chunks,
                "document_id": str(document_id)
            }

        except Exception as e:
            logger.error(f"Error indexing document {document_id}: {e}", exc_info=True)

            # Update document with error status
            try:
                document = db.query(Document).filter(Document.id == document_id).first()
                if document:
                    document.indexing_status = IndexingStatus.FAILED
                    document.indexing_error = str(e)
                    db.commit()
            except:
                pass

            return {
                "success": False,
                "message": f"Failed to index document: {str(e)}",
                "document_id": str(document_id)
            }

    async def reindex_document(
            self,
            document_id: uuid.UUID,
            db: Session,
            file_content: Optional[bytes] = None
    ) -> Dict:
        """
        Reindex a document (delete old chunks and create new ones)

        Args:
            document_id: Document to reindex
            db: Database session
            file_content: Optional new file content

        Returns:
            Dict with reindexing results
        """
        try:
            document = db.query(Document).filter(Document.id == document_id).first()
            if not document:
                return {"success": False, "message": "Document not found"}

            logger.info(f"Reindexing document {document_id}")

            # Delete existing chunks
            deleted_count = db.query(DocumentChunk).filter(
                DocumentChunk.document_id == document_id
            ).delete()

            db.commit()
            logger.info(f"Deleted {deleted_count} old chunks")

            # Index with new content
            result = await self.index_document(
                document_id=document_id,
                db=db,
                file_content=file_content
            )

            if result["success"]:
                result["deleted_chunks"] = deleted_count

            return result

        except Exception as e:
            logger.error(f"Error reindexing document: {e}")
            db.rollback()
            return {
                "success": False,
                "message": str(e)
            }

    async def create_and_index_document(
            self,
            business_id: uuid.UUID,
            title: str,
            doc_type: DocumentType,
            content: str,
            db: Session,
            file_content: Optional[bytes] = None,
            file_path: Optional[str] = None,
            original_filename: Optional[str] = None,
            file_size: Optional[int] = None,
            related_service_id: Optional[uuid.UUID] = None
    ) -> Dict:
        """
        Create a new document and index it in one operation

        Args:
            business_id: Business that owns the document
            title: Document title
            doc_type: Type of document
            content: Text content (or will be extracted from file_content)
            db: Database session
            file_content: Optional file bytes (for PDFs)
            file_path: Optional storage path
            original_filename: Original filename
            file_size: File size in bytes
            related_service_id: Optional service linkage

        Returns:
            Dict with creation and indexing results
        """
        try:
            # Create document record
            document = Document(
                id=uuid.uuid4(),
                business_id=business_id,
                title=title,
                type=doc_type,
                original_content=content,
                file_path=file_path,
                original_filename=original_filename,
                file_size=file_size,
                related_service_id=related_service_id,
                indexing_status=IndexingStatus.PENDING,
                is_active=True
            )

            db.add(document)
            db.commit()
            db.refresh(document)

            logger.info(f"Created document {document.id}: {title}")

            # Index the document
            index_result = await self.index_document(
                document_id=document.id,
                db=db,
                file_content=file_content
            )

            return {
                "success": index_result["success"],
                "message": index_result["message"],
                "document_id": str(document.id),
                "indexed_chunks": index_result.get("indexed_chunks", 0)
            }

        except Exception as e:
            logger.error(f"Error creating and indexing document: {e}")
            db.rollback()
            return {
                "success": False,
                "message": str(e)
            }

    async def update_document_version(
            self,
            document_id: uuid.UUID,
            new_content: str,
            db: Session,
            file_content: Optional[bytes] = None,
            new_title: Optional[str] = None
    ) -> Dict:
        """
        Create a new version of a document (1-level versioning)

        Process:
        1. Deactivate old document and its chunks
        2. Create new document with previous_version_id pointing to old
        3. Index new document

        Args:
            document_id: Current document ID
            new_content: Updated content
            db: Database session
            file_content: Optional new file content
            new_title: Optional new title

        Returns:
            Dict with versioning results
        """
        try:
            # Get current document
            old_doc = db.query(Document).filter(Document.id == document_id).first()
            if not old_doc:
                return {"success": False, "message": "Document not found"}

            logger.info(f"Creating new version of document {document_id}")

            # Deactivate old document
            old_doc.is_active = False

            # Deactivate old chunks
            db.query(DocumentChunk).filter(
                DocumentChunk.document_id == document_id
            ).update({"is_active": False})

            # Create new document version
            new_doc = Document(
                id=uuid.uuid4(),
                business_id=old_doc.business_id,
                title=new_title or old_doc.title,
                type=old_doc.type,
                original_content=new_content,
                file_path=old_doc.file_path,  # Keep same path if applicable
                original_filename=old_doc.original_filename,
                file_size=file_content and len(file_content) or old_doc.file_size,
                related_service_id=old_doc.related_service_id,
                previous_version_id=old_doc.id,  # Link to old version
                indexing_status=IndexingStatus.PENDING,
                is_active=True
            )

            db.add(new_doc)
            db.commit()
            db.refresh(new_doc)

            logger.info(f"Created new document version {new_doc.id}")

            # Index new version
            index_result = await self.index_document(
                document_id=new_doc.id,
                db=db,
                file_content=file_content
            )

            return {
                "success": index_result["success"],
                "message": f"Created new version: {index_result['message']}",
                "old_document_id": str(document_id),
                "new_document_id": str(new_doc.id),
                "indexed_chunks": index_result.get("indexed_chunks", 0)
            }

        except Exception as e:
            logger.error(f"Error creating document version: {e}")
            db.rollback()
            return {
                "success": False,
                "message": str(e)
            }

    async def revert_document_version(
            self,
            document_id: uuid.UUID,
            db: Session
    ) -> Dict:
        """
        Revert to previous version of a document

        Process:
        1. Find previous version via previous_version_id
        2. Deactivate current document and chunks
        3. Reactivate previous document and chunks

        Args:
            document_id: Current document ID
            db: Database session

        Returns:
            Dict with revert results
        """
        try:
            # Get current document
            current_doc = db.query(Document).filter(Document.id == document_id).first()
            if not current_doc:
                return {"success": False, "message": "Document not found"}

            if not current_doc.previous_version_id:
                return {"success": False, "message": "No previous version exists"}

            # Get previous version
            prev_doc = db.query(Document).filter(
                Document.id == current_doc.previous_version_id
            ).first()

            if not prev_doc:
                return {"success": False, "message": "Previous version not found"}

            logger.info(f"Reverting document {document_id} to {prev_doc.id}")

            # Deactivate current
            current_doc.is_active = False
            db.query(DocumentChunk).filter(
                DocumentChunk.document_id == current_doc.id
            ).update({"is_active": False})

            # Reactivate previous
            prev_doc.is_active = True
            db.query(DocumentChunk).filter(
                DocumentChunk.document_id == prev_doc.id
            ).update({"is_active": True})

            db.commit()

            logger.info(f"✅ Reverted to previous version {prev_doc.id}")

            return {
                "success": True,
                "message": "Reverted to previous version",
                "current_document_id": str(document_id),
                "reverted_to_document_id": str(prev_doc.id)
            }

        except Exception as e:
            logger.error(f"Error reverting document version: {e}")
            db.rollback()
            return {
                "success": False,
                "message": str(e)
            }