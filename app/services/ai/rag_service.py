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

from app.models.document import Document, DocumentChunk, DocumentType, IndexingStatus
from app.models.service import Service
from app.models.business import Business
from app.config.settings import Settings

logger = logging.getLogger(__name__)
settings = Settings()


class RAGService:
    """Handles RAG operations: embedding, indexing, and retrieval with new architecture"""

    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.embedding_model = "text-embedding-3-small"
        self.embedding_dimension = 1536
        self.similarity_threshold = 0.0  # Cosine similarity threshold
        self.max_context_chunks = 5  # Max chunks to include in context

    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding vector for text using OpenAI"""
        try:
            text = text.replace("\n", " ").strip()
            if not text:
                raise ValueError("Cannot generate embedding for empty text")

            logger.info(f"Generating embedding for text: {text[:50]}...")

            # Run sync API call in executor to avoid blocking
            import asyncio
            loop = asyncio.get_event_loop()

            def _sync_call():
                return self.client.embeddings.create(
                    input=[text],
                    model=self.embedding_model
                )

            # Run with timeout
            response = await asyncio.wait_for(
                loop.run_in_executor(None, _sync_call),
                timeout=30.0
            )

            embedding = response.data[0].embedding
            logger.info(f"✅ Generated embedding with dimension: {len(embedding)}")
            return embedding

        except asyncio.TimeoutError:
            logger.error(f"⏰ Timeout generating embedding for: {text[:50]}...")
            raise
        except Exception as e:
            logger.error(f"❌ Error generating embedding: {e}")
            raise

    async def retrieve_context(
        self,
        query: str,
        business_id: str,
        db: Session,
        service_filter: Optional[str] = None,
        document_type_filter: Optional[DocumentType] = None,
        limit: int = None,
        return_debug_info: bool = False
    ) -> Union[str, Tuple[str, Dict]]:
        """
        Retrieve relevant context for a query using hybrid retrieval strategy
        
        Strategy:
        1. Detect if query mentions a specific service
        2. If service detected, fetch structured data from Services table first
        3. Perform vector search with optional service scoping
        4. Fall back to keyword search if no vector results
        5. Return formatted context with provenance metadata
        
        Args:
            query: User's question/message
            business_id: Business to search knowledge for
            db: Database session
            service_filter: Optional service name to scope search
            document_type_filter: Optional document type to filter by
            limit: Max number of chunks to retrieve
            return_debug_info: If True, return (context, debug_info) tuple
        
        Returns:
            str if return_debug_info=False, else Tuple[str, Dict]
        """
        try:
            if limit is None:
                limit = self.max_context_chunks

            debug_info = {
                "query": query,
                "business_id": business_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "num_results": 0,
                "results": [],
                "service_detected": None,
                "structured_data_used": False,
                "used_fallback": False
            }

            context_parts = []
            
            # ========================================================================
            # STEP 1: Detect Service Intent (Simple Keyword Matching)
            # ========================================================================
            
            detected_service = self._detect_service_intent(query, business_id, db)
            if detected_service:
                debug_info["service_detected"] = detected_service.name
                logger.info(f"🎯 Detected service: {detected_service.name}")
                
                # Add structured service data to context
                service_context = self._format_service_data(detected_service)
                context_parts.append(service_context)
                debug_info["structured_data_used"] = True
            
            # ========================================================================
            # STEP 2: Generate Query Embedding
            # ========================================================================
            
            query_embedding = await self.generate_embedding(query)
            
            # ========================================================================
            # STEP 3: Vector Similarity Search with Provenance
            # ========================================================================
            
            # Build query with service scoping if detected
            similarity_query = self._build_similarity_query(
                service_id=detected_service.id if detected_service else None,
                document_type_filter=document_type_filter
            )
            
            result = db.execute(
                text(similarity_query),
                {
                    "query_embedding": str(query_embedding),
                    "business_id": business_id,
                    "service_id": str(detected_service.id) if detected_service else None,
                    "doc_type": document_type_filter.value if document_type_filter else None,
                    "threshold": self.similarity_threshold,
                    "limit": limit
                }
            )
            
            chunks = result.fetchall()
            
            # ========================================================================
            # STEP 4: Keyword Fallback if No Vector Results
            # ========================================================================
            
            if not chunks:
                logger.info(f"No vector results, trying keyword fallback for: {query}")
                chunks = self._keyword_fallback_search(
                    query=query,
                    business_id=business_id,
                    db=db,
                    service_id=detected_service.id if detected_service else None,
                    limit=limit
                )
                if chunks:
                    debug_info["used_fallback"] = True
                    logger.info(f"✅ Keyword fallback found {len(chunks)} results")
            
            debug_info["num_results"] = len(chunks)
            
            if not chunks and not detected_service:
                logger.info(f"No relevant context found for query: {query[:50]}...")
                if return_debug_info:
                    return "", debug_info
                return ""
            
            # ========================================================================
            # STEP 5: Format Context with Provenance
            # ========================================================================
            
            for chunk in chunks:
                debug_info["results"].append({
                    "content": chunk.content,
                    "document_title": chunk.document_title,
                    "document_type": chunk.document_type,
                    "service_name": chunk.service_name if hasattr(chunk, 'service_name') else None,
                    "score": float(chunk.similarity) if hasattr(chunk, 'similarity') else 0.0,
                    "chunk_metadata": chunk.extra_metadata if hasattr(chunk, 'extra_metadata') else {}
                })
            
            logger.info(
                f"Retrieved {len(chunks)} relevant chunks "
                f"(similarities: {[f'{c.similarity:.3f}' if hasattr(c, 'similarity') else 'keyword' for c in chunks]})"
            )
            
            # Format chunks with provenance
            chunks_context = self._format_context_with_provenance(chunks)
            if chunks_context:
                context_parts.append(chunks_context)
            
            final_context = "\n\n".join(context_parts)
            
            if return_debug_info:
                return final_context, debug_info
            return final_context

        except Exception as e:
            logger.error(f"Error retrieving context: {e}", exc_info=True)
            if return_debug_info:
                return "", {"error": str(e), "query": query}
            return ""

    def _detect_service_intent(
        self,
        query: str,
        business_id: str,
        db: Session
    ) -> Optional[Service]:
        """
        Detect if query mentions a specific service (simple keyword matching)
        Returns the matched Service object if found
        """
        try:
            query_lower = query.lower()
            
            # Fetch all active services for this business
            services = db.query(Service).filter(
                Service.business_id == business_id,
                Service.is_active == True
            ).all()
            
            # Check if any service name appears in query
            for service in services:
                if service.name.lower() in query_lower:
                    logger.info(f"🎯 Service detected: {service.name}")
                    return service
            
            return None
        
        except Exception as e:
            logger.error(f"Error detecting service intent: {e}")
            return None

    def _format_service_data(self, service: Service) -> str:
        """Format structured service data for context"""
        parts = [
            "=" * 60,
            f"SERVICE INFORMATION: {service.name.upper()}",
            "=" * 60
        ]
        
        if service.description:
            parts.append(f"Description: {service.description}")
        
        parts.append(f"Price: {service.formatted_price}")
        parts.append(f"Duration: {service.formatted_duration}")
        
        parts.append("-" * 60)
        
        return "\n".join(parts)

    def _build_similarity_query(
        self,
        service_id: Optional[uuid.UUID] = None,
        document_type_filter: Optional[DocumentType] = None
    ) -> str:
        """
        Build SQL query for vector similarity search with JOINs for provenance
        """
        query = """
            SELECT 
                dc.id,
                dc.content,
                dc.chunk_index,
                dc.extra_metadata,
                d.id as document_id,
                d.title as document_title,
                d.type as document_type,
                s.name as service_name,
                1 - (dc.embedding <=> :query_embedding) AS similarity
            FROM document_chunks dc
            INNER JOIN documents d ON dc.document_id = d.id
            LEFT JOIN services s ON d.related_service_id = s.id
            WHERE d.business_id = :business_id
                AND d.is_active = true
                AND d.indexing_status = 'complete'
                AND dc.is_active = true
        """
        
        # Add service scoping if detected
        if service_id:
            query += " AND (d.related_service_id = :service_id OR d.related_service_id IS NULL)"
        
        # Add document type filter
        if document_type_filter:
            query += " AND d.type = :doc_type"
        
        query += """
                AND 1 - (dc.embedding <=> :query_embedding) > :threshold
            ORDER BY dc.embedding <=> :query_embedding
            LIMIT :limit
        """
        
        return query

    def _keyword_fallback_search(
        self,
        query: str,
        business_id: str,
        db: Session,
        service_id: Optional[uuid.UUID] = None,
        limit: int = 5
    ) -> List:
        """
        Fallback to keyword matching when vector search returns nothing
        """
        try:
            # Extract meaningful keywords
            stop_words = {
                'what', 'is', 'your', 'the', 'about', 'do', 'you', 'have',
                'a', 'an', 'my', 'can', 'how', 'where', 'when', 'who',
                'does', 'are', 'will', 'would', 'could', 'should'
            }
            
            words = query.lower().replace('?', '').replace('!', '').split()
            keywords = [w for w in words if w not in stop_words and len(w) > 2]
            
            if not keywords:
                return []
            
            logger.info(f"Keyword fallback searching for: {keywords}")
            
            # Build OR conditions for each keyword
            conditions = []
            for keyword in keywords:
                conditions.append(func.lower(DocumentChunk.content).contains(keyword))
            
            # Query with JOINs for provenance
            query_builder = db.query(
                DocumentChunk,
                Document.title.label('document_title'),
                Document.type.label('document_type'),
                Service.name.label('service_name')
            ).join(
                Document, DocumentChunk.document_id == Document.id
            ).outerjoin(
                Service, Document.related_service_id == Service.id
            ).filter(
                Document.business_id == business_id,
                Document.is_active == True,
                Document.indexing_status == IndexingStatus.COMPLETE,
                DocumentChunk.is_active == True,
                or_(*conditions)
            )
            
            # Add service scoping if provided
            if service_id:
                query_builder = query_builder.filter(
                    or_(
                        Document.related_service_id == service_id,
                        Document.related_service_id == None
                    )
                )
            
            chunks = query_builder.limit(limit).all()
            
            logger.info(f"Keyword search found {len(chunks)} chunks")
            return chunks
        
        except Exception as e:
            logger.error(f"Error in keyword fallback: {e}", exc_info=True)
            return []

    def _format_context_with_provenance(self, chunks: List) -> str:
        """Format retrieved chunks with provenance metadata for LLM"""
        if not chunks:
            return ""
        
        context_parts = [
            "=" * 60,
            "RELEVANT KNOWLEDGE (USE THIS TO ANSWER)",
            "=" * 60
        ]
        
        for i, chunk in enumerate(chunks, 1):
            # Extract data (handle both SQL result rows and ORM objects)
            if hasattr(chunk, 'DocumentChunk'):
                # Result from keyword search (tuple)
                chunk_obj = chunk.DocumentChunk
                content = chunk_obj.content
                doc_title = chunk.document_title
                doc_type = chunk.document_type
                service_name = chunk.service_name
                extra_metadata = chunk_obj.extra_metadata
            else:
                # Result from vector search (row object)
                content = chunk.content
                doc_title = chunk.document_title
                doc_type = chunk.document_type
                service_name = chunk.service_name if hasattr(chunk, 'service_name') else None
                extra_metadata = chunk.extra_metadata if hasattr(chunk, 'extra_metadata') else {}
            
            # Build provenance header
            provenance = [f"Source: {doc_title} ({doc_type})"]
            if service_name:
                provenance.append(f"Related Service: {service_name}")
            
            if hasattr(chunk, 'similarity'):
                provenance.append(f"Confidence: {chunk.similarity:.0%}")
            else:
                provenance.append("Match: Keyword")
            
            context_parts.append(f"\n[{' | '.join(provenance)}]")
            
            # Add page number if available (for PDFs)
            if extra_metadata and 'page_number' in extra_metadata:
                context_parts.append(f"Page: {extra_metadata['page_number']}")
            
            context_parts.append(content)
            context_parts.append("-" * 40)
        
        context_parts.append(
            "\n⚠️ IMPORTANT: Use the SPECIFIC information above to answer the customer's question."
            "\nCite sources when possible (e.g., 'According to our [document name]...')."
            "\nDo NOT give generic responses when specific details are provided."
        )
        
        return "\n".join(context_parts)

    def retrieve_context_sync(
        self,
        query: str,
        business_id: str,
        db: Session,
        service_filter: Optional[str] = None,
        document_type_filter: Optional[DocumentType] = None,
        limit: int = None
    ) -> str:
        """
        Synchronous wrapper for retrieve_context.
        Safely handles async operations from sync context (like FastAPI endpoints).
        """
        import asyncio
        import concurrent.futures

        try:
            # Try to get the running loop
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop - safe to use asyncio.run()
            try:
                return asyncio.run(
                    self.retrieve_context(
                        query=query,
                        business_id=business_id,
                        db=db,
                        service_filter=service_filter,
                        document_type_filter=document_type_filter,
                        limit=limit,
                        return_debug_info=False
                    )
                )
            except Exception as e:
                logger.error(f"Error in retrieve_context_sync: {e}")
                return ""

        # There IS a running loop - run in thread pool
        try:
            def run_async_in_thread():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(
                        self.retrieve_context(
                            query=query,
                            business_id=business_id,
                            db=db,
                            service_filter=service_filter,
                            document_type_filter=document_type_filter,
                            limit=limit,
                            return_debug_info=False
                        )
                    )
                finally:
                    new_loop.close()

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_async_in_thread)
                context = future.result(timeout=30)

            logger.info(f"📚 Retrieved RAG context in thread pool ({len(context)} chars)")
            return context

        except concurrent.futures.TimeoutError:
            logger.warning("RAG context retrieval timed out (30s)")
            return ""
        except Exception as e:
            logger.error(f"Error in retrieve_context_sync (thread fallback): {e}")
            return ""