# ===== app/services/availability/availability_service.py =====
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.calendar_integration import CalendarIntegration
from app.models.availability import AvailabilityRule, AvailabilityOverride
from app.models.appointment import Appointment
from app.services.calendar.google_calendar_service import GoogleCalendarService
from app.services.calendar.outlook_service import OutlookCalendarService
from app.services.calendar.calendly_service import CalendlyService
import logging

logger = logging.getLogger(__name__)


class AvailabilityService:
    """Unified service for getting availability from any source"""

    @staticmethod
    async def get_available_slots(
            db: Session,
            business_id: str,
            start_date: datetime,
            end_date: datetime,
            duration_minutes: int = 30,
            limit: Optional[int] = None
    ) -> List[Dict]:
        """
        Get available slots from the best available source:
        1. Connected calendar (if exists)
        2. Availability rules + existing appointments
        3. Default business hours
        """

        # Try calendar integration first
        integration = db.query(CalendarIntegration).filter_by(
            business_id=business_id,
            is_active=True,
            is_primary=True
        ).first()

        if integration and integration.auto_sync_enabled:
            try:
                # Get slots from the appropriate calendar provider
                slots = await AvailabilityService._get_slots_from_calendar(
                    integration, db, start_date, end_date, duration_minutes
                )

                if slots:
                    logger.info(f"Retrieved {len(slots)} slots from {integration.provider}")
                    return slots[:limit] if limit else slots
                else:
                    logger.warning(f"No slots returned from {integration.provider}, falling back to rules")

            except Exception as e:
                logger.error(f"Calendar fetch failed for {integration.provider}: {e}, falling back to rules")

        # Fallback to availability rules
        return AvailabilityService._get_slots_from_rules(
            db, business_id, start_date, end_date, duration_minutes, limit
        )

    @staticmethod
    async def _get_slots_from_calendar(
            integration: CalendarIntegration,
            db: Session,
            start_date: datetime,
            end_date: datetime,
            duration_minutes: int
    ) -> List[Dict]:
        """Get available slots from the appropriate calendar provider"""

        if integration.provider == 'google':
            service = GoogleCalendarService()
            return await service.get_available_slots(
                integration, db, start_date, end_date, duration_minutes
            )

        elif integration.provider == 'outlook':
            service = OutlookCalendarService()
            return await service.get_available_slots(
                integration, db, start_date, end_date, duration_minutes
            )

        elif integration.provider == 'calendly':
            service = CalendlyService()
            return await service.get_available_slots(
                integration, db, start_date, end_date, duration_minutes
            )

        else:
            logger.error(f"Unknown calendar provider: {integration.provider}")
            return []

    @staticmethod
    def _get_slots_from_rules(
            db: Session,
            business_id: str,
            start_date: datetime,
            end_date: datetime,
            duration_minutes: int,
            limit: Optional[int]
    ) -> List[Dict]:
        """Generate slots from availability rules and block out existing appointments"""

        # Get availability rules
        rules = db.query(AvailabilityRule).filter_by(
            business_id=business_id,
            is_active=True
        ).all()

        if not rules:
            logger.warning(f"No availability rules found for business {business_id}")
            return []

        # Get overrides
        overrides = db.query(AvailabilityOverride).filter(
            AvailabilityOverride.business_id == business_id,
            AvailabilityOverride.date.between(start_date.date(), end_date.date())
        ).all()

        # Get existing appointments
        booked_slots = db.query(Appointment).filter(
            Appointment.business_id == business_id,
            Appointment.appointment_datetime.between(start_date, end_date),
            Appointment.status.in_(['scheduled', 'confirmed'])
        ).all()

        # Generate available slots
        slots = []
        current_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

        while current_date < end_date:
            # Check for override first
            override = next((o for o in overrides if o.date == current_date.date()), None)

            if override and not override.is_available:
                current_date += timedelta(days=1)
                continue

            # Get rule for this day
            rule = next((r for r in rules if r.day_of_week == current_date.weekday()), None)

            if rule or (override and override.is_available):
                day_slots = AvailabilityService._generate_day_slots(
                    current_date,
                    override if override else rule,
                    duration_minutes,
                    booked_slots
                )
                slots.extend(day_slots)

            current_date += timedelta(days=1)

            if limit and len(slots) >= limit:
                break

        return slots[:limit] if limit else slots

    @staticmethod
    def _generate_day_slots(
            date: datetime,
            rule_or_override,
            duration_minutes: int,
            booked_slots: List[Appointment]
    ) -> List[Dict]:
        """Generate time slots for a single day"""
        slots = []

        # Get start/end times
        if isinstance(rule_or_override, AvailabilityRule):
            start_time = rule_or_override.start_time
            end_time = rule_or_override.end_time
            buffer = rule_or_override.buffer_time_minutes
        else:  # AvailabilityOverride
            start_time = rule_or_override.start_time
            end_time = rule_or_override.end_time
            buffer = 0

        # Create datetime objects for the day
        current_slot = datetime.combine(date.date(), start_time)
        day_end = datetime.combine(date.date(), end_time)

        while current_slot + timedelta(minutes=duration_minutes) <= day_end:
            slot_end = current_slot + timedelta(minutes=duration_minutes)

            # Check if slot conflicts with existing appointments
            is_available = True
            for appointment in booked_slots:
                appt_end = appointment.appointment_datetime + timedelta(minutes=appointment.duration_minutes)

                if current_slot < appt_end and slot_end > appointment.appointment_datetime:
                    is_available = False
                    break

            if is_available:
                slots.append({
                    'start': current_slot.isoformat(),
                    'end': slot_end.isoformat(),
                    'duration_minutes': duration_minutes
                })

            # Move to next slot (including buffer time)
            current_slot += timedelta(minutes=duration_minutes + buffer)

        return slots