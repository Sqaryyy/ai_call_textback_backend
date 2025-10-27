# app/services/webhook_service.py
import httpx
import hmac
import hashlib
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from uuid import UUID

from app.models.webhook_endpoint import WebhookEndpoint
from app.models.webhook_event import WebhookEvent


class WebhookService:
    """Service for managing and delivering webhooks to businesses"""

    # Available webhook event types
    VALID_EVENT_TYPES = [
        "call.missed",
        "conversation.started",
        "conversation.completed",
        "message.received",
        "booking.created",
        "booking.confirmed",
        "booking.cancelled",
        "booking.completed"
    ]

    def __init__(self, db: AsyncSession):
        self.db = db
        self.http_client = httpx.AsyncClient(
            timeout=15.0,  # 15 second timeout
            follow_redirects=True
        )

    async def fire_webhook(
            self,
            event_type: str,
            business_id: UUID,
            event_data: Dict[str, Any],
            trigger_immediately: bool = True
    ) -> List[WebhookEvent]:
        """
        Fire a webhook event to all registered endpoints for a business.

        Args:
            event_type: Type of event (e.g., "call.missed")
            business_id: The business this event belongs to
            event_data: The payload data to send
            trigger_immediately: If True, send now. If False, queue for later.

        Returns:
            List of WebhookEvent records created
        """
        if event_type not in self.VALID_EVENT_TYPES:
            raise ValueError(f"Invalid event type: {event_type}")

        # Get all active webhook endpoints for this business that subscribe to this event
        endpoints = await self._get_subscribed_endpoints(business_id, event_type)

        if not endpoints:
            return []

        # Create webhook event records for each endpoint
        webhook_events = []
        for endpoint in endpoints:
            # Build the payload
            payload = self._build_payload(event_type, business_id, event_data)

            # Create event record
            webhook_event = WebhookEvent(
                webhook_endpoint_id=endpoint.id,
                business_id=business_id,
                event_type=event_type,
                event_data=payload,
                status="pending",
                attempts=0,
                max_attempts=5
            )

            self.db.add(webhook_event)
            webhook_events.append(webhook_event)

        await self.db.commit()

        # Trigger delivery immediately if requested
        if trigger_immediately:
            for event in webhook_events:
                await self.db.refresh(event)
                await self._deliver_webhook(event)

        return webhook_events

    async def _deliver_webhook(self, webhook_event: WebhookEvent) -> bool:
        """
        Attempt to deliver a single webhook event.

        Returns:
            True if successful, False otherwise
        """
        # Get the endpoint configuration
        result = await self.db.execute(
            select(WebhookEndpoint).where(WebhookEndpoint.id == webhook_event.webhook_endpoint_id)
        )
        endpoint = result.scalar_one_or_none()

        if not endpoint or not endpoint.is_active:
            webhook_event.status = "failed"
            webhook_event.error_message = "Endpoint not found or inactive"
            await self.db.commit()
            return False

        # Prepare the request
        payload_json = json.dumps(webhook_event.event_data)
        signature = self._sign_payload(payload_json, endpoint.secret)

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature,
            "X-Webhook-Event": webhook_event.event_type,
            "X-Webhook-Id": str(webhook_event.id),
            "X-Webhook-Timestamp": webhook_event.created_at.isoformat(),
            "User-Agent": "MCTB-Webhook/1.0"
        }

        # Track attempt
        webhook_event.attempts += 1
        webhook_event.last_attempt_at = datetime.now(timezone.utc)
        webhook_event.status = "retrying"

        start_time = datetime.now(timezone.utc)

        try:
            # Send the webhook
            response = await self.http_client.post(
                endpoint.url,
                content=payload_json,
                headers=headers
            )

            # Calculate response time
            response_time_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

            # Update event with response
            webhook_event.response_status_code = response.status_code
            webhook_event.response_body = response.text[:1000]  # Truncate to 1000 chars
            webhook_event.response_time_ms = response_time_ms

            # Check if successful (2xx status codes)
            if 200 <= response.status_code < 300:
                webhook_event.status = "delivered"
                webhook_event.delivered_at = datetime.now(timezone.utc)

                # Update endpoint health
                endpoint.consecutive_failures = 0
                endpoint.last_success_at = datetime.now(timezone.utc)

                await self.db.commit()
                return True
            else:
                # Non-2xx response
                webhook_event.error_message = f"HTTP {response.status_code}: {response.text[:200]}"
                await self._handle_failed_delivery(webhook_event, endpoint)
                return False

        except httpx.TimeoutException:
            webhook_event.error_message = "Request timeout (15s)"
            await self._handle_failed_delivery(webhook_event, endpoint)
            return False

        except httpx.RequestError as e:
            webhook_event.error_message = f"Request error: {str(e)[:200]}"
            await self._handle_failed_delivery(webhook_event, endpoint)
            return False

        except Exception as e:
            webhook_event.error_message = f"Unexpected error: {str(e)[:200]}"
            await self._handle_failed_delivery(webhook_event, endpoint)
            return False

    async def _handle_failed_delivery(
            self,
            webhook_event: WebhookEvent,
            endpoint: WebhookEndpoint
    ):
        """Handle a failed webhook delivery attempt."""

        # Update endpoint failure tracking
        endpoint.consecutive_failures += 1
        endpoint.last_failure_at = datetime.now(timezone.utc)
        endpoint.last_failure_reason = webhook_event.error_message

        # Auto-disable endpoint if too many failures
        if endpoint.consecutive_failures >= endpoint.max_consecutive_failures:
            endpoint.is_active = False
            endpoint.auto_disabled_at = datetime.now(timezone.utc)
            webhook_event.status = "failed"
            webhook_event.failed_at = datetime.now(timezone.utc)

        # Schedule retry with exponential backoff
        elif webhook_event.attempts < webhook_event.max_attempts:
            # Exponential backoff: 1min, 5min, 15min, 1hour, 6hours
            backoff_minutes = [1, 5, 15, 60, 360]
            delay_minutes = backoff_minutes[min(webhook_event.attempts - 1, len(backoff_minutes) - 1)]

            webhook_event.next_retry_at = datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)
            webhook_event.status = "pending"
        else:
            # Max attempts reached
            webhook_event.status = "failed"
            webhook_event.failed_at = datetime.now(timezone.utc)

        await self.db.commit()

    async def retry_pending_webhooks(self, batch_size: int = 50) -> int:
        """
        Process pending webhook deliveries that are ready for retry.
        This should be called by a background task/cron job.

        Returns:
            Number of webhooks processed
        """
        now = datetime.now(timezone.utc)

        # Get pending webhooks ready for retry
        query = select(WebhookEvent).where(
            and_(
                WebhookEvent.status == "pending",
                or_(
                    WebhookEvent.next_retry_at.is_(None),
                    WebhookEvent.next_retry_at <= now
                ),
                WebhookEvent.attempts < WebhookEvent.max_attempts
            )
        ).limit(batch_size)

        result = await self.db.execute(query)
        pending_events = result.scalars().all()

        processed = 0
        for event in pending_events:
            await self._deliver_webhook(event)
            processed += 1

        return processed

    async def get_endpoint_events(
            self,
            endpoint_id: UUID,
            status: Optional[str] = None,
            limit: int = 100
    ) -> List[WebhookEvent]:
        """Get delivery logs for a webhook endpoint."""
        query = select(WebhookEvent).where(
            WebhookEvent.webhook_endpoint_id == endpoint_id
        )

        if status:
            query = query.where(WebhookEvent.status == status)

        query = query.order_by(WebhookEvent.created_at.desc()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def test_webhook_endpoint(
            self,
            endpoint_id: UUID,
            business_id: UUID
    ) -> WebhookEvent:
        """
        Send a test webhook to verify endpoint configuration.
        """
        # Get endpoint
        result = await self.db.execute(
            select(WebhookEndpoint).where(
                and_(
                    WebhookEndpoint.id == endpoint_id,
                    WebhookEndpoint.business_id == business_id
                )
            )
        )
        endpoint = result.scalar_one_or_none()

        if not endpoint:
            raise ValueError("Webhook endpoint not found")

        # Create test event
        test_data = {
            "event": "webhook.test",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "business_id": str(business_id),
            "data": {
                "message": "This is a test webhook from MCTB",
                "endpoint_id": str(endpoint_id)
            }
        }

        webhook_event = WebhookEvent(
            webhook_endpoint_id=endpoint.id,
            business_id=business_id,
            event_type="webhook.test",
            event_data=test_data,
            status="pending",
            attempts=0,
            max_attempts=1  # Only try once for tests
        )

        self.db.add(webhook_event)
        await self.db.commit()
        await self.db.refresh(webhook_event)

        # Deliver immediately
        await self._deliver_webhook(webhook_event)
        await self.db.refresh(webhook_event)

        return webhook_event

    async def _get_subscribed_endpoints(
            self,
            business_id: UUID,
            event_type: str
    ) -> List[WebhookEndpoint]:
        """Get all webhook endpoints subscribed to this event type."""
        query = select(WebhookEndpoint).where(
            and_(
                WebhookEndpoint.business_id == business_id,
                WebhookEndpoint.is_active == True
            )
        )

        result = await self.db.execute(query)
        all_endpoints = result.scalars().all()

        # Filter by event subscription
        subscribed = []
        for endpoint in all_endpoints:
            # Check if endpoint subscribes to this event or all events (*)
            if "*" in endpoint.enabled_events or event_type in endpoint.enabled_events:
                subscribed.append(endpoint)

        return subscribed

    @staticmethod
    def _build_payload(
            event_type: str,
            business_id: UUID,
            event_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build the webhook payload in a consistent format."""
        return {
            "event": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "business_id": str(business_id),
            "data": event_data
        }

    @staticmethod
    def _sign_payload(payload_json: str, secret: str) -> str:
        """
        Sign the payload using HMAC-SHA256.
        Businesses can verify the signature to ensure the webhook came from you.
        """
        signature = hmac.new(
            secret.encode(),
            payload_json.encode(),
            hashlib.sha256
        ).hexdigest()

        return f"sha256={signature}"

    @staticmethod
    def verify_signature(payload_json: str, signature: str, secret: str) -> bool:
        """
        Verify a webhook signature.
        (This is for if YOU receive webhooks from others, not for your customers)
        """
        expected_signature = WebhookService._sign_payload(payload_json, secret)
        return hmac.compare_digest(signature, expected_signature)

    async def close(self):
        """Close the HTTP client."""
        await self.http_client.aclose()
