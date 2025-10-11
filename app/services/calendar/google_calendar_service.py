# app/services/calendar/google_calendar_service.py
from datetime import timedelta, datetime, timezone
from typing import List, Dict

from app.config.settings import get_settings
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session
import logging
from app.models import CalendarIntegration
settings=get_settings()

logger=logging.getLogger(__name__)

class GoogleCalendarService:
    SCOPES = ['https://www.googleapis.com/auth/calendar']

    def __init__(self):
        self.encryption_key = settings.CALENDAR_ENCRYPTION_KEY
        self.fernet = Fernet(self.encryption_key.encode())

        # OAuth credentials from Google Cloud Console
        self.client_config = {
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uris": ["http://localhost:8000/api/v1/calendar/google/callback"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token"
            }
        }

    def generate_authorization_url(self, business_id: str) -> str:
        """Step 1: Generate OAuth URL for business owner"""
        flow = Flow.from_client_config(
            self.client_config,
            scopes=self.SCOPES,
            redirect_uri=self.client_config['web']['redirect_uris'][0]
        )

        authorization_url, state = flow.authorization_url(
            access_type='offline',  # Gets refresh token
            include_granted_scopes='true',
            prompt='consent',  # Force consent screen to get refresh token
            state=business_id  # Pass business_id to identify after callback
        )

        return authorization_url

    def handle_oauth_callback(self, code: str, state: str, db):
        """Step 2: Exchange authorization code for tokens"""
        business_id = state  # Extract business_id from state

        flow = Flow.from_client_config(
            self.client_config,
            scopes=self.SCOPES,
            redirect_uri=self.client_config['web']['redirect_uris'][0]
        )

        # Exchange code for tokens
        flow.fetch_token(code=code)
        credentials = flow.credentials

        # Get list of calendars to let user choose
        service = build('calendar', 'v3', credentials=credentials)
        calendar_list = service.calendarList().list().execute()

        # Encrypt tokens
        access_token_encrypted = self.fernet.encrypt(
            credentials.token.encode()
        )
        refresh_token_encrypted = self.fernet.encrypt(
            credentials.refresh_token.encode()
        )

        # Store in database
        integration = CalendarIntegration(
            business_id=business_id,
            provider='google',
            is_active=True,
            access_token_encrypted=access_token_encrypted,
            refresh_token_encrypted=refresh_token_encrypted,
            token_expires_at=credentials.expiry,
            provider_config={
                'calendar_list': [
                    {'id': cal['id'], 'name': cal['summary']}
                    for cal in calendar_list.get('items', [])
                ],
                'selected_calendar_id': 'primary'  # Default
            }
        )

        db.add(integration)
        db.commit()

        from app.tasks.calendar_tasks import sync_calendar_connection
        sync_calendar_connection.delay(str(integration.id))

        return integration


    def get_valid_credentials(self, integration: CalendarIntegration, db: Session) -> Credentials:
        """Get valid credentials, refreshing if necessary"""
        # FIXED: Use timezone-aware datetime
        now = datetime.now(timezone.utc)

        # Check if token is expired or about to expire (5 min buffer)
        if integration.token_expires_at <= now + timedelta(minutes=5):
            return self.refresh_access_token(integration, db)

        # Token still valid - decrypt and return
        access_token = self.fernet.decrypt(
            integration.access_token_encrypted
        ).decode()

        refresh_token = self.fernet.decrypt(
            integration.refresh_token_encrypted
        ).decode()

        return Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri=self.client_config['web']['token_uri'],
            client_id=self.client_config['web']['client_id'],
            client_secret=self.client_config['web']['client_secret']
        )
    def refresh_access_token(self, integration: CalendarIntegration, db: Session) -> Credentials:
        """Refresh expired access token using refresh token"""
        refresh_token = self.fernet.decrypt(
            integration.refresh_token_encrypted
        ).decode()

        credentials = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri=self.client_config['web']['token_uri'],
            client_id=self.client_config['web']['client_id'],
            client_secret=self.client_config['web']['client_secret']
        )

        # Refresh the token
        credentials.refresh(Request())

        # Update encrypted token in database
        integration.access_token_encrypted = self.fernet.encrypt(
            credentials.token.encode()
        )
        integration.token_expires_at = credentials.expiry
        db.commit()

        return credentials

    async def get_available_slots(
            self,
            integration: CalendarIntegration,
            db: Session,
            start_date: datetime,
            end_date: datetime,
            duration_minutes: int,
            business_hours_start: int = 8,  # 8 AM
            business_hours_end: int = 18  # 6 PM
    ) -> List[Dict]:
        """
        Get available time slots from Google Calendar by fetching busy times
        and finding gaps

        Args:
            integration: Calendar integration instance
            db: Database session
            start_date: Start of search range (timezone-aware)
            end_date: End of search range (timezone-aware)
            duration_minutes: Required slot duration
            business_hours_start: Business day start hour (default 8 AM)
            business_hours_end: Business day end hour (default 6 PM)

        Returns:
            List of available slots with start/end times
        """
        # Validate time range
        if end_date <= start_date:
            raise ValueError(f"end_date ({end_date}) must be after start_date ({start_date})")

        credentials = self.get_valid_credentials(integration, db)
        service = build('calendar', 'v3', credentials=credentials)

        calendar_id = integration.provider_config.get('selected_calendar_id', 'primary')

        # Ensure timezone-aware datetimes
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)

        # Get busy times using freebusy query
        body = {
            "timeMin": start_date.isoformat(),
            "timeMax": end_date.isoformat(),
            "items": [{"id": calendar_id}],
            "timeZone": "UTC"
        }

        try:
            freebusy_result = service.freebusy().query(body=body).execute()
            busy_times = freebusy_result['calendars'][calendar_id].get('busy', [])
        except Exception as e:
            logger.error(f"Google Calendar API error: {e}")
            raise

        # Convert busy times to timezone-aware datetime objects
        busy_periods = []
        for busy in busy_times:
            start_str = busy['start'].replace('Z', '+00:00')
            end_str = busy['end'].replace('Z', '+00:00')
            busy_periods.append({
                'start': datetime.fromisoformat(start_str),
                'end': datetime.fromisoformat(end_str)
            })

        # Sort busy periods by start time for efficient processing
        busy_periods.sort(key=lambda x: x['start'])

        # Generate slots by finding gaps in busy times
        slots = []
        current_time = start_date

        while current_time < end_date:
            slot_end = current_time + timedelta(minutes=duration_minutes)

            # Don't create slots that extend past end_date
            if slot_end > end_date:
                break

            # Check if this slot overlaps with any busy period
            is_available = True
            for busy in busy_periods:
                # Skip busy periods that are completely before current slot
                if busy['end'] <= current_time:
                    continue

                # If busy period starts after this slot ends, we're done checking
                if busy['start'] >= slot_end:
                    break

                # Overlaps with busy period
                if current_time < busy['end'] and slot_end > busy['start']:
                    is_available = False
                    # Jump to end of busy period
                    current_time = busy['end']
                    break

            if is_available:
                # Only include slots during business hours
                if business_hours_start <= current_time.hour < business_hours_end:
                    # Ensure slot doesn't extend past business hours
                    slot_end_hour = slot_end.hour + (slot_end.minute / 60)
                    if slot_end_hour <= business_hours_end:
                        slots.append({
                            'start': current_time.isoformat(),
                            'end': slot_end.isoformat(),
                            'duration_minutes': duration_minutes
                        })

                # Move to next potential slot
                current_time += timedelta(minutes=duration_minutes)

            # Safety check: if we're stuck, break
            if current_time >= end_date:
                break

        logger.info(f"Generated {len(slots)} available slots between {start_date} and {end_date}")
        return slots

    async def create_event(
            self,
            integration: CalendarIntegration,
            db: Session,
            event_data: Dict
    ) -> Dict:
        """
        Create a calendar event

        event_data should contain:
        - summary: Event title
        - description: Event description
        - start: Start datetime
        - end: End datetime
        - attendees: List of email addresses (optional)
        """
        credentials = self.get_valid_credentials(integration, db)
        service = build('calendar', 'v3', credentials=credentials)

        calendar_id = integration.provider_config.get('selected_calendar_id', 'primary')

        # Format event for Google Calendar API
        event = {
            'summary': event_data.get('summary'),
            'description': event_data.get('description', ''),
            'start': {
                'dateTime': event_data['start'].isoformat(),
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': event_data['end'].isoformat(),
                'timeZone': 'UTC',
            }
        }

        # Add attendees if provided
        if event_data.get('attendees'):
            event['attendees'] = [
                {'email': email} for email in event_data['attendees']
            ]

        # Create the event
        created_event = service.events().insert(
            calendarId=calendar_id,
            body=event,
            sendUpdates='all'  # Send email notifications to attendees
        ).execute()

        return {
            'event_id': created_event['id'],
            'event_url': created_event.get('htmlLink'),
            'status': created_event.get('status')
        }

    async def update_event(
            self,
            integration: CalendarIntegration,
            db: Session,
            event_id: str,
            event_data: Dict
    ) -> Dict:
        """Update an existing calendar event"""
        credentials = self.get_valid_credentials(integration, db)
        service = build('calendar', 'v3', credentials=credentials)

        calendar_id = integration.provider_config.get('selected_calendar_id', 'primary')

        # Get existing event first
        existing_event = service.events().get(
            calendarId=calendar_id,
            eventId=event_id
        ).execute()

        # Update only provided fields
        if 'summary' in event_data:
            existing_event['summary'] = event_data['summary']
        if 'description' in event_data:
            existing_event['description'] = event_data['description']
        if 'start' in event_data:
            existing_event['start'] = {
                'dateTime': event_data['start'].isoformat(),
                'timeZone': 'UTC',
            }
        if 'end' in event_data:
            existing_event['end'] = {
                'dateTime': event_data['end'].isoformat(),
                'timeZone': 'UTC',
            }

        # Update the event
        updated_event = service.events().update(
            calendarId=calendar_id,
            eventId=event_id,
            body=existing_event,
            sendUpdates='all'
        ).execute()

        return {
            'event_id': updated_event['id'],
            'event_url': updated_event.get('htmlLink'),
            'status': updated_event.get('status')
        }

    async def delete_event(
            self,
            integration: CalendarIntegration,
            db: Session,
            event_id: str
    ) -> bool:
        """Delete a calendar event"""
        credentials = self.get_valid_credentials(integration, db)
        service = build('calendar', 'v3', credentials=credentials)

        calendar_id = integration.provider_config.get('selected_calendar_id', 'primary')

        try:
            service.events().delete(
                calendarId=calendar_id,
                eventId=event_id,
                sendUpdates='all'  # Notify attendees
            ).execute()
            return True
        except Exception as e:
            print(f"Failed to delete event: {e}")
            return False
