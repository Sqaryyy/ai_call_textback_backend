# ===== app/tasks/calendar_tasks.py =====
from datetime import datetime, timedelta, timezone
from app.config.celery_config import celery_app
from app.config.database import get_db
from app.models.appointment import Appointment
from app.models.calendar_integration import CalendarIntegration
from app.services.calendar.google_calendar_service import GoogleCalendarService
from app.services.calendar.outlook_service import OutlookCalendarService
import logging
import asyncio

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def sync_calendar_connection(self, integration_id: str):
    """Test calendar connection by fetching availability for next 7 days"""
    try:
        db = next(get_db())

        integration = db.query(CalendarIntegration).filter_by(id=integration_id).first()
        if not integration or not integration.is_active:
            return {"status": "failed", "reason": "integration_not_found_or_inactive"}

        # Get service based on provider
        if integration.provider == 'google':
            service = GoogleCalendarService()
        elif integration.provider == 'outlook':
            service = OutlookCalendarService()
        else:
            raise ValueError(f"Unsupported calendar provider: {integration.provider}")

        # Test connection by fetching availability for next 7 days
        start = datetime.now(timezone.utc)
        end = start + timedelta(days=7)

        slots = asyncio.run(service.get_available_slots(
            integration=integration,
            db=db,
            start_date=start,
            end_date=end,
            duration_minutes=60
        ))

        # Update integration metadata
        integration.last_sync_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(f"Successfully tested calendar connection {integration_id}")
        return {"status": "success", "slots_found": len(slots)}

    except Exception as exc:
        logger.error(f"Calendar sync failed for integration {integration_id}: {exc}")

        db = next(get_db())
        integration = db.query(CalendarIntegration).filter_by(id=integration_id).first()
        if integration:
            integration.last_sync_error = str(exc)
            db.commit()

        raise self.retry(countdown=60 * (self.request.retries + 1))


@celery_app.task(bind=True, max_retries=3)
def sync_appointment_to_calendar(self, appointment_id: str):
    """Sync appointment to external calendar (push operation)"""
    try:
        db = next(get_db())

        appointment = db.query(Appointment).filter_by(id=appointment_id).first()
        if not appointment:
            logger.error(f"Appointment {appointment_id} not found")
            return {"status": "failed", "reason": "appointment_not_found"}

        # Get calendar integration
        integration = db.query(CalendarIntegration).filter_by(
            business_id=appointment.business_id,
            is_active=True,
            is_primary=True
        ).first()

        if not integration or integration.sync_direction == 'read_only':
            appointment.sync_status = "sync_disabled"
            db.commit()
            return {"status": "skipped", "reason": "no_integration_or_read_only"}

        # Get the appropriate service based on provider
        if integration.provider == 'google':
            service = GoogleCalendarService()
            event_data = {
                'summary': f"{appointment.service_type} - {appointment.customer_name}",
                'description': appointment.notes or "",
                'start': appointment.appointment_datetime,
                'end': appointment.appointment_datetime + timedelta(minutes=appointment.duration_minutes),
                'attendees': [appointment.customer_email] if appointment.customer_email else []
            }
            event = asyncio.run(service.create_event(integration, db, event_data))

        elif integration.provider == 'outlook':
            service = OutlookCalendarService()
            event_data = {
                'subject': f"{appointment.service_type} - {appointment.customer_name}",
                'body': appointment.notes or "",
                'start': appointment.appointment_datetime,
                'end': appointment.appointment_datetime + timedelta(minutes=appointment.duration_minutes),
                'attendees': [appointment.customer_email] if appointment.customer_email else []
            }
            event = asyncio.run(service.create_event(integration, db, event_data))

        elif integration.provider == 'calendly':
            # Calendly is read-only, can't create events
            appointment.sync_status = "sync_disabled"
            db.commit()
            return {"status": "skipped", "reason": "calendly_is_read_only"}

        else:
            raise ValueError(f"Unsupported calendar provider: {integration.provider}")

        # Update appointment with calendar info
        appointment.external_event_id = event['event_id']
        appointment.external_event_url = event.get('event_url')
        appointment.calendar_integration_id = integration.id
        appointment.sync_status = "synced"
        appointment.last_synced_at = datetime.now(timezone.utc)
        appointment.sync_attempts = (appointment.sync_attempts or 0) + 1

        db.commit()

        logger.info(f"Successfully synced appointment {appointment_id} to {integration.provider}")
        return {"status": "synced", "event_id": event['event_id']}

    except Exception as exc:
        logger.error(f"Calendar sync failed for {appointment_id}: {exc}")

        db = next(get_db())
        appointment = db.query(Appointment).filter_by(id=appointment_id).first()
        if appointment:
            appointment.sync_status = "failed"
            appointment.sync_attempts = (appointment.sync_attempts or 0) + 1
            appointment.last_sync_error = str(exc)
            db.commit()

        raise self.retry(countdown=60 * (self.request.retries + 1))
