# ============================================================================
# FILE: app/api/v1/admin/conversations.py
# Platform admin endpoints for managing conversations
# CRITICAL: Contains sensitive PII (phone numbers, customer info, context)
# ============================================================================
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Optional, List
from uuid import UUID
from datetime import datetime

from app.api.dependencies import get_db, require_platform_admin
from app.models.auth.user import User
from app.models.conversation.conversation import Conversation
from app.utils.logger import get_logger
from app.schemas.admin.conversations import (
    MessageResponse,
    ConversationResponse,
    ConversationListResponse,
    ConversationStatsResponse,
    UpdateConversationRequest,
    ConversationsByBusinessResponse
)
logger = get_logger(__name__)
router = APIRouter(prefix="/conversations", tags=["Admin - Conversations"])

# ============================================================================
# Admin Conversation Endpoints
# ============================================================================

@router.get("/", response_model=ConversationListResponse)
async def list_conversations(
        page: int = Query(1, ge=1, description="Page number"),
        page_size: int = Query(50, ge=1, le=100, description="Items per page"),
        business_id: Optional[UUID] = Query(None, description="Filter by business ID"),
        status: Optional[str] = Query(None, description="Filter by status"),
        flow_state: Optional[str] = Query(None, description="Filter by flow state"),
        is_active: Optional[bool] = Query(None, description="Filter by active status"),
        customer_phone: Optional[str] = Query(None, description="Filter by customer phone"),
        conversation_sid: Optional[str] = Query(None, description="Filter by conversation SID"),
        from_date: Optional[datetime] = Query(None, description="Filter from date"),
        to_date: Optional[datetime] = Query(None, description="Filter to date"),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    List all conversations with filtering and pagination.

    Requires platform admin role.
    """
    # Build filter description for logging (WITHOUT PII)
    filters_applied = []
    if business_id:
        filters_applied.append("business_id")
    if status:
        filters_applied.append(f"status={status}")
    if flow_state:
        filters_applied.append(f"flow_state={flow_state}")
    if is_active is not None:
        filters_applied.append(f"is_active={is_active}")
    if customer_phone:
        filters_applied.append("customer_phone")  # Don't log the actual phone number
    if conversation_sid:
        filters_applied.append("conversation_sid")
    if from_date or to_date:
        filters_applied.append("date_range")

    filter_str = f" with filters: {', '.join(filters_applied)}" if filters_applied else ""
    logger.info(f"Admin {current_user.id} listing conversations - Page {page}, Size {page_size}{filter_str}")

    query = db.query(Conversation)

    # Apply filters
    if business_id:
        query = query.filter(Conversation.business_id == business_id)
    if status:
        query = query.filter(Conversation.status == status)
    if flow_state:
        query = query.filter(Conversation.flow_state == flow_state)
    if is_active is not None:
        query = query.filter(Conversation.is_active == is_active)
    if customer_phone:
        query = query.filter(Conversation.customer_phone == customer_phone)
        logger.debug("Filtering by specific customer phone number")  # Generic message
    if conversation_sid:
        query = query.filter(Conversation.conversation_sid == conversation_sid)
    if from_date:
        query = query.filter(Conversation.created_at >= from_date)
    if to_date:
        query = query.filter(Conversation.created_at <= to_date)

    # Get total count
    total = query.count()

    # Calculate pagination
    pages = (total + page_size - 1) // page_size
    offset = (page - 1) * page_size

    # Get paginated results
    conversations = query.order_by(desc(Conversation.created_at)).offset(offset).limit(page_size).all()

    logger.info(f"Returning {len(conversations)} conversations out of {total} total")

    items = [
        ConversationResponse(
            id=str(conv.id),
            conversation_sid=conv.conversation_sid,
            customer_phone=conv.customer_phone,
            business_phone=conv.business_phone,
            business_id=str(conv.business_id),
            status=conv.status,
            flow_state=conv.flow_state,
            customer_info=conv.customer_info or {},
            context=conv.context or {},
            message_count=conv.message_count,
            created_at=conv.created_at.isoformat(),
            updated_at=conv.updated_at.isoformat(),
            expires_at=conv.expires_at.isoformat() if conv.expires_at else None,
            is_active=conv.is_active
        )
        for conv in conversations
    ]

    return ConversationListResponse(
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        items=items
    )


@router.get("/stats", response_model=ConversationStatsResponse)
async def get_conversation_stats(
        business_id: Optional[UUID] = Query(None, description="Filter stats by business ID"),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Get comprehensive statistics about conversations.

    Requires platform admin role.
    """
    from datetime import timedelta

    filter_info = f" for business {business_id}" if business_id else " (platform-wide)"
    logger.info(f"Admin {current_user.id} requesting conversation stats{filter_info}")

    query = db.query(Conversation)
    if business_id:
        query = query.filter(Conversation.business_id == business_id)

    # Total conversations
    total_conversations = query.count()

    # Status breakdown
    active_conversations = query.filter(Conversation.is_active == True).count()
    completed_conversations = query.filter(Conversation.status == "completed").count()

    # Expired conversations (past expires_at)
    now = datetime.utcnow()
    expired_conversations = query.filter(
        Conversation.expires_at < now,
        Conversation.is_active == True
    ).count()

    # Message stats
    message_stats = db.query(
        func.avg(Conversation.message_count),
        func.sum(Conversation.message_count)
    ).filter(Conversation.business_id == business_id if business_id else True).first()

    avg_message_count = float(message_stats[0]) if message_stats[0] else 0.0
    total_messages = int(message_stats[1]) if message_stats[1] else 0

    # Unique counts
    unique_customers = db.query(func.count(func.distinct(Conversation.customer_phone))).scalar()
    unique_businesses = db.query(func.count(func.distinct(Conversation.business_id))).scalar()

    # Status distribution
    status_counts = db.query(
        Conversation.status,
        func.count(Conversation.id)
    ).group_by(Conversation.status).all()
    conversations_by_status = {status: count for status, count in status_counts}

    # Flow state distribution
    flow_state_counts = db.query(
        Conversation.flow_state,
        func.count(Conversation.id)
    ).group_by(Conversation.flow_state).all()
    conversations_by_flow_state = {state: count for state, count in flow_state_counts}

    # Time-based stats
    conversations_last_24h = query.filter(Conversation.created_at >= now - timedelta(hours=24)).count()
    conversations_last_7d = query.filter(Conversation.created_at >= now - timedelta(days=7)).count()
    conversations_last_30d = query.filter(Conversation.created_at >= now - timedelta(days=30)).count()

    logger.info(
        f"Stats calculated: {total_conversations} total, {active_conversations} active, "
        f"{unique_customers} unique customers, status distribution: {conversations_by_status}"
    )

    return ConversationStatsResponse(
        total_conversations=total_conversations,
        active_conversations=active_conversations,
        completed_conversations=completed_conversations,
        expired_conversations=expired_conversations,
        avg_message_count=round(avg_message_count, 2),
        total_messages=total_messages,
        unique_customers=unique_customers,
        unique_businesses=unique_businesses,
        conversations_by_status=conversations_by_status,
        conversations_by_flow_state=conversations_by_flow_state,
        conversations_last_24h=conversations_last_24h,
        conversations_last_7d=conversations_last_7d,
        conversations_last_30d=conversations_last_30d
    )


@router.get("/by-business", response_model=List[ConversationsByBusinessResponse])
async def get_conversations_by_business(
        from_date: Optional[datetime] = Query(None, description="Filter from date"),
        to_date: Optional[datetime] = Query(None, description="Filter to date"),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Get conversation statistics grouped by business.

    Requires platform admin role.
    """
    date_filter = ""
    if from_date or to_date:
        date_filter = " with date range filter"

    logger.info(f"Admin {current_user.id} requesting conversations grouped by business{date_filter}")

    query = db.query(
        Conversation.business_id,
        func.count(Conversation.id).label('total_conversations'),
        func.sum(func.case((Conversation.is_active == True, 1), else_=0)).label('active_conversations'),
        func.sum(func.case((Conversation.status == 'completed', 1), else_=0)).label('completed_conversations'),
        func.avg(Conversation.message_count).label('avg_message_count'),
        func.sum(Conversation.message_count).label('total_messages'),
        func.max(Conversation.created_at).label('last_conversation_at')
    )

    if from_date:
        query = query.filter(Conversation.created_at >= from_date)
    if to_date:
        query = query.filter(Conversation.created_at <= to_date)

    results = query.group_by(Conversation.business_id).all()

    logger.info(f"Returning conversations grouped by {len(results)} businesses")

    return [
        ConversationsByBusinessResponse(
            business_id=str(result.business_id),
            total_conversations=result.total_conversations,
            active_conversations=result.active_conversations,
            completed_conversations=result.completed_conversations,
            avg_message_count=round(float(result.avg_message_count), 2) if result.avg_message_count else 0.0,
            total_messages=result.total_messages,
            last_conversation_at=result.last_conversation_at.isoformat()
        )
        for result in results
    ]


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
        conversation_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Get details of a specific conversation.

    Requires platform admin role.
    """
    logger.info(f"Admin {current_user.id} viewing conversation {conversation_id}")

    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()

    if not conversation:
        logger.warning(f"Conversation {conversation_id} not found - requested by admin {current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    logger.debug(
        f"Retrieved conversation - SID: {conversation.conversation_sid}, "
        f"Business ID: {conversation.business_id}, Status: {conversation.status}"
    )

    return ConversationResponse(
        id=str(conversation.id),
        conversation_sid=conversation.conversation_sid,
        customer_phone=conversation.customer_phone,
        business_phone=conversation.business_phone,
        business_id=str(conversation.business_id),
        status=conversation.status,
        flow_state=conversation.flow_state,
        customer_info=conversation.customer_info or {},
        context=conversation.context or {},
        message_count=conversation.message_count,
        created_at=conversation.created_at.isoformat(),
        updated_at=conversation.updated_at.isoformat(),
        expires_at=conversation.expires_at.isoformat() if conversation.expires_at else None,
        is_active=conversation.is_active
    )


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
        conversation_id: UUID,
        request: UpdateConversationRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Update a conversation's properties.

    Requires platform admin role.
    """
    # Build update description for logging (WITHOUT PII)
    updates = []
    if request.status is not None:
        updates.append(f"status={request.status}")
    if request.flow_state is not None:
        updates.append(f"flow_state={request.flow_state}")
    if request.is_active is not None:
        updates.append(f"is_active={request.is_active}")
    if request.customer_info is not None:
        updates.append("customer_info")  # Don't log the actual customer info
    if request.context is not None:
        updates.append("context")  # Don't log the actual context

    update_str = ', '.join(updates) if updates else "no changes"
    logger.info(f"Admin {current_user.id} updating conversation {conversation_id} - Updates: {update_str}")

    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()

    if not conversation:
        logger.warning(f"Update failed - conversation {conversation_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    # Update fields if provided
    if request.status is not None:
        conversation.status = request.status
    if request.flow_state is not None:
        conversation.flow_state = request.flow_state
    if request.is_active is not None:
        conversation.is_active = request.is_active
    if request.customer_info is not None:
        conversation.customer_info = request.customer_info
    if request.context is not None:
        conversation.context = request.context

    db.commit()
    db.refresh(conversation)

    logger.info(f"Conversation {conversation_id} updated successfully")

    return ConversationResponse(
        id=str(conversation.id),
        conversation_sid=conversation.conversation_sid,
        customer_phone=conversation.customer_phone,
        business_phone=conversation.business_phone,
        business_id=str(conversation.business_id),
        status=conversation.status,
        flow_state=conversation.flow_state,
        customer_info=conversation.customer_info or {},
        context=conversation.context or {},
        message_count=conversation.message_count,
        created_at=conversation.created_at.isoformat(),
        updated_at=conversation.updated_at.isoformat(),
        expires_at=conversation.expires_at.isoformat() if conversation.expires_at else None,
        is_active=conversation.is_active
    )


@router.delete("/{conversation_id}", response_model=MessageResponse)
async def delete_conversation(
        conversation_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Permanently delete a conversation.

    Requires platform admin role. This action cannot be undone.
    """
    logger.warning(f"Admin {current_user.id} attempting to DELETE conversation {conversation_id}")

    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()

    if not conversation:
        logger.warning(f"Delete failed - conversation {conversation_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    conversation_sid = conversation.conversation_sid
    business_id = str(conversation.business_id)

    db.delete(conversation)
    db.commit()

    logger.warning(
        f"Conversation DELETED permanently - "
        f"Conversation ID: {conversation_id}, SID: {conversation_sid}, "
        f"Business ID: {business_id}, Deleted by: {current_user.id}"
    )

    return MessageResponse(
        message="Conversation deleted successfully",
        details={
            "conversation_id": str(conversation_id),
            "conversation_sid": conversation_sid
        }
    )