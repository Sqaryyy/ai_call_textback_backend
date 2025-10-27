# ============================================================================
# FILE 3: app/api/v1/dashboard/conversations.py
# Session authenticated endpoints - thin HTTP layer
# IMPORTANT: Specific routes MUST come before parameterized routes
# ============================================================================
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
from uuid import UUID

from app.config.database import get_db
from app.models.user import User
from app.api.dependencies import get_current_user
from app.services.conversation.conversation_query_service import ConversationQueryService

router = APIRouter(prefix="/conversations", tags=["dashboard-conversations"])


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
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    return ConversationQueryService.get_conversation_stats(
        db=db,
        business_id=current_user.active_business_id,
        start_date=start_date,
        end_date=end_date
    )


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
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    return ConversationQueryService.search_conversations_by_phone(
        db=db,
        business_id=current_user.active_business_id,
        phone=phone,
        skip=skip,
        limit=limit
    )


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
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    return ConversationQueryService.list_conversations(
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
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    result = ConversationQueryService.get_conversation_messages(
        db=db,
        business_id=current_user.active_business_id,
        conversation_id=conversation_id,
        skip=skip,
        limit=limit
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found or you don't have access to it"
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
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    result = ConversationQueryService.get_conversation_context(
        db=db,
        business_id=current_user.active_business_id,
        conversation_id=conversation_id
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found or you don't have access to it"
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
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    result = ConversationQueryService.get_conversation_by_id(
        db=db,
        business_id=current_user.active_business_id,
        conversation_id=conversation_id
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found or you don't have access to it"
        )

    return result