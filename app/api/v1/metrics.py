# app/api/v1/metrics.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from app.config.database import get_db
from app.models.conversation_metrics import ConversationMetrics
from app.models.api_key import APIKey
from app.api.dependencies import require_api_key, require_scope

router = APIRouter(prefix="/metrics", tags=["metrics"])


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


@router.get("/summary")
async def get_metrics_summary(
    year: int = Query(None, description="Year (defaults to current)"),
    month: int = Query(None, description="Month 1-12 (defaults to current)"),
    api_key: APIKey = Depends(require_api_key),
    _: None = Depends(require_scope("read:metrics")),
    db: Session = Depends(get_db)
):
    """
    Get high-level metrics summary for your business for a specific month.
    Returns key performance indicators like total conversations, bookings, etc.
    """
    business_id = api_key.business_id
    start_date, end_date = get_month_range(year, month)

    # Query all metrics for this business in the time period
    metrics = db.query(ConversationMetrics).filter(
        ConversationMetrics.business_id == business_id,
        ConversationMetrics.created_at >= start_date,
        ConversationMetrics.created_at < end_date
    ).all()

    if not metrics:
        return {
            "business_id": str(business_id),
            "period": f"{year}-{month:02d}" if year and month else f"{datetime.now().year}-{datetime.now().month:02d}",
            "total_conversations": 0,
            "customer_responses": 0,
            "response_rate": 0.0,
            "completed_conversations": 0,
            "completion_rate": 0.0,
            "bookings_created": 0,
            "booking_conversion_rate": 0.0,
            "bookings_abandoned": 0,
            "total_messages": 0,
            "avg_response_time_minutes": None,
            "avg_conversation_duration_minutes": None
        }

    total_conversations = len(metrics)
    customer_responses = sum(1 for m in metrics if m.customer_responded)
    completed_conversations = sum(1 for m in metrics if m.conversation_completed)
    bookings_created = sum(1 for m in metrics if m.booking_created)
    bookings_abandoned = sum(1 for m in metrics if m.booking_abandoned)
    total_messages = sum(m.total_messages for m in metrics)

    # Calculate averages
    response_times = [m.response_time_seconds for m in metrics if m.response_time_seconds]
    conversation_durations = [m.conversation_duration_seconds for m in metrics if m.conversation_duration_seconds]

    avg_response_time_seconds = sum(response_times) / len(response_times) if response_times else None
    avg_conversation_duration_seconds = sum(conversation_durations) / len(
        conversation_durations) if conversation_durations else None

    return {
        "business_id": str(business_id),
        "period": f"{year}-{month:02d}" if year and month else f"{datetime.now().year}-{datetime.now().month:02d}",
        "total_conversations": total_conversations,
        "customer_responses": customer_responses,
        "response_rate": round((customer_responses / total_conversations * 100), 2) if total_conversations > 0 else 0.0,
        "completed_conversations": completed_conversations,
        "completion_rate": round((completed_conversations / total_conversations * 100),
                                 2) if total_conversations > 0 else 0.0,
        "bookings_created": bookings_created,
        "booking_conversion_rate": round((bookings_created / total_conversations * 100),
                                         2) if total_conversations > 0 else 0.0,
        "bookings_abandoned": bookings_abandoned,
        "abandonment_rate": round((bookings_abandoned / bookings_created * 100), 2) if bookings_created > 0 else 0.0,
        "total_messages": total_messages,
        "avg_response_time_minutes": round(avg_response_time_seconds / 60, 2) if avg_response_time_seconds else None,
        "avg_conversation_duration_minutes": round(avg_conversation_duration_seconds / 60,
                                                   2) if avg_conversation_duration_seconds else None
    }


@router.get("/conversations")
async def get_conversations(
    year: int = Query(None),
    month: int = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    api_key: APIKey = Depends(require_api_key),
    _: None = Depends(require_scope("read:metrics")),
    db: Session = Depends(get_db)
):
    """
    Get detailed conversation metrics for your business.
    Includes individual conversation details sorted by most recent.
    """
    business_id = api_key.business_id
    start_date, end_date = get_month_range(year, month)

    # Query and sort by most recent
    query = db.query(ConversationMetrics).filter(
        ConversationMetrics.business_id == business_id,
        ConversationMetrics.created_at >= start_date,
        ConversationMetrics.created_at < end_date
    ).order_by(ConversationMetrics.created_at.desc())

    total = query.count()
    conversations = query.offset(skip).limit(limit).all()

    return {
        "business_id": str(business_id),
        "period": f"{year}-{month:02d}" if year and month else "all-time",
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
                "customer_responded": m.customer_responded,
                "conversation_completed": m.conversation_completed,
                "booking_created": m.booking_created,
                "booking_abandoned": m.booking_abandoned,
                "appointment_id": str(m.appointment_id) if m.appointment_id else None,
                "total_messages": m.total_messages,
                "customer_messages": m.customer_messages,
                "bot_messages": m.bot_messages,
                "response_time_minutes": round(m.response_time_seconds / 60, 2) if m.response_time_seconds else None,
                "conversation_duration_minutes": round(m.conversation_duration_seconds / 60,
                                                       2) if m.conversation_duration_seconds else None,
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


@router.get("/bookings")
async def get_bookings(
    year: int = Query(None),
    month: int = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    api_key: APIKey = Depends(require_api_key),
    _: None = Depends(require_scope("read:metrics")),
    db: Session = Depends(get_db)
):
    """
    Get all booked appointments for your business.
    Shows only conversations that resulted in bookings.
    """
    business_id = api_key.business_id
    start_date, end_date = get_month_range(year, month)

    # Query conversations with bookings
    query = db.query(ConversationMetrics).filter(
        ConversationMetrics.business_id == business_id,
        ConversationMetrics.booking_created == True,
        ConversationMetrics.created_at >= start_date,
        ConversationMetrics.created_at < end_date
    ).order_by(ConversationMetrics.booking_completed_at.desc())

    total = query.count()
    bookings = query.offset(skip).limit(limit).all()

    return {
        "business_id": str(business_id),
        "period": f"{year}-{month:02d}" if year and month else "all-time",
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
                "time_to_booking_minutes": round(m.time_to_booking_seconds / 60,
                                                 2) if m.time_to_booking_seconds else None,
                "estimated_revenue": float(m.estimated_revenue) if m.estimated_revenue else None,
                "created_at": m.created_at.isoformat()
            }
            for m in bookings
        ]
    }


@router.get("/daily-breakdown")
async def get_daily_breakdown(
    year: int = Query(None),
    month: int = Query(None),
    api_key: APIKey = Depends(require_api_key),
    _: None = Depends(require_scope("read:metrics")),
    db: Session = Depends(get_db)
):
    """
    Get day-by-day metrics breakdown for the month.
    Shows trends over time.
    """
    business_id = api_key.business_id
    start_date, end_date = get_month_range(year, month)

    metrics = db.query(ConversationMetrics).filter(
        ConversationMetrics.business_id == business_id,
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
                "total_messages": 0
            }

        daily_data[day_str]["conversations"] += 1
        if m.customer_responded:
            daily_data[day_str]["responses"] += 1
        if m.booking_created:
            daily_data[day_str]["bookings"] += 1
        if m.booking_abandoned:
            daily_data[day_str]["abandoned"] += 1
        daily_data[day_str]["total_messages"] += m.total_messages

    # Calculate daily rates
    for day_data in daily_data.values():
        if day_data["conversations"] > 0:
            day_data["response_rate"] = round((day_data["responses"] / day_data["conversations"]) * 100, 2)
            day_data["booking_rate"] = round((day_data["bookings"] / day_data["conversations"]) * 100, 2)
        else:
            day_data["response_rate"] = 0.0
            day_data["booking_rate"] = 0.0

    return {
        "business_id": str(business_id),
        "period": f"{year}-{month:02d}" if year and month else "all-time",
        "daily_breakdown": [daily_data[day] for day in sorted(daily_data.keys())]
    }


@router.get("/funnel")
async def get_conversion_funnel(
    year: int = Query(None),
    month: int = Query(None),
    api_key: APIKey = Depends(require_api_key),
    _: None = Depends(require_scope("read:metrics")),
    db: Session = Depends(get_db)
):
    """
    Get conversion funnel visualization data.
    Shows drop-off at each stage: outreach -> response -> completed -> booking.
    """
    business_id = api_key.business_id
    start_date, end_date = get_month_range(year, month)

    metrics = db.query(ConversationMetrics).filter(
        ConversationMetrics.business_id == business_id,
        ConversationMetrics.created_at >= start_date,
        ConversationMetrics.created_at < end_date
    ).all()

    total_outreach = len(metrics)
    total_responses = sum(1 for m in metrics if m.customer_responded)
    total_completed = sum(1 for m in metrics if m.conversation_completed)
    total_bookings = sum(1 for m in metrics if m.booking_created)

    return {
        "business_id": str(business_id),
        "period": f"{year}-{month:02d}" if year and month else "all-time",
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
                "stage": "Conversation Completed",
                "count": total_completed,
                "percentage": round((total_completed / total_outreach * 100), 2) if total_outreach > 0 else 0.0,
                "dropoff": total_outreach - total_completed
            },
            {
                "stage": "Booking",
                "count": total_bookings,
                "percentage": round((total_bookings / total_outreach * 100), 2) if total_outreach > 0 else 0.0,
                "dropoff": total_outreach - total_bookings
            }
        ]
    }


@router.get("/dropoff-analysis")
async def get_dropoff_analysis(
    year: int = Query(None),
    month: int = Query(None),
    api_key: APIKey = Depends(require_api_key),
    _: None = Depends(require_scope("read:metrics")),
    db: Session = Depends(get_db)
):
    """
    Analyze where conversations are being dropped off.
    Shows which flow states have the highest abandonment.
    """
    business_id = api_key.business_id
    start_date, end_date = get_month_range(year, month)

    dropped_metrics = db.query(ConversationMetrics).filter(
        ConversationMetrics.business_id == business_id,
        ConversationMetrics.dropped_off == True,
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
        ConversationMetrics.business_id == business_id,
        ConversationMetrics.created_at >= start_date,
        ConversationMetrics.created_at < end_date
    ).count()

    return {
        "business_id": str(business_id),
        "period": f"{year}-{month:02d}" if year and month else "all-time",
        "total_dropped": total_dropped,
        "dropoff_rate": round((total_dropped / total_conversations * 100), 2) if total_conversations > 0 else 0.0,
        "dropoff_by_state": sorted(
            dropoff_by_state.values(),
            key=lambda x: x["count"],
            reverse=True
        )
    }