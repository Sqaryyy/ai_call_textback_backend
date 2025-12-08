# ===== app/api/v1/dashboard/webhook.py =====
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List
from uuid import UUID
import secrets
from datetime import datetime

from app.config.database import get_db
from app.models.webhook_endpoint import WebhookEndpoint
from app.models.webhook_event import WebhookEvent
from app.schemas.webhook import (
    WebhookEndpointCreate,
    WebhookEndpointUpdate,
    WebhookEndpointResponse,
    WebhookEventResponse,
    WebhookTestResponse,
)
from app.api.dependencies import require_business_member
from app.models.auth.user import User
from app.services.webhook.webhook_service import WebhookService

router = APIRouter(tags=["webhooks"])

# Available event types that users can subscribe to
AVAILABLE_EVENTS = [
    "call.incoming",
    "call.completed",
    "call.missed",
    "call.failed",
    "sms.incoming",
    "sms.sent",
    "conversation.created",
    "conversation.updated",
    "booking.created",
    "booking.confirmed",
    "booking.cancelled",
    "booking.rescheduled",
    "*",  # All events
]


def get_business_id(current_user: User) -> UUID:
    """Helper to get business_id and ensure user has an active business"""
    if not current_user.active_business_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active business selected"
        )
    return current_user.active_business_id


@router.get("/events", response_model=List[str])
async def list_available_events(
        current_user: User = Depends(require_business_member),
):
    """Get list of all available webhook event types"""
    return AVAILABLE_EVENTS


@router.post("/", response_model=WebhookEndpointResponse, status_code=status.HTTP_201_CREATED)
async def create_webhook_endpoint(
        webhook_data: WebhookEndpointCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_business_member),
):
    """Create a new webhook endpoint for the current business"""
    business_id = get_business_id(current_user)

    # Validate events
    for event in webhook_data.enabled_events:
        if event not in AVAILABLE_EVENTS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid event type: {event}. Available events: {AVAILABLE_EVENTS}"
            )

    # Generate secret for HMAC signatures
    secret = secrets.token_urlsafe(32)

    webhook = WebhookEndpoint(
        business_id=business_id,
        url=webhook_data.url,
        description=webhook_data.description,
        enabled_events=webhook_data.enabled_events,
        secret=secret,
        is_active=True,
    )

    db.add(webhook)
    db.commit()
    db.refresh(webhook)

    return webhook


@router.get("/", response_model=List[WebhookEndpointResponse])
async def list_webhook_endpoints(
        db: Session = Depends(get_db),
        current_user: User = Depends(require_business_member),
):
    """List all webhook endpoints for the current business"""
    business_id = get_business_id(current_user)

    webhooks = db.query(WebhookEndpoint) \
        .filter(WebhookEndpoint.business_id == business_id) \
        .order_by(desc(WebhookEndpoint.created_at)) \
        .all()

    return webhooks


@router.get("/{webhook_id}", response_model=WebhookEndpointResponse)
async def get_webhook_endpoint(
        webhook_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_business_member),
):
    """Get a specific webhook endpoint"""
    business_id = get_business_id(current_user)

    webhook = db.query(WebhookEndpoint).filter(
        WebhookEndpoint.id == webhook_id,
        WebhookEndpoint.business_id == business_id
    ).first()

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook endpoint not found"
        )

    return webhook


@router.put("/{webhook_id}", response_model=WebhookEndpointResponse)
async def update_webhook_endpoint(
        webhook_id: UUID,
        webhook_data: WebhookEndpointUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_business_member),
):
    """Update a webhook endpoint"""
    business_id = get_business_id(current_user)

    webhook = db.query(WebhookEndpoint).filter(
        WebhookEndpoint.id == webhook_id,
        WebhookEndpoint.business_id == business_id
    ).first()

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook endpoint not found"
        )

    # Validate events if provided
    if webhook_data.enabled_events is not None:
        for event in webhook_data.enabled_events:
            if event not in AVAILABLE_EVENTS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid event type: {event}"
                )

    # Update fields
    update_data = webhook_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(webhook, field, value)

    db.commit()
    db.refresh(webhook)

    return webhook


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook_endpoint(
        webhook_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_business_member),
):
    """Delete a webhook endpoint"""
    business_id = get_business_id(current_user)

    webhook = db.query(WebhookEndpoint).filter(
        WebhookEndpoint.id == webhook_id,
        WebhookEndpoint.business_id == business_id
    ).first()

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook endpoint not found"
        )

    db.delete(webhook)
    db.commit()


@router.post("/{webhook_id}/regenerate-secret", response_model=WebhookEndpointResponse)
async def regenerate_webhook_secret(
        webhook_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_business_member),
):
    """Regenerate the webhook secret for HMAC signatures"""
    business_id = get_business_id(current_user)

    webhook = db.query(WebhookEndpoint).filter(
        WebhookEndpoint.id == webhook_id,
        WebhookEndpoint.business_id == business_id
    ).first()

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook endpoint not found"
        )

    webhook.secret = secrets.token_urlsafe(32)
    db.commit()
    db.refresh(webhook)

    return webhook


@router.post("/{webhook_id}/test", response_model=WebhookTestResponse)
async def test_webhook_endpoint(
        webhook_id: UUID,
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_business_member),
):
    """Send a test event to the webhook endpoint"""
    business_id = get_business_id(current_user)

    webhook = db.query(WebhookEndpoint).filter(
        WebhookEndpoint.id == webhook_id,
        WebhookEndpoint.business_id == business_id
    ).first()

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook endpoint not found"
        )

    # Create test event payload
    test_payload = {
        "event_type": "webhook.test",
        "timestamp": datetime.utcnow().isoformat(),
        "data": {
            "message": "This is a test webhook event",
            "webhook_id": str(webhook_id),
        }
    }

    # Send test webhook
    service = WebhookService(db)
    try:
        response = service.send_webhook_sync(webhook, test_payload)
        return WebhookTestResponse(
            success=True,
            status_code=response.get("status_code"),
            response_time_ms=response.get("response_time_ms"),
            message="Test webhook sent successfully"
        )
    except Exception as e:
        return WebhookTestResponse(
            success=False,
            message=f"Test webhook failed: {str(e)}"
        )


@router.get("/{webhook_id}/events", response_model=List[WebhookEventResponse])
async def list_webhook_events(
        webhook_id: UUID,
        limit: int = 50,
        offset: int = 0,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_business_member),
):
    """List recent webhook delivery events for an endpoint"""
    business_id = get_business_id(current_user)

    # Verify webhook belongs to user's business
    webhook = db.query(WebhookEndpoint).filter(
        WebhookEndpoint.id == webhook_id,
        WebhookEndpoint.business_id == business_id
    ).first()

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook endpoint not found"
        )

    # Get events
    events = db.query(WebhookEvent) \
        .filter(WebhookEvent.webhook_endpoint_id == webhook_id) \
        .order_by(desc(WebhookEvent.created_at)) \
        .limit(limit) \
        .offset(offset) \
        .all()

    return events


@router.post("/{webhook_id}/retry-failed")
async def retry_failed_events(
        webhook_id: UUID,
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_business_member),
):
    """Retry all failed webhook events for an endpoint"""
    business_id = get_business_id(current_user)

    # Verify webhook belongs to user's business
    webhook = db.query(WebhookEndpoint).filter(
        WebhookEndpoint.id == webhook_id,
        WebhookEndpoint.business_id == business_id
    ).first()

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook endpoint not found"
        )

    # Get failed events
    failed_events = db.query(WebhookEvent).filter(
        WebhookEvent.webhook_endpoint_id == webhook_id,
        WebhookEvent.status == "failed",
        WebhookEvent.attempts < WebhookEvent.max_attempts
    ).all()

    # Queue for retry
    service = WebhookService(db)
    for event in failed_events:
        background_tasks.add_task(service.retry_event, event.id)

    return {
        "message": f"Queued {len(failed_events)} events for retry"
    }