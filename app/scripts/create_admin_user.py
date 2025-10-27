#!/usr/bin/env python3
"""
Bootstrap script to create the first admin user and business.
Run this once to set up your initial admin account.

Usage:
    python scripts/create_admin_user.py
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.orm import Session
from app.config.database import SessionLocal, engine
from app.models.user import User, UserRole
from app.models.business import Business
from app.services.user_service import UserService
from app.services.invite_service import InviteService


def create_admin_user():
    """Create the first admin user and business."""
    db: Session = SessionLocal()

    try:
        print("=" * 80)
        print("🚀 Creating First Admin User")
        print("=" * 80)

        # Get admin details
        print("\nEnter admin user details:")
        email = input("Email: ").strip()
        password = input("Password (min 8 chars): ").strip()
        full_name = input("Full name: ").strip()

        print("\nEnter business details:")
        business_name = input("Business name: ").strip()
        phone_number = input("Business phone (e.g., +1234567890): ").strip()

        # Validate inputs
        if len(password) < 8:
            print("❌ Error: Password must be at least 8 characters")
            return

        if not email or not business_name or not phone_number:
            print("❌ Error: All fields are required")
            return

        # Check if user already exists
        existing_user = UserService.get_user_by_email(db, email)
        if existing_user:
            print(f"❌ Error: User with email {email} already exists")
            return

        print("\n" + "=" * 80)
        print("Creating admin user and business...")
        print("=" * 80)

        # Create business
        business = Business(
            name=business_name,
            phone_number=phone_number,
            is_active=True
        )
        db.add(business)
        db.commit()
        db.refresh(business)
        print(f"✅ Business created: {business.name} (ID: {business.id})")

        # Create admin user
        user = UserService.create_user(
            db=db,
            email=email,
            password=password,
            full_name=full_name
        )
        print(f"✅ User created: {user.email} (ID: {user.id})")

        # Add user to business as OWNER
        UserService.add_user_to_business(
            db=db,
            user_id=user.id,
            business_id=business.id,
            role=UserRole.OWNER
        )
        print(f"✅ User added to business as OWNER")

        # Set as active business
        user.active_business_id = business.id

        # Mark email as verified (skip verification for first admin)
        user.is_verified = True

        db.commit()

        # Create a starter invite for adding more users
        invite = InviteService.create_invite(
            db=db,
            business_id=business.id,
            created_by=user.id,
            role="member",
            email=None,  # Anyone can use it
            max_uses=10,
            expires_in_days=30
        )

        print("\n" + "=" * 80)
        print("🎉 SUCCESS! Admin user created")
        print("=" * 80)
        print(f"\n📧 Email: {user.email}")
        print(f"🔑 Password: {password}")
        print(f"🏢 Business: {business.name}")
        print(f"👤 Role: OWNER")
        print(f"✅ Email verified: Yes")

        print("\n" + "=" * 80)
        print("🎟️  Starter Invite Token (for adding team members)")
        print("=" * 80)
        print(f"\nToken: {invite.token}")
        print(f"Max uses: {invite.max_uses}")
        print(f"Expires: {invite.expires_at}")
        print(f"\nInvite URL: http://localhost:3000/register?invite={invite.token}")

        print("\n" + "=" * 80)
        print("🚀 Next Steps:")
        print("=" * 80)
        print("1. Go to http://localhost:8000/docs")
        print("2. Try POST /api/v1/auth/login with your credentials")
        print("3. Use the access token to test protected endpoints")
        print("4. Share the invite URL with team members to join")
        print("\n✨ Happy coding!\n")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Error creating admin user: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


def reset_admin_user():
    """Delete all users and businesses (DANGER!)"""
    db: Session = SessionLocal()

    try:
        print("=" * 80)
        print("⚠️  WARNING: This will delete ALL users and businesses!")
        print("=" * 80)
        confirm = input("\nType 'DELETE ALL' to confirm: ").strip()

        if confirm != "DELETE ALL":
            print("❌ Aborted")
            return

        # Delete all users (cascade will handle relationships)
        user_count = db.query(User).delete()
        business_count = db.query(Business).delete()
        db.commit()

        print(f"\n✅ Deleted {user_count} users")
        print(f"✅ Deleted {business_count} businesses")
        print("\nYou can now run the script again to create a new admin user.")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Error: {str(e)}")
    finally:
        db.close()


def main():
    """Main entry point."""
    print("\n🔐 Admin User Bootstrap Script")
    print("\nOptions:")
    print("1. Create first admin user")
    print("2. Reset all users and businesses (DANGER!)")
    print("3. Exit")

    choice = input("\nChoice [1]: ").strip() or "1"

    if choice == "1":
        create_admin_user()
    elif choice == "2":
        reset_admin_user()
    elif choice == "3":
        print("👋 Goodbye!")
    else:
        print("❌ Invalid choice")


if __name__ == "__main__":
    main()