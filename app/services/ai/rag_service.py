"""
RAG (Retrieval-Augmented Generation) Service - WITH DEBUG SUPPORT
Handles embedding generation, vector storage, and similarity search
"""
import logging
from typing import List, Dict, Optional, Tuple, Union
from datetime import datetime, timezone
from openai import OpenAI
from sqlalchemy.orm import Session
from sqlalchemy import text
import uuid

from app.models.business_knowledge import BusinessKnowledge, KnowledgeCategory
from app.models.business import Business
from app.config.settings import Settings

logger = logging.getLogger(__name__)
settings = Settings()


class RAGService:
    """Handles RAG operations: embedding, indexing, and retrieval"""

    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.embedding_model = "text-embedding-3-small"
        self.embedding_dimension = 1536
        self.similarity_threshold = 0  # Cosine similarity threshold
        self.max_context_chunks = 5  # Max chunks to include in context

    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding vector for text using OpenAI"""
        try:
            text = text.replace("\n", " ").strip()
            if not text:
                raise ValueError("Cannot generate embedding for empty text")

            print(f"🔄 Generating embedding...")

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
            logger.info(f"Generated embedding with dimension: {len(embedding)}")
            print(f"✅ Embedding generated")
            return embedding

        except asyncio.TimeoutError:
            logger.error(f"⏰ Timeout generating embedding for: {text[:50]}...")
            print(f"❌ Timeout after 30s, skipping this chunk")
            raise
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            print(f"❌ Embedding failed: {e}")
            raise

    async def retrieve_context(
            self,
            query: str,
            business_id: str,
            db: Session,
            category_filter: Optional[KnowledgeCategory] = None,
            limit: int = None,
            auto_index: bool = True,
            return_debug_info: bool = False
    ) -> Union[str, Tuple[str, Dict]]:
        """
        Retrieve relevant context for a query using vector similarity search
        with keyword fallback if no results found

        Args:
            query: User's question/message
            business_id: Business to search knowledge for
            db: Database session
            category_filter: Optional category to filter by
            limit: Max number of chunks to retrieve
            auto_index: If True, automatically index business if no knowledge found
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
                "auto_indexed": False,
                "used_fallback": False
            }

            # Check if business has any indexed knowledge
            existing_chunks = db.query(BusinessKnowledge).filter(
                BusinessKnowledge.business_id == business_id,
                BusinessKnowledge.is_active == True
            ).count()

            debug_info["existing_chunks"] = existing_chunks

            # Auto-index if no knowledge exists
            if existing_chunks == 0 and auto_index:
                logger.info(f"No knowledge found for business {business_id}, auto-indexing...")
                index_result = await self.index_business_knowledge(
                    business_id=business_id,
                    db=db,
                    force_reindex=False
                )

                debug_info["auto_indexed"] = True
                debug_info["index_result"] = index_result

                if not index_result["success"]:
                    logger.warning(f"Auto-indexing failed: {index_result['message']}")
                    if return_debug_info:
                        return "", debug_info
                    return ""

                logger.info(f"✅ Auto-indexed {index_result['indexed_count']} chunks")

                if index_result["indexed_count"] == 0:
                    logger.info(f"Business {business_id} has no knowledge to index")
                    if return_debug_info:
                        return "", debug_info
                    return ""

            # Generate embedding for query
            query_embedding = await self.generate_embedding(query)

            # Build similarity search query
            similarity_query = text("""
                SELECT 
                    id,
                    business_id,
                    content,
                    category,
                    extra_metadata,
                    source_field,
                    chunk_index,
                    1 - (embedding <=> :query_embedding) AS similarity
                FROM business_knowledge
                WHERE business_id = :business_id
                    AND is_active = true
                    AND (:category_filter IS NULL OR category = :category_filter)
                    AND 1 - (embedding <=> :query_embedding) > :threshold
                ORDER BY embedding <=> :query_embedding
                LIMIT :limit
            """)

            result = db.execute(
                similarity_query,
                {
                    "query_embedding": str(query_embedding),
                    "business_id": business_id,
                    "category_filter": category_filter.value if category_filter else None,
                    "threshold": self.similarity_threshold,
                    "limit": limit
                }
            )

            chunks = result.fetchall()

            # KEYWORD FALLBACK if no vector results
            if not chunks:
                logger.info(f"No vector results, trying keyword fallback for: {query}")
                chunks = self._keyword_fallback_search(query, business_id, db, limit)
                if chunks:
                    debug_info["used_fallback"] = True
                    logger.info(f"✅ Keyword fallback found {len(chunks)} results")

            debug_info["num_results"] = len(chunks)
            debug_info["similarity_threshold"] = self.similarity_threshold

            if not chunks:
                logger.info(f"No relevant context found for query: {query[:50]}...")
                if return_debug_info:
                    return "", debug_info
                return ""

            # Populate debug info
            for chunk in chunks:
                debug_info["results"].append({
                    "content": chunk.content,
                    "category": chunk.category,
                    "source_field": chunk.source_field,
                    "chunk_type": chunk.category,
                    "score": float(chunk.similarity) if hasattr(chunk, 'similarity') else 0.0,
                    "metadata": chunk.extra_metadata if hasattr(chunk, 'extra_metadata') else {}
                })

            logger.info(
                f"Retrieved {len(chunks)} relevant chunks "
                f"(similarities: {[f'{c.similarity:.3f}' if hasattr(c, 'similarity') else 'keyword' for c in chunks]})"
            )

            # Format context
            context = self.format_context_for_prompt(chunks)

            if return_debug_info:
                return context, debug_info
            return context

        except Exception as e:
            logger.error(f"Error retrieving context: {e}", exc_info=True)
            if return_debug_info:
                return "", {"error": str(e), "query": query}
            return ""

    # Add this method to the RAGService class

    def retrieve_context_sync(
            self,
            query: str,
            business_id: str,
            db: Session,
            category_filter: Optional[KnowledgeCategory] = None,
            limit: int = None,
            auto_index: bool = True
    ) -> str:
        """
        Synchronous wrapper for retrieve_context.
        Safely handles async operations from sync context (like FastAPI endpoints).

        This method detects if there's a running event loop and handles it appropriately.
        """
        import asyncio

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
                        category_filter=category_filter,
                        limit=limit,
                        auto_index=auto_index,
                        return_debug_info=False
                    )
                )
            except Exception as e:
                logger.error(f"Error in retrieve_context_sync: {e}")
                return ""

        # There IS a running loop (we're in async context)
        # We need to run async code in a thread pool to avoid the "cannot be called from running loop" error
        import concurrent.futures
        import threading

        try:
            # Create a new event loop in a separate thread
            def run_async_in_thread():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(
                        self.retrieve_context(
                            query=query,
                            business_id=business_id,
                            db=db,
                            category_filter=category_filter,
                            limit=limit,
                            auto_index=auto_index,
                            return_debug_info=False
                        )
                    )
                finally:
                    new_loop.close()

            # Execute in thread pool with timeout
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_async_in_thread)
                context = future.result(timeout=30)  # 30 second timeout

            logger.info(f"📚 Retrieved RAG context in thread pool ({len(context)} chars)")
            return context

        except concurrent.futures.TimeoutError:
            logger.warning("RAG context retrieval timed out (30s)")
            return ""
        except Exception as e:
            logger.error(f"Error in retrieve_context_sync (thread fallback): {e}")
            return ""
    def _keyword_fallback_search(
            self,
            query: str,
            business_id: str,
            db: Session,
            limit: int
    ) -> List:
        """
        Fallback to keyword matching when vector search returns nothing
        Searches for chunks containing ANY of the meaningful keywords from query
        """
        try:
            from sqlalchemy import or_, func

            # Extract meaningful keywords (remove common stop words)
            stop_words = {
                'what', 'is', 'your', 'the', 'about', 'do', 'you', 'have',
                'a', 'an', 'my', 'can', 'how', 'where', 'when', 'who',
                'does', 'are', 'will', 'would', 'could', 'should'
            }

            # Tokenize and filter
            words = query.lower().replace('?', '').replace('!', '').split()
            keywords = [w for w in words if w not in stop_words and len(w) > 2]

            if not keywords:
                logger.info("No meaningful keywords extracted from query")
                return []

            logger.info(f"Keyword fallback searching for: {keywords}")

            # Build OR conditions for each keyword
            conditions = []
            for keyword in keywords:
                conditions.append(func.lower(BusinessKnowledge.content).contains(keyword))

            # Search for chunks containing ANY keyword
            chunks = db.query(BusinessKnowledge).filter(
                BusinessKnowledge.business_id == business_id,
                BusinessKnowledge.is_active == True,
                or_(*conditions)
            ).limit(limit).all()

            logger.info(f"Keyword search found {len(chunks)} chunks")
            return chunks

        except Exception as e:
            logger.error(f"Error in keyword fallback: {e}", exc_info=True)
            return []

    def format_context_for_prompt(self, chunks: List) -> str:
        """Format retrieved chunks into context string for LLM"""
        if not chunks:
            return ""

        context_parts = [
            "=" * 60,
            "RELEVANT BUSINESS INFORMATION (USE THIS TO ANSWER)",
            "=" * 60
        ]

        for i, chunk in enumerate(chunks, 1):
            category = getattr(chunk, "category", "Uncategorized")
            content = getattr(chunk, "content", "")
            extra_metadata = getattr(chunk, "extra_metadata", {})

            # Handle both SQL result rows (with similarity) and ORM objects (without)
            if hasattr(chunk, 'similarity'):
                confidence_label = f"Confidence: {chunk.similarity:.0%}"
            else:
                confidence_label = "Keyword Match"

            # ✅ Reconstruct Q&A if 'answer' exists in extra_metadata
            if isinstance(extra_metadata, dict) and extra_metadata.get("answer"):
                question = content.strip()
                answer = extra_metadata["answer"].strip()
                formatted_content = f"Q: {question}\nA: {answer}"
            else:
                formatted_content = content

            context_parts.append(f"\n[{category.upper()} - {confidence_label}]")
            context_parts.append(formatted_content)
            context_parts.append("-" * 40)

        context_parts.append(
            "\n⚠️ IMPORTANT: Use the SPECIFIC information above to answer the customer's question."
            "\nDo NOT give generic responses when specific details are provided."
            "\nExample: If asked about service areas and areas are listed above, list those EXACT areas."
        )

        return "\n".join(context_parts)

    # In rag_service.py, update index_business_knowledge method:

    async def index_business_knowledge(
            self,
            business_id: str,
            db: Session,
            force_reindex: bool = False
    ) -> Dict:
        """Index all knowledge from a business into the vector database"""
        try:
            print(f"📥 Fetching business...")
            business = db.query(Business).filter(Business.id == business_id).first()
            if not business:
                return {"success": False, "message": "Business not found"}

            if force_reindex:
                print(f"🗑️  Deleting old knowledge...")
                db.query(BusinessKnowledge).filter(
                    BusinessKnowledge.business_id == business_id
                ).delete()
                db.commit()

            print(f"📝 Preparing documents...")
            documents = self._prepare_documents(business)

            print(f"📊 Found {len(documents)} documents to index")

            if not documents:
                return {
                    "success": False,
                    "message": "No knowledge to index for this business",
                    "indexed_count": 0
                }

            # Generate embeddings and store
            indexed_count = 0
            for i, doc in enumerate(documents, 1):
                try:
                    print(f"⏳ Processing {i}/{len(documents)}: {doc['content'][:40]}...")

                    embedding = await self.generate_embedding(doc["content"])

                    knowledge_chunk = BusinessKnowledge.create_chunk(
                        business_id=uuid.UUID(business_id),
                        content=doc["content"],
                        embedding=embedding,
                        category=doc["category"],
                        source_field=doc["source_field"],
                        chunk_index=doc.get("chunk_index", 0),
                        extra_metadata=doc.get("extra_metadata", {})
                    )

                    db.add(knowledge_chunk)
                    indexed_count += 1
                    print(f"✅ {i}/{len(documents)} indexed")

                except Exception as e:
                    logger.error(f"Error indexing document: {e}")
                    print(f"❌ Failed to index document {i}: {e}")
                    continue

            print(f"💾 Committing to database...")
            db.commit()

            logger.info(f"Successfully indexed {indexed_count} knowledge chunks")
            return {
                "success": True,
                "message": f"Indexed {indexed_count} knowledge chunks",
                "indexed_count": indexed_count,
                "business_id": business_id
            }

        except Exception as e:
            db.rollback()
            logger.error(f"Error indexing business knowledge: {e}", exc_info=True)
            print(f"❌ FATAL ERROR: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "message": f"Failed to index knowledge: {str(e)}",
                "indexed_count": 0
            }

    def _prepare_documents(self, business: Business) -> List[Dict]:
        """
        Extract knowledge from Business model and prepare for indexing
        Uses QUESTION-ONLY approach with answers stored in metadata for optimal matching
        """
        documents = []

        # ========================================================================
        # 1. BUSINESS PROFILE - AREAS SERVED
        # ========================================================================
        if business.business_profile and business.business_profile.get("areas_served"):
            areas = business.business_profile["areas_served"]
            areas_text = ", ".join(areas)
            answer_text = f"We serve {areas_text}."

            # Primary question
            documents.append({
                "content": "What areas do you serve?",
                "category": KnowledgeCategory.GENERAL,
                "source_field": "business_profile",
                "extra_metadata": {
                    "type": "service_areas",
                    "areas": areas,
                    "answer": answer_text
                }
            })

            # Alternative question
            documents.append({
                "content": "Where do you provide services?",
                "category": KnowledgeCategory.GENERAL,
                "source_field": "business_profile",
                "extra_metadata": {
                    "type": "service_areas",
                    "areas": areas,
                    "answer": f"We cover {areas_text}."
                }
            })

            # Another variation
            documents.append({
                "content": "What locations do you cover?",
                "category": KnowledgeCategory.GENERAL,
                "source_field": "business_profile",
                "extra_metadata": {
                    "type": "service_areas",
                    "areas": areas,
                    "answer": answer_text
                }
            })

        # ========================================================================
        # 2. BUSINESS PROFILE - DESCRIPTION
        # ========================================================================
        if business.business_profile and business.business_profile.get("description"):
            description = business.business_profile['description']

            documents.append({
                "content": "What does your business do?",
                "category": KnowledgeCategory.GENERAL,
                "source_field": "business_profile",
                "extra_metadata": {
                    "type": "description",
                    "answer": description
                }
            })

            documents.append({
                "content": "Tell me about your company",
                "category": KnowledgeCategory.GENERAL,
                "source_field": "business_profile",
                "extra_metadata": {
                    "type": "description",
                    "answer": description
                }
            })

            documents.append({
                "content": "What services do you offer?",
                "category": KnowledgeCategory.GENERAL,
                "source_field": "business_profile",
                "extra_metadata": {
                    "type": "description",
                    "answer": description
                }
            })

        # ========================================================================
        # 3. BUSINESS PROFILE - SPECIALTIES
        # ========================================================================
        if business.business_profile and business.business_profile.get("specialties"):
            specialties = business.business_profile['specialties']
            specialties_text = ", ".join(specialties)
            answer_text = f"We specialize in {specialties_text}."

            documents.append({
                "content": "What are your specialties?",
                "category": KnowledgeCategory.GENERAL,
                "source_field": "business_profile",
                "extra_metadata": {
                    "type": "specialties",
                    "specialties": specialties,
                    "answer": answer_text
                }
            })

            documents.append({
                "content": "What do you specialize in?",
                "category": KnowledgeCategory.GENERAL,
                "source_field": "business_profile",
                "extra_metadata": {
                    "type": "specialties",
                    "specialties": specialties,
                    "answer": answer_text
                }
            })

        # ========================================================================
        # 4. SERVICE CATALOG
        # ========================================================================
        if business.service_catalog:
            for service_name, service_info in business.service_catalog.items():
                # Build complete service answer
                details = []
                if service_info.get("description"):
                    details.append(service_info['description'])
                if service_info.get("price"):
                    price = service_info['price']
                    price_text = price if price == 'Free' else f'${price}'
                    details.append(f"Price: {price_text}")
                if service_info.get("duration"):
                    details.append(f"Duration: {service_info['duration']} minutes")

                full_answer = ". ".join(details)

                # Question 1: "Tell me about [service]"
                documents.append({
                    "content": f"Tell me about your {service_name} service",
                    "category": KnowledgeCategory.SERVICE_INFO,
                    "source_field": "service_catalog",
                    "extra_metadata": {
                        "service_name": service_name,
                        "answer": full_answer
                    }
                })

                # Question 2: "Do you offer [service]"
                documents.append({
                    "content": f"Do you offer {service_name}?",
                    "category": KnowledgeCategory.SERVICE_INFO,
                    "source_field": "service_catalog",
                    "extra_metadata": {
                        "service_name": service_name,
                        "answer": f"Yes, {full_answer}"
                    }
                })

                # Question 3: "What is [service]"
                documents.append({
                    "content": f"What is {service_name}?",
                    "category": KnowledgeCategory.SERVICE_INFO,
                    "source_field": "service_catalog",
                    "extra_metadata": {
                        "service_name": service_name,
                        "answer": full_answer
                    }
                })

                # Price-specific question if service has a price
                if service_info.get("price"):
                    price = service_info['price']
                    price_text = price if price == 'Free' else f'${price}'

                    documents.append({
                        "content": f"How much does {service_name} cost?",
                        "category": KnowledgeCategory.PRICING,
                        "source_field": "service_catalog",
                        "extra_metadata": {
                            "service_name": service_name,
                            "price": price,
                            "answer": f"The {service_name} costs {price_text}"
                        }
                    })

                    documents.append({
                        "content": f"What is the price of {service_name}?",
                        "category": KnowledgeCategory.PRICING,
                        "source_field": "service_catalog",
                        "extra_metadata": {
                            "service_name": service_name,
                            "price": price,
                            "answer": price_text
                        }
                    })

        # ========================================================================
        # 5. QUICK RESPONSES (FAQ) - Question-Only
        # ========================================================================
        if business.quick_responses:
            for question, answer in business.quick_responses.items():
                documents.append({
                    "content": question,  # JUST THE QUESTION
                    "category": KnowledgeCategory.FAQ,
                    "source_field": "quick_responses",
                    "extra_metadata": {
                        "question": question,
                        "answer": answer  # ANSWER IN METADATA
                    }
                })

        # ========================================================================
        # 6. CONVERSATION POLICIES - Question-Only
        # ========================================================================
        if business.conversation_policies:
            for policy_key, policy_value in business.conversation_policies.items():
                if isinstance(policy_value, str) and policy_value.strip():
                    # Convert snake_case to readable format
                    policy_name = policy_key.replace('_', ' ')

                    # Question variation 1: "What is your [policy]"
                    documents.append({
                        "content": f"What is your {policy_name}?",
                        "category": KnowledgeCategory.POLICIES,
                        "source_field": "conversation_policies",
                        "extra_metadata": {
                            "policy_key": policy_key,
                            "answer": policy_value
                        }
                    })

                    # Question variation 2: "Can you explain your [policy]"
                    documents.append({
                        "content": f"Can you explain your {policy_name}?",
                        "category": KnowledgeCategory.POLICIES,
                        "source_field": "conversation_policies",
                        "extra_metadata": {
                            "policy_key": policy_key,
                            "answer": policy_value
                        }
                    })

                    # Question variation 3: "Tell me about your [policy]"
                    documents.append({
                        "content": f"Tell me about your {policy_name}",
                        "category": KnowledgeCategory.POLICIES,
                        "source_field": "conversation_policies",
                        "extra_metadata": {
                            "policy_key": policy_key,
                            "answer": policy_value
                        }
                    })

        # ========================================================================
        # 7. CONTACT INFO - Split into Individual Questions
        # ========================================================================
        if business.contact_info:
            # Address
            if business.contact_info.get("address"):
                address = business.contact_info['address']
                documents.append({
                    "content": "What is your address?",
                    "category": KnowledgeCategory.CONTACT_INFO,
                    "source_field": "contact_info",
                    "extra_metadata": {"type": "address", "answer": address}
                })
                documents.append({
                    "content": "Where are you located?",
                    "category": KnowledgeCategory.CONTACT_INFO,
                    "source_field": "contact_info",
                    "extra_metadata": {"type": "address", "answer": address}
                })

            # Email
            if business.contact_info.get("email"):
                email = business.contact_info['email']
                documents.append({
                    "content": "What is your email?",
                    "category": KnowledgeCategory.CONTACT_INFO,
                    "source_field": "contact_info",
                    "extra_metadata": {"type": "email", "answer": email}
                })
                documents.append({
                    "content": "How can I email you?",
                    "category": KnowledgeCategory.CONTACT_INFO,
                    "source_field": "contact_info",
                    "extra_metadata": {"type": "email", "answer": f"You can reach us at {email}"}
                })

            # Website
            if business.contact_info.get("website"):
                website = business.contact_info['website']
                documents.append({
                    "content": "What is your website?",
                    "category": KnowledgeCategory.CONTACT_INFO,
                    "source_field": "contact_info",
                    "extra_metadata": {"type": "website", "answer": website}
                })

            # Office Phone
            if business.contact_info.get("office_phone"):
                phone = business.contact_info['office_phone']
                documents.append({
                    "content": "What is your phone number?",
                    "category": KnowledgeCategory.CONTACT_INFO,
                    "source_field": "contact_info",
                    "extra_metadata": {"type": "phone", "answer": phone}
                })
                documents.append({
                    "content": "How can I call you?",
                    "category": KnowledgeCategory.CONTACT_INFO,
                    "source_field": "contact_info",
                    "extra_metadata": {"type": "phone", "answer": f"You can reach us at {phone}"}
                })

            # Emergency Line
            if business.contact_info.get("emergency_line"):
                emergency = business.contact_info['emergency_line']
                documents.append({
                    "content": "Do you have an emergency contact?",
                    "category": KnowledgeCategory.CONTACT_INFO,
                    "source_field": "contact_info",
                    "extra_metadata": {"type": "emergency", "answer": f"Yes, our emergency line is {emergency}"}
                })

            # General "how to contact" question
            contact_methods = []
            if business.contact_info.get("office_phone"):
                contact_methods.append(f"call us at {business.contact_info['office_phone']}")
            if business.contact_info.get("email"):
                contact_methods.append(f"email {business.contact_info['email']}")
            if business.contact_info.get("website"):
                contact_methods.append(f"visit {business.contact_info['website']}")

            if contact_methods:
                contact_text = ", ".join(contact_methods)
                documents.append({
                    "content": "How can I contact you?",
                    "category": KnowledgeCategory.CONTACT_INFO,
                    "source_field": "contact_info",
                    "extra_metadata": {"type": "general_contact", "answer": f"You can {contact_text}"}
                })

        # ========================================================================
        # 8. AI INSTRUCTIONS
        # ========================================================================
        if business.ai_instructions and business.ai_instructions.strip():
            documents.append({
                "content": "Are there any special instructions for handling customers?",
                "category": KnowledgeCategory.GENERAL,
                "source_field": "ai_instructions",
                "extra_metadata": {"type": "instructions", "answer": business.ai_instructions}
            })

        logger.info(f"Prepared {len(documents)} question-only documents from business {business.id}")
        return documents

    async def check_and_update_if_stale(
            self,
            business_id: str,
            db: Session,
            business_updated_at: datetime
    ) -> bool:
        """Check if indexed knowledge is stale and reindex if needed"""
        try:
            latest_chunk = db.query(BusinessKnowledge).filter(
                BusinessKnowledge.business_id == business_id,
                BusinessKnowledge.is_active == True
            ).order_by(BusinessKnowledge.created_at.desc()).first()

            if not latest_chunk:
                logger.info(f"No knowledge exists for business {business_id}")
                return False

            if business_updated_at > latest_chunk.created_at:
                logger.info(
                    f"Business {business_id} knowledge is stale "
                    f"(business: {business_updated_at}, knowledge: {latest_chunk.created_at})"
                )

                reindex_result = await self.index_business_knowledge(
                    business_id=business_id,
                    db=db,
                    force_reindex=True
                )

                if reindex_result["success"]:
                    logger.info(f"✅ Reindexed {reindex_result['indexed_count']} chunks")
                    return True
                else:
                    logger.error(f"❌ Failed to reindex: {reindex_result['message']}")
                    return False

            return False

        except Exception as e:
            logger.error(f"Error checking knowledge staleness: {e}", exc_info=True)
            return False


    async def delete_business_knowledge(
            self,
            business_id: str,
            db: Session
    ) -> Dict:
        """
        Delete all knowledge for a business

        Args:
            business_id: Business to delete knowledge for
            db: Database session

        Returns:
            Dict with deletion results
        """
        try:
            deleted_count = db.query(BusinessKnowledge).filter(
                BusinessKnowledge.business_id == business_id
            ).delete()

            db.commit()

            logger.info(f"Deleted {deleted_count} knowledge chunks for business {business_id}")

            return {
                "success": True,
                "message": f"Deleted {deleted_count} knowledge chunks",
                "deleted_count": deleted_count
            }

        except Exception as e:
            db.rollback()
            logger.error(f"Error deleting business knowledge: {e}")
            return {
                "success": False,
                "message": f"Failed to delete knowledge: {str(e)}"
            }

    def get_knowledge_stats(self, business_id: str, db: Session) -> Dict:
        """
        Get statistics about indexed knowledge for a business

        Args:
            business_id: Business ID
            db: Database session

        Returns:
            Dict with knowledge statistics
        """
        try:
            total_chunks = db.query(BusinessKnowledge).filter(
                BusinessKnowledge.business_id == business_id,
                BusinessKnowledge.is_active == True
            ).count()

            # Count by category
            category_counts = db.query(
                BusinessKnowledge.category,
                text("COUNT(*)")
            ).filter(
                BusinessKnowledge.business_id == business_id,
                BusinessKnowledge.is_active == True
            ).group_by(BusinessKnowledge.category).all()

            category_breakdown = {
                cat.value: count for cat, count in category_counts
            }

            return {
                "success": True,
                "total_chunks": total_chunks,
                "category_breakdown": category_breakdown,
                "business_id": business_id
            }

        except Exception as e:
            logger.error(f"Error getting knowledge stats: {e}")
            return {
                "success": False,
                "message": str(e)
            }