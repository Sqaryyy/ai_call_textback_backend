# ===== app/api/v1/dashboard/api_keys.py =====
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional
from uuid import UUID
import secrets
import hashlib
from datetime import datetime, timedelta

from app.config.database import get_db
from app.models.auth.api_key import APIKey
from app.schemas.api_key import (
    APIKeyCreate,
    APIKeyUpdate,
    APIKeyResponse,
    APIKeyWithSecretResponse,
)
from app.api.dependencies import require_business_owner, require_business_member
from app.models.auth.user import User
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["api-keys"])

# Available scopes that users can assign to API keys
AVAILABLE_SCOPES = [
    "read:conversations",
    "write:conversations",
    "read:bookings",
    "write:bookings",
    "read:metrics",
    "read:documents",
    "write:documents",
    "read:services",
    "write:services",
    "read:webhooks",
    "write:webhooks",
    "read:calendar",
    "write:calendar",
    "*",  # Full access
]


def get_business_id(current_user: User) -> UUID:
    """Helper to get business_id and ensure user has an active business"""
    if not current_user.active_business_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active business selected"
        )
    return current_user.active_business_id


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key with prefix, secret, and hash.
    Returns: (full_key, key_prefix, key_hash)
    """
    # Generate random key
    random_part = secrets.token_urlsafe(32)

    # Create full key with prefix
    full_key = f"mctb_live_{random_part}"

    # Create prefix (first 12 chars for identification)
    key_prefix = full_key[:12]

    # Hash the full key for storage
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()

    return full_key, key_prefix, key_hash


@router.get("/scopes", response_model=List[str])
async def list_available_scopes(
        current_user: User = Depends(require_business_member),
):
    """Get list of all available API key scopes"""
    logger.info(f"User {current_user.id} listing available API key scopes")
    return AVAILABLE_SCOPES


@router.post("/", response_model=APIKeyWithSecretResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
        api_key_data: APIKeyCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_business_owner),
):
    """
    Create a new API key for the current business.
    The full API key is only returned once during creation.
    Requires business owner role.
    """
    business_id = get_business_id(current_user)

    logger.info(
        f"User {current_user.id} creating API key for business {business_id} - "
        f"Name: '{api_key_data.name}', Scopes: {api_key_data.scopes}"
    )

    # Validate scopes
    for scope in api_key_data.scopes:
        if scope not in AVAILABLE_SCOPES:
            logger.warning(f"Invalid scope attempted: {scope}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid scope: {scope}. Available scopes: {AVAILABLE_SCOPES}"
            )

    # Generate API key
    full_key, key_prefix, key_hash = generate_api_key()

    # Calculate expiration if provided
    expires_at = None
    if api_key_data.expires_in_days:
        expires_at = datetime.utcnow() + timedelta(days=api_key_data.expires_in_days)

    # Create API key record
    api_key = APIKey(
        business_id=business_id,
        key_prefix=key_prefix,
        key_hash=key_hash,
        name=api_key_data.name,
        description=api_key_data.description,
        scopes=api_key_data.scopes,
        is_active=True,
        expires_at=expires_at,
        rate_limit=api_key_data.rate_limit or 1000,
        allowed_ips=api_key_data.allowed_ips or [],
    )

    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    logger.info(
        f"API key {api_key.id} created successfully - Prefix: {key_prefix}, "
        f"Expires: {expires_at.isoformat() if expires_at else 'Never'}"
    )

    # Return response with full key (only time it's shown)
    return APIKeyWithSecretResponse(
        id=api_key.id,
        business_id=api_key.business_id,
        key_prefix=api_key.key_prefix,
        name=api_key.name,
        description=api_key.description,
        scopes=api_key.scopes,
        is_active=api_key.is_active,
        expires_at=api_key.expires_at,
        last_used_at=api_key.last_used_at,
        usage_count=api_key.usage_count,
        rate_limit=api_key.rate_limit,
        allowed_ips=api_key.allowed_ips,
        created_at=api_key.created_at,
        updated_at=api_key.updated_at,
        revoked_at=api_key.revoked_at,
        revoked_reason=api_key.revoked_reason,
        secret=full_key,  # Only returned during creation
    )


@router.get("/", response_model=List[APIKeyResponse])
async def list_api_keys(
        include_revoked: bool = False,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_business_member),
):
    """List all API keys for the current business"""
    business_id = get_business_id(current_user)

    filter_str = " (including revoked)" if include_revoked else " (active only)"
    logger.info(f"User {current_user.id} listing API keys for business {business_id}{filter_str}")

    query = db.query(APIKey).filter(APIKey.business_id == business_id)

    if not include_revoked:
        query = query.filter(APIKey.revoked_at.is_(None))

    api_keys = query.order_by(desc(APIKey.created_at)).all()

    logger.info(f"Returning {len(api_keys)} API keys")

    return api_keys


@router.get("/{api_key_id}", response_model=APIKeyResponse)
async def get_api_key(
        api_key_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_business_member),
):
    """Get a specific API key"""
    business_id = get_business_id(current_user)

    logger.info(f"User {current_user.id} viewing API key {api_key_id}")

    api_key = db.query(APIKey).filter(
        APIKey.id == api_key_id,
        APIKey.business_id == business_id
    ).first()

    if not api_key:
        logger.warning(f"API key {api_key_id} not found for business {business_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    logger.debug(
        f"Retrieved API key - Prefix: {api_key.key_prefix}, Active: {api_key.is_active}, "
        f"Usage: {api_key.usage_count}"
    )

    return api_key


@router.put("/{api_key_id}", response_model=APIKeyResponse)
async def update_api_key(
        api_key_id: UUID,
        api_key_data: APIKeyUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_business_owner),
):
    """Update an API key's metadata and settings. Requires business owner role."""
    business_id = get_business_id(current_user)

    # Build update description for logging
    updates = []
    update_data = api_key_data.model_dump(exclude_unset=True)
    for field in update_data.keys():
        if field == 'scopes':
            updates.append(f"scopes={update_data[field]}")
        elif field == 'is_active':
            updates.append(f"is_active={update_data[field]}")
        elif field == 'rate_limit':
            updates.append(f"rate_limit={update_data[field]}")
        elif field == 'allowed_ips':
            updates.append("allowed_ips")
        else:
            updates.append(field)

    update_str = ', '.join(updates) if updates else "no changes"
    logger.info(f"User {current_user.id} updating API key {api_key_id} - Updates: {update_str}")

    api_key = db.query(APIKey).filter(
        APIKey.id == api_key_id,
        APIKey.business_id == business_id
    ).first()

    if not api_key:
        logger.warning(f"Update failed - API key {api_key_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    # Validate scopes if provided
    if api_key_data.scopes is not None:
        for scope in api_key_data.scopes:
            if scope not in AVAILABLE_SCOPES:
                logger.warning(f"Invalid scope in update: {scope}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid scope: {scope}"
                )

    # Update fields
    update_data = api_key_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(api_key, field, value)

    db.commit()
    db.refresh(api_key)

    logger.info(f"API key {api_key_id} updated successfully")

    return api_key


@router.delete("/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
        api_key_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_business_owner),
):
    """Permanently delete an API key. Requires business owner role."""
    business_id = get_business_id(current_user)

    logger.warning(f"User {current_user.id} attempting to DELETE API key {api_key_id}")

    api_key = db.query(APIKey).filter(
        APIKey.id == api_key_id,
        APIKey.business_id == business_id
    ).first()

    if not api_key:
        logger.warning(f"Delete failed - API key {api_key_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    key_name = api_key.name
    key_prefix = api_key.key_prefix

    db.delete(api_key)
    db.commit()

    logger.warning(
        f"API key DELETED permanently - "
        f"Key ID: {api_key_id}, Name: '{key_name}', Prefix: {key_prefix}, "
        f"Business ID: {business_id}, Deleted by: {current_user.id}"
    )


@router.post("/{api_key_id}/revoke", response_model=APIKeyResponse)
async def revoke_api_key(
        api_key_id: UUID,
        reason: Optional[str] = None,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_business_owner),
):
    """
    Revoke an API key (soft delete). Requires business owner role.
    The key will no longer work but remains in the database for audit purposes.
    """
    business_id = get_business_id(current_user)

    reason_str = f" - Reason: {reason}" if reason else ""
    logger.info(f"User {current_user.id} revoking API key {api_key_id}{reason_str}")

    api_key = db.query(APIKey).filter(
        APIKey.id == api_key_id,
        APIKey.business_id == business_id
    ).first()

    if not api_key:
        logger.warning(f"Revoke failed - API key {api_key_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    if api_key.revoked_at:
        logger.warning(f"Revoke failed - API key {api_key_id} already revoked")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="API key is already revoked"
        )

    api_key.is_active = False
    api_key.revoked_at = datetime.utcnow()
    api_key.revoked_reason = reason

    db.commit()
    db.refresh(api_key)

    logger.info(f"API key {api_key_id} revoked successfully - Prefix: {api_key.key_prefix}")

    return api_key


@router.post("/{api_key_id}/activate", response_model=APIKeyResponse)
async def activate_api_key(
        api_key_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_business_owner),
):
    """Reactivate a previously deactivated (but not revoked) API key. Requires business owner role."""
    business_id = get_business_id(current_user)

    logger.info(f"User {current_user.id} activating API key {api_key_id}")

    api_key = db.query(APIKey).filter(
        APIKey.id == api_key_id,
        APIKey.business_id == business_id
    ).first()

    if not api_key:
        logger.warning(f"Activate failed - API key {api_key_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    if api_key.revoked_at:
        logger.warning(f"Activate failed - API key {api_key_id} is revoked")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot activate a revoked API key. Create a new one instead."
        )

    # Check if expired
    if api_key.expires_at and api_key.expires_at < datetime.utcnow():
        logger.warning(f"Activate failed - API key {api_key_id} is expired")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot activate an expired API key"
        )

    api_key.is_active = True
    db.commit()
    db.refresh(api_key)

    logger.info(f"API key {api_key_id} activated successfully - Prefix: {api_key.key_prefix}")

    return api_key


@router.post("/{api_key_id}/rotate", response_model=APIKeyWithSecretResponse)
async def rotate_api_key(
        api_key_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_business_owner),
):
    """
    Rotate an API key by generating a new secret while keeping the same settings.
    This is useful when a key may have been compromised. Requires business owner role.
    """
    business_id = get_business_id(current_user)

    logger.warning(f"User {current_user.id} ROTATING API key {api_key_id} (possible compromise)")

    old_api_key = db.query(APIKey).filter(
        APIKey.id == api_key_id,
        APIKey.business_id == business_id
    ).first()

    if not old_api_key:
        logger.warning(f"Rotate failed - API key {api_key_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    old_prefix = old_api_key.key_prefix

    # Generate new key
    full_key, key_prefix, key_hash = generate_api_key()

    # Update the existing record
    old_api_key.key_prefix = key_prefix
    old_api_key.key_hash = key_hash
    old_api_key.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(old_api_key)

    logger.warning(
        f"API key {api_key_id} ROTATED - "
        f"Old prefix: {old_prefix}, New prefix: {key_prefix}, "
        f"Rotated by: {current_user.id}"
    )

    # Return response with new full key
    return APIKeyWithSecretResponse(
        id=old_api_key.id,
        business_id=old_api_key.business_id,
        key_prefix=old_api_key.key_prefix,
        name=old_api_key.name,
        description=old_api_key.description,
        scopes=old_api_key.scopes,
        is_active=old_api_key.is_active,
        expires_at=old_api_key.expires_at,
        last_used_at=old_api_key.last_used_at,
        usage_count=old_api_key.usage_count,
        rate_limit=old_api_key.rate_limit,
        allowed_ips=old_api_key.allowed_ips,
        created_at=old_api_key.created_at,
        updated_at=old_api_key.updated_at,
        revoked_at=old_api_key.revoked_at,
        revoked_reason=old_api_key.revoked_reason,
        secret=full_key,  # New API key
    )


@router.get("/usage/stats")
async def get_api_key_usage_stats(
        db: Session = Depends(get_db),
        current_user: User = Depends(require_business_member),
):
    """Get usage statistics for all API keys in the current business"""
    business_id = get_business_id(current_user)

    logger.info(f"User {current_user.id} requesting API key usage stats for business {business_id}")

    api_keys = db.query(APIKey).filter(
        APIKey.business_id == business_id,
        APIKey.revoked_at.is_(None)
    ).all()

    total_keys = len(api_keys)
    active_keys = sum(1 for key in api_keys if key.is_active)
    total_usage = sum(key.usage_count for key in api_keys)

    logger.info(
        f"API key stats: {total_keys} total, {active_keys} active, "
        f"{total_usage} total requests"
    )

    return {
        "total_keys": total_keys,
        "active_keys": active_keys,
        "inactive_keys": total_keys - active_keys,
        "total_requests": total_usage,
    }