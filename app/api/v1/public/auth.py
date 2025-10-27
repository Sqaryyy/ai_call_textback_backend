# ============================================================================
# FILE: app/api/v1/auth.py
# Public authentication endpoints - login, register, verify, password reset
# ============================================================================
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field
from typing import Optional

from app.tasks.email_tasks import (
    send_verification_email,
    send_password_reset_email,
)

from app.api.dependencies import (
    get_db,
    get_current_user,
    get_current_active_user,
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
    revoke_refresh_token,
    revoke_all_user_tokens
)
from app.services.user.user_service import UserService
from app.services.invite.invite_service import InviteService
from app.services.invite.platform_invite_service import PlatformInviteService
from app.services.invite.business_invite_service import BusinessInviteService
from app.models.user import User, BusinessRole
from app.models.invite import InviteType
from app.models.email_verification import EmailVerification
from app.models.password_reset import PasswordReset

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ============================================================================
# Pydantic Schemas
# ============================================================================

class RegisterRequest(BaseModel):
    """Request body for user registration."""
    email: EmailStr
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters")
    full_name: Optional[str] = None
    invite_token: str = Field(..., description="Invite token required for registration")

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "password": "SecurePass123!",
                "full_name": "John Doe",
                "invite_token": "abc123xyz789"
            }
        }


class LoginRequest(BaseModel):
    """Request body for login."""
    email: EmailStr
    password: str

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "password": "SecurePass123!"
            }
        }


class TokenResponse(BaseModel):
    """Response with access and refresh tokens."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    full_name: Optional[str] = None
    active_business_id: Optional[str] = None
    is_verified: bool = False

    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "def456ghi789jkl012mno345pqr678stu901vwx234...",
                "token_type": "bearer",
                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                "email": "user@example.com",
                "full_name": "John Doe",
                "active_business_id": "660e8400-e29b-41d4-a716-446655440001",
                "is_verified": True
            }
        }


class RefreshTokenRequest(BaseModel):
    """Request body for refreshing access token."""
    refresh_token: str


class VerifyEmailRequest(BaseModel):
    """Request body for email verification."""
    token: str


class ForgotPasswordRequest(BaseModel):
    """Request body for forgot password."""
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Request body for password reset."""
    token: str
    new_password: str = Field(..., min_length=8)


class ChangePasswordRequest(BaseModel):
    """Request body for changing password."""
    old_password: str
    new_password: str = Field(..., min_length=8)


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    details: Optional[dict] = None


class InviteValidationResponse(BaseModel):
    """Response for invite validation."""
    valid: bool
    message: str
    invite_type: Optional[str] = None
    business_name: Optional[str] = None
    role: Optional[str] = None


# ============================================================================
# Registration & Login Endpoints
# ============================================================================

@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def register(
        request: RegisterRequest,
        db: Session = Depends(get_db)
):
    """
    Register a new user with an invite token.

    Supports two types of invites:
    - Platform invites: Creates a new business owner (no business assignment yet)
    - Business invites: Adds user to a specific business as owner/member

    The user will receive an email verification link and must verify their email
    before they can fully access the system.
    """
    # Validate the invite token (auto-detects type)
    is_valid, error_msg, invite = InviteService.validate_invite(
        db,
        request.invite_token,
        request.email
    )

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg or "Invalid invite token"
        )

    if not invite:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invite not found"
        )

    try:
        # Check if user with this email already exists
        existing_user = UserService.get_user_by_email(db, request.email)

        # Handle based on invite type
        if invite.invite_type == InviteType.PLATFORM:
            # ============================================================
            # PLATFORM INVITE: Create new business owner
            # ============================================================
            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User with this email already exists. Platform invites are for new users only."
                )

            # Create the user with platform role = USER
            user = UserService.create_user(
                db=db,
                email=request.email,
                password=request.password,
                full_name=request.full_name
            )

            # Mark the platform invite as used
            PlatformInviteService.use_platform_invite(db, invite.id)

            # Create email verification token
            verification = EmailVerification.create_for_user(user.id, expiry_hours=24)
            db.add(verification)
            db.commit()
            db.refresh(verification)

            print(f"DEBUG: About to send email to {user.email} with token {verification.token}")

            # Send verification email via Celery
            task = send_verification_email.delay(
                email=user.email,
                token=verification.token,
                user_name=user.full_name
            )

            print(f"DEBUG: Task ID: {task.id}")

            return MessageResponse(
                message="Registration successful! You can now create your first business. Please check your email to verify your account.",
                details={
                    "email": user.email,
                    "user_id": str(user.id),
                    "verification_required": True,
                    "invite_type": "platform",
                    "next_step": "create_business"
                }
            )

        else:
            # ============================================================
            # BUSINESS INVITE: Add user to business
            # ============================================================
            if not invite.business_id:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Business invite is missing business_id"
                )

            # If user doesn't exist, create them
            if not existing_user:
                user = UserService.create_user(
                    db=db,
                    email=request.email,
                    password=request.password,
                    full_name=request.full_name
                )
            else:
                # User exists, check if they already belong to this business
                existing_role = UserService.get_user_role_in_business(
                    db=db,
                    user_id=existing_user.id,
                    business_id=invite.business_id
                )

                if existing_role:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="User is already a member of this business"
                    )

                user = existing_user

            # Add user to the business from the invite
            role_map = {
                "owner": BusinessRole.OWNER,
                "member": BusinessRole.MEMBER
            }
            business_role = role_map.get(invite.role, BusinessRole.MEMBER)

            UserService.add_user_to_business(
                db=db,
                user_id=user.id,
                business_id=invite.business_id,
                role=business_role
            )

            # Mark the business invite as used
            BusinessInviteService.use_business_invite(db, invite.id)

            # Only create verification for new users
            if not existing_user:
                verification = EmailVerification.create_for_user(user.id, expiry_hours=24)
                db.add(verification)
                db.commit()
                db.refresh(verification)

                # Send verification email via Celery
                send_verification_email.delay(
                    email=user.email,
                    token=verification.token,
                    user_name=user.full_name
                )

            # Get business name for response
            from app.models.business import Business
            business = db.query(Business).filter(Business.id == invite.business_id).first()

            return MessageResponse(
                message=f"Registration successful! You've been added to {business.name if business else 'the business'}. Please check your email to verify your account." if not existing_user else f"Successfully joined {business.name if business else 'the business'}!",
                details={
                    "email": user.email,
                    "user_id": str(user.id),
                    "business_id": str(invite.business_id),
                    "business_name": business.name if business else None,
                    "role": invite.role,
                    "verification_required": not existing_user,
                    "invite_type": "business",
                    "is_new_user": not existing_user
                }
            )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )


@router.post("/login", response_model=TokenResponse)
async def login(
        request: LoginRequest,
        db: Session = Depends(get_db)
):
    """
    Login with email and password.

    Returns access and refresh tokens. Users can login even without email verification,
    but some features may be restricted until verification is complete.
    """
    user = UserService.authenticate_user(
        db=db,
        email=request.email,
        password=request.password
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Generate tokens
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )

    refresh_token_obj = create_refresh_token(db, user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token_obj.token,
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        active_business_id=str(user.active_business_id) if user.active_business_id else None,
        is_verified=user.is_verified
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_access_token(
        request: RefreshTokenRequest,
        db: Session = Depends(get_db)
):
    """
    Refresh an access token using a refresh token.

    The refresh token must be valid and not revoked. Returns a new access token
    and the same refresh token (refresh tokens are long-lived).
    """
    # Verify refresh token
    refresh_token = verify_refresh_token(db, request.refresh_token)

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user
    user = db.query(User).filter(User.id == refresh_token.user_id).first()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Update last used timestamp
    refresh_token.update_last_used()
    db.commit()

    # Generate new access token
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token.token,
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        active_business_id=str(user.active_business_id) if user.active_business_id else None,
        is_verified=user.is_verified
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
        request: RefreshTokenRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Logout by revoking the refresh token.

    This invalidates the refresh token, preventing new access tokens from being generated.
    The current access token will still work until it expires.
    """
    success = revoke_refresh_token(db, request.refresh_token)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Refresh token not found"
        )

    return MessageResponse(
        message="Successfully logged out"
    )


@router.post("/logout-all", response_model=MessageResponse)
async def logout_all_devices(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_active_user)
):
    """
    Logout from all devices by revoking all refresh tokens for the user.

    This is useful for security purposes if you suspect your account has been compromised.
    """
    count = revoke_all_user_tokens(db, current_user.id)

    return MessageResponse(
        message=f"Successfully logged out from all devices",
        details={"tokens_revoked": count}
    )


# ============================================================================
# Email Verification Endpoints
# ============================================================================

@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
        request: VerifyEmailRequest,
        db: Session = Depends(get_db)
):
    """
    Verify user's email address using the verification token sent via email.
    """
    # Find verification token
    verification = db.query(EmailVerification).filter(
        EmailVerification.token == request.token
    ).first()

    if not verification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid verification token"
        )

    if not verification.is_valid():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification token has expired or already been used"
        )

    # Mark as verified
    verification.mark_as_used()

    # Update user
    user = verification.user
    user.is_verified = True

    db.commit()

    return MessageResponse(
        message="Email verified successfully! You can now access all features.",
        details={
            "email": user.email,
            "verified_at": verification.verified_at.isoformat()
        }
    )


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification_email(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Resend email verification link to the current user.

    Can only be used if the user is not already verified.
    """
    if current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already verified"
        )

    # Invalidate any existing verification tokens
    db.query(EmailVerification).filter(
        EmailVerification.user_id == current_user.id,
        EmailVerification.is_used == False
    ).update({"is_used": True})

    # Create new verification token
    verification = EmailVerification.create_for_user(current_user.id, expiry_hours=24)
    db.add(verification)
    db.commit()
    db.refresh(verification)

    # Send verification email via Celery
    send_verification_email.delay(
        email=current_user.email,
        token=verification.token,
        user_name=current_user.full_name
    )

    return MessageResponse(
        message="Verification email sent! Please check your inbox.",
        details={"email": current_user.email}
    )


# ============================================================================
# Password Reset Endpoints
# ============================================================================

@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
        request: ForgotPasswordRequest,
        db: Session = Depends(get_db)
):
    """
    Request a password reset link.

    Sends an email with a password reset token. Always returns success
    to prevent email enumeration attacks.
    """
    # Find user (but don't reveal if they exist)
    user = UserService.get_user_by_email(db, request.email)

    if user and user.is_active:
        # Invalidate any existing password reset tokens
        db.query(PasswordReset).filter(
            PasswordReset.user_id == user.id,
            PasswordReset.is_used == False
        ).update({"is_used": True})

        # Create password reset token (1 hour expiry for security)
        reset_token = PasswordReset.create_for_user(user.id, expiry_hours=1)
        db.add(reset_token)
        db.commit()
        db.refresh(reset_token)

        # Send password reset email via Celery
        send_password_reset_email.delay(
            email=user.email,
            token=reset_token.token,
            user_name=user.full_name
        )

    # Always return success to prevent email enumeration
    return MessageResponse(
        message="If an account exists with that email, a password reset link has been sent."
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
        request: ResetPasswordRequest,
        db: Session = Depends(get_db)
):
    """
    Reset password using the token sent via email.
    """
    # Find reset token
    reset_token = db.query(PasswordReset).filter(
        PasswordReset.token == request.token
    ).first()

    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired reset token"
        )

    if not reset_token.is_valid():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has expired or already been used"
        )

    # Update password
    user = reset_token.user
    user.hashed_password = User.hash_password(request.new_password)

    # Mark token as used
    reset_token.mark_as_used()

    # Revoke all refresh tokens for security
    revoke_all_user_tokens(db, user.id)

    db.commit()

    return MessageResponse(
        message="Password reset successful! Please login with your new password.",
        details={"email": user.email}
    )


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
        request: ChangePasswordRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_active_user)
):
    """
    Change password for the currently logged-in user.

    Requires the old password for verification.
    """
    success = UserService.change_password(
        db=db,
        user_id=current_user.id,
        old_password=request.old_password,
        new_password=request.new_password
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect old password"
        )

    # Revoke all refresh tokens except current session for security
    # (User will need to re-login on other devices)
    revoke_all_user_tokens(db, current_user.id)

    return MessageResponse(
        message="Password changed successfully! Please login again on other devices."
    )


# ============================================================================
# Utility Endpoints
# ============================================================================

@router.get("/validate-invite", response_model=InviteValidationResponse)
async def validate_invite(
        token: str,
        email: Optional[str] = None,
        db: Session = Depends(get_db)
):
    """
    Validate an invite token before registration.

    This endpoint can be used by the frontend to check if an invite is valid
    and show appropriate information to the user.
    """
    is_valid, error_msg, invite = InviteService.validate_invite(db, token, email)

    if not is_valid or not invite:
        return InviteValidationResponse(
            valid=False,
            message=error_msg or "Invalid invite"
        )

    # Handle based on invite type
    if invite.invite_type == InviteType.PLATFORM:
        return InviteValidationResponse(
            valid=True,
            message="Valid platform invite - you'll be able to create your own business",
            invite_type="platform",
            business_name=None,
            role="owner"
        )
    else:
        # Get business info for business invites
        from app.models.business import Business
        business = db.query(Business).filter(Business.id == invite.business_id).first()

        return InviteValidationResponse(
            valid=True,
            message=f"Valid business invite - you'll join {business.name if business else 'a business'}",
            invite_type="business",
            business_name=business.name if business else None,
            role=invite.role
        )


@router.get("/me", response_model=TokenResponse)
async def get_current_user_info(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Get current user information from the JWT token.

    Useful for the frontend to check authentication status and get user details.
    """
    return TokenResponse(
        access_token="",  # Don't send token back
        refresh_token="",  # Don't send token back
        user_id=str(current_user.id),
        email=current_user.email,
        full_name=current_user.full_name,
        active_business_id=str(current_user.active_business_id) if current_user.active_business_id else None,
        is_verified=current_user.is_verified
    )