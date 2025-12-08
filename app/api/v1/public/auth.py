# ============================================================================
# FILE: app/api/v1/auth.py
# Public authentication endpoints - login, register, verify, password reset
# MODIFIED: Now uses httpOnly cookies instead of returning tokens in response
# ============================================================================
import uuid

from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
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
from app.models.auth.user import User, BusinessRole
from app.models.invite import InviteType
from app.models.auth.email_verification import EmailVerification
from app.models.auth.password_reset import PasswordReset
from app.models.auth.user import user_business_association
from app.services.business.business_service import BusinessService

router = APIRouter(prefix="/auth", tags=["Authentication"])

# ============================================================================
# Cookie Configuration
# ============================================================================
COOKIE_CONFIG = {
    "httponly": True,  # Prevent JavaScript access
    "secure": True,  # Only send over HTTPS (set to False in development)
    "samesite": "lax",  # CSRF protection
    "max_age": 60 * 60 * 24 * 30,  # 30 days for refresh token
}

ACCESS_TOKEN_COOKIE = "access_token"
REFRESH_TOKEN_COOKIE = "refresh_token"


# ============================================================================
# Helper Functions
# ============================================================================

def set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    """Set authentication cookies on the response."""
    # Access token - shorter expiry (15 minutes)
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=access_token,
        httponly=True,
        secure=COOKIE_CONFIG["secure"],
        samesite=COOKIE_CONFIG["samesite"],
        max_age=60 * 15,  # 15 minutes
    )

    # Refresh token - longer expiry (30 days)
    response.set_cookie(
        key=REFRESH_TOKEN_COOKIE,
        value=refresh_token,
        httponly=True,
        secure=COOKIE_CONFIG["secure"],
        samesite=COOKIE_CONFIG["samesite"],
        max_age=COOKIE_CONFIG["max_age"],
    )


def clear_auth_cookies(response: Response):
    """Clear authentication cookies."""
    response.delete_cookie(
        key=ACCESS_TOKEN_COOKIE,
        httponly=True,
        secure=COOKIE_CONFIG["secure"],
        samesite=COOKIE_CONFIG["samesite"],
    )
    response.delete_cookie(
        key=REFRESH_TOKEN_COOKIE,
        httponly=True,
        secure=COOKIE_CONFIG["secure"],
        samesite=COOKIE_CONFIG["samesite"],
    )


# ============================================================================
# Pydantic Schemas
# ============================================================================

class RegisterRequest(BaseModel):
    """Request body for user registration."""
    email: EmailStr
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters")
    full_name: Optional[str] = None
    invite_token: str = Field(..., description="Invite token required for registration")


class LoginRequest(BaseModel):
    """Request body for login."""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Response after successful authentication - NO TOKENS in body anymore."""
    user_id: str
    email: str
    full_name: Optional[str] = None
    active_business_id: Optional[str] = None
    is_verified: bool = False


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
        response: Response,
        db: Session = Depends(get_db)
):
    """
    Register a new user with an invite token.
    Sets httpOnly cookies for authentication.
    """
    print("\n" + "=" * 80)
    print("=== REGISTRATION START ===")
    print(f"Email: {request.email}")
    print(f"Invite token: {request.invite_token[:20]}...")

    # Validate the invite token (auto-detects type)
    is_valid, error_msg, invite = InviteService.validate_invite(
        db,
        request.invite_token,
        request.email
    )

    if not is_valid:
        print(f"ERROR: Invite validation failed: {error_msg}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg or "Invalid invite token"
        )

    if not invite:
        print("ERROR: Invite not found after validation")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invite not found"
        )

    print(f"\n✓ Invite validated successfully")
    print(f"  - Invite ID: {invite.id}")
    print(f"  - Invite type: {invite.invite_type}")
    print(f"  - Invite role: {invite.role}")
    print(f"  - Invite role type: {type(invite.role)}")
    print(f"  - Invite role repr: {repr(invite.role)}")

    try:
        # Check if user with this email already exists
        existing_user = UserService.get_user_by_email(db, request.email)
        print(f"\nExisting user check: {'Found' if existing_user else 'Not found'}")

        # Handle based on invite type
        if invite.invite_type == InviteType.PLATFORM:
            print("\n" + "=" * 80)
            print("=== PLATFORM INVITE FLOW ===")
            print("=" * 80)

            if existing_user:
                print("ERROR: User already exists for platform invite")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User with this email already exists. Platform invites are for new users only."
                )

            # Create the user
            print("\n[1] Creating new user...")
            user = UserService.create_user(
                db=db,
                email=request.email,
                password=request.password,
                full_name=request.full_name
            )
            print(f"  ✓ User created")
            print(f"    - ID: {user.id}")
            print(f"    - Email: {user.email}")
            print(f"    - Name: {user.full_name}")

            # AUTO-CREATE DEFAULT BUSINESS FOR NEW USER
            print("\n[2] Creating default business...")
            default_business = BusinessService.create_default_business(db, user.id)
            print(f"  ✓ Business created")
            print(f"    - ID: {default_business.id}")
            print(f"    - Name: {default_business.name}")

            user.active_business_id = default_business.id
            db.flush()
            print(f"  ✓ Set active_business_id to {default_business.id}")

            # Link user to business
            print("\n[3] Linking user to business")
            print("=" * 80)
            association_id = uuid.uuid4()
            print(f"  - association_id: {association_id} (type: {type(association_id)})")
            print(f"  - user_id: {user.id} (type: {type(user.id)})")
            print(f"  - business_id: {default_business.id} (type: {type(default_business.id)})")
            print(f"  - role: 'owner' (hardcoded string)")

            stmt = user_business_association.insert().values(
                id=association_id,
                user_id=user.id,
                business_id=default_business.id,
                role="owner"
            )

            print(f"\n  Executing INSERT statement...")
            print(f"  Statement object: {stmt}")
            print(f"  Statement compile: {stmt.compile(compile_kwargs={'literal_binds': True})}")

            try:
                result = db.execute(stmt)
                print(f"  ✓ INSERT executed successfully")
                print(f"  Result: {result}")
            except Exception as insert_error:
                print("\n" + "!" * 80)
                print("!!! INSERT FAILED !!!")
                print("!" * 80)
                print(f"  Error type: {type(insert_error).__name__}")
                print(f"  Error message: {str(insert_error)}")
                print(f"  Error args: {insert_error.args}")
                if hasattr(insert_error, 'orig'):
                    print(f"  Original error: {insert_error.orig}")
                print("!" * 80)
                raise

            # Mark the platform invite as used
            print("\n[4] Marking platform invite as used...")
            PlatformInviteService.use_platform_invite(db, invite.id)
            print("  ✓ Invite marked as used")

            # Create email verification token
            print("\n[5] Creating email verification token...")
            verification = EmailVerification.create_for_user(user.id, expiry_hours=24)
            db.add(verification)
            db.commit()
            db.refresh(verification)
            print(f"  ✓ Verification token created: {verification.token[:20]}...")

            # Send verification email via Celery
            print("\n[6] Sending verification email...")
            send_verification_email.delay(
                email=user.email,
                token=verification.token,
                user_name=user.full_name
            )
            print("  ✓ Email task queued")

            # Generate tokens and set cookies
            print("\n[7] Generating auth tokens...")
            access_token = create_access_token(
                data={"sub": str(user.id), "email": user.email}
            )
            refresh_token_obj = create_refresh_token(db, user.id)
            set_auth_cookies(response, access_token, refresh_token_obj.token)
            print("  ✓ Tokens generated and cookies set")

            print("\n" + "=" * 80)
            print("=== REGISTRATION COMPLETE ===")
            print("=" * 80 + "\n")

            return MessageResponse(
                message="Registration successful! Your business has been created.",
                details={
                    "email": user.email,
                    "user_id": str(user.id),
                    "business_id": str(default_business.id),
                    "verification_required": True,
                    "invite_type": "platform",
                    "next_step": "business_info"
                }
            )
        else:
            print("\n" + "=" * 80)
            print("=== BUSINESS INVITE FLOW ===")
            print("=" * 80)

            # BUSINESS INVITE logic
            if not invite.business_id:
                print("ERROR: Business invite missing business_id")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Business invite is missing business_id"
                )

            print(f"Business ID from invite: {invite.business_id}")

            if not existing_user:
                print("\n[1] Creating new user...")
                user = UserService.create_user(
                    db=db,
                    email=request.email,
                    password=request.password,
                    full_name=request.full_name
                )
                print(f"  ✓ User created: {user.id}")
            else:
                print("\n[1] Using existing user...")
                existing_role = UserService.get_user_role_in_business(
                    db=db,
                    user_id=existing_user.id,
                    business_id=invite.business_id
                )

                if existing_role:
                    print(f"ERROR: User already member with role: {existing_role}")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="User is already a member of this business"
                    )
                user = existing_user
                print(f"  ✓ Existing user: {user.id}")

            business_role = invite.role
            print(f"\n[2] Adding user to business")
            print(f"  - user_id: {user.id}")
            print(f"  - business_id: {invite.business_id}")
            print(f"  - role from invite: {business_role}")
            print(f"  - role type: {type(business_role)}")
            print(f"  - role repr: {repr(business_role)}")

            try:
                UserService.add_user_to_business(
                    db=db,
                    user_id=user.id,
                    business_id=invite.business_id,
                    role=business_role
                )
                print("  ✓ User added to business successfully")
            except Exception as add_error:
                print("\n" + "!" * 80)
                print("!!! ADD USER TO BUSINESS FAILED !!!")
                print("!" * 80)
                print(f"  Error type: {type(add_error).__name__}")
                print(f"  Error message: {str(add_error)}")
                if hasattr(add_error, 'orig'):
                    print(f"  Original error: {add_error.orig}")
                print("!" * 80)
                raise

            print("\n[3] Marking business invite as used...")
            BusinessInviteService.use_business_invite(db, invite.id)
            print("  ✓ Invite marked as used")

            if not existing_user:
                print("\n[4] Creating verification for new user...")
                verification = EmailVerification.create_for_user(user.id, expiry_hours=24)
                db.add(verification)
                db.commit()
                db.refresh(verification)

                send_verification_email.delay(
                    email=user.email,
                    token=verification.token,
                    user_name=user.full_name
                )
                print("  ✓ Verification email queued")

            # Generate tokens and set cookies
            print("\n[5] Generating auth tokens...")
            access_token = create_access_token(
                data={"sub": str(user.id), "email": user.email}
            )
            refresh_token_obj = create_refresh_token(db, user.id)
            set_auth_cookies(response, access_token, refresh_token_obj.token)
            print("  ✓ Tokens set")

            from app.models.business.business import Business
            business = db.query(Business).filter(Business.id == invite.business_id).first()

            print("\n" + "=" * 80)
            print("=== REGISTRATION COMPLETE ===")
            print("=" * 80 + "\n")

            return MessageResponse(
                message=f"Registration successful! You've been added to {business.name if business else 'the business'}.",
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
        print(f"\nValueError caught: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        print("\nHTTPException caught - re-raising")
        raise
    except Exception as e:
        print("\n" + "!" * 80)
        print("!!! UNEXPECTED ERROR !!!")
        print("!" * 80)
        print(f"  Error type: {type(e).__name__}")
        print(f"  Error message: {str(e)}")
        print(f"  Error args: {e.args}")
        if hasattr(e, '__traceback__'):
            import traceback
            print("\nTraceback:")
            traceback.print_exc()
        print("!" * 80 + "\n")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )


@router.post("/login", response_model=TokenResponse)
async def login(
        request: LoginRequest,
        response: Response,
        db: Session = Depends(get_db)
):
    """
    Login with email and password.
    Sets httpOnly cookies for authentication.
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

    # Set cookies
    set_auth_cookies(response, access_token, refresh_token_obj.token)

    return TokenResponse(
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        active_business_id=str(user.active_business_id) if user.active_business_id else None,
        is_verified=user.is_verified
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_access_token(
        request: Request,
        response: Response,
        db: Session = Depends(get_db)
):
    """
    Refresh an access token using the refresh token from cookies.
    """
    # Get refresh token from cookie
    refresh_token_value = request.cookies.get(REFRESH_TOKEN_COOKIE)

    if not refresh_token_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify refresh token
    refresh_token = verify_refresh_token(db, refresh_token_value)

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

    # Update only the access token cookie
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=access_token,
        httponly=True,
        secure=COOKIE_CONFIG["secure"],
        samesite=COOKIE_CONFIG["samesite"],
        max_age=60 * 15,  # 15 minutes
    )

    return TokenResponse(
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        active_business_id=str(user.active_business_id) if user.active_business_id else None,
        is_verified=user.is_verified
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
        request: Request,
        response: Response,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Logout by revoking the refresh token and clearing cookies.
    """
    # Get refresh token from cookie
    refresh_token_value = request.cookies.get(REFRESH_TOKEN_COOKIE)

    if refresh_token_value:
        revoke_refresh_token(db, refresh_token_value)

    # Clear cookies
    clear_auth_cookies(response)

    return MessageResponse(
        message="Successfully logged out"
    )


@router.post("/logout-all", response_model=MessageResponse)
async def logout_all_devices(
        response: Response,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_active_user)
):
    """
    Logout from all devices by revoking all refresh tokens.
    """
    count = revoke_all_user_tokens(db, current_user.id)

    # Clear cookies
    clear_auth_cookies(response)

    return MessageResponse(
        message=f"Successfully logged out from all devices",
        details={"tokens_revoked": count}
    )


# ============================================================================
# Email Verification, Password Reset, etc. (unchanged)
# ============================================================================

@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
        request: VerifyEmailRequest,
        db: Session = Depends(get_db)
):
    """Verify user's email address using the verification token sent via email."""
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

    verification.mark_as_used()
    user = verification.user
    user.is_verified = True
    db.commit()

    return MessageResponse(
        message="Email verified successfully!",
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
    """Resend email verification link."""
    if current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already verified"
        )

    db.query(EmailVerification).filter(
        EmailVerification.user_id == current_user.id,
        EmailVerification.is_used == False
    ).update({"is_used": True})

    verification = EmailVerification.create_for_user(current_user.id, expiry_hours=24)
    db.add(verification)
    db.commit()
    db.refresh(verification)

    send_verification_email.delay(
        email=current_user.email,
        token=verification.token,
        user_name=current_user.full_name
    )

    return MessageResponse(
        message="Verification email sent!",
        details={"email": current_user.email}
    )


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
        request: ForgotPasswordRequest,
        db: Session = Depends(get_db)
):
    """Request a password reset link."""
    user = UserService.get_user_by_email(db, request.email)

    if user and user.is_active:
        db.query(PasswordReset).filter(
            PasswordReset.user_id == user.id,
            PasswordReset.is_used == False
        ).update({"is_used": True})

        reset_token = PasswordReset.create_for_user(user.id, expiry_hours=1)
        db.add(reset_token)
        db.commit()
        db.refresh(reset_token)

        send_password_reset_email.delay(
            email=user.email,
            token=reset_token.token,
            user_name=user.full_name
        )

    return MessageResponse(
        message="If an account exists with that email, a password reset link has been sent."
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
        request: ResetPasswordRequest,
        db: Session = Depends(get_db)
):
    """Reset password using the token sent via email."""
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

    user = reset_token.user
    user.hashed_password = User.hash_password(request.new_password)
    reset_token.mark_as_used()
    revoke_all_user_tokens(db, user.id)
    db.commit()

    return MessageResponse(
        message="Password reset successful!",
        details={"email": user.email}
    )


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
        request: ChangePasswordRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_active_user)
):
    """Change password for the currently logged-in user."""
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

    revoke_all_user_tokens(db, current_user.id)

    return MessageResponse(
        message="Password changed successfully!"
    )


@router.get("/validate-invite", response_model=InviteValidationResponse)
async def validate_invite(
        token: str,
        email: Optional[str] = None,
        db: Session = Depends(get_db)
):
    """Validate an invite token before registration."""
    is_valid, error_msg, invite = InviteService.validate_invite(db, token, email)

    if not is_valid or not invite:
        return InviteValidationResponse(
            valid=False,
            message=error_msg or "Invalid invite"
        )

    if invite.invite_type == InviteType.PLATFORM:
        return InviteValidationResponse(
            valid=True,
            message="Valid platform invite",
            invite_type="platform",
            business_name=None,
            role="owner"
        )
    else:
        from app.models.business.business import Business
        business = db.query(Business).filter(Business.id == invite.business_id).first()

        return InviteValidationResponse(
            valid=True,
            message=f"Valid business invite",
            invite_type="business",
            business_name=business.name if business else None,
            role=invite.role
        )


@router.get("/me", response_model=TokenResponse)
async def get_current_user_info(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Get current user information."""
    return TokenResponse(
        user_id=str(current_user.id),
        email=current_user.email,
        full_name=current_user.full_name,
        active_business_id=str(current_user.active_business_id) if current_user.active_business_id else None,
        is_verified=current_user.is_verified
    )