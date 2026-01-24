"""
Admin Messages API
System admins can view and manage all messages across the platform
CRITICAL: Contains PII (phone numbers, message content)
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Optional, List
from uuid import UUID
from datetime import datetime, timedelta

from app.config.database import get_db
from app.models.auth.user import User
from app.models.conversation.message import Message
from app.models.conversation.conversation import Conversation
from app.models.business.business import Business
from app.api.dependencies import require_platform_admin
from app.utils.logger import get_logger
from app.schemas.admin.messages import (
    MessageResponse,
    MessageListResponse,
    MessageStatsResponse,
    GenericMessageResponse,
    UpdateMessageRequest,
    BusinessMessageStatsResponse,
    MessagesByConversationResponse
)
logger = get_logger(__name__)

# ============================================================================
# Router
# ============================================================================

admin_messages_router = APIRouter(
    prefix="/messages",
    tags=["admin-messages"]
)
# ============================================================================
# Helper Functions
# ============================================================================

def _message_to_response(message: Message, db: Session) -> MessageResponse:
    """Convert Message model to MessageResponse with business context"""
    # Get conversation to find business
    conversation = db.query(Conversation).filter(
        Conversation.id == message.conversation_id
    ).first()

    business_id = None
    business_name = None

    if conversation and conversation.business_id:
        business = db.query(Business).filter(
            Business.id == conversation.business_id
        ).first()
        if business:
            business_id = str(business.id)
            business_name = business.name

    return MessageResponse(
        id=str(message.id),
        conversation_id=str(message.conversation_id),
        business_id=business_id,
        business_name=business_name,
        sender_phone=message.sender_phone,
        recipient_phone=message.recipient_phone,
        role=message.role,
        content=message.content,
        message_status=message.message_status,
        media_urls=message.media_urls or [],
        message_metadata=message.message_metadata or {},
        error_code=message.error_code,
        error_message=message.error_message,
        is_inbound=message.is_inbound,
        created_at=message.created_at.isoformat(),
        updated_at=message.updated_at.isoformat()
    )


# ============================================================================
# Admin Message Endpoints
# ============================================================================

@admin_messages_router.get("/", response_model=MessageListResponse)
async def list_all_messages(
        page: int = Query(1, ge=1, description="Page number"),
        page_size: int = Query(50, ge=1, le=100, description="Items per page"),
        business_id: Optional[UUID] = Query(None, description="Filter by business ID"),
        conversation_id: Optional[UUID] = Query(None, description="Filter by conversation ID"),
        role: Optional[str] = Query(None, description="Filter by role (customer, assistant, system)"),
        message_status: Optional[str] = Query(None, description="Filter by message status"),
        is_inbound: Optional[bool] = Query(None, description="Filter by direction"),
        sender_phone: Optional[str] = Query(None, description="Filter by sender phone"),
        recipient_phone: Optional[str] = Query(None, description="Filter by recipient phone"),
        has_media: Optional[bool] = Query(None, description="Filter messages with media"),
        has_errors: Optional[bool] = Query(None, description="Filter messages with errors"),
        from_date: Optional[datetime] = Query(None, description="Filter from date"),
        to_date: Optional[datetime] = Query(None, description="Filter to date"),
        current_user: User = Depends(require_platform_admin),
        db: Session = Depends(get_db)
):
    """
    List all messages across the platform with filtering and pagination.
    Admin can see messages from all businesses.
    """
    # Build filter description for logging (WITHOUT PII)
    filters_applied = []
    if business_id:
        filters_applied.append("business_id")
    if conversation_id:
        filters_applied.append("conversation_id")
    if role:
        filters_applied.append(f"role={role}")
    if message_status:
        filters_applied.append(f"status={message_status}")
    if is_inbound is not None:
        filters_applied.append(f"is_inbound={is_inbound}")
    if sender_phone:
        filters_applied.append("sender_phone")  # Don't log actual phone
    if recipient_phone:
        filters_applied.append("recipient_phone")  # Don't log actual phone
    if has_media is not None:
        filters_applied.append(f"has_media={has_media}")
    if has_errors is not None:
        filters_applied.append(f"has_errors={has_errors}")
    if from_date or to_date:
        filters_applied.append("date_range")

    filter_str = f" with filters: {', '.join(filters_applied)}" if filters_applied else ""
    logger.info(f"Admin {current_user.id} listing messages - Page {page}, Size {page_size}{filter_str}")

    query = db.query(Message)

    # Filter by business if specified
    if business_id:
        # Join with conversations to filter by business
        query = query.join(Conversation).filter(Conversation.business_id == business_id)

    # Apply other filters
    if conversation_id:
        query = query.filter(Message.conversation_id == conversation_id)
    if role:
        query = query.filter(Message.role == role)
    if message_status:
        query = query.filter(Message.message_status == message_status)
    if is_inbound is not None:
        query = query.filter(Message.is_inbound == is_inbound)
    if sender_phone:
        query = query.filter(Message.sender_phone == sender_phone)
        logger.debug("Filtering by specific sender phone number")  # Generic message
    if recipient_phone:
        query = query.filter(Message.recipient_phone == recipient_phone)
        logger.debug("Filtering by specific recipient phone number")  # Generic message
    if has_media is not None:
        if has_media:
            query = query.filter(func.json_array_length(Message.media_urls) > 0)
        else:
            query = query.filter(func.json_array_length(Message.media_urls) == 0)
    if has_errors is not None:
        if has_errors:
            query = query.filter(Message.error_code.isnot(None))
        else:
            query = query.filter(Message.error_code.is_(None))
    if from_date:
        query = query.filter(Message.created_at >= from_date)
    if to_date:
        query = query.filter(Message.created_at <= to_date)

    # Get total count
    total = query.count()

    # Calculate pagination
    pages = (total + page_size - 1) // page_size
    offset = (page - 1) * page_size

    # Get paginated results
    messages = query.order_by(desc(Message.created_at)).offset(offset).limit(page_size).all()

    logger.info(f"Returning {len(messages)} messages out of {total} total")

    items = [_message_to_response(msg, db) for msg in messages]

    return MessageListResponse(
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        items=items
    )


@admin_messages_router.get("/stats", response_model=MessageStatsResponse)
async def get_platform_message_stats(
        business_id: Optional[UUID] = Query(None, description="Filter stats by business ID"),
        conversation_id: Optional[UUID] = Query(None, description="Filter stats by conversation ID"),
        current_user: User = Depends(require_platform_admin),
        db: Session = Depends(get_db)
):
    """
    Get comprehensive platform-wide message statistics.
    Optionally filter by business or conversation.
    """
    filter_info = ""
    if business_id:
        filter_info = f" for business {business_id}"
    elif conversation_id:
        filter_info = f" for conversation {conversation_id}"
    else:
        filter_info = " (platform-wide)"

    logger.info(f"Admin {current_user.id} requesting message stats{filter_info}")

    query = db.query(Message)

    if business_id:
        query = query.join(Conversation).filter(Conversation.business_id == business_id)
    if conversation_id:
        query = query.filter(Message.conversation_id == conversation_id)

    # Total messages
    total_messages = query.count()

    # Direction breakdown
    inbound_messages = query.filter(Message.is_inbound == True).count()
    outbound_messages = query.filter(Message.is_inbound == False).count()

    # Role distribution
    role_query = db.query(Message.role, func.count(Message.id))
    if business_id:
        role_query = role_query.join(Conversation).filter(Conversation.business_id == business_id)
    if conversation_id:
        role_query = role_query.filter(Message.conversation_id == conversation_id)

    role_counts = role_query.group_by(Message.role).all()
    messages_by_role = {role: count for role, count in role_counts}

    # Status distribution
    status_query = db.query(Message.message_status, func.count(Message.id))
    if business_id:
        status_query = status_query.join(Conversation).filter(Conversation.business_id == business_id)
    if conversation_id:
        status_query = status_query.filter(Message.conversation_id == conversation_id)

    status_counts = status_query.group_by(Message.message_status).all()
    messages_by_status = {status: count for status, count in status_counts if status}

    # Failed messages
    failed_messages = query.filter(Message.error_code.isnot(None)).count()

    # Messages with media
    messages_with_media = query.filter(
        func.json_array_length(Message.media_urls) > 0
    ).count()

    # Average messages per conversation
    conv_query = db.query(func.count(func.distinct(Message.conversation_id)))
    if business_id:
        conv_query = conv_query.join(Conversation).filter(Conversation.business_id == business_id)
    if conversation_id:
        conv_query = conv_query.filter(Message.conversation_id == conversation_id)

    conv_count = conv_query.scalar()
    avg_messages_per_conversation = float(total_messages) / conv_count if conv_count > 0 else 0.0

    # Time-based stats
    now = datetime.utcnow()
    messages_last_24h = query.filter(Message.created_at >= now - timedelta(hours=24)).count()
    messages_last_7d = query.filter(Message.created_at >= now - timedelta(days=7)).count()
    messages_last_30d = query.filter(Message.created_at >= now - timedelta(days=30)).count()

    # Unique counts
    unique_senders_query = db.query(func.count(func.distinct(Message.sender_phone)))
    unique_recipients_query = db.query(func.count(func.distinct(Message.recipient_phone)))

    if business_id:
        unique_senders_query = unique_senders_query.join(Conversation).filter(Conversation.business_id == business_id)
        unique_recipients_query = unique_recipients_query.join(Conversation).filter(
            Conversation.business_id == business_id)

    unique_senders = unique_senders_query.scalar()
    unique_recipients = unique_recipients_query.scalar()

    # Messages by business (top 10)
    business_stats = db.query(
        Conversation.business_id,
        func.count(Message.id).label('count')
    ).join(Conversation).group_by(Conversation.business_id).order_by(desc('count')).limit(10).all()

    messages_by_business = {}
    for biz_id, count in business_stats:
        if biz_id:
            business = db.query(Business).filter(Business.id == biz_id).first()
            business_name = business.name if business else "Unknown"
            messages_by_business[business_name] = count

    logger.info(
        f"Stats calculated: {total_messages} total, {inbound_messages} inbound, "
        f"{outbound_messages} outbound, {failed_messages} failed, role distribution: {messages_by_role}"
    )

    return MessageStatsResponse(
        total_messages=total_messages,
        inbound_messages=inbound_messages,
        outbound_messages=outbound_messages,
        messages_by_role=messages_by_role,
        messages_by_status=messages_by_status,
        failed_messages=failed_messages,
        messages_with_media=messages_with_media,
        avg_messages_per_conversation=round(avg_messages_per_conversation, 2),
        messages_last_24h=messages_last_24h,
        messages_last_7d=messages_last_7d,
        messages_last_30d=messages_last_30d,
        unique_senders=unique_senders,
        unique_recipients=unique_recipients,
        messages_by_business=messages_by_business
    )


@admin_messages_router.get("/by-conversation", response_model=List[MessagesByConversationResponse])
async def get_messages_by_conversation(
        business_id: Optional[UUID] = Query(None, description="Filter by business ID"),
        from_date: Optional[datetime] = Query(None, description="Filter from date"),
        to_date: Optional[datetime] = Query(None, description="Filter to date"),
        current_user: User = Depends(require_platform_admin),
        db: Session = Depends(get_db)
):
    """
    Get message statistics grouped by conversation across all businesses.
    """
    date_filter = ""
    if from_date or to_date:
        date_filter = " with date range filter"

    filter_info = f" for business {business_id}" if business_id else ""
    logger.info(f"Admin {current_user.id} requesting messages grouped by conversation{filter_info}{date_filter}")

    query = db.query(
        Message.conversation_id,
        func.count(Message.id).label('total_messages'),
        func.sum(func.case((Message.is_inbound == True, 1), else_=0)).label('inbound_messages'),
        func.sum(func.case((Message.is_inbound == False, 1), else_=0)).label('outbound_messages'),
        func.sum(func.case((Message.error_code.isnot(None), 1), else_=0)).label('failed_messages'),
        func.min(Message.created_at).label('first_message_at'),
        func.max(Message.created_at).label('last_message_at')
    )

    if business_id:
        query = query.join(Conversation).filter(Conversation.business_id == business_id)
    if from_date:
        query = query.filter(Message.created_at >= from_date)
    if to_date:
        query = query.filter(Message.created_at <= to_date)

    results = query.group_by(Message.conversation_id).all()

    logger.info(f"Returning message stats grouped by {len(results)} conversations")

    # Get conversation details
    response_list = []
    for result in results:
        conversation = db.query(Conversation).filter(
            Conversation.id == result.conversation_id
        ).first()

        business_id = None
        business_name = None
        if conversation and conversation.business_id:
            business = db.query(Business).filter(
                Business.id == conversation.business_id
            ).first()
            if business:
                business_id = str(business.id)
                business_name = business.name

        response_list.append(
            MessagesByConversationResponse(
                conversation_id=str(result.conversation_id),
                conversation_sid=conversation.conversation_sid if conversation else "N/A",
                business_id=business_id,
                business_name=business_name,
                total_messages=result.total_messages,
                inbound_messages=result.inbound_messages,
                outbound_messages=result.outbound_messages,
                failed_messages=result.failed_messages,
                first_message_at=result.first_message_at.isoformat(),
                last_message_at=result.last_message_at.isoformat()
            )
        )

    return response_list


@admin_messages_router.get("/business/{business_id}/stats", response_model=BusinessMessageStatsResponse)
async def get_business_message_stats(
        business_id: UUID,
        current_user: User = Depends(require_platform_admin),
        db: Session = Depends(get_db)
):
    """
    Get detailed message statistics for a specific business.
    """
    logger.info(f"Admin {current_user.id} requesting message stats for business {business_id}")

    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        logger.warning(f"Business {business_id} not found - requested by admin {current_user.id}")
        raise HTTPException(status_code=404, detail="Business not found")

    query = db.query(Message).join(Conversation).filter(Conversation.business_id == business_id)

    total_messages = query.count()
    inbound_messages = query.filter(Message.is_inbound == True).count()
    outbound_messages = query.filter(Message.is_inbound == False).count()
    failed_messages = query.filter(Message.error_code.isnot(None)).count()

    unique_conversations = db.query(func.count(func.distinct(Message.conversation_id))).join(
        Conversation
    ).filter(Conversation.business_id == business_id).scalar()

    avg_messages = float(total_messages) / unique_conversations if unique_conversations > 0 else 0.0

    now = datetime.utcnow()
    messages_last_24h = query.filter(Message.created_at >= now - timedelta(hours=24)).count()
    messages_last_7d = query.filter(Message.created_at >= now - timedelta(days=7)).count()
    messages_last_30d = query.filter(Message.created_at >= now - timedelta(days=30)).count()

    logger.info(
        f"Business message stats: {total_messages} total, {unique_conversations} conversations, "
        f"{failed_messages} failed"
    )

    return BusinessMessageStatsResponse(
        business_id=str(business_id),
        business_name=business.name,
        total_messages=total_messages,
        inbound_messages=inbound_messages,
        outbound_messages=outbound_messages,
        failed_messages=failed_messages,
        unique_conversations=unique_conversations,
        avg_messages_per_conversation=round(avg_messages, 2),
        messages_last_24h=messages_last_24h,
        messages_last_7d=messages_last_7d,
        messages_last_30d=messages_last_30d
    )


@admin_messages_router.get("/{message_id}", response_model=MessageResponse)
async def get_message(
        message_id: UUID,
        current_user: User = Depends(require_platform_admin),
        db: Session = Depends(get_db)
):
    """
    Get details of a specific message.
    """
    logger.info(f"Admin {current_user.id} viewing message {message_id}")

    message = db.query(Message).filter(Message.id == message_id).first()

    if not message:
        logger.warning(f"Message {message_id} not found - requested by admin {current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )

    logger.debug(
        f"Retrieved message - Conversation ID: {message.conversation_id}, "
        f"Role: {message.role}, Direction: {'inbound' if message.is_inbound else 'outbound'}"
    )

    return _message_to_response(message, db)


@admin_messages_router.patch("/{message_id}", response_model=MessageResponse)
async def update_message(
        message_id: UUID,
        request: UpdateMessageRequest,
        current_user: User = Depends(require_platform_admin),
        db: Session = Depends(get_db)
):
    """
    Update a message's properties (admin can update any message).
    """
    # Build update description for logging
    updates = []
    if request.message_status is not None:
        updates.append(f"status={request.message_status}")
    if request.error_code is not None:
        updates.append(f"error_code={request.error_code}")
    if request.error_message is not None:
        updates.append("error_message")
    if request.message_metadata is not None:
        updates.append("metadata")

    update_str = ', '.join(updates) if updates else "no changes"
    logger.info(f"Admin {current_user.id} updating message {message_id} - Updates: {update_str}")

    message = db.query(Message).filter(Message.id == message_id).first()

    if not message:
        logger.warning(f"Update failed - message {message_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )

    # Update fields if provided
    if request.message_status is not None:
        message.message_status = request.message_status
    if request.error_code is not None:
        message.error_code = request.error_code
    if request.error_message is not None:
        message.error_message = request.error_message
    if request.message_metadata is not None:
        message.message_metadata = request.message_metadata

    db.commit()
    db.refresh(message)

    logger.info(f"Message {message_id} updated successfully")

    return _message_to_response(message, db)


@admin_messages_router.delete("/{message_id}", response_model=GenericMessageResponse)
async def delete_message(
        message_id: UUID,
        current_user: User = Depends(require_platform_admin),
        db: Session = Depends(get_db)
):
    """
    Permanently delete a message (admin only).
    This action cannot be undone.
    """
    logger.warning(f"Admin {current_user.id} attempting to DELETE message {message_id}")

    message = db.query(Message).filter(Message.id == message_id).first()

    if not message:
        logger.warning(f"Delete failed - message {message_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )

    conversation_id = str(message.conversation_id)
    message_role = message.role

    db.delete(message)
    db.commit()

    logger.warning(
        f"Message DELETED permanently - "
        f"Message ID: {message_id}, Conversation ID: {conversation_id}, "
        f"Role: {message_role}, Deleted by: {current_user.id}"
    )

    return GenericMessageResponse(
        message="Message deleted successfully",
        details={
            "message_id": str(message_id),
            "conversation_id": conversation_id
        }
    )


@admin_messages_router.get("/conversation/{conversation_id}/messages", response_model=MessageListResponse)
async def get_conversation_messages(
        conversation_id: UUID,
        page: int = Query(1, ge=1, description="Page number"),
        page_size: int = Query(100, ge=1, le=500, description="Items per page"),
        current_user: User = Depends(require_platform_admin),
        db: Session = Depends(get_db)
):
    """
    Get all messages for a specific conversation (admin can view any conversation).
    """
    logger.info(
        f"Admin {current_user.id} viewing messages for conversation {conversation_id} - "
        f"Page {page}, Size {page_size}"
    )

    # Verify conversation exists
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        logger.warning(f"Conversation {conversation_id} not found - requested by admin {current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    query = db.query(Message).filter(Message.conversation_id == conversation_id)

    # Get total count
    total = query.count()

    # Calculate pagination
    pages = (total + page_size - 1) // page_size
    offset = (page - 1) * page_size

    # Get paginated results (ordered chronologically)
    messages = query.order_by(Message.created_at).offset(offset).limit(page_size).all()

    logger.info(f"Returning {len(messages)} messages out of {total} total for conversation {conversation_id}")

    items = [_message_to_response(msg, db) for msg in messages]

    return MessageListResponse(
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        items=items
    )