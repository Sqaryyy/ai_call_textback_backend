"""
FastAPI application for handling Twilio webhooks

Webhooks only - all business logic happens in workers
"""
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from contextlib import asynccontextmanager

from app.config.settings import get_settings
from app.core.middleware import correlation_id_middleware, request_logging_middleware
from app.core.monitoring import health_router
from app.webhooks.router import webhook_router
from app.api.v1.router import api_v1_router
from app.utils.my_logging import setup_logging
from app.api.middleware.logging_middleware import APIRequestLoggingMiddleware
from app.api.middleware.rate_limit_middleware import RateLimitMiddleware
from app.api.middleware.ip_whitelist_middleware import IPWhitelistMiddleware

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

    # Print all registered routes
    print("\n" + "="*80)
    print("📋 REGISTERED ROUTES:")
    print("="*80)

    routes_list = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in route.methods:
                routes_list.append((method, route.path, route.name, route.tags))

    # Sort by path for better readability
    routes_list.sort(key=lambda x: (x[1], x[0]))

    # Group by tag
    from collections import defaultdict
    routes_by_tag = defaultdict(list)

    for method, path, name, tags in routes_list:
        tag = tags[0] if tags else "other"
        routes_by_tag[tag].append((method, path, name))

    # Print grouped routes
    for tag, routes in sorted(routes_by_tag.items()):
        print(f"\n[{tag.upper()}]")
        for method, path, name in routes:
            print(f"  {method:8} {path:50} ({name})")

    print("\n" + "="*80)
    print(f"✅ Total routes registered: {len(routes_list)}")
    print("="*80 + "\n")

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

    app.add_middleware(APIRequestLoggingMiddleware)
    app.add_middleware(RateLimitMiddleware, requests_per_second=10)
    app.add_middleware(IPWhitelistMiddleware)

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "PUT"],
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


@app.get("/debug/routes", tags=["debug"])
async def list_all_routes():
    """List all registered routes (only available in DEBUG mode)"""
    routes = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            routes.append({
                "path": route.path,
                "name": route.name,
                "methods": list(route.methods),
                "tags": route.tags
            })
    return {
        "total": len(routes),
        "routes": sorted(routes, key=lambda x: x["path"])
    }


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info"
    )
