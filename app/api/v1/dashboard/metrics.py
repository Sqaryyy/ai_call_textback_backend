"""
Dashboard Metrics Endpoints
RESTful API for accessing business metrics and analytics in the dashboard
Separate from the public API key based metrics endpoints
UPDATED: Added comprehensive logging with user audit trail
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone

from app.config.database import get_db
from app.models.auth.user import User
from app.models.business.business import Business
from app.models.conversation.conversation_metrics import ConversationMetrics, ConversationStatus
from app.api.dependencies import get_current_user
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Create router for dashboard metrics
router = APIRouter(tags=["dashboard-metrics"])


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_business_or_404(user: User, db: Session) -> Business:
    """Get current user's business or raise 404"""
    if not user.active_business_id:
        logger.warning(
            f"User {user.id} attempted to access metrics without active business"
        )
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    business = db.query(Business).filter(
        Business.id == user.active_business_id
    ).first()

    if not business:
        logger.warning(
            f"Business {user.active_business_id} not found for user {user.id}"
        )
        raise HTTPException(status_code=404, detail="Business not found")

    return business


def get_month_range(year: int = None, month: int = None):
    """Get start and end datetime for a given month"""
    today = datetime.now(timezone.utc)

    if year is None:
        year = today.year
    if month is None:
        month = today.month

    # First day of month
    start_date = datetime(year, month, 1, tzinfo=timezone.utc)

    # Last day of month
    if month == 12:
        end_date = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end_date = datetime(year, month + 1, 1, tzinfo=timezone.utc)

    return start_date, end_date


# ============================================================================
# DASHBOARD METRICS ENDPOINTS
# ============================================================================

@router.get("/summary", response_model=dict)
async def get_metrics_summary(
        year: Optional[int] = Query(None),
        month: Optional[int] = Query(None),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Get high-level metrics summary with conversation status breakdown"""
    business = get_business_or_404(current_user, db)
    start_date, end_date = get_month_range(year, month)

    period_str = f"{year}-{month:02d}" if year and month else f"{datetime.now().year}-{datetime.now().month:02d}"

    logger.info(
        f"User {current_user.id} requesting metrics summary - "
        f"Business: {business.id}, Period: {period_str}"
    )

    metrics = db.query(ConversationMetrics).filter(
        ConversationMetrics.business_id == business.id,
        ConversationMetrics.created_at >= start_date,
        ConversationMetrics.created_at < end_date
    ).all()

    if not metrics:
        logger.info(
            f"No metrics found for business {business.id} in period {period_str}"
        )
        return {
            "business_id": str(business.id),
            "period": period_str,
            "total_conversations": 0,
            "customer_responses": 0,
            "response_rate": 0.0,
            "completed_conversations": 0,
            "completion_rate": 0.0,
            "natural_completions": 0,
            "natural_completion_rate": 0.0,
            "bookings_created": 0,
            "booking_conversion_rate": 0.0,
            "bookings_abandoned": 0,
            "booking_abandonment_rate": 0.0,
            "booking_initiated": 0,
            "dropped_conversations": 0,
            "drop_rate": 0.0,
            "active_conversations": 0,
            "soft_closed_conversations": 0,
            "total_messages": 0,
            "avg_response_time_minutes": None,
            "avg_conversation_duration_minutes": None,
            "conversation_status_breakdown": {
                "active": 0,
                "soft_close": 0,
                "hard_close": 0,
                "dropped": 0
            }
        }

    total_conversations = len(metrics)
    customer_responses = sum(1 for m in metrics if m.customer_responded)
    completed_conversations = sum(1 for m in metrics if m.conversation_completed)
    bookings_created = sum(1 for m in metrics if m.booking_created)
    bookings_initiated = sum(1 for m in metrics if m.booking_initiated)
    bookings_abandoned = sum(1 for m in metrics if m.booking_initiated and not m.booking_created)

    # Conversation status breakdown
    active_count = sum(1 for m in metrics if m.conversation_status == ConversationStatus.active)
    soft_close_count = sum(1 for m in metrics if m.conversation_status == ConversationStatus.soft_close)
    hard_close_count = sum(1 for m in metrics if m.conversation_status == ConversationStatus.hard_close)
    dropped_count = sum(1 for m in metrics if m.conversation_status == ConversationStatus.dropped)

    # Natural completions = hard_close without booking (info queries, polite endings)
    natural_completions = sum(1 for m in metrics if m.conversation_status == ConversationStatus.hard_close and not m.booking_created)

    total_messages = sum(m.total_messages for m in metrics)

    # Calculate averages
    response_times = [m.response_time_seconds for m in metrics if m.response_time_seconds]
    conversation_durations = [m.conversation_duration_seconds for m in metrics if m.conversation_duration_seconds]

    avg_response_time_seconds = sum(response_times) / len(response_times) if response_times else None
    avg_conversation_duration_seconds = sum(conversation_durations) / len(conversation_durations) if conversation_durations else None

    logger.info(
        f"Metrics summary retrieved - Business: {business.id}, Period: {period_str}, "
        f"Total convos: {total_conversations}, Bookings: {bookings_created}, "
        f"Dropped: {dropped_count}, Active: {active_count}"
    )

    return {
        "business_id": str(business.id),
        "period": period_str,
        "total_conversations": total_conversations,
        "customer_responses": customer_responses,
        "response_rate": round((customer_responses / total_conversations * 100), 2) if total_conversations > 0 else 0.0,
        "completed_conversations": completed_conversations,
        "completion_rate": round((completed_conversations / total_conversations * 100), 2) if total_conversations > 0 else 0.0,
        "natural_completions": natural_completions,
        "natural_completion_rate": round((natural_completions / total_conversations * 100), 2) if total_conversations > 0 else 0.0,
        "bookings_initiated": bookings_initiated,
        "bookings_created": bookings_created,
        "booking_conversion_rate": round((bookings_created / total_conversations * 100), 2) if total_conversations > 0 else 0.0,
        "bookings_abandoned": bookings_abandoned,
        "booking_abandonment_rate": round((bookings_abandoned / bookings_initiated * 100), 2) if bookings_initiated > 0 else 0.0,
        "dropped_conversations": dropped_count,
        "drop_rate": round((dropped_count / total_conversations * 100), 2) if total_conversations > 0 else 0.0,
        "active_conversations": active_count,
        "soft_closed_conversations": soft_close_count,
        "total_messages": total_messages,
        "avg_response_time_minutes": round(avg_response_time_seconds / 60, 2) if avg_response_time_seconds else None,
        "avg_conversation_duration_minutes": round(avg_conversation_duration_seconds / 60, 2) if avg_conversation_duration_seconds else None,
        "conversation_status_breakdown": {
            "active": active_count,
            "soft_close": soft_close_count,
            "hard_close": hard_close_count,
            "dropped": dropped_count
        }
    }


@router.get("/conversations", response_model=dict)
async def get_conversations(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="Filter by status: active, soft_close, hard_close, dropped"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get detailed conversation metrics for your business.
    Includes individual conversation details sorted by most recent.
    """
    business = get_business_or_404(current_user, db)
    start_date, end_date = get_month_range(year, month)

    period_str = f"{year}-{month:02d}" if year and month else "all-time"

    logger.info(
        f"User {current_user.id} requesting conversation metrics - "
        f"Business: {business.id}, Period: {period_str}, Status filter: {status or 'none'}, "
        f"Skip: {skip}, Limit: {limit}"
    )

    # Query and sort by most recent
    query = db.query(ConversationMetrics).filter(
        ConversationMetrics.business_id == business.id,
        ConversationMetrics.created_at >= start_date,
        ConversationMetrics.created_at < end_date
    )

    # Filter by status if provided
    if status:
        try:
            status_enum = ConversationStatus[status]
            query = query.filter(ConversationMetrics.conversation_status == status_enum)
        except KeyError:
            logger.warning(
                f"Invalid status filter '{status}' provided - User: {current_user.id}"
            )
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    query = query.order_by(ConversationMetrics.created_at.desc())

    total = query.count()
    conversations = query.offset(skip).limit(limit).all()

    logger.info(
        f"Conversation metrics retrieved - Business: {business.id}, "
        f"Returned: {len(conversations)}, Total: {total}"
    )

    return {
        "business_id": str(business.id),
        "period": period_str,
        "filter": {"status": status} if status else None,
        "total_conversations": total,
        "page": {
            "skip": skip,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit
        },
        "conversations": [
            {
                "id": str(m.id),
                "conversation_id": str(m.conversation_id),
                "conversation_status": m.conversation_status.value,
                "soft_close_at": m.soft_close_at.isoformat() if m.soft_close_at else None,
                "hard_close_at": m.hard_close_at.isoformat() if m.hard_close_at else None,
                "customer_responded": m.customer_responded,
                "conversation_completed": m.conversation_completed,
                "booking_created": m.booking_created,
                "booking_abandoned": m.booking_abandoned,
                "appointment_id": str(m.appointment_id) if m.appointment_id else None,
                "total_messages": m.total_messages,
                "customer_messages": m.customer_messages,
                "bot_messages": m.bot_messages,
                "response_time_minutes": round(m.response_time_seconds / 60, 2) if m.response_time_seconds else None,
                "conversation_duration_minutes": round(m.conversation_duration_seconds / 60, 2) if m.conversation_duration_seconds else None,
                "last_flow_state": m.last_flow_state,
                "dropped_off": m.dropped_off,
                "outreach_sent_at": m.outreach_sent_at.isoformat() if m.outreach_sent_at else None,
                "first_response_at": m.first_response_at.isoformat() if m.first_response_at else None,
                "conversation_ended_at": m.conversation_ended_at.isoformat() if m.conversation_ended_at else None,
                "created_at": m.created_at.isoformat()
            }
            for m in conversations
        ]
    }


@router.get("/bookings", response_model=dict)
async def get_bookings(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all booked appointments for your business.
    Shows only conversations that resulted in bookings.
    """
    business = get_business_or_404(current_user, db)
    start_date, end_date = get_month_range(year, month)

    period_str = f"{year}-{month:02d}" if year and month else "all-time"

    logger.info(
        f"User {current_user.id} requesting booking metrics - "
        f"Business: {business.id}, Period: {period_str}, Skip: {skip}, Limit: {limit}"
    )

    # Query conversations with bookings
    query = db.query(ConversationMetrics).filter(
        ConversationMetrics.business_id == business.id,
        ConversationMetrics.booking_created == True,
        ConversationMetrics.created_at >= start_date,
        ConversationMetrics.created_at < end_date
    ).order_by(ConversationMetrics.booking_completed_at.desc())

    total = query.count()
    bookings = query.offset(skip).limit(limit).all()

    # Calculate total revenue
    total_revenue = sum(float(m.estimated_revenue) for m in bookings if m.estimated_revenue)

    logger.info(
        f"Booking metrics retrieved - Business: {business.id}, "
        f"Returned: {len(bookings)}, Total bookings: {total}, "
        f"Revenue in page: ${total_revenue:.2f}"
    )

    return {
        "business_id": str(business.id),
        "period": period_str,
        "total_bookings": total,
        "page": {
            "skip": skip,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit
        },
        "bookings": [
            {
                "id": str(m.id),
                "conversation_id": str(m.conversation_id),
                "appointment_id": str(m.appointment_id) if m.appointment_id else None,
                "booking_completed_at": m.booking_completed_at.isoformat() if m.booking_completed_at else None,
                "conversation_completed": m.conversation_completed,
                "total_messages": m.total_messages,
                "customer_messages": m.customer_messages,
                "response_time_minutes": round(m.response_time_seconds / 60, 2) if m.response_time_seconds else None,
                "time_to_booking_minutes": round(m.time_to_booking_seconds / 60, 2) if m.time_to_booking_seconds else None,
                "estimated_revenue": float(m.estimated_revenue) if m.estimated_revenue else None,
                "created_at": m.created_at.isoformat()
            }
            for m in bookings
        ]
    }


@router.get("/daily-breakdown", response_model=dict)
async def get_daily_breakdown(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get day-by-day metrics breakdown for the month.
    Shows trends over time including conversation status.
    """
    business = get_business_or_404(current_user, db)
    start_date, end_date = get_month_range(year, month)

    period_str = f"{year}-{month:02d}" if year and month else "all-time"

    logger.info(
        f"User {current_user.id} requesting daily breakdown - "
        f"Business: {business.id}, Period: {period_str}"
    )

    metrics = db.query(ConversationMetrics).filter(
        ConversationMetrics.business_id == business.id,
        ConversationMetrics.created_at >= start_date,
        ConversationMetrics.created_at < end_date
    ).all()

    # Group by day
    daily_data = {}
    for m in metrics:
        day = m.created_at.date()
        day_str = day.isoformat()

        if day_str not in daily_data:
            daily_data[day_str] = {
                "date": day_str,
                "conversations": 0,
                "responses": 0,
                "bookings": 0,
                "abandoned": 0,
                "dropped": 0,
                "natural_completions": 0,
                "total_messages": 0
            }

        daily_data[day_str]["conversations"] += 1
        if m.customer_responded:
            daily_data[day_str]["responses"] += 1
        if m.booking_created:
            daily_data[day_str]["bookings"] += 1
        if m.booking_abandoned:
            daily_data[day_str]["abandoned"] += 1
        if m.conversation_status == ConversationStatus.dropped:
            daily_data[day_str]["dropped"] += 1
        if m.conversation_status == ConversationStatus.hard_close and not m.booking_created:
            daily_data[day_str]["natural_completions"] += 1
        daily_data[day_str]["total_messages"] += m.total_messages

    # Calculate daily rates
    for day_data in daily_data.values():
        if day_data["conversations"] > 0:
            day_data["response_rate"] = round((day_data["responses"] / day_data["conversations"]) * 100, 2)
            day_data["booking_rate"] = round((day_data["bookings"] / day_data["conversations"]) * 100, 2)
            day_data["drop_rate"] = round((day_data["dropped"] / day_data["conversations"]) * 100, 2)
        else:
            day_data["response_rate"] = 0.0
            day_data["booking_rate"] = 0.0
            day_data["drop_rate"] = 0.0

    logger.info(
        f"Daily breakdown retrieved - Business: {business.id}, "
        f"Period: {period_str}, Days: {len(daily_data)}"
    )

    return {
        "business_id": str(business.id),
        "period": period_str,
        "daily_breakdown": [daily_data[day] for day in sorted(daily_data.keys())]
    }


@router.get("/funnel", response_model=dict)
async def get_conversion_funnel(
        year: Optional[int] = Query(None),
        month: Optional[int] = Query(None),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Get conversion funnel visualization data"""
    business = get_business_or_404(current_user, db)
    start_date, end_date = get_month_range(year, month)

    period_str = f"{year}-{month:02d}" if year and month else "all-time"

    logger.info(
        f"User {current_user.id} requesting conversion funnel - "
        f"Business: {business.id}, Period: {period_str}"
    )

    metrics = db.query(ConversationMetrics).filter(
        ConversationMetrics.business_id == business.id,
        ConversationMetrics.created_at >= start_date,
        ConversationMetrics.created_at < end_date
    ).all()

    total_outreach = len(metrics)
    total_responses = sum(1 for m in metrics if m.customer_responded)
    total_booking_initiated = sum(1 for m in metrics if m.booking_initiated)
    total_completed = sum(1 for m in metrics if m.conversation_completed)
    total_bookings = sum(1 for m in metrics if m.booking_created)

    logger.info(
        f"Conversion funnel retrieved - Business: {business.id}, "
        f"Outreach: {total_outreach}, Responses: {total_responses}, "
        f"Bookings: {total_bookings} ({round(total_bookings/total_outreach*100, 2) if total_outreach > 0 else 0}%)"
    )

    return {
        "business_id": str(business.id),
        "period": period_str,
        "funnel": [
            {
                "stage": "Outreach",
                "count": total_outreach,
                "percentage": 100.0
            },
            {
                "stage": "Response",
                "count": total_responses,
                "percentage": round((total_responses / total_outreach * 100), 2) if total_outreach > 0 else 0.0,
                "dropoff": total_outreach - total_responses
            },
            {
                "stage": "Booking Initiated",
                "count": total_booking_initiated,
                "percentage": round((total_booking_initiated / total_outreach * 100), 2) if total_outreach > 0 else 0.0,
                "dropoff": total_responses - total_booking_initiated
            },
            {
                "stage": "Conversation Completed",
                "count": total_completed,
                "percentage": round((total_completed / total_outreach * 100), 2) if total_outreach > 0 else 0.0,
                "dropoff": total_outreach - total_completed
            },
            {
                "stage": "Booking",
                "count": total_bookings,
                "percentage": round((total_bookings / total_outreach * 100), 2) if total_outreach > 0 else 0.0,
                "dropoff": total_booking_initiated - total_bookings
            }
        ]
    }


@router.get("/dropoff-analysis", response_model=dict)
async def get_dropoff_analysis(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Analyze where conversations are being dropped off.
    Shows which flow states have the highest abandonment.
    Now distinguishes between dropped vs natural endings.
    """
    business = get_business_or_404(current_user, db)
    start_date, end_date = get_month_range(year, month)

    period_str = f"{year}-{month:02d}" if year and month else "all-time"

    logger.info(
        f"User {current_user.id} requesting dropoff analysis - "
        f"Business: {business.id}, Period: {period_str}"
    )

    # Get dropped conversations only
    dropped_metrics = db.query(ConversationMetrics).filter(
        ConversationMetrics.business_id == business.id,
        ConversationMetrics.conversation_status == ConversationStatus.dropped,
        ConversationMetrics.created_at >= start_date,
        ConversationMetrics.created_at < end_date
    ).all()

    # Group by flow state
    dropoff_by_state = {}
    for m in dropped_metrics:
        state = m.last_flow_state or "unknown"
        if state not in dropoff_by_state:
            dropoff_by_state[state] = {
                "state": state,
                "count": 0,
                "avg_duration_minutes": 0.0
            }
        dropoff_by_state[state]["count"] += 1

    # Calculate averages
    for state in dropoff_by_state:
        state_metrics = [m for m in dropped_metrics if (m.last_flow_state or "unknown") == state]
        durations = [m.conversation_duration_seconds for m in state_metrics if m.conversation_duration_seconds]
        if durations:
            dropoff_by_state[state]["avg_duration_minutes"] = round(sum(durations) / len(durations) / 60, 2)

    total_dropped = len(dropped_metrics)
    total_conversations = db.query(ConversationMetrics).filter(
        ConversationMetrics.business_id == business.id,
        ConversationMetrics.created_at >= start_date,
        ConversationMetrics.created_at < end_date
    ).count()

    # Get top dropoff state
    top_dropoff_state = max(dropoff_by_state.values(), key=lambda x: x["count"])["state"] if dropoff_by_state else "none"

    logger.info(
        f"Dropoff analysis retrieved - Business: {business.id}, "
        f"Total dropped: {total_dropped}, Drop rate: {round(total_dropped/total_conversations*100, 2) if total_conversations > 0 else 0}%, "
        f"Top state: {top_dropoff_state}"
    )

    return {
        "business_id": str(business.id),
        "period": period_str,
        "total_dropped": total_dropped,
        "dropoff_rate": round((total_dropped / total_conversations * 100), 2) if total_conversations > 0 else 0.0,
        "dropoff_by_state": sorted(
            dropoff_by_state.values(),
            key=lambda x: x["count"],
            reverse=True
        )
    }


@router.get("/completion-analysis", response_model=dict)
async def get_completion_analysis(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Analyze conversation completion patterns.
    Shows breakdown of how conversations end (booking, natural, dropped, active).
    """
    business = get_business_or_404(current_user, db)
    start_date, end_date = get_month_range(year, month)

    period_str = f"{year}-{month:02d}" if year and month else "all-time"

    logger.info(
        f"User {current_user.id} requesting completion analysis - "
        f"Business: {business.id}, Period: {period_str}"
    )

    metrics = db.query(ConversationMetrics).filter(
        ConversationMetrics.business_id == business.id,
        ConversationMetrics.created_at >= start_date,
        ConversationMetrics.created_at < end_date
    ).all()

    total = len(metrics)

    # Status breakdown
    active = sum(1 for m in metrics if m.conversation_status == ConversationStatus.active)
    soft_close = sum(1 for m in metrics if m.conversation_status == ConversationStatus.soft_close)
    hard_close = sum(1 for m in metrics if m.conversation_status == ConversationStatus.hard_close)
    dropped = sum(1 for m in metrics if m.conversation_status == ConversationStatus.dropped)

    # Completion types
    booking_completions = sum(1 for m in metrics if m.booking_created)
    natural_completions = sum(1 for m in metrics if m.conversation_status == ConversationStatus.hard_close and not m.booking_created)

    # Calculate average time to completion
    hard_close_metrics = [m for m in metrics if m.conversation_status == ConversationStatus.hard_close]
    avg_time_to_completion = None
    if hard_close_metrics:
        durations = [m.conversation_duration_seconds for m in hard_close_metrics if m.conversation_duration_seconds]
        if durations:
            avg_time_to_completion = round(sum(durations) / len(durations) / 60, 2)

    logger.info(
        f"Completion analysis retrieved - Business: {business.id}, "
        f"Total: {total}, Bookings: {booking_completions}, Natural: {natural_completions}, "
        f"Dropped: {dropped}, Still active: {active + soft_close}"
    )

    return {
        "business_id": str(business.id),
        "period": period_str,
        "total_conversations": total,
        "status_breakdown": {
            "active": {
                "count": active,
                "percentage": round((active / total * 100), 2) if total > 0 else 0.0,
                "description": "Currently ongoing conversations"
            },
            "soft_close": {
                "count": soft_close,
                "percentage": round((soft_close / total * 100), 2) if total > 0 else 0.0,
                "description": "Natural ending detected, grace period active"
            },
            "hard_close": {
                "count": hard_close,
                "percentage": round((hard_close / total * 100), 2) if total > 0 else 0.0,
                "description": "Definitively completed"
            },
            "dropped": {
                "count": dropped,
                "percentage": round((dropped / total * 100), 2) if total > 0 else 0.0,
                "description": "Abandoned/ghosted mid-conversation"
            }
        },
        "completion_types": {
            "booking_completions": booking_completions,
            "natural_completions": natural_completions,
            "dropped": dropped,
            "still_active": active + soft_close
        },
        "avg_time_to_completion_minutes": avg_time_to_completion
    }