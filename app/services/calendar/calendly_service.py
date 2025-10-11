# app/services/calendar/calendly_service.py
import os

import requests
from cryptography.fernet import Fernet

from app.models import CalendarIntegration


class CalendlyService:
    BASE_URL = "https://api.calendly.com"

    def __init__(self):
        self.encryption_key = os.getenv('CALENDAR_ENCRYPTION_KEY')
        self.fernet = Fernet(self.encryption_key.encode())

    def setup_integration(self, business_id: str, personal_access_token: str, db):
        """Setup Calendly integration"""

        # Verify token by fetching user info
        headers = {"Authorization": f"Bearer {personal_access_token}"}
        response = requests.get(f"{self.BASE_URL}/users/me", headers=headers)

        if response.status_code != 200:
            raise ValueError("Invalid Calendly token")

        user_data = response.json()['resource']

        # Fetch event types
        event_types_response = requests.get(
            f"{self.BASE_URL}/event_types",
            headers=headers,
            params={"user": user_data['uri']}
        )
        event_types = event_types_response.json()['collection']

        # Encrypt token
        token_encrypted = self.fernet.encrypt(personal_access_token.encode())

        integration = CalendarIntegration(
            business_id=business_id,
            provider='calendly',
            is_active=True,
            access_token_encrypted=token_encrypted,
            provider_config={
                'user_uri': user_data['uri'],
                'scheduling_url': user_data['scheduling_url'],
                'event_types': [
                    {
                        'uri': et['uri'],
                        'name': et['name'],
                        'duration': et['duration'],
                        'booking_url': et['scheduling_url']
                    }
                    for et in event_types
                ]
            },
            sync_direction='read_only'
        )

        db.add(integration)
        db.commit()
        return integration
