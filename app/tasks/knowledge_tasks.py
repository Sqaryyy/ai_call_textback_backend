"""
Celery tasks for knowledge indexing operations
"""
import logging
from typing import List, Optional
from sqlalchemy.orm import Session

from app.config.celery_config import celery_app
from app.config.database import get_db
from app.services.ai.knowledge_indexer import KnowledgeIndexer

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.index_business_knowledge", bind=True, max_retries=3)
def index_business_knowledge(self, business_id: str, force_reindex: bool = False):
    """
    Index knowledge for a single business

    Args:
        business_id: Business UUID to index
        force_reindex: Delete existing knowledge before indexing
    """
    try:
        logger.info(f"📚 Starting knowledge indexing task for business {business_id}")

        db = next(get_db())
        indexer = KnowledgeIndexer()

        # Run async function in sync context
        import asyncio
        result = asyncio.run(
            indexer.index_single_business(
                business_id=business_id,
                db=db,
                force_reindex=force_reindex
            )
        )

        db.close()

        if result["success"]:
            logger.info(f"✅ Successfully indexed {result['indexed_count']} chunks for business {business_id}")
            return {
                "status": "success",
                "business_id": business_id,
                "indexed_count": result["indexed_count"]
            }
        else:
            logger.error(f"❌ Failed to index business {business_id}: {result['message']}")
            return {
                "status": "failed",
                "business_id": business_id,
                "message": result["message"]
            }

    except Exception as e:
        logger.error(f"Error in index_business_knowledge task: {e}", exc_info=True)
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


@celery_app.task(name="tasks.index_all_businesses", bind=True)
def index_all_businesses(self, force_reindex: bool = False, batch_size: int = 10):
    """
    Index knowledge for all active businesses

    Args:
        force_reindex: Delete existing knowledge before indexing
        batch_size: Number of businesses to process at once
    """
    try:
        logger.info(f"📚 Starting bulk knowledge indexing task")

        db = next(get_db())
        indexer = KnowledgeIndexer()

        import asyncio
        result = asyncio.run(
            indexer.index_all_businesses(
                db=db,
                force_reindex=force_reindex,
                batch_size=batch_size
            )
        )

        db.close()

        logger.info(
            f"✅ Bulk indexing complete: {result['successful']} successful, "
            f"{result['failed']} failed out of {result['total_businesses']}"
        )

        return {
            "status": "success",
            "total_businesses": result["total_businesses"],
            "successful": result["successful"],
            "failed": result["failed"]
        }

    except Exception as e:
        logger.error(f"Error in index_all_businesses task: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=300)  # Retry after 5 minutes


@celery_app.task(name="tasks.reindex_business_knowledge", bind=True, max_retries=3)
def reindex_business_knowledge(self, business_id: str):
    """
    Reindex knowledge for a business (delete old + create new)

    Args:
        business_id: Business UUID to reindex
    """
    try:
        logger.info(f"📚 Starting knowledge reindexing task for business {business_id}")

        db = next(get_db())
        indexer = KnowledgeIndexer()

        import asyncio
        result = asyncio.run(
            indexer.reindex_business(
                business_id=business_id,
                db=db
            )
        )

        db.close()

        if result["success"]:
            logger.info(
                f"✅ Successfully reindexed business {business_id}: "
                f"deleted {result['deleted_count']}, indexed {result['indexed_count']} chunks"
            )
            return {
                "status": "success",
                "business_id": business_id,
                "deleted_count": result["deleted_count"],
                "indexed_count": result["indexed_count"]
            }
        else:
            logger.error(f"❌ Failed to reindex business {business_id}: {result['message']}")
            return {
                "status": "failed",
                "business_id": business_id,
                "message": result["message"]
            }

    except Exception as e:
        logger.error(f"Error in reindex_business_knowledge task: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


@celery_app.task(name="tasks.update_business_knowledge_incremental", bind=True, max_retries=3)
def update_business_knowledge_incremental(
        self,
        business_id: str,
        updated_fields: List[str]
):
    """
    Incrementally update knowledge for specific business fields

    Args:
        business_id: Business UUID
        updated_fields: List of field names that changed
    """
    try:
        logger.info(
            f"📚 Starting incremental knowledge update for business {business_id}, "
            f"fields: {updated_fields}"
        )

        db = next(get_db())
        indexer = KnowledgeIndexer()

        import asyncio
        result = asyncio.run(
            indexer.update_business_knowledge_incremental(
                business_id=business_id,
                db=db,
                updated_fields=updated_fields
            )
        )

        db.close()

        if result["success"]:
            logger.info(
                f"✅ Incremental update complete for business {business_id}: "
                f"deleted {result['deleted_count']}, indexed {result['indexed_count']} chunks"
            )
            return {
                "status": "success",
                "business_id": business_id,
                "deleted_count": result["deleted_count"],
                "indexed_count": result["indexed_count"],
                "updated_fields": updated_fields
            }
        else:
            logger.error(f"❌ Failed incremental update for business {business_id}: {result['message']}")
            return {
                "status": "failed",
                "business_id": business_id,
                "message": result["message"]
            }

    except Exception as e:
        logger.error(f"Error in update_business_knowledge_incremental task: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


@celery_app.task(name="tasks.delete_business_knowledge")
def delete_business_knowledge(business_id: str):
    """
    Delete all knowledge for a business

    Args:
        business_id: Business UUID
    """
    try:
        logger.info(f"📚 Deleting knowledge for business {business_id}")

        db = next(get_db())
        indexer = KnowledgeIndexer()

        import asyncio
        result = asyncio.run(
            indexer.rag_service.delete_business_knowledge(
                business_id=business_id,
                db=db
            )
        )

        db.close()

        if result["success"]:
            logger.info(f"✅ Deleted {result['deleted_count']} chunks for business {business_id}")
            return {
                "status": "success",
                "business_id": business_id,
                "deleted_count": result["deleted_count"]
            }
        else:
            logger.error(f"❌ Failed to delete knowledge for business {business_id}: {result['message']}")
            return {
                "status": "failed",
                "business_id": business_id,
                "message": result["message"]
            }

    except Exception as e:
        logger.error(f"Error in delete_business_knowledge task: {e}", exc_info=True)
        raise