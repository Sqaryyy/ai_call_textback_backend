# ============================================================================
# FILE: app/services/user_service.py
# User business logic - authentication, creation, business management
# ============================================================================
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime

# FIX: Changed UserRole to BusinessRole as per the user model
from app.models.user import User, BusinessRole, user_business_association
from app.models.business import Business


class UserService:
    """Service layer for user operations."""

    @staticmethod
    def create_user(
            db: Session,
            email: str,
            password: str,
            full_name: Optional[str] = None
    ) -> User:
        """
        Create a new user with hashed password.
        Raises ValueError if email already exists.
        """
        # Check if email already exists
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            raise ValueError("Email already registered")

        # Create new user
        user = User(
            email=email.lower().strip(),
            hashed_password=User.hash_password(password),
            full_name=full_name,
            is_active=True
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        return user

    @staticmethod
    def authenticate_user(
            db: Session,
            email: str,
            password: str
    ) -> Optional[User]:
        """
        Authenticate a user by email and password.
        Returns User if valid, None if invalid credentials.
        """
        user = db.query(User).filter(User.email == email.lower().strip()).first()

        if not user:
            return None

        if not user.is_active:
            return None

        if not user.verify_password(password):
            return None

        # Update last login timestamp
        user.last_login_at = datetime.utcnow()
        db.commit()

        return user

    @staticmethod
    def get_user_by_id(
            db: Session,
            user_id: UUID
    ) -> Optional[User]:
        """Get a user by their ID."""
        return db.query(User).filter(User.id == user_id).first()

    @staticmethod
    def get_user_by_email(
            db: Session,
            email: str
    ) -> Optional[User]:
        """Get a user by their email."""
        return db.query(User).filter(User.email == email.lower().strip()).first()

    @staticmethod
    def add_user_to_business(
            db: Session,
            user_id: UUID,
            business_id: UUID,
            # FIX: Use BusinessRole instead of UserRole
            role: BusinessRole = BusinessRole.MEMBER
    ) -> bool:
        """
        Add a user to a business with a specific role.
        Returns True if successful, False if already exists.
        """
        # Check if relationship already exists
        existing = db.execute(
            select(user_business_association).where(
                user_business_association.c.user_id == user_id,
                user_business_association.c.business_id == business_id
            )
        ).first()

        if existing:
            return False

        # Insert new relationship
        db.execute(
            user_business_association.insert().values(
                user_id=user_id,
                business_id=business_id,
                # FIX: Use BusinessRole for the role value
                role=role
            )
        )

        # Set as active business if user has no active business
        user = db.query(User).filter(User.id == user_id).first()
        if user and not user.active_business_id:
            user.active_business_id = business_id

        db.commit()
        return True

    @staticmethod
    def remove_user_from_business(
            db: Session,
            user_id: UUID,
            business_id: UUID
    ) -> bool:
        """
        Remove a user from a business.
        Returns True if successful, False if relationship didn't exist.
        """
        result = db.execute(
            user_business_association.delete().where(
                user_business_association.c.user_id == user_id,
                user_business_association.c.business_id == business_id
            )
        )

        # If this was the active business, clear it
        user = db.query(User).filter(User.id == user_id).first()
        if user and user.active_business_id == business_id:
            user.active_business_id = None

            # Set another business as active if available
            if user.businesses:
                # Ensure there's a business to pick from and pick the first one's ID
                # This needs careful consideration if 'first' is always desired logic.
                # A more robust solution might involve user input or a more complex default rule.
                if user.businesses:
                    user.active_business_id = user.businesses[0].id

        db.commit()
        return result.rowcount > 0

    @staticmethod
    def get_user_role_in_business(
            db: Session,
            user_id: UUID,
            business_id: UUID
            # FIX: Use BusinessRole for return type
    ) -> Optional[BusinessRole]:
        """Get the user's role in a specific business."""
        result = db.execute(
            select(user_business_association.c.role).where(
                user_business_association.c.user_id == user_id,
                user_business_association.c.business_id == business_id
            )
        ).first()

        # The result from SQLEnum will be an enum member, e.g., BusinessRole.MEMBER
        return result[0] if result else None

    @staticmethod
    def update_user_role_in_business(
            db: Session,
            user_id: UUID,
            business_id: UUID,
            # FIX: Use BusinessRole for new_role
            new_role: BusinessRole
    ) -> bool:
        """Update a user's role in a business."""
        result = db.execute(
            user_business_association.update()
            .where(
                user_business_association.c.user_id == user_id,
                user_business_association.c.business_id == business_id
            )
            # FIX: Ensure new_role is of BusinessRole type
            .values(role=new_role)
        )

        db.commit()
        return result.rowcount > 0

    @staticmethod
    def set_active_business(
            db: Session,
            user_id: UUID,
            business_id: UUID
    ) -> bool:
        """
        Set a business as the user's active business.
        Returns True if successful, False if user doesn't belong to that business.
        """
        # Verify user belongs to this business
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False

        # Check if user has access to this business
        # Using a direct query on the association table for efficiency
        has_access_stmt = select(user_business_association).where(
            user_business_association.c.user_id == user_id,
            user_business_association.c.business_id == business_id
        )
        has_access = db.execute(has_access_stmt).first() is not None

        if not has_access:
            return False

        user.active_business_id = business_id
        db.commit()
        return True

    @staticmethod
    def get_user_businesses(
            db: Session,
            user_id: UUID
    ) -> List[Dict[str, Any]]:
        """
        Get all businesses a user belongs to with their roles.
        """
        results = db.execute(
            select(
                Business,
                user_business_association.c.role
            ).join(
                user_business_association,
                Business.id == user_business_association.c.business_id
            ).where(
                user_business_association.c.user_id == user_id
            )
        ).all()

        return [
            {
                "business_id": str(business.id),
                "business_name": business.name,
                "business_phone": business.phone_number,
                # `role` here is already a BusinessRole enum member, so .value extracts the string
                "role": role.value,
                "created_at": business.created_at.isoformat()
            }
            for business, role in results
        ]

    @staticmethod
    def update_user_profile(
            db: Session,
            user_id: UUID,
            full_name: Optional[str] = None,
            email: Optional[str] = None
    ) -> Optional[User]:
        """Update user profile information."""
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            return None

        if full_name is not None:
            user.full_name = full_name

        if email is not None:
            # Check if new email is already taken
            existing = db.query(User).filter(
                User.email == email.lower().strip(),
                User.id != user_id
            ).first()

            if existing:
                raise ValueError("Email already in use")

            user.email = email.lower().strip()

        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def change_password(
            db: Session,
            user_id: UUID,
            old_password: str,
            new_password: str
    ) -> bool:
        """
        Change a user's password.
        Returns True if successful, False if old password is incorrect.
        """
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            return False

        if not user.verify_password(old_password):
            return False

        user.hashed_password = User.hash_password(new_password)
        db.commit()
        return True

    @staticmethod
    def deactivate_user(
            db: Session,
            user_id: UUID
    ) -> bool:
        """Deactivate a user account."""
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            return False

        user.is_active = False
        db.commit()
        return True

    @staticmethod
    def reactivate_user(
            db: Session,
            user_id: UUID
    ) -> bool:
        """Reactivate a user account."""
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            return False

        user.is_active = True
        db.commit()
        return True