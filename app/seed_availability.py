# ===== seed_availability.py =====
import uuid
from datetime import date, time
from app.config.database import get_db
from app.models.availability import AvailabilityRule, AvailabilityOverride

# Replace with a real business ID from your DB
BUSINESS_ID = "4267ca4e-1b71-4b5c-882b-c52475f8c613"

def seed_availability():
    db = next(get_db())

    try:
        # 1. Mon–Fri availability rules (9–5, 30 min slots)
        rules = []
        for day in range(0, 5):  # 0=Monday ... 4=Friday
            rules.append(AvailabilityRule(
                id=uuid.uuid4(),
                business_id=BUSINESS_ID,
                day_of_week=day,
                start_time=time(9, 0),
                end_time=time(17, 0),
                slot_duration_minutes=30,
                buffer_time_minutes=0,
                is_active=True
            ))

        # 2. Example override: closed on Oct 10, 2025
        override_day_off = AvailabilityOverride(
            id=uuid.uuid4(),
            business_id=BUSINESS_ID,
            date=date(2025, 10, 10),
            is_available=False,
            reason="Vacation"
        )

        # 3. Example override: shorter hours on Oct 15, 2025
        override_half_day = AvailabilityOverride(
            id=uuid.uuid4(),
            business_id=BUSINESS_ID,
            date=date(2025, 10, 15),
            is_available=True,
            start_time=time(10, 0),
            end_time=time(14, 0),
            reason="Half day"
        )

        db.add_all(rules + [override_day_off, override_half_day])
        db.commit()
        print("✅ Availability rules and overrides seeded successfully!")

    except Exception as e:
        db.rollback()
        print("❌ Error seeding availability:", e)
    finally:
        db.close()

if __name__ == "__main__":
    seed_availability()
