# app/services/calendar/outlook_service.py
import os
from datetime import datetime, timedelta, timezone
from typing import List, Dict

import msal
import requests
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.models import CalendarIntegration


class OutlookCalendarService:
    SCOPES = ['Calendars.ReadWrite']
    AUTHORITY = 'https://login.microsoftonline.com/common'
    GRAPH_ENDPOINT = 'https://graph.microsoft.com/v1.0'

    def __init__(self):
        self.client_id = os.getenv('MICROSOFT_CLIENT_ID')
        self.client_secret = os.getenv('MICROSOFT_CLIENT_SECRET')
        self.redirect_uri = os.getenv('MICROSOFT_REDIRECT_URI')
        self.fernet = Fernet(os.getenv('CALENDAR_ENCRYPTION_KEY').encode())

    def generate_authorization_url(self, business_id: str) -> str:
        """Generate Microsoft OAuth URL"""
        app = msal.ConfidentialClientApplication(
            self.client_id,
            authority=self.AUTHORITY,
            client_credential=self.client_secret
        )

        auth_url = app.initiate_auth_code_flow(
            scopes=self.SCOPES,
            redirect_uri=self.redirect_uri,
            state=business_id
        )

        return auth_url

    def handle_oauth_callback(self, code: str, state: str, db):
        """Exchange code for tokens"""
        business_id = state

        app = msal.ConfidentialClientApplication(
            self.client_id,
            authority=self.AUTHORITY,
            client_credential=self.client_secret
        )

        # Correct method with proper parameters
        result = app.acquire_token_by_auth_code_flow(
            code=code,
            scopes=self.SCOPES,
            redirect_uri=self.redirect_uri
        )

        if "error" in result:
            raise ValueError(f"Auth error: {result.get('error_description')}")

        # Get calendars
        headers = {'Authorization': f"Bearer {result['access_token']}"}
        calendars_response = requests.get(
            f"{self.GRAPH_ENDPOINT}/me/calendars",
            headers=headers
        )
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
                'selected_calendar_id': calendars[0]['id']
            }
        )

        db.add(integration)
        db.commit()
        return integration

    def _get_valid_access_token(self, integration: CalendarIntegration, db: Session) -> str:
        """Get valid access token, refreshing if necessary"""
        # Check if token is expired (with 5 min buffer)
        if integration.token_expires_at <= datetime.now(timezone.utc) + timedelta(minutes=5):
            # Refresh token
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
            duration_minutes: int
    ) -> List[Dict]:
        """
        Get available time slots from Outlook Calendar using Microsoft Graph API
        """
        access_token = self._get_valid_access_token(integration, db)
        headers = {'Authorization': f'Bearer {access_token}'}

        calendar_id = integration.provider_config.get('selected_calendar_id')

        # Get calendar view (all events in time range)
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
            raise Exception(f"Failed to fetch calendar events: {response.text}")

        events = response.json()['value']

        # Convert events to busy periods
        busy_periods = []
        for event in events:
            # Skip declined events
            if event.get('responseStatus', {}).get('response') == 'declined':
                continue

            busy_periods.append({
                'start': datetime.fromisoformat(event['start']['dateTime']),
                'end': datetime.fromisoformat(event['end']['dateTime'])
            })

        # Sort busy periods by start time
        busy_periods.sort(key=lambda x: x['start'])

        # Generate slots by finding gaps
        slots = []
        current_time = start_date

        while current_time < end_date:
            slot_end = current_time + timedelta(minutes=duration_minutes)

            # Check if this slot overlaps with any busy period
            is_available = True
            for busy in busy_periods:
                if current_time < busy['end'] and slot_end > busy['start']:
                    is_available = False
                    # Jump to end of busy period
                    current_time = busy['end']
                    break

            if is_available:
                # Only include slots during business hours (8 AM - 6 PM)
                if 8 <= current_time.hour < 18:
                    slots.append({
                        'start': current_time.isoformat(),
                        'end': slot_end.isoformat(),
                        'duration_minutes': duration_minutes
                    })
                current_time += timedelta(minutes=duration_minutes)

        return slots

    async def create_event(
            self,
            integration: CalendarIntegration,
            db: Session,
            event_data: Dict
    ) -> Dict:
        """
        Create a calendar event in Outlook

        event_data should contain:
        - subject: Event title
        - body: Event description
        - start: Start datetime
        - end: End datetime
        - attendees: List of email addresses (optional)
        """
        access_token = self._get_valid_access_token(integration, db)
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        calendar_id = integration.provider_config.get('selected_calendar_id')

        # Format event for Microsoft Graph API
        event = {
            'subject': event_data.get('subject'),
            'body': {
                'contentType': 'HTML',
                'content': event_data.get('body', '')
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

        # Add attendees if provided
        if event_data.get('attendees'):
            event['attendees'] = [
                {
                    'emailAddress': {'address': email},
                    'type': 'required'
                }
                for email in event_data['attendees']
            ]

        # Create the event
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

        # Build update payload with only provided fields
        update_payload = {}

        if 'subject' in event_data:
            update_payload['subject'] = event_data['subject']
        if 'body' in event_data:
            update_payload['body'] = {
                'contentType': 'HTML',
                'content': event_data['body']
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

        # Update the event
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
            print(f"Failed to delete event: {e}")
            return False
