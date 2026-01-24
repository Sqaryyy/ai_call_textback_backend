# ============================================================================
# FILE: app/api/v1/admin/conversation_states.py
# Platform admin endpoints for managing conversation states
# ============================================================================
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Optional
from uuid import UUID
from datetime import datetime

from app.api.dependencies import get_db, require_platform_admin
from app.models.auth.user import User
from app.models.conversation.conversation_state import ConversationState
from app.utils.logger import get_logger
from app.schemas.admin.conversation_state import (
    MessageResponse,
    ConversationStateResponse,
    ConversationStateStatsResponse,
    ConversationStateListResponse,
    UpdateConversationStateRequest
)
logger = get_logger(__name__)
router = APIRouter(prefix="/conversation-states", tags=["Admin - Conversation States"])

# ============================================================================
# Admin Conversation State Endpoints
# ============================================================================

@router.get("/", response_model=ConversationStateListResponse)
async def list_conversation_states(
        page: int = Query(1, ge=1, description="Page number"),
        page_size: int = Query(50, ge=1, le=100, description="Items per page"),
        flow_state: Optional[str] = Query(None, description="Filter by flow state"),
        is_waiting_for_response: Optional[bool] = Query(None, description="Filter by waiting status"),
        has_expired: Optional[bool] = Query(None, description="Filter by expiration status"),
        min_retry_count: Optional[int] = Query(None, ge=0, description="Filter by minimum retry count"),
        from_date: Optional[datetime] = Query(None, description="Filter from date"),
        to_date: Optional[datetime] = Query(None, description="Filter to date"),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    List all conversation states with filtering and pagination.

    Requires platform admin role.
    """
    # Build filter description for logging
    filters_applied = []
    if flow_state:
        filters_applied.append(f"flow_state={flow_state}")
    if is_waiting_for_response is not None:
        filters_applied.append("waiting_status")
    if has_expired is not None:
        filters_applied.append(f"has_expired={has_expired}")
    if min_retry_count is not None:
        filters_applied.append(f"min_retry_count={min_retry_count}")
    if from_date or to_date:
        filters_applied.append("date_range")

    filter_str = f" with filters: {', '.join(filters_applied)}" if filters_applied else ""
    logger.info(f"Admin {current_user.id} listing conversation states - Page {page}, Size {page_size}{filter_str}")

    query = db.query(ConversationState)

    # Apply filters
    if flow_state:
        query = query.filter(ConversationState.flow_state == flow_state)
    if is_waiting_for_response is not None:
        query = query.filter(ConversationState.is_waiting_for_response == is_waiting_for_response)
    if has_expired is not None:
        now = datetime.utcnow()
        if has_expired:
            query = query.filter(ConversationState.expires_at < now)
        else:
            query = query.filter(ConversationState.expires_at >= now)
    if min_retry_count is not None:
        query = query.filter(ConversationState.retry_count >= min_retry_count)
    if from_date:
        query = query.filter(ConversationState.created_at >= from_date)
    if to_date:
        query = query.filter(ConversationState.created_at <= to_date)

    # Get total count
    total = query.count()

    # Calculate pagination
    pages = (total + page_size - 1) // page_size
    offset = (page - 1) * page_size

    # Get paginated results
    states = query.order_by(desc(ConversationState.updated_at)).offset(offset).limit(page_size).all()

    logger.info(f"Returning {len(states)} conversation states out of {total} total")

    items = [
        ConversationStateResponse(
            id=str(state.id),
            state_data=state.state_data or {},
            flow_state=state.flow_state,
            last_message_at=state.last_message_at.isoformat() if state.last_message_at else None,
            expires_at=state.expires_at.isoformat() if state.expires_at else None,
            is_waiting_for_response=state.is_waiting_for_response,
            retry_count=state.retry_count,
            created_at=state.created_at.isoformat(),
            updated_at=state.updated_at.isoformat()
        )
        for state in states
    ]

    return ConversationStateListResponse(
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        items=items
    )


@router.get("/stats", response_model=ConversationStateStatsResponse)
async def get_conversation_state_stats(
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Get comprehensive statistics about conversation states.

    Requires platform admin role.
    """
    from datetime import timedelta

    logger.info(f"Admin {current_user.id} requesting conversation state stats")

    query = db.query(ConversationState)

    # Total states
    total_states = query.count()

    # Waiting for response
    waiting_for_response_count = query.filter(ConversationState.is_waiting_for_response == True).count()
    waiting_for_response_rate = (waiting_for_response_count / total_states * 100) if total_states > 0 else 0.0

    # Expired states
    now = datetime.utcnow()
    expired_states_count = query.filter(ConversationState.expires_at < now).count()

    # Flow state distribution
    flow_state_counts = db.query(
        ConversationState.flow_state,
        func.count(ConversationState.id)
    ).group_by(ConversationState.flow_state).all()
    states_by_flow_state = {state: count for state, count in flow_state_counts}

    # Retry statistics
    retry_stats = db.query(
        func.avg(ConversationState.retry_count),
        func.max(ConversationState.retry_count)
    ).first()

    avg_retry_count = float(retry_stats[0]) if retry_stats[0] else 0.0
    max_retry_count = int(retry_stats[1]) if retry_stats[1] else 0

    states_with_retries = query.filter(ConversationState.retry_count > 0).count()

    # Time-based stats
    states_last_24h = query.filter(ConversationState.created_at >= now - timedelta(hours=24)).count()
    states_last_7d = query.filter(ConversationState.created_at >= now - timedelta(days=7)).count()
    states_last_30d = query.filter(ConversationState.created_at >= now - timedelta(days=30)).count()

    logger.info(
        f"Stats calculated: {total_states} total states, {waiting_for_response_count} waiting, "
        f"{expired_states_count} expired, flow distribution: {states_by_flow_state}"
    )

    return ConversationStateStatsResponse(
        total_states=total_states,
        waiting_for_response_count=waiting_for_response_count,
        waiting_for_response_rate=round(waiting_for_response_rate, 2),
        expired_states_count=expired_states_count,
        states_by_flow_state=states_by_flow_state,
        avg_retry_count=round(avg_retry_count, 2),
        max_retry_count=max_retry_count,
        states_with_retries=states_with_retries,
        states_last_24h=states_last_24h,
        states_last_7d=states_last_7d,
        states_last_30d=states_last_30d
    )


@router.get("/{state_id}", response_model=ConversationStateResponse)
async def get_conversation_state(
        state_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Get details of a specific conversation state.

    Requires platform admin role.
    """
    logger.info(f"Admin {current_user.id} viewing conversation state {state_id}")

    state = db.query(ConversationState).filter(ConversationState.id == state_id).first()

    if not state:
        logger.warning(f"Conversation state {state_id} not found - requested by admin {current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation state not found"
        )

    logger.debug(f"Retrieved state with flow_state={state.flow_state}, retry_count={state.retry_count}")

    return ConversationStateResponse(
        id=str(state.id),
        state_data=state.state_data or {},
        flow_state=state.flow_state,
        last_message_at=state.last_message_at.isoformat() if state.last_message_at else None,
        expires_at=state.expires_at.isoformat() if state.expires_at else None,
        is_waiting_for_response=state.is_waiting_for_response,
        retry_count=state.retry_count,
        created_at=state.created_at.isoformat(),
        updated_at=state.updated_at.isoformat()
    )


@router.patch("/{state_id}", response_model=ConversationStateResponse)
async def update_conversation_state(
        state_id: UUID,
        request: UpdateConversationStateRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Update a conversation state's properties.

    Requires platform admin role.
    """
    # Build update description for logging
    updates = []
    if request.state_data is not None:
        updates.append("state_data")
    if request.flow_state is not None:
        updates.append(f"flow_state={request.flow_state}")
    if request.is_waiting_for_response is not None:
        updates.append(f"waiting={request.is_waiting_for_response}")
    if request.retry_count is not None:
        updates.append(f"retry_count={request.retry_count}")
    if request.expires_at is not None:
        updates.append("expires_at")

    update_str = ', '.join(updates) if updates else "no changes"
    logger.info(f"Admin {current_user.id} updating conversation state {state_id} - Updates: {update_str}")

    state = db.query(ConversationState).filter(ConversationState.id == state_id).first()

    if not state:
        logger.warning(f"Update failed - state {state_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation state not found"
        )

    # Update fields if provided
    if request.state_data is not None:
        state.state_data = request.state_data
    if request.flow_state is not None:
        state.flow_state = request.flow_state
    if request.is_waiting_for_response is not None:
        state.is_waiting_for_response = request.is_waiting_for_response
    if request.retry_count is not None:
        state.retry_count = request.retry_count
    if request.expires_at is not None:
        state.expires_at = request.expires_at

    db.commit()
    db.refresh(state)

    logger.info(f"Conversation state {state_id} updated successfully")

    return ConversationStateResponse(
        id=str(state.id),
        state_data=state.state_data or {},
        flow_state=state.flow_state,
        last_message_at=state.last_message_at.isoformat() if state.last_message_at else None,
        expires_at=state.expires_at.isoformat() if state.expires_at else None,
        is_waiting_for_response=state.is_waiting_for_response,
        retry_count=state.retry_count,
        created_at=state.created_at.isoformat(),
        updated_at=state.updated_at.isoformat()
    )


@router.delete("/{state_id}", response_model=MessageResponse)
async def delete_conversation_state(
        state_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Permanently delete a conversation state.

    Requires platform admin role. This action cannot be undone.
    """
    logger.warning(f"Admin {current_user.id} attempting to DELETE conversation state {state_id}")

    state = db.query(ConversationState).filter(ConversationState.id == state_id).first()

    if not state:
        logger.warning(f"Delete failed - state {state_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation state not found"
        )

    flow_state = state.flow_state

    db.delete(state)
    db.commit()

    logger.warning(
        f"Conversation state DELETED permanently - "
        f"State ID: {state_id}, Flow State: {flow_state}, Deleted by: {current_user.id}"
    )

    return MessageResponse(
        message="Conversation state deleted successfully",
        details={
            "state_id": str(state_id),
            "flow_state": flow_state
        }
    )


@router.post("/{state_id}/reset-retry", response_model=ConversationStateResponse)
async def reset_retry_count(
        state_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Reset the retry count for a conversation state to 0.

    Requires platform admin role. Useful for debugging or manual intervention.
    """
    logger.info(f"Admin {current_user.id} resetting retry count for state {state_id}")

    state = db.query(ConversationState).filter(ConversationState.id == state_id).first()

    if not state:
        logger.warning(f"Reset retry failed - state {state_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation state not found"
        )

    old_retry_count = state.retry_count
    state.retry_count = 0
    db.commit()
    db.refresh(state)

    logger.info(f"Retry count reset for state {state_id} - Previous: {old_retry_count}, New: 0")

    return ConversationStateResponse(
        id=str(state.id),
        state_data=state.state_data or {},
        flow_state=state.flow_state,
        last_message_at=state.last_message_at.isoformat() if state.last_message_at else None,
        expires_at=state.expires_at.isoformat() if state.expires_at else None,
        is_waiting_for_response=state.is_waiting_for_response,
        retry_count=state.retry_count,
        created_at=state.created_at.isoformat(),
        updated_at=state.updated_at.isoformat()
    )


@router.get("/expired/list", response_model=ConversationStateListResponse)
async def list_expired_states(
        page: int = Query(1, ge=1, description="Page number"),
        page_size: int = Query(50, ge=1, le=100, description="Items per page"),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    List all expired conversation states.

    Requires platform admin role. Useful for cleanup operations.
    """
    logger.info(f"Admin {current_user.id} listing expired conversation states - Page {page}, Size {page_size}")

    now = datetime.utcnow()
    query = db.query(ConversationState).filter(ConversationState.expires_at < now)

    # Get total count
    total = query.count()

    # Calculate pagination
    pages = (total + page_size - 1) // page_size
    offset = (page - 1) * page_size

    # Get paginated results
    states = query.order_by(desc(ConversationState.expires_at)).offset(offset).limit(page_size).all()

    logger.info(f"Returning {len(states)} expired states out of {total} total expired")

    items = [
        ConversationStateResponse(
            id=str(state.id),
            state_data=state.state_data or {},
            flow_state=state.flow_state,
            last_message_at=state.last_message_at.isoformat() if state.last_message_at else None,
            expires_at=state.expires_at.isoformat() if state.expires_at else None,
            is_waiting_for_response=state.is_waiting_for_response,
            retry_count=state.retry_count,
            created_at=state.created_at.isoformat(),
            updated_at=state.updated_at.isoformat()
        )
        for state in states
    ]

    return ConversationStateListResponse(
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        items=items
    )