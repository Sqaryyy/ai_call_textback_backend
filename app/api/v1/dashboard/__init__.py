from fastapi import APIRouter
from app.api.v1.dashboard import appointments, metrics as dashboard_metrics, api_key, conversations, invites as BizInvites, business, calendar,business_onboarding,services,documents,demo as dashboard_demo,webhook

dashboard_router = APIRouter(prefix="/dashboard", tags=["Admin"])

# ============================================================================
# DASHBOARD ROUTES (JWT authentication required)
# ============================================================================
dashboard_router.include_router(
    conversations.router,
    prefix="/conversations",  # ← Just /dashboard
    tags=["Dashboard"]
)
dashboard_router.include_router(
    api_key.router,
    prefix="/api-keys",  # ← Just /dashboard
    tags=["Dashboard"]
)

dashboard_router.include_router(
    appointments.router,
    prefix="/appointments",  # ← Just /dashboard
    tags=["Dashboard"]
)
dashboard_router.include_router(
    webhook.router,
    prefix="/webhooks",  # ← Just /dashboard
    tags=["Dashboard"]
)
dashboard_router.include_router(
    business_onboarding.router,
    prefix="/businesses",  # ← Use this for the new onboarding endpoints
    tags=["Business Onboarding"]
)
dashboard_router.include_router(
    dashboard_metrics.router,
    prefix="/metrics",  # ← Use this for the new onboarding endpoints
    tags=["Metrics"]
)
dashboard_router.include_router(
    dashboard_demo.router,
    prefix="/demo",  # ← Use this for the new onboarding endpoints
    tags=["Business Demo"]
)
dashboard_router.include_router(
    business.router,
    prefix="/business",
    tags=["Dashboard"]
)
dashboard_router.include_router(
    services.router,
    prefix="/services",
    tags=["Dashboard"]
)
dashboard_router.include_router(
    documents.router,
    prefix="/documents",
    tags=["Dashboard"]
)
dashboard_router.include_router(BizInvites.router,
    prefix="/business-invites",
    tags=["Dashboard"]
)

dashboard_router.include_router(
    calendar.router,
    prefix="/calendar",
    tags=["Dashboard"]
)