# ============================================================================
# FILE 2: app/api/v1/api_key/conversations.py
# API key authenticated endpoints - thin HTTP layer
# ============================================================================
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
from uuid import UUID

from app.config.database import get_db
from app.models.api_key import APIKey
from app.api.dependencies import require_api_key, require_scope
from app.services.conversation.conversation_query_service import ConversationQueryService

router = APIRouter(prefix="/conversations", tags=["api-conversations"])


@router.get("")
async def list_conversations(
        start_date: Optional[datetime] = Query(None, description="Filter conversations after this date (ISO 8601)"),
        end_date: Optional[datetime] = Query(None, description="Filter conversations before this date (ISO 8601)"),
        status: Optional[str] = Query(None, description="Filter by status (active, completed, expired)"),
        customer_phone: Optional[str] = Query(None, description="Filter by customer phone number"),
        flow_state: Optional[str] = Query(None, description="Filter by flow state"),
        skip: int = Query(0, ge=0, description="Number of records to skip"),
        limit: int = Query(50, ge=1, le=100, description="Number of records to return"),
        api_key: APIKey = Depends(require_api_key),
        _: None = Depends(require_scope("read:conversations")),
        db: Session = Depends(get_db)
):
    """
    Get a list of all conversations for your business.
    Requires API key with 'read:conversations' scope.
    """
    return ConversationQueryService.list_conversations(
        db=db,
        business_id=api_key.business_id,
        start_date=start_date,
        end_date=end_date,
        status=status,
        customer_phone=customer_phone,
        flow_state=flow_state,
        skip=skip,
        limit=limit
    )


@router.get("/{conversation_id}")
async def get_conversation(
        conversation_id: UUID = Path(..., description="The conversation ID"),
        api_key: APIKey = Depends(require_api_key),
        _: None = Depends(require_scope("read:conversations")),
        db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific conversation.
    Requires API key with 'read:conversations' scope.
    """
    result = ConversationQueryService.get_conversation_by_id(
        db=db,
        business_id=api_key.business_id,
        conversation_id=conversation_id
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found or you don't have access to it"
        )

    return result


@router.get("/{conversation_id}/messages")
async def get_conversation_messages(
        conversation_id: UUID = Path(..., description="The conversation ID"),
        skip: int = Query(0, ge=0, description="Number of messages to skip"),
        limit: int = Query(100, ge=1, le=500, description="Number of messages to return"),
        api_key: APIKey = Depends(require_api_key),
        _: None = Depends(require_scope("read:conversations")),
        db: Session = Depends(get_db)
):
    """
    Get all messages for a specific conversation.
    Requires API key with 'read:conversations' scope.
    """
    result = ConversationQueryService.get_conversation_messages(
        db=db,
        business_id=api_key.business_id,
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


@router.get("/search/by-phone")
async def search_conversations_by_phone(
        phone: str = Query(..., description="Phone number to search for", min_length=10),
        skip: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        api_key: APIKey = Depends(require_api_key),
        _: None = Depends(require_scope("read:conversations")),
        db: Session = Depends(get_db)
):
    """
    Search for all conversations with a specific phone number.
    Requires API key with 'read:conversations' scope.
    """
    return ConversationQueryService.search_conversations_by_phone(
        db=db,
        business_id=api_key.business_id,
        phone=phone,
        skip=skip,
        limit=limit
    )


@router.get("/stats/summary")
async def get_conversation_stats(
        start_date: Optional[datetime] = Query(None, description="Stats from this date"),
        end_date: Optional[datetime] = Query(None, description="Stats until this date"),
        api_key: APIKey = Depends(require_api_key),
        _: None = Depends(require_scope("read:conversations")),
        db: Session = Depends(get_db)
):
    """
    Get summary statistics about your conversations.
    Requires API key with 'read:conversations' scope.
    """
    return ConversationQueryService.get_conversation_stats(
        db=db,
        business_id=api_key.business_id,
        start_date=start_date,
        end_date=end_date
    )


@router.get("/{conversation_id}/context")
async def get_conversation_context(
        conversation_id: UUID = Path(..., description="The conversation ID"),
        api_key: APIKey = Depends(require_api_key),
        _: None = Depends(require_scope("read:conversations")),
        db: Session = Depends(get_db)
):
    """
    Get the context and customer info for a conversation.
    Requires API key with 'read:conversations' scope.
    """
    result = ConversationQueryService.get_conversation_context(
        db=db,
        business_id=api_key.business_id,
        conversation_id=conversation_id
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found or you don't have access to it"
        )

    return result
