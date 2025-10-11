"""API v1 router setup"""
from fastapi import APIRouter

from app.api.v1 import calendar, demo

api_v1_router = APIRouter()

# Mount sub-routers with explicit prefixes
api_v1_router.include_router(calendar.router, prefix="/calendar")
api_v1_router.include_router(demo.router, prefix="/demo")

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
            "demo": "/api/v1/demo"
        }
    }