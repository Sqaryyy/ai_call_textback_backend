# app/webhooks/router.py
from fastapi import APIRouter

webhook_router = APIRouter()

# Import handlers inside a function to avoid circular imports
def register_handlers():
    from app.webhooks import sms_handler,call_handler
    webhook_router.include_router(sms_handler.router, prefix="/sms")
    webhook_router.include_router(call_handler.router, prefix="/call")

register_handlers()

@webhook_router.get("/")
async def webhook_info():
    return {
        "endpoints": {
            "incoming_calls": "/webhooks/call/incoming",
            "sms_messages": "/webhooks/sms/incoming",
        },
        "note": "All endpoints accept POST requests from Twilio"
    }
