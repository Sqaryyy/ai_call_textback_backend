# ============================================================================
# FILE: app/api/v1/dashboard/conversations.py
# Session authenticated endpoints - thin HTTP layer
# UPDATED: Added comprehensive logging with user audit trail
# IMPORTANT: Specific routes MUST come before parameterized routes
# ============================================================================
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
from uuid import UUID

from app.config.database import get_db
from app.models.auth.user import User
from app.api.dependencies import get_current_user
from app.services.conversation.conversation_query_service import ConversationQueryService
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["dashboard-conversations"])


# ============================================================================
# SPECIFIC ROUTES - Must come BEFORE /{conversation_id}
# ============================================================================

@router.get("/stats/summary")
async def get_conversation_stats(
        start_date: Optional[datetime] = Query(None, description="Stats from this date"),
        end_date: Optional[datetime] = Query(None, description="Stats until this date"),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Get summary statistics about your conversations.
    Requires authenticated session.
    """
    if not current_user.active_business_id:
        logger.warning(
            f"User {current_user.id} attempted to get conversation stats without active business"
        )
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    date_range = "all time"
    if start_date and end_date:
        date_range = f"{start_date.date()} to {end_date.date()}"
    elif start_date:
        date_range = f"from {start_date.date()}"
    elif end_date:
        date_range = f"until {end_date.date()}"

    logger.info(
        f"User {current_user.id} requesting conversation statistics for business {current_user.active_business_id} - "
        f"Date range: {date_range}"
    )

    result = ConversationQueryService.get_conversation_stats(
        db=db,
        business_id=current_user.active_business_id,
        start_date=start_date,
        end_date=end_date
    )

    logger.info(
        f"Conversation statistics retrieved for business {current_user.active_business_id} - "
        f"Total conversations: {result.get('total_conversations', 0)}, "
        f"Active: {result.get('active_conversations', 0)}"
    )

    return result


@router.get("/search/by-phone")
async def search_conversations_by_phone(
        phone: str = Query(..., description="Phone number to search for", min_length=10),
        skip: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Search for all conversations with a specific phone number.
    Requires authenticated session.
    """
    if not current_user.active_business_id:
        logger.warning(
            f"User {current_user.id} attempted to search conversations by phone without active business"
        )
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    # Mask phone number for privacy logging (show only last 4 digits)
    masked_phone = f"***{phone[-4:]}" if len(phone) >= 4 else "***"

    logger.info(
        f"User {current_user.id} searching conversations by phone for business {current_user.active_business_id} - "
        f"Phone: {masked_phone}, Skip: {skip}, Limit: {limit}"
    )

    result = ConversationQueryService.search_conversations_by_phone(
        db=db,
        business_id=current_user.active_business_id,
        phone=phone,
        skip=skip,
        limit=limit
    )

    conversation_count = len(result.get('conversations', []))
    total_count = result.get('total', 0)

    logger.info(
        f"Phone search completed - Found {conversation_count} conversations (Total: {total_count}) "
        f"for phone {masked_phone} in business {current_user.active_business_id}"
    )

    return result


# ============================================================================
# LIST ROUTE - Base endpoint
# ============================================================================

@router.get("")
async def list_conversations(
        start_date: Optional[datetime] = Query(None, description="Filter conversations after this date (ISO 8601)"),
        end_date: Optional[datetime] = Query(None, description="Filter conversations before this date (ISO 8601)"),
        status: Optional[str] = Query(None, description="Filter by status (active, completed, expired)"),
        customer_phone: Optional[str] = Query(None, description="Filter by customer phone number"),
        flow_state: Optional[str] = Query(None, description="Filter by flow state"),
        skip: int = Query(0, ge=0, description="Number of records to skip"),
        limit: int = Query(50, ge=1, le=100, description="Number of records to return"),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Get a list of all conversations for your business.
    Requires authenticated session.
    """
    if not current_user.active_business_id:
        logger.warning(
            f"User {current_user.id} attempted to list conversations without active business"
        )
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    # Build filter description for logging
    filters = []
    if start_date:
        filters.append(f"start_date={start_date.date()}")
    if end_date:
        filters.append(f"end_date={end_date.date()}")
    if status:
        filters.append(f"status={status}")
    if customer_phone:
        # Mask phone number for privacy (show only last 4 digits)
        masked_phone = f"***{customer_phone[-4:]}" if len(customer_phone) >= 4 else "***"
        filters.append(f"phone={masked_phone}")
    if flow_state:
        filters.append(f"flow_state={flow_state}")

    filter_str = ", ".join(filters) if filters else "no filters"

    logger.info(
        f"User {current_user.id} listing conversations for business {current_user.active_business_id} - "
        f"Filters: {filter_str}, Skip: {skip}, Limit: {limit}"
    )

    result = ConversationQueryService.list_conversations(
        db=db,
        business_id=current_user.active_business_id,
        start_date=start_date,
        end_date=end_date,
        status=status,
        customer_phone=customer_phone,
        flow_state=flow_state,
        skip=skip,
        limit=limit
    )

    conversation_count = len(result.get('conversations', []))
    total_count = result.get('total', 0)

    logger.info(
        f"Returned {conversation_count} conversations (Total: {total_count}) for business {current_user.active_business_id}"
    )

    return result


# ============================================================================
# PARAMETERIZED ROUTES - Must come AFTER specific routes
# ============================================================================

@router.get("/{conversation_id:uuid}/messages")
async def get_conversation_messages(
        conversation_id: UUID = Path(..., description="The conversation ID"),
        skip: int = Query(0, ge=0, description="Number of messages to skip"),
        limit: int = Query(100, ge=1, le=500, description="Number of messages to return"),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Get all messages for a specific conversation.
    Requires authenticated session.
    """
    if not current_user.active_business_id:
        logger.warning(
            f"User {current_user.id} attempted to get conversation messages without active business"
        )
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    logger.info(
        f"User {current_user.id} requesting messages for conversation {conversation_id} - "
        f"Business: {current_user.active_business_id}, Skip: {skip}, Limit: {limit}"
    )

    result = ConversationQueryService.get_conversation_messages(
        db=db,
        business_id=current_user.active_business_id,
        conversation_id=conversation_id,
        skip=skip,
        limit=limit
    )

    if not result:
        logger.warning(
            f"Conversation {conversation_id} not found or access denied - "
            f"Business: {current_user.active_business_id}, User: {current_user.id}"
        )
        raise HTTPException(
            status_code=404,
            detail="Conversation not found or you don't have access to it"
        )

    message_count = len(result.get('messages', []))
    total_count = result.get('total', 0)

    logger.info(
        f"Messages retrieved for conversation {conversation_id} - "
        f"Returned: {message_count}, Total: {total_count}"
    )

    return result


@router.get("/{conversation_id:uuid}/context")
async def get_conversation_context(
        conversation_id: UUID = Path(..., description="The conversation ID"),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Get the context and customer info for a conversation.
    Requires authenticated session.
    """
    if not current_user.active_business_id:
        logger.warning(
            f"User {current_user.id} attempted to get conversation context without active business"
        )
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    logger.info(
        f"User {current_user.id} requesting context for conversation {conversation_id} - "
        f"Business: {current_user.active_business_id}"
    )

    result = ConversationQueryService.get_conversation_context(
        db=db,
        business_id=current_user.active_business_id,
        conversation_id=conversation_id
    )

    if not result:
        logger.warning(
            f"Conversation {conversation_id} context not found or access denied - "
            f"Business: {current_user.active_business_id}, User: {current_user.id}"
        )
        raise HTTPException(
            status_code=404,
            detail="Conversation not found or you don't have access to it"
        )

    logger.info(
        f"Context retrieved for conversation {conversation_id} - "
        f"Flow state: {result.get('flow_state')}, Has context: {bool(result.get('context'))}"
    )

    return result


@router.get("/{conversation_id:uuid}")
async def get_conversation(
        conversation_id: UUID = Path(..., description="The conversation ID"),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific conversation.
    Requires authenticated session.
    """
    if not current_user.active_business_id:
        logger.warning(
            f"User {current_user.id} attempted to get conversation details without active business"
        )
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    logger.info(
        f"User {current_user.id} requesting conversation details - "
        f"Conversation ID: {conversation_id}, Business: {current_user.active_business_id}"
    )

    result = ConversationQueryService.get_conversation_by_id(
        db=db,
        business_id=current_user.active_business_id,
        conversation_id=conversation_id
    )

    if not result:
        logger.warning(
            f"Conversation {conversation_id} not found or access denied - "
            f"Business: {current_user.active_business_id}, User: {current_user.id}"
        )
        raise HTTPException(
            status_code=404,
            detail="Conversation not found or you don't have access to it"
        )

    logger.info(
        f"Conversation details retrieved - "
        f"Conversation ID: {conversation_id}, Status: {result.get('status')}, "
        f"Flow state: {result.get('flow_state')}, Message count: {result.get('message_count', 0)}"
    )

    return result