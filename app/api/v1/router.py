"""API v1 router setup"""
from fastapi import APIRouter

from app.api.v1 import calendar, demo, metrics, onboarding

api_v1_router = APIRouter()

# Mount sub-routers with explicit prefixes
api_v1_router.include_router(calendar.router, prefix="/calendar")
api_v1_router.include_router(demo.router, prefix="/demo")
api_v1_router.include_router(metrics.router, prefix="/metrics")
api_v1_router.include_router(onboarding.router, prefix="/onboarding")

@api_v1_router.get("/")
async def api_info():
    """API information"""
    return {
        "version": "1.0",
        "endpoints": {
            "health": "/health",
            "businesses": "/businesses",
            "conversations": "/conversations",
            "analytics": "/analytics",
            "calendar": "/api/v1/calendar",
            "demo": "/api/v1/demo",
            "metrics": "/api/v1/metrics",
            "onboarding": "/api/v1/onboarding"
        }
    }