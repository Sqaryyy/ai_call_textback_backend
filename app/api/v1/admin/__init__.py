# ============================================================================
# FILE: app/api/v1/admin/__init__.py
# Admin module initialization - aggregates all admin routers
# ============================================================================
from fastapi import APIRouter
from app.api.v1.admin import conversations, messages,appointments,availability,businesses,calendar_integrations,call_events,conversation_metrics,conversation_state,documents,invites,services

# Create main admin router
admin_router = APIRouter(prefix="/admin", tags=["Admin"])

# Include all admin sub-routers
admin_router.include_router(conversations.router)
admin_router.include_router(messages.admin_messages_router)
admin_router.include_router(appointments.router)
admin_router.include_router(availability.availability_rules_router)
admin_router.include_router(availability.availability_overrides_router)
admin_router.include_router(businesses.router)
admin_router.include_router(businesses.business_hours_router)
admin_router.include_router(calendar_integrations.router)
admin_router.include_router(call_events.router)
admin_router.include_router(conversation_state.router)
admin_router.include_router(conversation_metrics.router)
admin_router.include_router(documents.admin_documents_router)
admin_router.include_router(services.admin_services_router)
admin_router.include_router(invites.router)




# Export for easy import
__all__ = ["admin_router"]