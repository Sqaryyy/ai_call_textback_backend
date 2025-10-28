# ============================================================================
# FILE: app/models/user.py
# UPDATED: Added platform role (admin/user) separate from business roles
# ============================================================================
from sqlalchemy import Column, String, Boolean, DateTime, Table, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from passlib.context import CryptContext
import uuid
import enum
from app.models.base import Base

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class PlatformRole(str, enum.Enum):
    """Platform-level user roles."""
    ADMIN = "admin"    # Platform admin - can create platform invites
    USER = "user"      # Regular user - can own/join businesses


class BusinessRole(str, enum.Enum):
    """User roles within a business."""
    OWNER = "owner"
    MEMBER = "member"


# Association table for many-to-many User <-> Business relationship with roles
user_business_association = Table(
    'user_businesses',
    Base.metadata,
    Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column('user_id', UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
    Column('business_id', UUID(as_uuid=True), ForeignKey('businesses.id', ondelete='CASCADE'), nullable=False),
    Column('role', SQLEnum(BusinessRole), default=BusinessRole.MEMBER, nullable=False),
    Column('created_at', DateTime(timezone=True), server_default=func.now())
)


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)

    # Platform role - admin or user
    role = Column(
        SQLEnum(PlatformRole),
        default=PlatformRole.USER,
        nullable=False,
        index=True
    )

    # Currently active business for this user (for dashboard context)
    active_business_id = Column(UUID(as_uuid=True), ForeignKey('businesses.id'), nullable=True)

    # Status flags
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    businesses = relationship(
        "Business",
        secondary=user_business_association,
        backref="users",
        lazy="selectin"
    )
    active_business = relationship("Business", foreign_keys=[active_business_id], lazy="joined")

    def verify_password(self, plain_password: str) -> bool:
        """Verify a plain password against the hashed password."""
        return pwd_context.verify(plain_password, self.hashed_password)

    @staticmethod
    def hash_password(plain_password: str) -> str:
        """Hash a plain password."""
        return pwd_context.hash(plain_password)

    def is_platform_admin(self) -> bool:
        """Check if user is a platform admin."""
        return self.role == PlatformRole.ADMIN

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"