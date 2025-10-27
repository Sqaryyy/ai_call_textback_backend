# app/services/api_key_service.py
import secrets
import hashlib
from typing import Optional, List, Tuple
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from uuid import UUID

from app.models.api_key import APIKey
from app.models.api_request_log import APIRequestLog


class APIKeyService:
    """Service for managing API keys and authentication"""

    VALID_SCOPES = [
        "read:metrics",
        "read:calls",
        "read:conversations",
        "read:appointments",
        "write:webhooks",
        "write:appointments",
        "*"  # Admin - all permissions
    ]

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_key(
            self,
            business_id: UUID,
            name: str,
            scopes: List[str],
            description: Optional[str] = None,
            rate_limit: int = 1000,
            expires_at: Optional[datetime] = None,
            environment: str = "live"  # "live" or "test"
    ) -> Tuple[APIKey, str]:
        """
        Generate a new API key for a business.

        Returns:
            Tuple of (APIKey model, raw_key_string)
            Raw key is only returned ONCE - never retrievable again!
        """
        # Validate scopes
        invalid_scopes = [s for s in scopes if s not in self.VALID_SCOPES]
        if invalid_scopes:
            raise ValueError(f"Invalid scopes: {invalid_scopes}")

        if not scopes:
            raise ValueError("At least one scope is required")

        # Generate random key
        random_part = secrets.token_urlsafe(24)  # 32 characters, URL-safe
        raw_key = f"mctb_{environment}_{random_part}"

        # Extract prefix (first 12 chars for identification)
        key_prefix = raw_key[:12]

        # Hash the full key
        key_hash = self._hash_key(raw_key)

        # Create API key record
        api_key = APIKey(
            business_id=business_id,
            key_prefix=key_prefix,
            key_hash=key_hash,
            name=name,
            description=description,
            scopes=scopes,
            rate_limit=rate_limit,
            expires_at=expires_at,
            is_active=True
        )

        self.db.add(api_key)
        await self.db.commit()
        await self.db.refresh(api_key)

        return api_key, raw_key

    async def validate_key(
            self,
            raw_key: str,
            check_rate_limit: bool = True
    ) -> Optional[APIKey]:
        """
        Validate an API key and return the APIKey model if valid.

        Checks:
        - Key exists
        - Key is active
        - Key not expired
        - Key not revoked
        - Rate limit (optional)

        Returns None if invalid.
        """
        # Hash the provided key
        key_hash = self._hash_key(raw_key)

        # Look up key by hash (constant-time comparison via DB)
        query = select(APIKey).where(
            and_(
                APIKey.key_hash == key_hash,
                APIKey.is_active == True,
                APIKey.revoked_at.is_(None)
            )
        )

        result = await self.db.execute(query)
        api_key = result.scalar_one_or_none()

        if not api_key:
            return None

        # Check expiration
        if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
            return None

        # Check rate limit if requested
        if check_rate_limit:
            is_allowed = await self.check_rate_limit(api_key)
            if not is_allowed:
                return None

        # Update usage tracking
        api_key.last_used_at = datetime.now(timezone.utc)
        api_key.usage_count += 1
        await self.db.commit()

        return api_key

    async def check_rate_limit(self, api_key: APIKey) -> bool:
        """
        Check if API key is within rate limit.
        DB-based sliding window (last hour).

        Returns True if under limit, False if exceeded.
        """
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)

        # Count requests in last hour
        query = select(func.count(APIRequestLog.id)).where(
            and_(
                APIRequestLog.api_key_id == api_key.id,
                APIRequestLog.created_at >= one_hour_ago
            )
        )

        result = await self.db.execute(query)
        request_count = result.scalar()

        return request_count < api_key.rate_limit

    def check_scope(self, api_key: APIKey, required_scope: str) -> bool:
        """
        Check if API key has required permission scope.

        Args:
            api_key: The API key to check
            required_scope: The scope needed (e.g., "read:metrics")

        Returns:
            True if key has permission, False otherwise
        """
        # Admin wildcard has all permissions
        if "*" in api_key.scopes:
            return True

        # Check for exact scope match
        return required_scope in api_key.scopes

    async def list_keys(
            self,
            business_id: UUID,
            include_revoked: bool = False
    ) -> List[APIKey]:
        """
        List all API keys for a business.
        Keys are returned with masked values (only prefix visible).
        """
        query = select(APIKey).where(APIKey.business_id == business_id)

        if not include_revoked:
            query = query.where(APIKey.revoked_at.is_(None))

        query = query.order_by(APIKey.created_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def revoke_key(
            self,
            key_id: UUID,
            reason: str,
            business_id: Optional[UUID] = None
    ) -> APIKey:
        """
        Revoke an API key.

        Args:
            key_id: The API key ID to revoke
            reason: Reason for revocation
            business_id: Optional - verify key belongs to this business
        """
        query = select(APIKey).where(APIKey.id == key_id)

        if business_id:
            query = query.where(APIKey.business_id == business_id)

        result = await self.db.execute(query)
        api_key = result.scalar_one_or_none()

        if not api_key:
            raise ValueError("API key not found")

        api_key.is_active = False
        api_key.revoked_at = datetime.now(timezone.utc)
        api_key.revoked_reason = reason

        await self.db.commit()
        await self.db.refresh(api_key)

        return api_key

    async def rotate_key(
            self,
            old_key_id: UUID,
            business_id: UUID,
            environment: str = "live"
    ) -> Tuple[APIKey, str]:
        """
        Rotate an API key - revoke old one and generate new one with same permissions.

        Returns:
            Tuple of (new_APIKey, raw_key_string)
        """
        # Get old key
        result = await self.db.execute(
            select(APIKey).where(
                and_(
                    APIKey.id == old_key_id,
                    APIKey.business_id == business_id
                )
            )
        )
        old_key = result.scalar_one_or_none()

        if not old_key:
            raise ValueError("API key not found")

        # Revoke old key
        await self.revoke_key(old_key_id, "Rotated to new key", business_id)

        # Generate new key with same permissions
        new_key, raw_key = await self.generate_key(
            business_id=business_id,
            name=f"{old_key.name} (Rotated)",
            scopes=old_key.scopes,
            description=old_key.description,
            rate_limit=old_key.rate_limit,
            expires_at=old_key.expires_at,
            environment=environment
        )

        return new_key, raw_key

    async def log_request(
            self,
            api_key: APIKey,
            method: str,
            path: str,
            status_code: int,
            response_time_ms: int,
            query_params: Optional[dict] = None,
            ip_address: Optional[str] = None,
            user_agent: Optional[str] = None,
            error_message: Optional[str] = None
    ) -> APIRequestLog:
        """
        Log an API request for analytics and debugging.
        Per-endpoint tracking.
        """
        log_entry = APIRequestLog(
            api_key_id=api_key.id,
            business_id=api_key.business_id,
            method=method,
            path=path,
            query_params=query_params or {},
            status_code=status_code,
            response_time_ms=response_time_ms,
            ip_address=ip_address,
            user_agent=user_agent,
            error_message=error_message
        )

        self.db.add(log_entry)
        await self.db.commit()

        return log_entry

    async def get_usage_stats(
            self,
            api_key_id: UUID,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None
    ) -> dict:
        """
        Get usage statistics for an API key.
        Per-endpoint breakdown.
        """
        query = select(APIRequestLog).where(APIRequestLog.api_key_id == api_key_id)

        if start_date:
            query = query.where(APIRequestLog.created_at >= start_date)
        if end_date:
            query = query.where(APIRequestLog.created_at <= end_date)

        result = await self.db.execute(query)
        logs = result.scalars().all()

        # Aggregate stats
        total_requests = len(logs)

        # Per-endpoint breakdown
        endpoint_stats = {}
        for log in logs:
            if log.path not in endpoint_stats:
                endpoint_stats[log.path] = {
                    "count": 0,
                    "avg_response_time": 0.0,
                    "error_count": 0
                }

            endpoint_stats[log.path]["count"] += 1
            endpoint_stats[log.path]["avg_response_time"] += log.response_time_ms or 0
            if log.status_code >= 400:
                endpoint_stats[log.path]["error_count"] += 1

        # Calculate averages
        for path, stats in endpoint_stats.items():
            if stats["count"] > 0:
                stats["avg_response_time"] = stats["avg_response_time"] / stats["count"]

        return {
            "total_requests": total_requests,
            "endpoint_breakdown": endpoint_stats,
            "date_range": {
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None
            }
        }

    @staticmethod
    def _hash_key(raw_key: str) -> str:
        """Hash an API key using SHA-256."""
        return hashlib.sha256(raw_key.encode()).hexdigest()

    @staticmethod
    def mask_key(key_prefix: str) -> str:
        """Return masked key for display (only shows prefix)."""
        return f"{key_prefix}{'*' * 20}"
