"""
Business Management Dashboard Routes
Session-authenticated endpoints for managing business information and knowledge
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime
import time
import logging

from app.config.database import get_db
from app.models.user import User
from app.models.business import Business
from app.api.dependencies import get_current_user
from app.schemas.business import (
    BusinessUpdateRequest,
    BusinessResponse,
    BusinessUpdateResponse,
    ReindexResult,
    KnowledgeStatsResponse,
    ManualReindexResponse
)
from app.services.ai.rag_service import RAGService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["dashboard-business"])

# ============================================================================
# REMOVED: rag_service = RAGService()  # Don't initialize at module level
# ============================================================================

# Fields that trigger knowledge reindexing when changed
KNOWLEDGE_FIELDS = {
    "business_profile",
    "service_catalog",
    "conversation_policies",
    "quick_responses",
    "services",
    "contact_info",
    "ai_instructions"
}


# ============================================================================
# Helper Functions
# ============================================================================

def get_rag_service() -> RAGService:
    """Lazy initialization of RAG service"""
    return RAGService()


def detect_changes(business: Business, updates: dict) -> list:
    """
    Detect which fields actually changed by comparing old vs new values.
    Returns list of changed field names.
    """
    changed_fields = []

    for field, new_value in updates.items():
        if new_value is None:
            continue

        old_value = getattr(business, field, None)

        # Compare values (handle dicts/lists specially)
        if isinstance(new_value, (dict, list)):
            if old_value != new_value:
                changed_fields.append(field)
        else:
            if str(old_value) != str(new_value):
                changed_fields.append(field)

    return changed_fields


def should_reindex(changed_fields: list) -> bool:
    """
    Determine if reindexing is needed based on which fields changed.
    Returns True if any knowledge-related field changed.
    """
    return bool(set(changed_fields) & KNOWLEDGE_FIELDS)


# ============================================================================
# GET Business Info
# ============================================================================

@router.get("", response_model=BusinessResponse)
async def get_business(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get complete business information for the current user's business.
    Requires authenticated session.
    """
    if not current_user.active_business_id:
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    business = db.query(Business).filter(
        Business.id == current_user.active_business_id
    ).first()

    if not business:
        raise HTTPException(
            status_code=404,
            detail="Business not found"
        )

    return business


# ============================================================================
# UPDATE Business Info
# ============================================================================

@router.put("", response_model=BusinessUpdateResponse)
async def update_business(
    updates: BusinessUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update business information.

    - Validates all incoming data
    - Detects which fields changed
    - Automatically reindexes knowledge if relevant fields changed
    - Returns updated business + reindex results

    Requires authenticated session.
    """
    if not current_user.active_business_id:
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    # Fetch business
    business = db.query(Business).filter(
        Business.id == current_user.active_business_id
    ).first()

    if not business:
        raise HTTPException(
            status_code=404,
            detail="Business not found"
        )

    # Convert Pydantic model to dict, excluding None values
    update_data = updates.model_dump(exclude_none=True)

    if not update_data:
        raise HTTPException(
            status_code=400,
            detail="No valid fields to update"
        )

    # Detect what actually changed
    changed_fields = detect_changes(business, update_data)

    if not changed_fields:
        # Nothing actually changed
        return BusinessUpdateResponse(
            success=True,
            business=BusinessResponse.model_validate(business),
            changes_detected=[],
            reindex_result=ReindexResult(
                triggered=False,
                reason="No changes detected"
            )
        )

    logger.info(f"Updating business {business.id}: {changed_fields}")

    # Apply updates
    for field, value in update_data.items():
        if hasattr(business, field):
            setattr(business, field, value)

    # Save to database
    try:
        db.commit()
        db.refresh(business)
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving business: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update business: {str(e)}"
        )

    # Check if reindexing is needed
    needs_reindex = should_reindex(changed_fields)

    reindex_result = ReindexResult(triggered=False)

    if needs_reindex:
        logger.info(f"Knowledge fields changed, triggering reindex: {changed_fields}")

        start_time = time.time()

        try:
            # Initialize RAG service here (lazy)
            rag_service = get_rag_service()

            result = await rag_service.index_business_knowledge(
                business_id=str(business.id),
                db=db,
                force_reindex=True
            )

            duration_ms = (time.time() - start_time) * 1000

            reindex_result = ReindexResult(
                triggered=True,
                success=result["success"],
                indexed_count=result.get("indexed_count", 0),
                duration_ms=round(duration_ms, 2),
                message=result.get("message")
            )

            logger.info(f"Reindex completed: {result['indexed_count']} chunks in {duration_ms:.0f}ms")

        except Exception as e:
            logger.error(f"Error reindexing knowledge: {e}", exc_info=True)
            reindex_result = ReindexResult(
                triggered=True,
                success=False,
                message=f"Reindexing failed: {str(e)}"
            )
    else:
        reindex_result = ReindexResult(
            triggered=False,
            reason="No knowledge-related fields were modified"
        )

    return BusinessUpdateResponse(
        success=True,
        business=BusinessResponse.model_validate(business),
        changes_detected=changed_fields,
        reindex_result=reindex_result
    )


# ============================================================================
# Manual Reindex Trigger
# ============================================================================

@router.post("/knowledge/reindex", response_model=ManualReindexResponse)
async def reindex_knowledge(
    force: bool = Query(
        False,
        description="Force full reindex even if knowledge appears up-to-date"
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Manually trigger knowledge reindexing.

    Use this endpoint to:
    - Force a fresh reindex of all business knowledge
    - Recover from failed automatic reindexing
    - Update embeddings after model changes

    Requires authenticated session.
    """
    if not current_user.active_business_id:
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    business = db.query(Business).filter(
        Business.id == current_user.active_business_id
    ).first()

    if not business:
        raise HTTPException(
            status_code=404,
            detail="Business not found"
        )

    logger.info(f"Manual reindex triggered for business {business.id} (force={force})")

    start_time = time.time()

    try:
        # Initialize RAG service here (lazy)
        rag_service = get_rag_service()

        result = await rag_service.index_business_knowledge(
            business_id=str(business.id),
            db=db,
            force_reindex=force
        )

        duration_ms = (time.time() - start_time) * 1000

        if not result["success"]:
            raise HTTPException(
                status_code=500,
                detail=result.get("message", "Reindexing failed")
            )

        return ManualReindexResponse(
            success=True,
            message=result["message"],
            indexed_count=result["indexed_count"],
            business_id=business.id,
            duration_ms=round(duration_ms, 2)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during manual reindex: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Reindexing failed: {str(e)}"
        )


# ============================================================================
# Get Knowledge Stats
# ============================================================================

@router.get("/knowledge/stats", response_model=KnowledgeStatsResponse)
async def get_knowledge_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get statistics about indexed knowledge for your business.

    Returns:
    - Total number of knowledge chunks
    - Breakdown by category (FAQ, services, policies, etc.)
    - Last indexing timestamp

    Requires authenticated session.
    """
    if not current_user.active_business_id:
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    business = db.query(Business).filter(
        Business.id == current_user.active_business_id
    ).first()

    if not business:
        raise HTTPException(
            status_code=404,
            detail="Business not found"
        )

    try:
        # Initialize RAG service here (lazy)
        rag_service = get_rag_service()

        stats = rag_service.get_knowledge_stats(
            business_id=str(business.id),
            db=db
        )

        if not stats["success"]:
            raise HTTPException(
                status_code=500,
                detail="Failed to retrieve knowledge statistics"
            )

        # Get last indexed timestamp from most recent chunk
        from app.models.business_knowledge import BusinessKnowledge
        latest_chunk = db.query(BusinessKnowledge).filter(
            BusinessKnowledge.business_id == business.id,
            BusinessKnowledge.is_active == True
        ).order_by(BusinessKnowledge.created_at.desc()).first()

        last_indexed = latest_chunk.created_at if latest_chunk else None

        return KnowledgeStatsResponse(
            success=True,
            total_chunks=stats["total_chunks"],
            category_breakdown=stats["category_breakdown"],
            business_id=business.id,
            last_indexed=last_indexed
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting knowledge stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get statistics: {str(e)}"
        )