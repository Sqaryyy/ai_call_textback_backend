# ============================================================================
# FILE: app/config/email_config.py
# Email configuration for alerts (using Resend - free tier)
# ============================================================================
import httpx
from typing import List, Optional
from app.config.settings import get_settings
from app.utils.logger import get_logger

settings = get_settings()
logger = get_logger(__name__)


class EmailService:
    """
    Lightweight email service using Resend (https://resend.com)

    Free tier: 3,000 emails/month, 100/day
    No dependencies - just HTTP requests
    """

    def __init__(self):
        self.api_key = settings.RESEND_API_KEY
        self.from_email = settings.ALERT_EMAIL_FROM
        self.base_url = "https://api.resend.com"

    async def send_alert(
            self,
            subject: str,
            body: str,
            to_emails: Optional[List[str]] = None,
            severity: str = "warning"
    ):
        """
        Send an alert email.

        Args:
            subject: Email subject
            body: Email body (plain text or HTML)
            to_emails: List of recipient emails (defaults to ALERT_EMAIL_TO)
            severity: "critical", "warning", "info"
        """
        if not self.api_key:
            logger.warning(f"Email not sent (no RESEND_API_KEY): {subject}")
            return False

        recipients = to_emails or [settings.ALERT_EMAIL_TO]

        # Add severity emoji
        emoji = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}.get(severity, "📧")

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/emails",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "from": self.from_email,
                        "to": recipients,
                        "subject": f"{emoji} {subject}",
                        "html": f"<pre>{body}</pre>",  # Simple formatting
                    },
                    timeout=10.0
                )

                if response.status_code == 200:
                    logger.info(f"Alert email sent: {subject}")
                    return True
                else:
                    logger.error(f"Email send failed: {response.status_code} - {response.text}")
                    return False

            except Exception as e:
                logger.error(f"Email send error: {e}")
                return False


# Singleton instance
email_service = EmailService()