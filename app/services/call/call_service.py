# ============================================================================
# FILE 1: app/services/call_service.py
# Pure business logic - no FastAPI dependencies, fully testable
# ============================================================================
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID

from app.models.call_event import CallEvent


class CallService:
    """Service layer for call-related business logic."""

    @staticmethod
    def list_calls(
            db: Session,
            business_id: UUID,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None,
            call_status: Optional[str] = None,
            caller_phone: Optional[str] = None,
            skip: int = 0,
            limit: int = 50
    ) -> Dict[str, Any]:
        """Get paginated list of calls with filters."""
        query = db.query(CallEvent).filter(CallEvent.business_id == business_id)

        if start_date:
            query = query.filter(CallEvent.created_at >= start_date)
        if end_date:
            query = query.filter(CallEvent.created_at <= end_date)
        if call_status:
            query = query.filter(CallEvent.call_status == call_status)
        if caller_phone:
            query = query.filter(CallEvent.caller_phone == caller_phone)

        query = query.order_by(desc(CallEvent.created_at))
        total = query.count()
        calls = query.offset(skip).limit(limit).all()

        return {
            "business_id": str(business_id),
            "total_calls": total,
            "page": {
                "skip": skip,
                "limit": limit,
                "total_pages": (total + limit - 1) // limit if total > 0 else 0
            },
            "filters": {
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "call_status": call_status,
                "caller_phone": caller_phone
            },
            "calls": [CallService._serialize_call(call) for call in calls]
        }

    @staticmethod
    def get_call_by_id(
            db: Session,
            business_id: UUID,
            call_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """Get a single call by ID. Returns None if not found."""
        call = db.query(CallEvent).filter(
            CallEvent.id == call_id,
            CallEvent.business_id == business_id
        ).first()

        if not call:
            return None

        return CallService._serialize_call(call)

    @staticmethod
    def get_call_stats(
            db: Session,
            business_id: UUID,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Calculate call statistics for a business."""
        query = db.query(CallEvent).filter(CallEvent.business_id == business_id)

        if start_date:
            query = query.filter(CallEvent.created_at >= start_date)
        if end_date:
            query = query.filter(CallEvent.created_at <= end_date)

        calls = query.all()

        if not calls:
            return {
                "business_id": str(business_id),
                "period": {
                    "start": start_date.isoformat() if start_date else None,
                    "end": end_date.isoformat() if end_date else None
                },
                "total_calls": 0,
                "by_status": {},
                "by_direction": {},
                "unique_callers": 0,
                "avg_duration_seconds": None
            }

        # Calculate statistics
        total_calls = len(calls)

        by_status = {}
        for call in calls:
            status = call.call_status or "unknown"
            by_status[status] = by_status.get(status, 0) + 1

        by_direction = {}
        for call in calls:
            direction = call.direction or "unknown"
            by_direction[direction] = by_direction.get(direction, 0) + 1

        unique_callers = len(set(call.caller_phone for call in calls if call.caller_phone))

        durations = [int(call.duration) for call in calls if call.duration and call.duration.isdigit()]
        avg_duration = sum(durations) / len(durations) if durations else None

        return {
            "business_id": str(business_id),
            "period": {
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None
            },
            "total_calls": total_calls,
            "by_status": by_status,
            "by_direction": by_direction,
            "unique_callers": unique_callers,
            "avg_duration_seconds": round(avg_duration, 2) if avg_duration else None
        }

    @staticmethod
    def search_calls_by_phone(
            db: Session,
            business_id: UUID,
            phone: str,
            skip: int = 0,
            limit: int = 20
    ) -> Dict[str, Any]:
        """Search for all calls from a specific phone number."""
        query = db.query(CallEvent).filter(
            CallEvent.business_id == business_id,
            CallEvent.caller_phone == phone
        ).order_by(desc(CallEvent.created_at))

        total = query.count()
        calls = query.offset(skip).limit(limit).all()

        return {
            "business_id": str(business_id),
            "phone": phone,
            "total_calls": total,
            "page": {
                "skip": skip,
                "limit": limit,
                "total_pages": (total + limit - 1) // limit if total > 0 else 0
            },
            "calls": [CallService._serialize_call(call) for call in calls]
        }

    @staticmethod
    def _serialize_call(call: CallEvent) -> Dict[str, Any]:
        """Convert CallEvent model to dictionary."""
        return {
            "id": str(call.id),
            "twilio_call_sid": call.twilio_call_sid,
            "caller_phone": call.caller_phone,
            "business_phone": call.business_phone,
            "call_status": call.call_status,
            "direction": call.direction,
            "duration": call.duration,
            "caller_name": call.caller_name,
            "caller_location": call.caller_location,
            "recording_url": call.recording_url,
            "call_metadata": call.call_metadata,
            "created_at": call.created_at.isoformat(),
            "updated_at": call.updated_at.isoformat()
        }
