"""
API v1 router setup
Organized into: public, dashboard (JWT), api_key, and admin routes
"""
from fastapi import APIRouter

# Existing routes
from app.api.v1 import metrics
from app.api.v1.dashboard import onboarding, conversations, invites as BizInvites, business, calendar
from app.api.v1.public import demo, auth
from app.api.v1.admin import invites

api_v1_router = APIRouter()

# ============================================================================
# PUBLIC ROUTES (No authentication required)
# ============================================================================
api_v1_router.include_router(
    demo.router,
    prefix="/public/demo",
    tags=["Public"]
)

api_v1_router.include_router(
    auth.router,
    # No prefix needed - auth.router already has "/auth" prefix
    tags=["Authentication"]
)

# ============================================================================
# DASHBOARD ROUTES (JWT authentication required)
# ============================================================================
api_v1_router.include_router(
    conversations.router,
    prefix="/dashboard",  # ← Just /dashboard
    tags=["Dashboard"]
)

api_v1_router.include_router(
    onboarding.router,
    prefix="/dashboard/onboarding",
    tags=["Dashboard"]
)
api_v1_router.include_router(
    business.router,
    prefix="/dashboard/business",
    tags=["Dashboard"]
)
api_v1_router.include_router(BizInvites.router,
    prefix="/dashboard/business-invites",
    tags=["Dashboard"]
)

api_v1_router.include_router(
    calendar.router,
    prefix="/dashboard/calendar",
    tags=["Dashboard"]
)
# ============================================================================
# ADMIN ROUTES (JWT authentication + admin role required)
# ============================================================================
api_v1_router.include_router(
    invites.router,
    # No prefix needed - invites.router already has "/admin/invites" prefix
    tags=["Admin"]
)

# ============================================================================
# API KEY ROUTES (API key authentication required)
# ============================================================================
# These routes require API key authentication (for webhooks, integrations)

api_v1_router.include_router(
    metrics.router,
    prefix="/metrics",
    tags=["API Key - Metrics"]
)

# ============================================================================
# ROOT ENDPOINT - API Info
# ============================================================================
@api_v1_router.get("/", tags=["Info"])
async def api_info():
    """
    API information and available endpoints.
    Shows the structure of all API routes organized by authentication type.
    """
    return {
        "version": "1.0",
        "authentication": {
            "public": "No authentication required",
            "dashboard": "JWT Bearer token required (user login)",
            "api_key": "API key required (for integrations)",
            "admin": "JWT Bearer token + admin/owner role required"
        }
    }


@api_v1_router.get("/health", tags=["Info"])
async def health_check():
    """
    Health check endpoint.
    Useful for monitoring and load balancers.
    """
    return {
        "status": "healthy",
        "version": "1.0",
        "service": "After-Hours API"
    }