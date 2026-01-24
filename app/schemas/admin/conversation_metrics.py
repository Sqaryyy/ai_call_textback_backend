from pydantic import BaseModel
from typing import Optional, List
# ============================================================================
# Pydantic Schemas
# ============================================================================

class ConversationMetricsResponse(BaseModel):
    """Response schema for conversation metrics."""
    id: str
    conversation_id: str
    call_event_id: str
    business_id: str
    customer_responded: bool
    conversation_completed: bool
    conversation_status: str
    soft_close_at: Optional[str]
    hard_close_at: Optional[str]
    booking_initiated: bool
    booking_initiated_at: Optional[str]
    booking_created: bool
    booking_abandoned: bool
    appointment_id: Optional[str]
    outreach_sent_at: Optional[str]
    first_response_at: Optional[str]
    conversation_ended_at: Optional[str]
    booking_completed_at: Optional[str]
    total_messages: int
    customer_messages: int
    bot_messages: int
    last_flow_state: Optional[str]
    dropped_off: bool
    response_time_seconds: Optional[int]
    conversation_duration_seconds: Optional[int]
    time_to_booking_seconds: Optional[int]
    estimated_revenue: Optional[str]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "conversation_id": "660e8400-e29b-41d4-a716-446655440001",
                "call_event_id": "770e8400-e29b-41d4-a716-446655440002",
                "business_id": "880e8400-e29b-41d4-a716-446655440003",
                "customer_responded": True,
                "conversation_completed": True,
                "conversation_status": "hard_close",
                "soft_close_at": "2025-10-19T12:30:00+00:00",
                "hard_close_at": "2025-10-19T12:45:00+00:00",
                "booking_initiated": True,
                "booking_initiated_at": "2025-10-19T12:20:00+00:00",
                "booking_created": True,
                "booking_abandoned": False,
                "appointment_id": "990e8400-e29b-41d4-a716-446655440004",
                "outreach_sent_at": "2025-10-19T12:00:00+00:00",
                "first_response_at": "2025-10-19T12:02:00+00:00",
                "conversation_ended_at": "2025-10-19T12:45:00+00:00",
                "booking_completed_at": "2025-10-19T12:40:00+00:00",
                "total_messages": 15,
                "customer_messages": 8,
                "bot_messages": 7,
                "last_flow_state": "confirmation",
                "dropped_off": False,
                "response_time_seconds": 120,
                "conversation_duration_seconds": 2700,
                "time_to_booking_seconds": 2400,
                "estimated_revenue": "150.00",
                "created_at": "2025-10-19T12:00:00+00:00",
                "updated_at": "2025-10-19T12:45:00+00:00"
            }
        }


class ConversationMetricsListResponse(BaseModel):
    """Response schema for paginated conversation metrics list."""
    total: int
    page: int
    page_size: int
    pages: int
    items: List[ConversationMetricsResponse]


class ConversationMetricsStatsResponse(BaseModel):
    """Response schema for conversation metrics statistics."""
    total_metrics: int
    customer_responded_count: int
    customer_responded_rate: float
    conversation_completed_count: int
    conversation_completed_rate: float
    booking_initiated_count: int
    booking_initiated_rate: float
    booking_created_count: int
    booking_created_rate: float
    booking_abandoned_count: int
    booking_abandoned_rate: float
    dropped_off_count: int
    dropped_off_rate: float
    avg_response_time_seconds: float
    avg_conversation_duration_seconds: float
    avg_time_to_booking_seconds: float
    total_estimated_revenue: str
    avg_estimated_revenue: str
    avg_total_messages: float
    avg_customer_messages: float
    avg_bot_messages: float
    status_distribution: dict
    metrics_last_24h: int
    metrics_last_7d: int
    metrics_last_30d: int

    class Config:
        json_schema_extra = {
            "example": {
                "total_metrics": 500,
                "customer_responded_count": 400,
                "customer_responded_rate": 80.0,
                "conversation_completed_count": 350,
                "conversation_completed_rate": 70.0,
                "booking_initiated_count": 250,
                "booking_initiated_rate": 50.0,
                "booking_created_count": 200,
                "booking_created_rate": 40.0,
                "booking_abandoned_count": 50,
                "booking_abandoned_rate": 10.0,
                "dropped_off_count": 100,
                "dropped_off_rate": 20.0,
                "avg_response_time_seconds": 180.5,
                "avg_conversation_duration_seconds": 1800.0,
                "avg_time_to_booking_seconds": 1500.0,
                "total_estimated_revenue": "30000.00",
                "avg_estimated_revenue": "150.00",
                "avg_total_messages": 12.5,
                "avg_customer_messages": 6.5,
                "avg_bot_messages": 6.0,
                "status_distribution": {
                    "active": 50,
                    "soft_close": 100,
                    "hard_close": 300,
                    "dropped": 50
                },
                "metrics_last_24h": 20,
                "metrics_last_7d": 120,
                "metrics_last_30d": 400
            }
        }


class ConversationMetricsByBusinessResponse(BaseModel):
    """Response schema for conversation metrics grouped by business."""
    business_id: str
    total_metrics: int
    customer_responded_count: int
    customer_responded_rate: float
    booking_created_count: int
    booking_created_rate: float
    avg_response_time_seconds: float
    total_estimated_revenue: str
    last_metric_at: str


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    details: Optional[dict] = None