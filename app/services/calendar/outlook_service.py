# app/services/calendar/outlook_service.py
import os
from datetime import datetime, timedelta, timezone
from typing import List, Dict
import logging
import json

import msal
import requests
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.models import CalendarIntegration
from app.config.redis import get_redis

logger = logging.getLogger(__name__)


class OutlookCalendarService:
    SCOPES = ['Calendars.ReadWrite']
    AUTHORITY = 'https://login.microsoftonline.com/common'
    GRAPH_ENDPOINT = 'https://graph.microsoft.com/v1.0'
    AUTH_FLOW_TTL = 600  # 10 minutes

    def __init__(self):
        self.client_id = os.getenv('MICROSOFT_CLIENT_ID')
        self.client_secret = os.getenv('MICROSOFT_CLIENT_SECRET')
        self.redirect_uri = os.getenv('MICROSOFT_REDIRECT_URI')
        self.fernet = Fernet(os.getenv('CALENDAR_ENCRYPTION_KEY').encode())

    def _get_auth_flow_key(self, business_id: str) -> str:
        """Generate Redis key for auth flow"""
        return f"outlook_auth_flow:{business_id}"

    async def generate_authorization_url(self, business_id: str) -> str:
        """Generate Microsoft OAuth URL"""
        app = msal.ConfidentialClientApplication(
            self.client_id,
            authority=self.AUTHORITY,
            client_credential=self.client_secret
        )

        # initiate_auth_code_flow returns a dict with auth_uri and state
        auth_flow = app.initiate_auth_code_flow(
            scopes=self.SCOPES,
            redirect_uri=self.redirect_uri,
            state=business_id
        )

        # Store the auth flow in Redis with TTL
        redis_client = await get_redis()
        try:
            key = self._get_auth_flow_key(business_id)
            await redis_client.setex(
                key,
                self.AUTH_FLOW_TTL,
                json.dumps(auth_flow)
            )
            logger.info(f"Stored auth flow in Redis with key: {key}")
        finally:
            await redis_client.close()

        return auth_flow['auth_uri']

    async def handle_oauth_callback(self, code: str, state: str, db):
        """Exchange code for tokens"""
        business_id = state

        app = msal.ConfidentialClientApplication(
            self.client_id,
            authority=self.AUTHORITY,
            client_credential=self.client_secret
        )

        # Retrieve the stored auth_flow from Redis
        redis_client = await get_redis()
        try:
            key = self._get_auth_flow_key(business_id)
            auth_flow_json = await redis_client.get(key)

            if not auth_flow_json:
                logger.error(f"Auth flow not found in Redis for key: {key}")
                raise ValueError("Auth flow not found. Please restart the authorization process.")

            auth_flow = json.loads(auth_flow_json)

            # Clean up Redis entry
            await redis_client.delete(key)
        finally:
            await redis_client.close()

        # Build auth_response from the callback parameters
        auth_response = {
            'code': code,
            'state': state
        }

        # Exchange code for tokens using the stored auth_flow
        result = app.acquire_token_by_auth_code_flow(
            auth_code_flow=auth_flow,
            auth_response=auth_response
        )

        if "error" in result:
            logger.error(f"Token exchange error: {result.get('error_description')}")
            raise ValueError(f"Auth error: {result.get('error_description')}")

        # Get calendars
        headers = {'Authorization': f"Bearer {result['access_token']}"}
        calendars_response = requests.get(
            f"{self.GRAPH_ENDPOINT}/me/calendars",
            headers=headers
        )

        if calendars_response.status_code != 200:
            raise Exception(f"Failed to fetch calendars: {calendars_response.text}")

        calendars = calendars_response.json()['value']

        # Encrypt tokens
        access_token_encrypted = self.fernet.encrypt(
            result['access_token'].encode()
        )
        refresh_token_encrypted = self.fernet.encrypt(
            result['refresh_token'].encode()
        )

        integration = CalendarIntegration(
            business_id=business_id,
            provider='outlook',
            is_active=True,
            access_token_encrypted=access_token_encrypted,
            refresh_token_encrypted=refresh_token_encrypted,
            token_expires_at=datetime.now(timezone.utc) + timedelta(seconds=result['expires_in']),
            provider_config={
                'calendar_list': [
                    {'id': cal['id'], 'name': cal['name']}
                    for cal in calendars
                ],
                'selected_calendar_id': calendars[0]['id'] if calendars else None
            }
        )

        db.add(integration)
        db.commit()

        # Trigger calendar sync
        from app.tasks.calendar_tasks import sync_calendar_connection
        sync_calendar_connection.delay(str(integration.id))

        logger.info(f"Successfully created Outlook integration for business {business_id}")
        return integration

    def _get_valid_access_token(self, integration: CalendarIntegration, db: Session) -> str:
        """Get valid access token, refreshing if necessary"""
        now = datetime.now(timezone.utc)

        # Check if token is expired (with 5 min buffer)
        if integration.token_expires_at <= now + timedelta(minutes=5):
            self.refresh_access_token(integration, db)

        # Decrypt and return access token
        return self.fernet.decrypt(integration.access_token_encrypted).decode()

    def refresh_access_token(self, integration: CalendarIntegration, db: Session):
        """Refresh expired access token"""
        refresh_token = self.fernet.decrypt(integration.refresh_token_encrypted).decode()

        app = msal.ConfidentialClientApplication(
            self.client_id,
            authority=self.AUTHORITY,
            client_credential=self.client_secret
        )

        result = app.acquire_token_by_refresh_token(
            refresh_token=refresh_token,
            scopes=self.SCOPES
        )

        if "error" in result:
            raise Exception(f"Token refresh failed: {result.get('error_description')}")

        # Update encrypted tokens
        integration.access_token_encrypted = self.fernet.encrypt(
            result['access_token'].encode()
        )
        integration.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=result['expires_in'])
        db.commit()

    async def get_available_slots(
            self,
            integration: CalendarIntegration,
            db: Session,
            start_date: datetime,
            end_date: datetime,
            duration_minutes: int,
            business_hours_start: int = 8,
            business_hours_end: int = 18
    ) -> List[Dict]:
        """Get available time slots from Outlook Calendar"""
        if end_date <= start_date:
            raise ValueError(f"end_date ({end_date}) must be after start_date ({start_date})")

        access_token = self._get_valid_access_token(integration, db)
        headers = {'Authorization': f'Bearer {access_token}'}

        calendar_id = integration.provider_config.get('selected_calendar_id')

        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)

        params = {
            'startDateTime': start_date.isoformat(),
            'endDateTime': end_date.isoformat()
        }

        response = requests.get(
            f"{self.GRAPH_ENDPOINT}/me/calendars/{calendar_id}/calendarView",
            headers=headers,
            params=params
        )

        if response.status_code != 200:
            logger.error(f"Microsoft Graph API error: {response.text}")
            raise Exception(f"Failed to fetch calendar events: {response.text}")

        events = response.json()['value']

        # Convert events to busy periods
        busy_periods = []
        for event in events:
            if event.get('responseStatus', {}).get('response') == 'declined':
                continue

            start_str = event['start']['dateTime']
            end_str = event['end']['dateTime']

            if not start_str.endswith('Z') and '+' not in start_str:
                start_str += 'Z'
            if not end_str.endswith('Z') and '+' not in end_str:
                end_str += 'Z'

            busy_periods.append({
                'start': datetime.fromisoformat(start_str.replace('Z', '+00:00')),
                'end': datetime.fromisoformat(end_str.replace('Z', '+00:00'))
            })

        busy_periods.sort(key=lambda x: x['start'])

        # Generate available slots
        slots = []
        current_time = start_date

        while current_time < end_date:
            slot_end = current_time + timedelta(minutes=duration_minutes)

            if slot_end > end_date:
                break

            is_available = True
            for busy in busy_periods:
                if busy['end'] <= current_time:
                    continue
                if busy['start'] >= slot_end:
                    break
                if current_time < busy['end'] and slot_end > busy['start']:
                    is_available = False
                    current_time = busy['end']
                    break

            if is_available:
                if business_hours_start <= current_time.hour < business_hours_end:
                    slot_end_hour = slot_end.hour + (slot_end.minute / 60)
                    if slot_end_hour <= business_hours_end:
                        slots.append({
                            'start': current_time.isoformat(),
                            'end': slot_end.isoformat(),
                            'duration_minutes': duration_minutes
                        })

                current_time += timedelta(minutes=duration_minutes)

            if current_time >= end_date:
                break

        logger.info(f"Generated {len(slots)} available slots")
        return slots

    async def create_event(
            self,
            integration: CalendarIntegration,
            db: Session,
            event_data: Dict
    ) -> Dict:
        """Create a calendar event in Outlook"""
        access_token = self._get_valid_access_token(integration, db)
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        calendar_id = integration.provider_config.get('selected_calendar_id')

        event = {
            'subject': event_data.get('summary') or event_data.get('subject'),
            'body': {
                'contentType': 'HTML',
                'content': event_data.get('description', '') or event_data.get('body', '')
            },
            'start': {
                'dateTime': event_data['start'].isoformat(),
                'timeZone': 'UTC'
            },
            'end': {
                'dateTime': event_data['end'].isoformat(),
                'timeZone': 'UTC'
            }
        }

        if event_data.get('attendees'):
            event['attendees'] = [
                {
                    'emailAddress': {'address': email},
                    'type': 'required'
                }
                for email in event_data['attendees']
            ]

        response = requests.post(
            f"{self.GRAPH_ENDPOINT}/me/calendars/{calendar_id}/events",
            headers=headers,
            json=event
        )

        if response.status_code not in [200, 201]:
            raise Exception(f"Failed to create event: {response.text}")

        created_event = response.json()

        return {
            'event_id': created_event['id'],
            'event_url': created_event.get('webLink'),
            'status': 'created'
        }

    async def update_event(
            self,
            integration: CalendarIntegration,
            db: Session,
            event_id: str,
            event_data: Dict
    ) -> Dict:
        """Update an existing calendar event"""
        access_token = self._get_valid_access_token(integration, db)
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        update_payload = {}

        if 'summary' in event_data or 'subject' in event_data:
            update_payload['subject'] = event_data.get('summary') or event_data.get('subject')
        if 'description' in event_data or 'body' in event_data:
            update_payload['body'] = {
                'contentType': 'HTML',
                'content': event_data.get('description', '') or event_data.get('body', '')
            }
        if 'start' in event_data:
            update_payload['start'] = {
                'dateTime': event_data['start'].isoformat(),
                'timeZone': 'UTC'
            }
        if 'end' in event_data:
            update_payload['end'] = {
                'dateTime': event_data['end'].isoformat(),
                'timeZone': 'UTC'
            }

        response = requests.patch(
            f"{self.GRAPH_ENDPOINT}/me/events/{event_id}",
            headers=headers,
            json=update_payload
        )

        if response.status_code != 200:
            raise Exception(f"Failed to update event: {response.text}")

        updated_event = response.json()

        return {
            'event_id': updated_event['id'],
            'event_url': updated_event.get('webLink'),
            'status': 'updated'
        }

    async def delete_event(
            self,
            integration: CalendarIntegration,
            db: Session,
            event_id: str
    ) -> bool:
        """Delete a calendar event"""
        access_token = self._get_valid_access_token(integration, db)
        headers = {'Authorization': f'Bearer {access_token}'}

        try:
            response = requests.delete(
                f"{self.GRAPH_ENDPOINT}/me/events/{event_id}",
                headers=headers
            )
            return response.status_code == 204
        except Exception as e:
            logger.error(f"Failed to delete event: {e}")
            return False