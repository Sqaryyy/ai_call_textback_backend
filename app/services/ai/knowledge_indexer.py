"""
Knowledge Indexer - Background job for indexing business knowledge
Handles bulk operations, re-indexing, and batch processing
"""
import logging
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.services.ai.rag_service import RAGService
from app.models.business import Business
from app.models.business_knowledge import BusinessKnowledge
from app.config.settings import Settings

logger = logging.getLogger(__name__)
settings = Settings()


class KnowledgeIndexer:
    """Handles batch indexing and reindexing of business knowledge"""

    def __init__(self):
        self.rag_service = RAGService()

    async def index_single_business(
            self,
            business_id: str,
            db: Session,
            force_reindex: bool = False
    ) -> Dict:
        """
        Index knowledge for a single business

        Args:
            business_id: Business to index
            db: Database session
            force_reindex: Delete existing knowledge before indexing

        Returns:
            Dict with indexing results
        """
        try:
            logger.info(f"Starting indexing for business {business_id}")

            result = await self.rag_service.index_business_knowledge(
                business_id=business_id,
                db=db,
                force_reindex=force_reindex
            )

            if result["success"]:
                logger.info(f"✅ Successfully indexed business {business_id}: {result['indexed_count']} chunks")
            else:
                logger.error(f"❌ Failed to index business {business_id}: {result['message']}")

            return result

        except Exception as e:
            logger.error(f"Error indexing single business {business_id}: {e}", exc_info=True)
            return {
                "success": False,
                "message": str(e),
                "business_id": business_id
            }

    async def index_all_businesses(
            self,
            db: Session,
            force_reindex: bool = False,
            batch_size: int = None
    ) -> Dict:
        """
        Index knowledge for all active businesses

        Args:
            db: Database session
            force_reindex: Delete existing knowledge before indexing
            batch_size: Number of businesses to process at once

        Returns:
            Dict with overall results
        """
        try:
            if batch_size is None:
                batch_size = settings.RAG_BATCH_SIZE

            # Fetch all active businesses
            businesses = db.query(Business).filter(Business.is_active == True).all()

            if not businesses:
                return {
                    "success": True,
                    "message": "No active businesses to index",
                    "total_businesses": 0,
                    "successful": 0,
                    "failed": 0
                }

            logger.info(f"Starting bulk indexing for {len(businesses)} businesses")

            results = {
                "total_businesses": len(businesses),
                "successful": 0,
                "failed": 0,
                "details": []
            }

            # Process in batches
            for i in range(0, len(businesses), batch_size):
                batch = businesses[i:i + batch_size]
                logger.info(f"Processing batch {i // batch_size + 1} ({len(batch)} businesses)")

                for business in batch:
                    result = await self.index_single_business(
                        business_id=str(business.id),
                        db=db,
                        force_reindex=force_reindex
                    )

                    if result["success"]:
                        results["successful"] += 1
                    else:
                        results["failed"] += 1

                    results["details"].append({
                        "business_id": str(business.id),
                        "business_name": business.name,
                        "success": result["success"],
                        "indexed_count": result.get("indexed_count", 0),
                        "message": result.get("message", "")
                    })

            logger.info(
                f"✅ Bulk indexing complete: {results['successful']} successful, "
                f"{results['failed']} failed out of {results['total_businesses']}"
            )

            return {
                "success": True,
                "message": f"Indexed {results['successful']} businesses",
                **results
            }

        except Exception as e:
            logger.error(f"Error in bulk indexing: {e}", exc_info=True)
            return {
                "success": False,
                "message": str(e)
            }

    async def reindex_business(
            self,
            business_id: str,
            db: Session
    ) -> Dict:
        """
        Reindex a business (delete old knowledge and create new)

        Args:
            business_id: Business to reindex
            db: Database session

        Returns:
            Dict with reindexing results
        """
        try:
            logger.info(f"Reindexing business {business_id}")

            # Delete existing knowledge
            delete_result = await self.rag_service.delete_business_knowledge(
                business_id=business_id,
                db=db
            )

            if not delete_result["success"]:
                return {
                    "success": False,
                    "message": f"Failed to delete old knowledge: {delete_result['message']}"
                }

            logger.info(f"Deleted {delete_result['deleted_count']} old chunks")

            # Index new knowledge
            index_result = await self.rag_service.index_business_knowledge(
                business_id=business_id,
                db=db,
                force_reindex=False  # Already deleted above
            )

            if index_result["success"]:
                return {
                    "success": True,
                    "message": f"Reindexed successfully: {index_result['indexed_count']} new chunks",
                    "deleted_count": delete_result["deleted_count"],
                    "indexed_count": index_result["indexed_count"]
                }
            else:
                return {
                    "success": False,
                    "message": f"Failed to index new knowledge: {index_result['message']}"
                }

        except Exception as e:
            logger.error(f"Error reindexing business {business_id}: {e}", exc_info=True)
            return {
                "success": False,
                "message": str(e)
            }

    async def update_business_knowledge_incremental(
            self,
            business_id: str,
            db: Session,
            updated_fields: List[str] = None
    ) -> Dict:
        """
        Incrementally update knowledge for specific business fields
        Useful when only certain fields change (e.g., service_catalog updated)

        Args:
            business_id: Business to update
            db: Database session
            updated_fields: List of field names that changed (e.g., ['service_catalog', 'business_profile'])

        Returns:
            Dict with update results
        """
        try:
            if not updated_fields:
                logger.info("No fields specified for incremental update, doing full reindex")
                return await self.reindex_business(business_id, db)

            logger.info(f"Incremental update for business {business_id}, fields: {updated_fields}")

            # Delete knowledge chunks from those specific fields
            deleted_count = 0
            for field in updated_fields:
                result = db.query(BusinessKnowledge).filter(
                    BusinessKnowledge.business_id == business_id,
                    BusinessKnowledge.source_field == field
                ).delete()
                deleted_count += result

            db.commit()
            logger.info(f"Deleted {deleted_count} chunks from updated fields")

            # Fetch business
            business = db.query(Business).filter(Business.id == business_id).first()
            if not business:
                return {"success": False, "message": "Business not found"}

            # Prepare documents only from updated fields
            documents = []
            for field in updated_fields:
                field_docs = self._get_documents_for_field(business, field)
                documents.extend(field_docs)

            if not documents:
                return {
                    "success": True,
                    "message": "No new documents to index from updated fields",
                    "deleted_count": deleted_count,
                    "indexed_count": 0
                }

            # Index new documents
            indexed_count = 0
            for doc in documents:
                try:
                    embedding = await self.rag_service.generate_embedding(doc["content"])

                    knowledge_chunk = BusinessKnowledge.create_chunk(
                        business_id=business.id,
                        content=doc["content"],
                        embedding=embedding,
                        category=doc["category"],
                        source_field=doc["source_field"],
                        chunk_index=doc.get("chunk_index", 0),
                        extra_metadata=doc.get("metadata", {})
                    )

                    db.add(knowledge_chunk)
                    indexed_count += 1

                except Exception as e:
                    logger.error(f"Error indexing document: {e}")
                    continue

            db.commit()

            return {
                "success": True,
                "message": f"Incremental update complete: deleted {deleted_count}, indexed {indexed_count}",
                "deleted_count": deleted_count,
                "indexed_count": indexed_count,
                "updated_fields": updated_fields
            }

        except Exception as e:
            db.rollback()
            logger.error(f"Error in incremental update: {e}", exc_info=True)
            return {
                "success": False,
                "message": str(e)
            }

    """
    Updated _get_documents_for_field method for knowledge_indexer.py
    Replace the existing method in KnowledgeIndexer class
    """

    def _get_documents_for_field(self, business: Business, field_name: str) -> List[Dict]:
        """
        Get documents for a specific business field (for incremental updates)
        Uses QUESTION-ONLY approach matching _prepare_documents in RAGService
        """
        from app.models.business_knowledge import KnowledgeCategory
        documents = []

        if field_name == "service_catalog" and business.service_catalog:
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

                # Question variations (QUESTION-ONLY)
                documents.append({
                    "content": f"Tell me about your {service_name} service",
                    "category": KnowledgeCategory.SERVICE_INFO,
                    "source_field": "service_catalog",
                    "extra_metadata": {"service_name": service_name, "answer": full_answer}
                })

                documents.append({
                    "content": f"Do you offer {service_name}?",
                    "category": KnowledgeCategory.SERVICE_INFO,
                    "source_field": "service_catalog",
                    "extra_metadata": {"service_name": service_name, "answer": f"Yes, {full_answer}"}
                })

                if service_info.get("price"):
                    price = service_info['price']
                    price_text = price if price == 'Free' else f'${price}'
                    documents.append({
                        "content": f"How much does {service_name} cost?",
                        "category": KnowledgeCategory.PRICING,
                        "source_field": "service_catalog",
                        "extra_metadata": {"service_name": service_name, "answer": price_text}
                    })

        elif field_name == "business_profile" and business.business_profile:
            profile = business.business_profile

            if profile.get("description"):
                description = profile['description']
                documents.append({
                    "content": "What does your business do?",
                    "category": KnowledgeCategory.GENERAL,
                    "source_field": "business_profile",
                    "extra_metadata": {"type": "description", "answer": description}
                })
                documents.append({
                    "content": "Tell me about your company",
                    "category": KnowledgeCategory.GENERAL,
                    "source_field": "business_profile",
                    "extra_metadata": {"type": "description", "answer": description}
                })

            if profile.get("specialties"):
                specialties_text = ", ".join(profile['specialties'])
                answer = f"We specialize in {specialties_text}."
                documents.append({
                    "content": "What are your specialties?",
                    "category": KnowledgeCategory.GENERAL,
                    "source_field": "business_profile",
                    "extra_metadata": {"type": "specialties", "answer": answer}
                })

            if profile.get("areas_served"):
                areas_text = ", ".join(profile['areas_served'])
                answer = f"We serve {areas_text}."
                documents.append({
                    "content": "What areas do you serve?",
                    "category": KnowledgeCategory.GENERAL,
                    "source_field": "business_profile",
                    "extra_metadata": {"type": "service_areas", "answer": answer}
                })

        elif field_name == "conversation_policies" and business.conversation_policies:
            for policy_key, policy_value in business.conversation_policies.items():
                if isinstance(policy_value, str) and policy_value.strip():
                    policy_name = policy_key.replace('_', ' ')

                    # Question variations (QUESTION-ONLY)
                    documents.append({
                        "content": f"What is your {policy_name}?",
                        "category": KnowledgeCategory.POLICIES,
                        "source_field": "conversation_policies",
                        "extra_metadata": {"policy_key": policy_key, "answer": policy_value}
                    })

                    documents.append({
                        "content": f"Can you explain your {policy_name}?",
                        "category": KnowledgeCategory.POLICIES,
                        "source_field": "conversation_policies",
                        "extra_metadata": {"policy_key": policy_key, "answer": policy_value}
                    })

        elif field_name == "quick_responses" and business.quick_responses:
            for question, answer in business.quick_responses.items():
                documents.append({
                    "content": question,  # QUESTION-ONLY
                    "category": KnowledgeCategory.FAQ,
                    "source_field": "quick_responses",
                    "extra_metadata": {"question": question, "answer": answer}
                })

        elif field_name == "contact_info" and business.contact_info:
            # Split contact info into individual questions
            if business.contact_info.get("address"):
                address = business.contact_info['address']
                documents.append({
                    "content": "What is your address?",
                    "category": KnowledgeCategory.CONTACT_INFO,
                    "source_field": "contact_info",
                    "extra_metadata": {"type": "address", "answer": address}
                })

            if business.contact_info.get("email"):
                email = business.contact_info['email']
                documents.append({
                    "content": "What is your email?",
                    "category": KnowledgeCategory.CONTACT_INFO,
                    "source_field": "contact_info",
                    "extra_metadata": {"type": "email", "answer": email}
                })

            if business.contact_info.get("office_phone"):
                phone = business.contact_info['office_phone']
                documents.append({
                    "content": "What is your phone number?",
                    "category": KnowledgeCategory.CONTACT_INFO,
                    "source_field": "contact_info",
                    "extra_metadata": {"type": "phone", "answer": phone}
                })

        elif field_name == "ai_instructions" and business.ai_instructions and business.ai_instructions.strip():
            documents.append({
                "content": "Are there any special instructions for handling customers?",
                "category": KnowledgeCategory.GENERAL,
                "source_field": "ai_instructions",
                "extra_metadata": {"type": "instructions", "answer": business.ai_instructions}
            })

        return documents

    def get_indexing_status(self, db: Session) -> Dict:
        """
        Get overall indexing status for all businesses

        Returns:
            Dict with indexing statistics
        """
        try:
            total_businesses = db.query(Business).filter(Business.is_active == True).count()

            indexed_businesses = db.query(BusinessKnowledge.business_id).distinct().count()

            total_chunks = db.query(BusinessKnowledge).filter(
                BusinessKnowledge.is_active == True
            ).count()

            return {
                "success": True,
                "total_active_businesses": total_businesses,
                "indexed_businesses": indexed_businesses,
                "not_indexed": total_businesses - indexed_businesses,
                "total_knowledge_chunks": total_chunks,
                "average_chunks_per_business": round(total_chunks / indexed_businesses,
                                                     2) if indexed_businesses > 0 else 0
            }

        except Exception as e:
            logger.error(f"Error getting indexing status: {e}")
            return {
                "success": False,
                "message": str(e)
            }