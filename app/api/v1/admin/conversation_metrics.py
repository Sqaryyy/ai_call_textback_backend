# ============================================================================
# FILE: app/api/v1/admin/conversation_metrics.py
# Platform admin endpoints for managing conversation metrics
# ============================================================================
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from decimal import Decimal

from app.api.dependencies import get_db, require_platform_admin
from app.models.auth.user import User
from app.models.conversation.conversation_metrics import ConversationMetrics, ConversationStatus
from app.utils.logger import get_logger
from app.schemas.admin.conversation_metrics import (
    MessageResponse,
    ConversationMetricsResponse,
    ConversationMetricsStatsResponse,
    ConversationMetricsListResponse,
    ConversationMetricsByBusinessResponse
)
logger = get_logger(__name__)
router = APIRouter(prefix="/conversation-metrics", tags=["Admin - Conversation Metrics"])

# ============================================================================
# Admin Conversation Metrics Endpoints
# ============================================================================

@router.get("/", response_model=ConversationMetricsListResponse)
async def list_conversation_metrics(
        page: int = Query(1, ge=1, description="Page number"),
        page_size: int = Query(50, ge=1, le=100, description="Items per page"),
        business_id: Optional[UUID] = Query(None, description="Filter by business ID"),
        conversation_status: Optional[ConversationStatus] = Query(None, description="Filter by conversation status"),
        customer_responded: Optional[bool] = Query(None, description="Filter by customer responded"),
        booking_created: Optional[bool] = Query(None, description="Filter by booking created"),
        booking_abandoned: Optional[bool] = Query(None, description="Filter by booking abandoned"),
        dropped_off: Optional[bool] = Query(None, description="Filter by dropped off"),
        from_date: Optional[datetime] = Query(None, description="Filter from date"),
        to_date: Optional[datetime] = Query(None, description="Filter to date"),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    List all conversation metrics with filtering and pagination.

    Requires platform admin role.
    """
    # Build filter description for logging
    filters_applied = []
    if business_id:
        filters_applied.append("business_id")
    if conversation_status:
        filters_applied.append(f"status={conversation_status.value}")
    if customer_responded is not None:
        filters_applied.append(f"customer_responded={customer_responded}")
    if booking_created is not None:
        filters_applied.append(f"booking_created={booking_created}")
    if booking_abandoned is not None:
        filters_applied.append(f"booking_abandoned={booking_abandoned}")
    if dropped_off is not None:
        filters_applied.append(f"dropped_off={dropped_off}")
    if from_date or to_date:
        filters_applied.append("date_range")

    filter_str = f" with filters: {', '.join(filters_applied)}" if filters_applied else ""
    logger.info(f"Admin {current_user.id} listing conversation metrics - Page {page}, Size {page_size}{filter_str}")

    query = db.query(ConversationMetrics)

    # Apply filters
    if business_id:
        query = query.filter(ConversationMetrics.business_id == business_id)
    if conversation_status:
        query = query.filter(ConversationMetrics.conversation_status == conversation_status)
    if customer_responded is not None:
        query = query.filter(ConversationMetrics.customer_responded == customer_responded)
    if booking_created is not None:
        query = query.filter(ConversationMetrics.booking_created == booking_created)
    if booking_abandoned is not None:
        query = query.filter(ConversationMetrics.booking_abandoned == booking_abandoned)
    if dropped_off is not None:
        query = query.filter(ConversationMetrics.dropped_off == dropped_off)
    if from_date:
        query = query.filter(ConversationMetrics.created_at >= from_date)
    if to_date:
        query = query.filter(ConversationMetrics.created_at <= to_date)

    # Get total count
    total = query.count()

    # Calculate pagination
    pages = (total + page_size - 1) // page_size
    offset = (page - 1) * page_size

    # Get paginated results
    metrics = query.order_by(desc(ConversationMetrics.created_at)).offset(offset).limit(page_size).all()

    logger.info(f"Returning {len(metrics)} conversation metrics out of {total} total")

    items = [
        ConversationMetricsResponse(
            id=str(m.id),
            conversation_id=str(m.conversation_id),
            call_event_id=str(m.call_event_id),
            business_id=str(m.business_id),
            customer_responded=m.customer_responded,
            conversation_completed=m.conversation_completed,
            conversation_status=m.conversation_status.value,
            soft_close_at=m.soft_close_at.isoformat() if m.soft_close_at else None,
            hard_close_at=m.hard_close_at.isoformat() if m.hard_close_at else None,
            booking_initiated=m.booking_initiated,
            booking_initiated_at=m.booking_initiated_at.isoformat() if m.booking_initiated_at else None,
            booking_created=m.booking_created,
            booking_abandoned=m.booking_abandoned,
            appointment_id=str(m.appointment_id) if m.appointment_id else None,
            outreach_sent_at=m.outreach_sent_at.isoformat() if m.outreach_sent_at else None,
            first_response_at=m.first_response_at.isoformat() if m.first_response_at else None,
            conversation_ended_at=m.conversation_ended_at.isoformat() if m.conversation_ended_at else None,
            booking_completed_at=m.booking_completed_at.isoformat() if m.booking_completed_at else None,
            total_messages=m.total_messages,
            customer_messages=m.customer_messages,
            bot_messages=m.bot_messages,
            last_flow_state=m.last_flow_state,
            dropped_off=m.dropped_off,
            response_time_seconds=m.response_time_seconds,
            conversation_duration_seconds=m.conversation_duration_seconds,
            time_to_booking_seconds=m.time_to_booking_seconds,
            estimated_revenue=str(m.estimated_revenue) if m.estimated_revenue else None,
            created_at=m.created_at.isoformat(),
            updated_at=m.updated_at.isoformat()
        )
        for m in metrics
    ]

    return ConversationMetricsListResponse(
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        items=items
    )


@router.get("/stats", response_model=ConversationMetricsStatsResponse)
async def get_conversation_metrics_stats(
        business_id: Optional[UUID] = Query(None, description="Filter stats by business ID"),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Get comprehensive statistics about conversation metrics.

    Requires platform admin role.
    """
    from datetime import timedelta

    filter_info = f" for business {business_id}" if business_id else " (platform-wide)"
    logger.info(f"Admin {current_user.id} requesting conversation metrics stats{filter_info}")

    query = db.query(ConversationMetrics)
    if business_id:
        query = query.filter(ConversationMetrics.business_id == business_id)

    # Total metrics
    total_metrics = query.count()

    # Response and completion rates
    customer_responded_count = query.filter(ConversationMetrics.customer_responded == True).count()
    customer_responded_rate = (customer_responded_count / total_metrics * 100) if total_metrics > 0 else 0.0

    conversation_completed_count = query.filter(ConversationMetrics.conversation_completed == True).count()
    conversation_completed_rate = (conversation_completed_count / total_metrics * 100) if total_metrics > 0 else 0.0

    # Booking metrics
    booking_initiated_count = query.filter(ConversationMetrics.booking_initiated == True).count()
    booking_initiated_rate = (booking_initiated_count / total_metrics * 100) if total_metrics > 0 else 0.0

    booking_created_count = query.filter(ConversationMetrics.booking_created == True).count()
    booking_created_rate = (booking_created_count / total_metrics * 100) if total_metrics > 0 else 0.0

    booking_abandoned_count = query.filter(ConversationMetrics.booking_abandoned == True).count()
    booking_abandoned_rate = (booking_abandoned_count / total_metrics * 100) if total_metrics > 0 else 0.0

    dropped_off_count = query.filter(ConversationMetrics.dropped_off == True).count()
    dropped_off_rate = (dropped_off_count / total_metrics * 100) if total_metrics > 0 else 0.0

    # Timing averages
    timing_stats = db.query(
        func.avg(ConversationMetrics.response_time_seconds),
        func.avg(ConversationMetrics.conversation_duration_seconds),
        func.avg(ConversationMetrics.time_to_booking_seconds)
    ).filter(ConversationMetrics.business_id == business_id if business_id else True).first()

    avg_response_time = float(timing_stats[0]) if timing_stats[0] else 0.0
    avg_conversation_duration = float(timing_stats[1]) if timing_stats[1] else 0.0
    avg_time_to_booking = float(timing_stats[2]) if timing_stats[2] else 0.0

    # Revenue stats
    revenue_stats = db.query(
        func.sum(ConversationMetrics.estimated_revenue),
        func.avg(ConversationMetrics.estimated_revenue)
    ).filter(ConversationMetrics.business_id == business_id if business_id else True).first()

    total_revenue = revenue_stats[0] if revenue_stats[0] else Decimal('0.00')
    avg_revenue = revenue_stats[1] if revenue_stats[1] else Decimal('0.00')

    # Message averages
    message_stats = db.query(
        func.avg(ConversationMetrics.total_messages),
        func.avg(ConversationMetrics.customer_messages),
        func.avg(ConversationMetrics.bot_messages)
    ).filter(ConversationMetrics.business_id == business_id if business_id else True).first()

    avg_total_messages = float(message_stats[0]) if message_stats[0] else 0.0
    avg_customer_messages = float(message_stats[1]) if message_stats[1] else 0.0
    avg_bot_messages = float(message_stats[2]) if message_stats[2] else 0.0

    # Status distribution
    status_counts = db.query(
        ConversationMetrics.conversation_status,
        func.count(ConversationMetrics.id)
    ).group_by(ConversationMetrics.conversation_status).all()
    status_distribution = {status.value: count for status, count in status_counts}

    # Time-based stats
    now = datetime.utcnow()
    metrics_last_24h = query.filter(ConversationMetrics.created_at >= now - timedelta(hours=24)).count()
    metrics_last_7d = query.filter(ConversationMetrics.created_at >= now - timedelta(days=7)).count()
    metrics_last_30d = query.filter(ConversationMetrics.created_at >= now - timedelta(days=30)).count()

    logger.info(
        f"Stats calculated: {total_metrics} total metrics, {booking_created_count} bookings created, {status_distribution}")

    return ConversationMetricsStatsResponse(
        total_metrics=total_metrics,
        customer_responded_count=customer_responded_count,
        customer_responded_rate=round(customer_responded_rate, 2),
        conversation_completed_count=conversation_completed_count,
        conversation_completed_rate=round(conversation_completed_rate, 2),
        booking_initiated_count=booking_initiated_count,
        booking_initiated_rate=round(booking_initiated_rate, 2),
        booking_created_count=booking_created_count,
        booking_created_rate=round(booking_created_rate, 2),
        booking_abandoned_count=booking_abandoned_count,
        booking_abandoned_rate=round(booking_abandoned_rate, 2),
        dropped_off_count=dropped_off_count,
        dropped_off_rate=round(dropped_off_rate, 2),
        avg_response_time_seconds=round(avg_response_time, 2),
        avg_conversation_duration_seconds=round(avg_conversation_duration, 2),
        avg_time_to_booking_seconds=round(avg_time_to_booking, 2),
        total_estimated_revenue=str(total_revenue),
        avg_estimated_revenue=str(avg_revenue),
        avg_total_messages=round(avg_total_messages, 2),
        avg_customer_messages=round(avg_customer_messages, 2),
        avg_bot_messages=round(avg_bot_messages, 2),
        status_distribution=status_distribution,
        metrics_last_24h=metrics_last_24h,
        metrics_last_7d=metrics_last_7d,
        metrics_last_30d=metrics_last_30d
    )


@router.get("/by-business", response_model=List[ConversationMetricsByBusinessResponse])
async def get_conversation_metrics_by_business(
        from_date: Optional[datetime] = Query(None, description="Filter from date"),
        to_date: Optional[datetime] = Query(None, description="Filter to date"),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Get conversation metrics grouped by business.

    Requires platform admin role.
    """
    date_filter = ""
    if from_date or to_date:
        date_filter = " with date range filter"

    logger.info(f"Admin {current_user.id} requesting metrics grouped by business{date_filter}")

    query = db.query(
        ConversationMetrics.business_id,
        func.count(ConversationMetrics.id).label('total_metrics'),
        func.sum(func.case((ConversationMetrics.customer_responded == True, 1), else_=0)).label(
            'customer_responded_count'),
        func.sum(func.case((ConversationMetrics.booking_created == True, 1), else_=0)).label('booking_created_count'),
        func.avg(ConversationMetrics.response_time_seconds).label('avg_response_time'),
        func.sum(ConversationMetrics.estimated_revenue).label('total_revenue'),
        func.max(ConversationMetrics.created_at).label('last_metric_at')
    )

    if from_date:
        query = query.filter(ConversationMetrics.created_at >= from_date)
    if to_date:
        query = query.filter(ConversationMetrics.created_at <= to_date)

    results = query.group_by(ConversationMetrics.business_id).all()

    logger.info(f"Returning metrics grouped by {len(results)} businesses")

    return [
        ConversationMetricsByBusinessResponse(
            business_id=str(result.business_id),
            total_metrics=result.total_metrics,
            customer_responded_count=result.customer_responded_count,
            customer_responded_rate=round((result.customer_responded_count / result.total_metrics * 100),
                                          2) if result.total_metrics > 0 else 0.0,
            booking_created_count=result.booking_created_count,
            booking_created_rate=round((result.booking_created_count / result.total_metrics * 100),
                                       2) if result.total_metrics > 0 else 0.0,
            avg_response_time_seconds=round(float(result.avg_response_time), 2) if result.avg_response_time else 0.0,
            total_estimated_revenue=str(result.total_revenue if result.total_revenue else Decimal('0.00')),
            last_metric_at=result.last_metric_at.isoformat()
        )
        for result in results
    ]


@router.get("/{metric_id}", response_model=ConversationMetricsResponse)
async def get_conversation_metric(
        metric_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Get details of a specific conversation metric.

    Requires platform admin role.
    """
    logger.info(f"Admin {current_user.id} viewing conversation metric {metric_id}")

    metric = db.query(ConversationMetrics).filter(ConversationMetrics.id == metric_id).first()

    if not metric:
        logger.warning(f"Conversation metric {metric_id} not found - requested by admin {current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation metric not found"
        )

    logger.debug(f"Retrieved metric for conversation {metric.conversation_id}, business {metric.business_id}")

    return ConversationMetricsResponse(
        id=str(metric.id),
        conversation_id=str(metric.conversation_id),
        call_event_id=str(metric.call_event_id),
        business_id=str(metric.business_id),
        customer_responded=metric.customer_responded,
        conversation_completed=metric.conversation_completed,
        conversation_status=metric.conversation_status.value,
        soft_close_at=metric.soft_close_at.isoformat() if metric.soft_close_at else None,
        hard_close_at=metric.hard_close_at.isoformat() if metric.hard_close_at else None,
        booking_initiated=metric.booking_initiated,
        booking_initiated_at=metric.booking_initiated_at.isoformat() if metric.booking_initiated_at else None,
        booking_created=metric.booking_created,
        booking_abandoned=metric.booking_abandoned,
        appointment_id=str(metric.appointment_id) if metric.appointment_id else None,
        outreach_sent_at=metric.outreach_sent_at.isoformat() if metric.outreach_sent_at else None,
        first_response_at=metric.first_response_at.isoformat() if metric.first_response_at else None,
        conversation_ended_at=metric.conversation_ended_at.isoformat() if metric.conversation_ended_at else None,
        booking_completed_at=metric.booking_completed_at.isoformat() if metric.booking_completed_at else None,
        total_messages=metric.total_messages,
        customer_messages=metric.customer_messages,
        bot_messages=metric.bot_messages,
        last_flow_state=metric.last_flow_state,
        dropped_off=metric.dropped_off,
        response_time_seconds=metric.response_time_seconds,
        conversation_duration_seconds=metric.conversation_duration_seconds,
        time_to_booking_seconds=metric.time_to_booking_seconds,
        estimated_revenue=str(metric.estimated_revenue) if metric.estimated_revenue else None,
        created_at=metric.created_at.isoformat(),
        updated_at=metric.updated_at.isoformat()
    )


@router.delete("/{metric_id}", response_model=MessageResponse)
async def delete_conversation_metric(
        metric_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_platform_admin)
):
    """
    Permanently delete a conversation metric.

    Requires platform admin role. This action cannot be undone.
    """
    logger.warning(f"Admin {current_user.id} attempting to DELETE conversation metric {metric_id}")

    metric = db.query(ConversationMetrics).filter(ConversationMetrics.id == metric_id).first()

    if not metric:
        logger.warning(f"Delete failed - metric {metric_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation metric not found"
        )

    conversation_id = str(metric.conversation_id)
    business_id = str(metric.business_id)

    db.delete(metric)
    db.commit()

    logger.warning(
        f"Conversation metric DELETED permanently - "
        f"Metric ID: {metric_id}, Conversation ID: {conversation_id}, "
        f"Business ID: {business_id}, Deleted by: {current_user.id}"
    )

    return MessageResponse(
        message="Conversation metric deleted successfully",
        details={
            "metric_id": str(metric_id),
            "conversation_id": conversation_id
        }
    )