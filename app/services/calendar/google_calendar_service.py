# app/services/calendar/google_calendar_service.py
import os
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

settings = get_settings()

logger = logging.getLogger(__name__)


class GoogleCalendarService:
    SCOPES = ['https://www.googleapis.com/auth/calendar']

    def __init__(self):
        self.encryption_key = settings.CALENDAR_ENCRYPTION_KEY
        self.fernet = Fernet(self.encryption_key.encode())

        # Get redirect URI from settings (preferred) or environment variable
        redirect_uri = getattr(settings, 'GOOGLE_REDIRECT_URI', None) or os.getenv("GOOGLE_REDIRECT_URI")

        if not redirect_uri:
            error_msg = "GOOGLE_REDIRECT_URI is not set! Please add it to your .env file."
            logger.error(error_msg)
            print(f"\n{'!' * 80}\nERROR: {error_msg}\n{'!' * 80}\n")
            raise ValueError(error_msg)

        # OAuth credentials from Google Cloud Console
        self.client_config = {
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uris": [redirect_uri],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token"
            }
        }

        # DEBUG: Print configuration on initialization
        logger.info("=" * 80)
        logger.info("GoogleCalendarService Configuration:")
        logger.info(
            f"Client ID: {settings.GOOGLE_CLIENT_ID[:20]}..." if settings.GOOGLE_CLIENT_ID else "Client ID: NOT SET")
        logger.info(f"Client Secret: {'*' * 10}{'SET' if settings.GOOGLE_CLIENT_SECRET else 'NOT SET'}")
        logger.info(f"Redirect URI: {redirect_uri}")
        logger.info(f"Redirect URIs in config: {self.client_config['web']['redirect_uris']}")
        logger.info("=" * 80)

        # Print to console for visibility
        print("\n" + "=" * 80)
        print("GoogleCalendarService Initialized")
        print(f"Redirect URI: {redirect_uri}")
        print("=" * 80 + "\n")

    def generate_authorization_url(self, business_id: str) -> str:
        """Step 1: Generate OAuth URL for business owner"""
        redirect_uri = self.client_config['web']['redirect_uris'][0]

        # DEBUG: Print detailed information
        logger.info("=" * 80)
        logger.info("Generating Authorization URL")
        logger.info(f"Business ID: {business_id}")
        logger.info(f"Redirect URI being used: {redirect_uri}")
        logger.info(f"Client ID: {self.client_config['web']['client_id'][:20]}...")
        logger.info(f"Scopes: {self.SCOPES}")
        logger.info("=" * 80)

        # Print to console as well (in case logger isn't configured)
        print("\n" + "=" * 80)
        print("OAUTH CONFIGURATION DEBUG:")
        print(f"Redirect URI: {redirect_uri}")
        print(f"Client ID: {self.client_config['web']['client_id']}")
        print(f"Business ID (state): {business_id}")
        print("=" * 80 + "\n")

        flow = Flow.from_client_config(
            self.client_config,
            scopes=self.SCOPES,
            redirect_uri=redirect_uri
        )

        authorization_url, state = flow.authorization_url(
            access_type='offline',  # Gets refresh token
            include_granted_scopes='true',
            prompt='consent',  # Force consent screen to get refresh token
            state=business_id  # Pass business_id to identify after callback
        )

        # DEBUG: Print the generated URL
        logger.info("=" * 80)
        logger.info("Generated Authorization URL:")
        logger.info(authorization_url)
        logger.info(f"State parameter: {state}")
        logger.info("=" * 80)

        print("\n" + "=" * 80)
        print("GENERATED AUTHORIZATION URL:")
        print(authorization_url)
        print(f"\nState: {state}")
        print("=" * 80 + "\n")

        return authorization_url

    def handle_oauth_callback(self, code: str, state: str, db):
        """Step 2: Exchange authorization code for tokens"""
        business_id = state  # Extract business_id from state

        # DEBUG: Print callback information
        logger.info("=" * 80)
        logger.info("Handling OAuth Callback")
        logger.info(f"Authorization code: {code[:20]}...")
        logger.info(f"State (business_id): {state}")
        logger.info(f"Redirect URI: {self.client_config['web']['redirect_uris'][0]}")
        logger.info("=" * 80)

        print("\n" + "=" * 80)
        print("OAUTH CALLBACK DEBUG:")
        print(f"Code received: {code[:20]}...")
        print(f"State: {state}")
        print(f"Redirect URI: {self.client_config['web']['redirect_uris'][0]}")
        print("=" * 80 + "\n")

        flow = Flow.from_client_config(
            self.client_config,
            scopes=self.SCOPES,
            redirect_uri=self.client_config['web']['redirect_uris'][0]
        )

        try:
            # Exchange code for tokens
            flow.fetch_token(code=code)
            credentials = flow.credentials

            logger.info("Successfully exchanged authorization code for tokens")
            print("✓ Successfully obtained tokens")
        except Exception as e:
            logger.error(f"Failed to exchange code for tokens: {e}")
            print(f"✗ Error exchanging code: {e}")
            raise

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

        logger.info(f"Successfully created calendar integration with ID: {integration.id}")
        print(f"✓ Created integration ID: {integration.id}")

        return integration

    # ... rest of the methods remain the same ...
    def get_valid_credentials(self, integration: CalendarIntegration, db: Session) -> Credentials:
        """Get valid credentials, refreshing if necessary"""
        now = datetime.now(timezone.utc)
        if integration.token_expires_at <= now + timedelta(minutes=5):
            return self.refresh_access_token(integration, db)
        access_token = self.fernet.decrypt(integration.access_token_encrypted).decode()
        refresh_token = self.fernet.decrypt(integration.refresh_token_encrypted).decode()
        return Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri=self.client_config['web']['token_uri'],
            client_id=self.client_config['web']['client_id'],
            client_secret=self.client_config['web']['client_secret']
        )

    def refresh_access_token(self, integration: CalendarIntegration, db: Session) -> Credentials:
        """Refresh expired access token using refresh token"""
        refresh_token = self.fernet.decrypt(integration.refresh_token_encrypted).decode()
        credentials = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri=self.client_config['web']['token_uri'],
            client_id=self.client_config['web']['client_id'],
            client_secret=self.client_config['web']['client_secret']
        )
        credentials.refresh(Request())
        integration.access_token_encrypted = self.fernet.encrypt(credentials.token.encode())
        integration.token_expires_at = credentials.expiry
        db.commit()
        return credentials