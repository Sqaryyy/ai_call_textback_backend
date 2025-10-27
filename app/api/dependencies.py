# ============================================================================
# FILE: app/api/dependencies.py
# Authentication dependencies for API keys and JWT tokens
# ============================================================================
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
import time
from uuid import UUID

from app.config.database import get_db
from app.config.settings import settings
from app.services.api_key.api_key_service import APIKeyService
from app.models.api_key import APIKey
from app.models.user import User, PlatformRole, BusinessRole
from app.models.refresh_token import RefreshToken

from app.services.user.user_service import UserService

# ============================================================================
# Security Schemes
# ============================================================================

# API Key security (existing)
api_key_security = HTTPBearer(
    scheme_name="API Key Authentication",
    description="Enter your API key in the format: mctb_live_xxxxx or mctb_test_xxxxx"
)

# JWT security for user authentication
jwt_security = HTTPBearer(
    scheme_name="JWT Bearer Token",
    description="Enter your JWT access token"
)


# ============================================================================
# JWT Token Functions
# ============================================================================

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.

    Args:
        data: Dictionary with claims (should include 'sub' with user_id)
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access"
    })

    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )

    return encoded_jwt


def create_refresh_token(db: Session, user_id: UUID) -> RefreshToken:
    """
    Create and store a refresh token in the database.

    Args:
        db: Database session
        user_id: User ID to create token for

    Returns:
        RefreshToken model instance with generated token
    """
    token_string = RefreshToken.generate_token()

    expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )

    refresh_token = RefreshToken(
        token=token_string,
        user_id=user_id,
        expires_at=expires_at,
        is_revoked=False
    )

    db.add(refresh_token)
    db.commit()
    db.refresh(refresh_token)

    return refresh_token


def verify_access_token(token: str) -> dict:
    """
    Verify and decode a JWT access token.

    Args:
        token: JWT token string

    Returns:
        Decoded token payload

    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )

        # Verify token type
        token_type = payload.get("type")
        if token_type != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return payload

    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def verify_refresh_token(db: Session, token: str) -> Optional[RefreshToken]:
    """
    Verify a refresh token from the database.

    Args:
        db: Database session
        token: Refresh token string

    Returns:
        RefreshToken model if valid, None otherwise
    """
    refresh_token = db.query(RefreshToken).filter(
        RefreshToken.token == token
    ).first()

    if not refresh_token:
        return None

    if not refresh_token.is_valid():
        return None

    return refresh_token


def revoke_refresh_token(db: Session, token: str) -> bool:
    """
    Revoke a refresh token.

    Args:
        db: Database session
        token: Refresh token string

    Returns:
        True if revoked, False if not found
    """
    refresh_token = db.query(RefreshToken).filter(
        RefreshToken.token == token
    ).first()

    if not refresh_token:
        return False

    refresh_token.revoke()
    db.commit()

    return True


def revoke_all_user_tokens(db: Session, user_id: UUID) -> int:
    """
    Revoke all refresh tokens for a user (logout from all devices).

    Args:
        db: Database session
        user_id: User ID

    Returns:
        Number of tokens revoked
    """
    count = db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.is_revoked == False
    ).update({"is_revoked": True})

    db.commit()

    return count


# ============================================================================
# JWT Authentication Dependencies
# ============================================================================

async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(jwt_security),
        db: Session = Depends(get_db)
) -> User:
    """
    Dependency to get the current authenticated user from JWT access token.

    Usage in routes:
        @router.get("/profile")
        async def get_profile(current_user: User = Depends(get_current_user)):
            return {"email": current_user.email}

    Raises:
        HTTPException 401: If token is invalid or user not found
    """
    token = credentials.credentials

    # Verify and decode token
    payload = verify_access_token(token)

    # Extract user ID from token
    user_id_str: Optional[str] = payload.get("sub")
    if user_id_str is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Convert to UUID
    try:
        user_id = UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID in token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user from database
    user = db.query(User).filter(User.id == user_id).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_active_user(
        current_user: User = Depends(get_current_user)
) -> User:
    """
    Dependency to ensure the current user is active.

    Usage in routes:
        @router.get("/dashboard")
        async def dashboard(user: User = Depends(get_current_active_user)):
            # User is guaranteed to be active
            pass
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account"
        )

    return current_user


async def optional_current_user(
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(
            HTTPBearer(auto_error=False)
        ),
        db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Optional JWT authentication dependency.
    Returns User if valid token provided, None otherwise.

    Useful for endpoints that work differently with/without auth.
    """
    if not credentials:
        return None

    try:
        token = credentials.credentials
        payload = verify_access_token(token)
        user_id_str = payload.get("sub")

        if user_id_str:
            user_id = UUID(user_id_str)
            user = db.query(User).filter(User.id == user_id).first()
            return user
    except:
        return None

    return None


# ============================================================================
# Platform-Level Role Dependencies (NEW)
# ============================================================================

async def require_platform_admin(
        current_user: User = Depends(get_current_active_user)
) -> User:
    """
    Dependency that requires user to be a platform admin.
    Used for platform management routes (creating platform invites, etc.)

    Usage in routes:
        @router.post("/admin/invites")
        async def create_platform_invite(user: User = Depends(require_platform_admin)):
            # User is guaranteed to be platform admin
            pass
    """
    if not current_user.is_platform_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin access required"
        )

    return current_user


# ============================================================================
# Business-Level Role Dependencies (UPDATED)
# ============================================================================

async def require_business_owner(
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
) -> User:
    """
    Dependency that requires user to be an owner of the active business.
    Used for business management routes (creating business invites, settings, etc.)

    Usage in routes:
        @router.post("/business/{business_id}/invites")
        async def create_business_invite(user: User = Depends(require_business_owner)):
            # User is guaranteed to be owner of active business
            pass
    """
    if not current_user.active_business_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active business selected"
        )

    role = UserService.get_user_role_in_business(
        db=db,
        user_id=current_user.id,
        business_id=current_user.active_business_id
    )

    if role != BusinessRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Business owner access required"
        )

    return current_user


def require_business_owner_for_business(business_id: UUID):
    """
    Dependency factory that requires user to be an owner of a SPECIFIC business.
    Used when business_id is in the path parameter.

    Usage in routes:
        @router.post("/business/{business_id}/invites")
        async def create_invite(
            business_id: UUID,
            user: User = Depends(require_business_owner_for_business(business_id))
        ):
            pass
    """
    async def _check_owner(
            current_user: User = Depends(get_current_active_user),
            db: Session = Depends(get_db)
    ) -> User:
        role = UserService.get_user_role_in_business(
            db=db,
            user_id=current_user.id,
            business_id=business_id
        )

        if role != BusinessRole.OWNER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Business owner access required for this business"
            )

        return current_user

    return _check_owner


async def require_business_member(
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
) -> User:
    """
    Dependency that requires user to be at least a member of the active business.
    (Owner or Member - any role works)

    Usage in routes:
        @router.get("/business/dashboard")
        async def dashboard(user: User = Depends(require_business_member)):
            # User is guaranteed to be member or owner
            pass
    """
    if not current_user.active_business_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active business selected"
        )

    role = UserService.get_user_role_in_business(
        db=db,
        user_id=current_user.id,
        business_id=current_user.active_business_id
    )

    if role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this business"
        )

    return current_user


# ============================================================================
# DEPRECATED - Keep for backwards compatibility
# ============================================================================

async def require_admin(
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
) -> User:
    """
    DEPRECATED: Use require_business_owner instead.
    Kept for backwards compatibility.
    """
    return await require_business_owner(current_user, db)


async def require_owner(
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
) -> User:
    """
    DEPRECATED: Use require_business_owner instead.
    Kept for backwards compatibility.
    """
    return await require_business_owner(current_user, db)


# ============================================================================
# API Key Dependencies (Existing - Kept for compatibility)
# ============================================================================

async def get_api_key_service(db: AsyncSession = Depends(get_db)) -> APIKeyService:
    """Dependency to get APIKeyService instance."""
    return APIKeyService(db)


async def require_api_key(
        request: Request,
        credentials: HTTPAuthorizationCredentials = Depends(api_key_security),
        service: APIKeyService = Depends(get_api_key_service)
) -> APIKey:
    """
    Dependency that requires a valid API key.
    Validates the key and returns the APIKey model.
    """
    start_time = time.time()
    token = credentials.credentials

    api_key = await service.validate_key(token, check_rate_limit=True)

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    request.state.api_key = api_key
    request.state.start_time = start_time

    return api_key


def require_scope(required_scope: str):
    """Dependency factory that creates a scope-checking dependency."""

    async def scope_checker(
            api_key: APIKey = Depends(require_api_key),
            service: APIKeyService = Depends(get_api_key_service)
    ):
        if not service.check_scope(api_key, required_scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required scope: {required_scope}"
            )
        return None

    return scope_checker


async def optional_api_key(
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(
            HTTPBearer(auto_error=False)
        ),
        service: APIKeyService = Depends(get_api_key_service)
) -> Optional[APIKey]:
    """Optional API key dependency."""
    if not credentials:
        return None

    start_time = time.time()
    token = credentials.credentials

    api_key = await service.validate_key(token, check_rate_limit=True)

    if api_key:
        request.state.api_key = api_key
        request.state.start_time = start_time

    return api_key