"""
Demo Session Service - Manages in-memory demo sessions and mock data
File: app/services/demo/demo_session_service.py
"""
from typing import Dict, List, Optional
from datetime import datetime, timedelta, timezone
import uuid
import logging

logger = logging.getLogger(__name__)

# In-memory storage for demo sessions
# Key: session_id -> Value: session data
demo_sessions = {}


class DemoSessionService:
    """Service for managing demo conversation sessions and mock data"""

    @staticmethod
    def create_session(
        conversation_id: str,
        customer_phone: str,
        business_id: str
    ) -> str:
        """
        Create new demo session with mock calendar and appointment storage.
        Returns session_id.
        """
        session_id = str(uuid.uuid4())
        demo_sessions[session_id] = {
            "conversation_id": conversation_id,
            "customer_phone": customer_phone,
            "business_id": business_id,
            "business_overrides": {},
            "demo_appointments": [],
            "demo_availability_config": {
                "business_hours_start": 9,   # 9 AM
                "business_hours_end": 17,    # 5 PM
                "slot_duration": 30,         # 30 minutes
                "days_ahead": 7,             # Show slots for next 7 days
                "exclude_weekends": True
            }
        }
        logger.info(f"📝 Created demo session: {session_id}")
        return session_id

    @staticmethod
    def get_session(session_id: str) -> Optional[Dict]:
        """Get session data by session_id"""
        return demo_sessions.get(session_id)

    @staticmethod
    def session_exists(session_id: str) -> bool:
        """Check if session exists"""
        return session_id in demo_sessions

    @staticmethod
    def add_appointment(session_id: str, appointment: Dict) -> bool:
        """
        Add appointment to session's demo appointments.
        Returns True if successful, False if session not found.
        """
        session = demo_sessions.get(session_id)
        if not session:
            logger.warning(f"Cannot add appointment - session {session_id} not found")
            return False

        session["demo_appointments"].append(appointment)
        logger.info(f"✅ Added demo appointment to session {session_id}: {appointment['service']}")
        return True

    @staticmethod
    def get_appointments(session_id: str) -> List[Dict]:
        """Get all appointments for a session"""
        session = demo_sessions.get(session_id)
        if not session:
            return []
        return session.get("demo_appointments", [])

    @staticmethod
    def cancel_appointment(session_id: str, appointment_id: str) -> bool:
        """
        Cancel (remove) appointment from session.
        Returns True if found and cancelled, False otherwise.
        """
        session = demo_sessions.get(session_id)
        if not session:
            return False

        appointments = session.get("demo_appointments", [])
        for i, apt in enumerate(appointments):
            if apt["id"] == appointment_id:
                appointments[i]["status"] = "cancelled"
                logger.info(f"❌ Cancelled demo appointment {appointment_id}")
                return True

        return False

    @staticmethod
    def reschedule_appointment(
        session_id: str,
        appointment_id: str,
        new_datetime: str
    ) -> bool:
        """
        Reschedule appointment to new time.
        Returns True if found and rescheduled, False otherwise.
        """
        session = demo_sessions.get(session_id)
        if not session:
            return False

        appointments = session.get("demo_appointments", [])
        for apt in appointments:
            if apt["id"] == appointment_id:
                apt["start_time"] = new_datetime
                apt["updated_at"] = datetime.now(timezone.utc).isoformat()
                logger.info(f"🔄 Rescheduled demo appointment {appointment_id} to {new_datetime}")
                return True

        return False

    @staticmethod
    def generate_available_slots(
        session_id: str,
        start_date: Optional[str],
        end_date: Optional[str],
        duration_minutes: int,
        limit: int = 20
    ) -> List[Dict]:
        """
        Generate mock available slots, excluding already booked times.
        Returns list of slot dictionaries.
        """
        session = demo_sessions.get(session_id)
        if not session:
            logger.warning(f"Cannot generate slots - session {session_id} not found")
            return []

        config = session.get("demo_availability_config", {})
        booked_appointments = session.get("demo_appointments", [])

        # Parse dates or use defaults
        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
                # If just a date (no time), start from business open
                if start_dt.hour == 0 and start_dt.minute == 0:
                    start_dt = start_dt.replace(hour=config.get("business_hours_start", 9))
            except ValueError:
                logger.error(f"Invalid start_date format: {start_date}")
                start_dt = datetime.now(timezone.utc) + timedelta(hours=1)
                start_dt = start_dt.replace(minute=0, second=0, microsecond=0)
        else:
            # Default: start from next available hour
            now = datetime.now(timezone.utc)
            start_dt = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
                # If just a date, search until end of day
                if end_dt.hour == 0 and end_dt.minute == 0:
                    end_dt = end_dt.replace(hour=23, minute=59)
            except ValueError:
                logger.error(f"Invalid end_date format: {end_date}")
                end_dt = start_dt + timedelta(days=config.get("days_ahead", 3))
        else:
            # If specific date requested, just that day; otherwise next N days
            if start_date:
                end_dt = start_dt.replace(hour=23, minute=59, second=59)
            else:
                end_dt = start_dt + timedelta(days=config.get("days_ahead", 3))

        business_start = config.get("business_hours_start", 9)
        business_end = config.get("business_hours_end", 17)
        exclude_weekends = config.get("exclude_weekends", True)

        # Get booked times as set for quick lookup (only non-cancelled)
        booked_times = {
            appt["start_time"]
            for appt in booked_appointments
            if appt.get("status", "scheduled") != "cancelled"
        }

        slots = []
        current = start_dt

        while current < end_dt and len(slots) < limit:
            # Skip if outside business hours
            if current.hour < business_start or current.hour >= business_end:
                # Jump to next day at business start
                current += timedelta(days=1)
                current = current.replace(hour=business_start, minute=0, second=0, microsecond=0)
                continue

            # Skip weekends if configured
            if exclude_weekends and current.weekday() >= 5:  # 5=Saturday, 6=Sunday
                current += timedelta(days=1)
                current = current.replace(hour=business_start, minute=0, second=0, microsecond=0)
                continue

            slot_start = current.isoformat()
            slot_end = (current + timedelta(minutes=duration_minutes)).isoformat()

            # Only add if not already booked
            if slot_start not in booked_times:
                slots.append({
                    "start_time": slot_start,
                    "end_time": slot_end,
                    "display_time": current.strftime("%A, %B %d at %I:%M %p")
                })

            current += timedelta(minutes=duration_minutes)

        logger.info(f"📅 Generated {len(slots)} demo slots for session {session_id}")
        return slots

    @staticmethod
    def update_business_overrides(
        session_id: str,
        overrides: Dict
    ) -> bool:
        """
        Update business context overrides for this session.
        Used when testing custom business configurations.
        """
        session = demo_sessions.get(session_id)
        if not session:
            return False

        session["business_overrides"].update(overrides)
        logger.info(f"🔧 Updated business overrides for session {session_id}")
        return True

    @staticmethod
    def cleanup_session(session_id: str) -> bool:
        """
        Remove session from memory.
        Returns True if session was found and removed.
        """
        if session_id in demo_sessions:
            del demo_sessions[session_id]
            logger.info(f"🗑️ Cleaned up demo session: {session_id}")
            return True
        return False

    @staticmethod
    def get_all_sessions() -> List[str]:
        """Get list of all active session IDs (for debugging/admin)"""
        return list(demo_sessions.keys())

    @staticmethod
    def get_session_count() -> int:
        """Get count of active sessions"""
        return len(demo_sessions)