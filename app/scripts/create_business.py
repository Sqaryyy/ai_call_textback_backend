#!/usr/bin/env python3
"""
Script to create a business with business hours
Usage: python create_business.py
"""
import sys
import uuid
from sqlalchemy.orm import Session

from app.config.database import SessionLocal
from app.models.business import Business, BusinessHours


def create_business_with_hours():
    """Create a demo business with business hours"""
    db: Session = SessionLocal()

    try:
        # Business configuration
        business_data = {
            "name": "Sunset Realty Group",
            "phone_number": "+1234567890",  # Change this to your actual phone number
            "business_type": "real_estate",
            "timezone": "America/New_York",

            # Business profile
            "business_profile": {
                "description": "Full-service real estate agency specializing in residential and commercial properties",
                "personality": "professional, knowledgeable, and trustworthy",
                "tone": "confident and helpful",
                "specialties": ["residential sales", "commercial properties", "luxury homes", "investment properties"],
                "areas_served": ["Downtown", "Suburban areas", "Waterfront properties", "Historic districts"]
            },

            # Service catalog
            "service_catalog": {
                "Home Buying Consultation": {
                    "description": "Personalized consultation to find your dream home",
                    "price": "Free",
                    "duration": 60,
                    "requires_booking": True
                },
                "Property Listing": {
                    "description": "Professional listing service with marketing and staging advice",
                    "price": "Commission-based",
                    "duration": 90,
                    "requires_booking": True
                },
                "Property Valuation": {
                    "description": "Comprehensive market analysis and property valuation",
                    "price": "Free",
                    "duration": 45,
                    "requires_booking": True
                },
                "Investment Property Analysis": {
                    "description": "Detailed analysis of investment opportunities and ROI projections",
                    "price": "Free",
                    "duration": 60,
                    "requires_booking": True
                }
            },

            # Conversation policies
            "conversation_policies": {
                "cancellation_policy": "Appointments can be rescheduled with 24 hours notice",
                "commission_policy": "Standard commission is 6% of sale price, split between buyer and seller agents",
                "availability_policy": "Our agents are available 7 days a week for showings",
                "confidentiality_policy": "All client information is kept strictly confidential"
            },

            # Quick responses (FAQs)
            "quick_responses": {
                "What are your hours?": "We're available Monday-Friday 9am-7pm, Saturday 10am-5pm, and Sunday by appointment",
                "Do you charge buyers?": "No, buyer services are typically free as we're compensated by the seller's agent",
                "How long does it take to buy a home?": "On average, the home buying process takes 30-45 days from offer to closing",
                "What areas do you cover?": "We serve the entire metropolitan area including downtown, suburbs, waterfront, and historic districts",
                "Do you help with first-time buyers?": "Absolutely! We specialize in helping first-time buyers navigate the entire process"
            },

            # Contact info
            "contact_info": {
                "address": "123 Main Street, Suite 200, Your City, ST 12345",
                "email": "info@sunsetrealtygroup.com",
                "office_phone": "+1234567890"
            },

            # AI instructions
            "ai_instructions": "Always emphasize our market expertise and local knowledge. Encourage scheduling property viewings. Be responsive to urgency - buyers often need quick responses in competitive markets.",

            # Booking settings
            "booking_settings": {
                "allow_online_booking": True,
                "require_confirmation": True,
                "buffer_time": 15
            },

            # Webhook URLs (optional)
            "webhook_urls": {},

            # Onboarding status
            "onboarding_status": {
                "completed": True,
                "steps": ["business_info", "services", "hours", "policies"]
            }
        }

        # Create business
        business = Business(**business_data)
        db.add(business)
        db.flush()  # Get the ID without committing

        print(f"\n✅ Created business: {business.name}")
        print(f"   Business ID: {business.id}")
        print(f"   Phone: {business.phone_number}")

        # Business hours (Monday=0, Sunday=6)
        business_hours = [
            {"day_of_week": 0, "open_time": "09:00", "close_time": "19:00", "is_closed": False},  # Monday
            {"day_of_week": 1, "open_time": "09:00", "close_time": "19:00", "is_closed": False},  # Tuesday
            {"day_of_week": 2, "open_time": "09:00", "close_time": "19:00", "is_closed": False},  # Wednesday
            {"day_of_week": 3, "open_time": "09:00", "close_time": "19:00", "is_closed": False},  # Thursday
            {"day_of_week": 4, "open_time": "09:00", "close_time": "19:00", "is_closed": False},  # Friday
            {"day_of_week": 5, "open_time": "10:00", "close_time": "17:00", "is_closed": False},  # Saturday
            {"day_of_week": 6, "open_time": "10:00", "close_time": "17:00", "is_closed": False},
            # Sunday (by appointment)
        ]

        # Create business hours
        for hours_data in business_hours:
            hours = BusinessHours(
                business_id=business.id,
                **hours_data
            )
            db.add(hours)

        db.commit()

        print(f"\n✅ Created {len(business_hours)} business hours entries")
        print("\n" + "=" * 60)
        print("BUSINESS CREATED SUCCESSFULLY!")
        print("=" * 60)
        print(f"\nBusiness ID: {business.id}")
        print(f"Name: {business.name}")
        print(f"Type: {business.business_type}")
        print(f"Phone: {business.phone_number}")
        print(f"\nServices:")
        for service_name in business.service_catalog.keys():
            print(f"  - {service_name}")
        print(f"\nBusiness Hours:")
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for hours_data in business_hours:
            day_name = days[hours_data["day_of_week"]]
            if hours_data["is_closed"]:
                print(f"  {day_name}: CLOSED")
            else:
                print(f"  {day_name}: {hours_data['open_time']} - {hours_data['close_time']}")

        print("\n" + "=" * 60)
        print("NEXT STEP: Index the business knowledge")
        print("=" * 60)
        print(f"\nRun this command:")
        print(f"python index_business_knowledge.py {business.id}")
        print()

        return str(business.id)

    except Exception as e:
        db.rollback()
        print(f"\n❌ Error creating business: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    business_id = create_business_with_hours()