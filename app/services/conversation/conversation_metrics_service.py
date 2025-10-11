# ============================================================================
# app/services/conversation/conversation_metrics_service.py
# ============================================================================
"""Service for managing conversation metrics"""
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List
from uuid import uuid4
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.conversation_metrics import ConversationMetrics

logger = logging.getLogger(__name__)


class ConversationMetricsService:
    """Handles conversation metrics operations"""

    @staticmethod
    def create_metrics(
            db: Session,
            conversation_id: str,
            call_event_id: str,
            business_id: str
    ) -> ConversationMetrics:
        """Create new metrics record when conversation starts"""
        metrics = ConversationMetrics(
            id=str(uuid4()),
            conversation_id=conversation_id,
            call_event_id=call_event_id,
            business_id=business_id,
            outreach_sent_at=datetime.now(timezone.utc),
            customer_responded=False,
            conversation_completed=False,
            booking_created=False,
            booking_abandoned=False,
            total_messages=0,
            customer_messages=0,
            bot_messages=0,
            dropped_off=False
        )

        db.add(metrics)
        db.commit()
        db.refresh(metrics)

        logger.info(f"Created metrics for conversation: {conversation_id}")
        return metrics

    @staticmethod
    def mark_customer_responded(
            db: Session,
            conversation_id: str
    ) -> Optional[ConversationMetrics]:
        """Mark that customer responded and calculate response time"""
        metrics = db.query(ConversationMetrics).filter(
            ConversationMetrics.conversation_id == conversation_id
        ).first()

        if not metrics or metrics.customer_responded:
            return metrics

        now = datetime.now(timezone.utc)
        metrics.customer_responded = True
        metrics.first_response_at = now

        if metrics.outreach_sent_at:
            metrics.response_time_seconds = int(
                (now - metrics.outreach_sent_at).total_seconds()
            )

        metrics.updated_at = now
        db.commit()
        db.refresh(metrics)

        logger.info(f"Customer responded to conversation: {conversation_id}")
        return metrics

    @staticmethod
    def increment_message_count(
            db: Session,
            conversation_id: str,
            is_customer_message: bool = False
    ) -> None:
        """Increment message counts"""
        metrics = db.query(ConversationMetrics).filter(
            ConversationMetrics.conversation_id == conversation_id
        ).first()

        if metrics:
            metrics.total_messages += 1
            if is_customer_message:
                metrics.customer_messages += 1
            else:
                metrics.bot_messages += 1
            db.commit()

    @staticmethod
    def mark_booking_created(
            db: Session,
            conversation_id: str,
            appointment_id: str,
            estimated_revenue: Optional[float] = None
    ) -> Optional[ConversationMetrics]:
        """Mark that booking was successfully created"""
        metrics = db.query(ConversationMetrics).filter(
            ConversationMetrics.conversation_id == conversation_id
        ).first()

        if not metrics:
            return None

        now = datetime.now(timezone.utc)
        metrics.booking_created = True
        metrics.appointment_id = appointment_id
        metrics.booking_completed_at = now

        if estimated_revenue:
            metrics.estimated_revenue = estimated_revenue

        if metrics.outreach_sent_at:
            metrics.time_to_booking_seconds = int(
                (now - metrics.outreach_sent_at).total_seconds()
            )

        metrics.updated_at = now
        db.commit()
        db.refresh(metrics)

        logger.info(f"Booking created for conversation: {conversation_id}")
        return metrics

    @staticmethod
    def mark_booking_abandoned(
            db: Session,
            conversation_id: str,
            last_flow_state: str
    ) -> Optional[ConversationMetrics]:
        """Mark that customer abandoned booking process"""
        metrics = db.query(ConversationMetrics).filter(
            ConversationMetrics.conversation_id == conversation_id
        ).first()

        if not metrics:
            return None

        metrics.booking_abandoned = True
        metrics.last_flow_state = last_flow_state
        metrics.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(metrics)

        logger.info(f"Booking abandoned at {last_flow_state} for conversation: {conversation_id}")
        return metrics

    @staticmethod
    def mark_conversation_completed(
            db: Session,
            conversation_id: str,
            last_flow_state: str,
            dropped_off: bool = False
    ) -> Optional[ConversationMetrics]:
        """Mark conversation as completed or dropped off"""
        metrics = db.query(ConversationMetrics).filter(
            ConversationMetrics.conversation_id == conversation_id
        ).first()

        if not metrics:
            return None

        now = datetime.now(timezone.utc)
        metrics.conversation_completed = not dropped_off
        metrics.dropped_off = dropped_off
        metrics.last_flow_state = last_flow_state
        metrics.conversation_ended_at = now

        if metrics.outreach_sent_at:
            metrics.conversation_duration_seconds = int(
                (now - metrics.outreach_sent_at).total_seconds()
            )

        metrics.updated_at = now
        db.commit()
        db.refresh(metrics)

        logger.info(f"Conversation ended for: {conversation_id} (dropped_off={dropped_off})")
        return metrics

    @staticmethod
    def get_business_stats(
            db: Session,
            business_id: str,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None
    ) -> Dict:
        """Get aggregated stats for a business"""
        query = db.query(ConversationMetrics).filter(
            ConversationMetrics.business_id == business_id
        )

        if start_date:
            query = query.filter(ConversationMetrics.created_at >= start_date)
        if end_date:
            query = query.filter(ConversationMetrics.created_at <= end_date)

        total_outreach = query.count()
        responded = query.filter(ConversationMetrics.customer_responded == True).count()
        completed = query.filter(ConversationMetrics.conversation_completed == True).count()
        bookings = query.filter(ConversationMetrics.booking_created == True).count()
        abandoned = query.filter(ConversationMetrics.booking_abandoned == True).count()
        dropped_off = query.filter(ConversationMetrics.dropped_off == True).count()

        # Calculate averages
        avg_response_time = db.query(
            func.avg(ConversationMetrics.response_time_seconds)
        ).filter(
            ConversationMetrics.business_id == business_id,
            ConversationMetrics.response_time_seconds.isnot(None)
        ).scalar()

        avg_time_to_booking = db.query(
            func.avg(ConversationMetrics.time_to_booking_seconds)
        ).filter(
            ConversationMetrics.business_id == business_id,
            ConversationMetrics.time_to_booking_seconds.isnot(None)
        ).scalar()

        total_revenue = db.query(
            func.sum(ConversationMetrics.estimated_revenue)
        ).filter(
            ConversationMetrics.business_id == business_id,
            ConversationMetrics.estimated_revenue.isnot(None)
        ).scalar() or 0

        return {
            "total_outreach": total_outreach,
            "response_rate": round((responded / total_outreach * 100), 2) if total_outreach > 0 else 0,
            "conversation_completion_rate": round((completed / total_outreach * 100), 2) if total_outreach > 0 else 0,
            "booking_conversion_rate": round((bookings / total_outreach * 100), 2) if total_outreach > 0 else 0,
            "booking_abandonment_rate": round((abandoned / total_outreach * 100), 2) if total_outreach > 0 else 0,
            "drop_off_rate": round((dropped_off / total_outreach * 100), 2) if total_outreach > 0 else 0,
            "total_bookings": bookings,
            "total_revenue_recovered": float(total_revenue),
            "avg_response_time_seconds": int(avg_response_time) if avg_response_time else None,
            "avg_time_to_booking_seconds": int(avg_time_to_booking) if avg_time_to_booking else None
        }

    @staticmethod
    def get_drop_off_analysis(
            db: Session,
            business_id: str
    ) -> List[Dict]:
        """Analyze where conversations are dropping off"""
        results = db.query(
            ConversationMetrics.last_flow_state,
            func.count(ConversationMetrics.id).label('count')
        ).filter(
            ConversationMetrics.business_id == business_id,
            ConversationMetrics.dropped_off == True
        ).group_by(
            ConversationMetrics.last_flow_state
        ).order_by(
            func.count(ConversationMetrics.id).desc()
        ).all()

        return [
            {"flow_state": state, "drop_off_count": count}
            for state, count in results
        ]