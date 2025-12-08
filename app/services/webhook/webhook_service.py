# ===== app/services/webhook_service.py =====
import httpx
import hmac
import hashlib
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from uuid import UUID
from sqlalchemy.orm import Session
import asyncio

from app.models.webhook_endpoint import WebhookEndpoint
from app.models.webhook_event import WebhookEvent


class WebhookService:
    def __init__(self, db: Session):
        self.db = db
        self.timeout = 30  # seconds
        self.retry_delays = [60, 300, 900, 3600, 7200]  # Exponential backoff in seconds

    def _generate_signature(self, secret: str, payload: Dict[str, Any]) -> str:
        """Generate HMAC signature for webhook payload"""
        payload_str = json.dumps(payload, sort_keys=True)
        signature = hmac.new(
            secret.encode(),
            payload_str.encode(),
            hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"

    def send_webhook(
            self,
            business_id: UUID,
            event_type: str,
            event_data: Dict[str, Any]
    ):
        """Send webhook to all matching endpoints for a business"""
        # Get all active endpoints that subscribe to this event
        endpoints = self.db.query(WebhookEndpoint).filter(
            WebhookEndpoint.business_id == business_id,
            WebhookEndpoint.is_active == True
        ).all()

        # Filter endpoints that listen to this event type
        matching_endpoints = [
            ep for ep in endpoints
            if "*" in ep.enabled_events or event_type in ep.enabled_events
        ]

        # Create webhook events for each endpoint
        for endpoint in matching_endpoints:
            self._create_and_send_event(endpoint, event_type, event_data)

    def _create_and_send_event(
            self,
            endpoint: WebhookEndpoint,
            event_type: str,
            event_data: Dict[str, Any]
    ):
        """Create webhook event record and send it"""
        # Create event record
        event = WebhookEvent(
            webhook_endpoint_id=endpoint.id,
            business_id=endpoint.business_id,
            event_type=event_type,
            event_data=event_data,
            status="pending",
            attempts=0,
        )

        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)

        # Send webhook synchronously
        self._send_event(endpoint, event)

    def _send_event(self, endpoint: WebhookEndpoint, event: WebhookEvent):
        """Actually send the webhook HTTP request"""
        payload = {
            "event_id": str(event.id),
            "event_type": event.event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": event.event_data,
        }

        signature = self._generate_signature(endpoint.secret, payload)
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature,
            "X-Webhook-Event": event.event_type,
            "X-Webhook-ID": str(event.id),
        }

        event.attempts += 1
        event.last_attempt_at = datetime.utcnow()
        event.status = "retrying" if event.attempts > 1 else "pending"

        start_time = datetime.utcnow()

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    str(endpoint.url),
                    json=payload,
                    headers=headers,
                )

                end_time = datetime.utcnow()
                response_time_ms = int((end_time - start_time).total_seconds() * 1000)

                event.response_status_code = response.status_code
                event.response_body = response.text[:1000]  # Truncate
                event.response_time_ms = response_time_ms

                if 200 <= response.status_code < 300:
                    # Success
                    event.status = "delivered"
                    event.delivered_at = datetime.utcnow()
                    endpoint.consecutive_failures = 0
                    endpoint.last_success_at = datetime.utcnow()
                else:
                    # HTTP error
                    raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")

        except Exception as e:
            # Failed
            error_message = str(e)
            event.error_message = error_message[:500]
            endpoint.consecutive_failures += 1
            endpoint.last_failure_at = datetime.utcnow()
            endpoint.last_failure_reason = error_message[:500]

            # Check if we should retry
            if event.attempts < event.max_attempts:
                # Schedule retry
                retry_delay = self.retry_delays[min(event.attempts - 1, len(self.retry_delays) - 1)]
                event.next_retry_at = datetime.utcnow() + timedelta(seconds=retry_delay)
                event.status = "retrying"
            else:
                # Max attempts reached
                event.status = "failed"
                event.failed_at = datetime.utcnow()

            # Auto-disable endpoint if too many failures
            if endpoint.consecutive_failures >= endpoint.max_consecutive_failures:
                endpoint.is_active = False
                endpoint.auto_disabled_at = datetime.utcnow()

        self.db.commit()

    def retry_event(self, event_id: UUID):
        """Retry a failed webhook event"""
        event = self.db.query(WebhookEvent).filter(
            WebhookEvent.id == event_id
        ).first()

        if not event:
            return

        # Get endpoint
        endpoint = self.db.query(WebhookEndpoint).filter(
            WebhookEndpoint.id == event.webhook_endpoint_id
        ).first()

        if not endpoint or not endpoint.is_active:
            return

        self._send_event(endpoint, event)

    def send_webhook_sync(
            self,
            endpoint: WebhookEndpoint,
            payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send a webhook synchronously (for testing) and return response details"""
        signature = self._generate_signature(endpoint.secret, payload)
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature,
            "X-Webhook-Event": payload.get("event_type", "test"),
        }

        start_time = datetime.utcnow()

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                str(endpoint.url),
                json=payload,
                headers=headers,
            )

            end_time = datetime.utcnow()
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)

            return {
                "status_code": response.status_code,
                "response_time_ms": response_time_ms,
                "response_body": response.text[:1000],
            }