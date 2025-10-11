"""
FastAPI application for handling Twilio webhooks

Webhooks only - all business logic happens in workers
"""
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config.settings import get_settings
from app.core.middleware import correlation_id_middleware, request_logging_middleware
from app.core.monitoring import health_router
from app.webhooks.router import webhook_router
from app.api.v1.router import api_v1_router
from app.utils.my_logging import setup_logging

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    setup_logging()
    print("🚀 After-Hours Service API starting up...")
    print(f"📱 Webhook endpoints ready at /webhooks/")
    print(f"🔧 Admin API available at /api/v1/")
    print(f"❤️  Health check at /health")

    yield

    # Shutdown
    print("🛑 After-Hours Service API shutting down...")


def create_app() -> FastAPI:
    """Create and configure FastAPI application"""

    app = FastAPI(
        title="After-Hours Service API",
        description="Queue-based AI customer service with appointment booking",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # Add custom middleware
    app.middleware("http")(correlation_id_middleware)
    app.middleware("http")(request_logging_middleware)

    # Include routers
    app.include_router(webhook_router, prefix="/webhooks", tags=["webhooks"])
    app.include_router(health_router, prefix="/health", tags=["monitoring"])
    app.include_router(api_v1_router, prefix="/api/v1", tags=["api"])

    @app.get("/")
    async def root():
        return {
            "service": "After-Hours Service API",
            "version": "0.1.0",
            "status": "running",
            "endpoints": {
                "webhooks": "/webhooks/",
                "health": "/health",
                "docs": "/docs" if settings.DEBUG else "disabled"
            }
        }

    return app


app = create_app()

# 🔥 TEST ROUTES - Define after app creation
@app.get("/test")
async def test():
    print("🔥 TEST ROUTE HIT!", flush=True)
    return {"status": "working"}

@app.post("/test-sms")
async def test_sms(request: Request):
    print("=" * 80, flush=True)
    print("📱 SMS TEST WEBHOOK RECEIVED!", flush=True)

    form_data = await request.form()
    print(f"Form Data: {dict(form_data)}", flush=True)

    print("=" * 80, flush=True)
    return {"status": "received"}


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info"
    )