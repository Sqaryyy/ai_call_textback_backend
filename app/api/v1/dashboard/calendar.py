# ============================================================================
# FILE: app/api/v1/dashboard/calendar.py
# Session authenticated endpoints - thin HTTP layer
# IMPORTANT: Specific routes MUST come before parameterized routes
# ============================================================================

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from app.config.database import get_db
from app.config.redis import get_redis
from app.models.user import User
from app.models import CalendarIntegration
from app.api.dependencies import get_current_user
from app.services.calendar.google_calendar_service import GoogleCalendarService
from app.services.calendar.outlook_service import OutlookCalendarService
from app.services.calendar.calendly_service import CalendlyService
from app.services.availability.availability_service import AvailabilityService
import json

router = APIRouter(tags=["dashboard-calendar"])


# ========== HELPER FUNCTIONS FOR REDIS ==========

async def store_oauth_callback(business_id: str, data: dict):
    """Store OAuth callback data in Redis with 5 minute expiration"""
    redis_client = await get_redis()
    key = f"oauth_callback:{business_id}"
    await redis_client.setex(
        key,
        300,  # 5 minutes TTL
        json.dumps(data)
    )


async def get_oauth_callback(business_id: str) -> dict | None:
    """Retrieve OAuth callback data from Redis"""
    redis_client = await get_redis()
    key = f"oauth_callback:{business_id}"
    data = await redis_client.get(key)

    if data:
        return json.loads(data)
    return None


async def delete_oauth_callback(business_id: str):
    """Delete OAuth callback data from Redis"""
    redis_client = await get_redis()
    key = f"oauth_callback:{business_id}"
    await redis_client.delete(key)


# ========== GOOGLE CALENDAR ==========

@router.post("/google/authorize")
async def initiate_google_auth(
        current_user: User = Depends(get_current_user)
):
    """
    Returns authorization URL for business owner to visit.
    Requires authenticated session.
    """
    if not current_user.active_business_id:
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    service = GoogleCalendarService()
    auth_url = service.generate_authorization_url(str(current_user.active_business_id))
    return {"authorization_url": auth_url}


@router.get("/google/callback")
async def google_callback(
        code: str,
        state: str,  # business_id
        db: Session = Depends(get_db)
):
    """
    Google redirects here after authorization.
    This endpoint does NOT require authentication as it's a callback from Google.
    """
    service = GoogleCalendarService()
    integration = service.handle_oauth_callback(code, state, db)

    # Store the callback result in Redis for polling
    await store_oauth_callback(state, {
        'integration_id': str(integration.id),
        'calendars': integration.provider_config['calendar_list'],
        'provider': 'google'
    })

    # Return HTML to close the popup window
    return """
    <html>
        <head>
            <title>Authorization Successful</title>
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                }
                .container {
                    text-align: center;
                    background: white;
                    padding: 3rem;
                    border-radius: 1rem;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                }
                .success-icon {
                    font-size: 4rem;
                    margin-bottom: 1rem;
                }
                h1 {
                    color: #10b981;
                    margin: 0 0 0.5rem 0;
                }
                p {
                    color: #6b7280;
                    margin: 0;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="success-icon">✅</div>
                <h1>Authorization Successful!</h1>
                <p>You can close this window and return to the setup.</p>
            </div>
            <script>
                // Auto-close after 2 seconds
                setTimeout(() => window.close(), 2000);
            </script>
        </body>
    </html>
    """


@router.get("/google/callback-status")
async def check_google_callback_status(
        current_user: User = Depends(get_current_user)
):
    """
    Poll this endpoint to check if OAuth callback completed.
    Requires authenticated session.
    """
    if not current_user.active_business_id:
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    callback_data = await get_oauth_callback(str(current_user.active_business_id))

    if callback_data:
        return {
            "success": True,
            "integration_id": callback_data['integration_id'],
            "calendars": callback_data['calendars'],
            "provider": callback_data['provider']
        }

    return {"success": False, "message": "No callback received yet"}


@router.patch("/google/{integration_id:uuid}/select-calendar")
async def select_google_calendar(
        integration_id: UUID = Path(..., description="The integration ID"),
        calendar_id: str = Query(..., description="The calendar ID to select"),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Let business choose which Google calendar to use.
    Requires authenticated session.
    """
    if not current_user.active_business_id:
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    integration = db.query(CalendarIntegration).filter(
        CalendarIntegration.id == integration_id,
        CalendarIntegration.business_id == current_user.active_business_id,
        CalendarIntegration.provider == 'google'
    ).first()

    if not integration:
        raise HTTPException(
            status_code=404,
            detail="Google integration not found or you don't have access to it"
        )

    integration.provider_config['selected_calendar_id'] = calendar_id
    db.commit()
    return {"success": True, "selected_calendar_id": calendar_id}


# ========== OUTLOOK CALENDAR ==========

@router.post("/outlook/authorize")
async def initiate_outlook_auth(
        current_user: User = Depends(get_current_user)
):
    """
    Returns authorization URL for business owner to visit.
    Requires authenticated session.
    """
    if not current_user.active_business_id:
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    service = OutlookCalendarService()
    auth_url = await service.generate_authorization_url(str(current_user.active_business_id))
    return {"authorization_url": auth_url}


@router.get("/outlook/callback")
async def outlook_callback(
        code: str,
        state: str,  # business_id
        db: Session = Depends(get_db)
):
    """
    Microsoft redirects here after authorization.
    This endpoint does NOT require authentication as it's a callback from Microsoft.
    """
    service = OutlookCalendarService()
    integration = await service.handle_oauth_callback(code, state, db)

    # Store the callback result in Redis for polling
    await store_oauth_callback(state, {
        'integration_id': str(integration.id),
        'calendars': integration.provider_config['calendar_list'],
        'provider': 'outlook'
    })

    return """
    <html>
        <head>
            <title>Authorization Successful</title>
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                }
                .container {
                    text-align: center;
                    background: white;
                    padding: 3rem;
                    border-radius: 1rem;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                }
                .success-icon {
                    font-size: 4rem;
                    margin-bottom: 1rem;
                }
                h1 {
                    color: #10b981;
                    margin: 0 0 0.5rem 0;
                }
                p {
                    color: #6b7280;
                    margin: 0;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="success-icon">✅</div>
                <h1>Authorization Successful!</h1>
                <p>You can close this window and return to the setup.</p>
            </div>
            <script>
                setTimeout(() => window.close(), 2000);
            </script>
        </body>
    </html>
    """


@router.get("/outlook/callback-status")
async def check_outlook_callback_status(
        current_user: User = Depends(get_current_user)
):
    """
    Poll this endpoint to check if OAuth callback completed.
    Requires authenticated session.
    """
    if not current_user.active_business_id:
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    callback_data = await get_oauth_callback(str(current_user.active_business_id))

    if callback_data:
        return {
            "success": True,
            "integration_id": callback_data['integration_id'],
            "calendars": callback_data['calendars'],
            "provider": callback_data['provider']
        }

    return {"success": False, "message": "No callback received yet"}


@router.patch("/outlook/{integration_id:uuid}/select-calendar")
async def select_outlook_calendar(
        integration_id: UUID = Path(..., description="The integration ID"),
        calendar_id: str = Query(..., description="The calendar ID to select"),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Let business choose which Outlook calendar to use.
    Requires authenticated session.
    """
    if not current_user.active_business_id:
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    integration = db.query(CalendarIntegration).filter(
        CalendarIntegration.id == integration_id,
        CalendarIntegration.business_id == current_user.active_business_id,
        CalendarIntegration.provider == 'outlook'
    ).first()

    if not integration:
        raise HTTPException(
            status_code=404,
            detail="Outlook integration not found or you don't have access to it"
        )

    integration.provider_config['selected_calendar_id'] = calendar_id
    db.commit()
    return {"success": True, "selected_calendar_id": calendar_id}


# ========== CALENDLY ==========

@router.post("/calendly/setup")
async def setup_calendly(
        personal_access_token: str = Query(..., description="Calendly Personal Access Token"),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Business owner provides their Calendly Personal Access Token.
    Requires authenticated session.
    """
    if not current_user.active_business_id:
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    service = CalendlyService()
    try:
        integration = service.setup_integration(
            str(current_user.active_business_id),
            personal_access_token,
            db
        )
        return {
            "success": True,
            "integration_id": str(integration.id),
            "event_types": integration.provider_config['event_types']
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/calendly/{integration_id:uuid}/select-event-type")
async def select_calendly_event_type(
        integration_id: UUID = Path(..., description="The integration ID"),
        event_type_uri: str = Query(..., description="The event type URI to select"),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Let business choose which Calendly event type to use.
    Requires authenticated session.
    """
    if not current_user.active_business_id:
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    integration = db.query(CalendarIntegration).filter(
        CalendarIntegration.id == integration_id,
        CalendarIntegration.business_id == current_user.active_business_id,
        CalendarIntegration.provider == 'calendly'
    ).first()

    if not integration:
        raise HTTPException(
            status_code=404,
            detail="Calendly integration not found or you don't have access to it"
        )

    integration.provider_config['selected_event_type_uri'] = event_type_uri
    db.commit()
    return {"success": True}


# ========== GENERAL CALENDAR ENDPOINTS ==========

@router.get("/integrations")
async def list_calendar_integrations(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    List all calendar integrations for your business.
    Requires authenticated session.
    """
    if not current_user.active_business_id:
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    integrations = db.query(CalendarIntegration).filter(
        CalendarIntegration.business_id == current_user.active_business_id,
        CalendarIntegration.is_active.is_(True)
    ).all()

    return {
        "integrations": [
            {
                "id": str(i.id),
                "provider": i.provider,
                "is_primary": i.is_primary,
                "sync_direction": i.sync_direction,
                "last_sync_at": i.last_sync_at,
                "last_sync_status": i.last_sync_status
            }
            for i in integrations
        ]
    }


@router.delete("/integrations/{integration_id:uuid}")
async def remove_calendar_integration(
        integration_id: UUID = Path(..., description="The integration ID"),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Remove a calendar integration.
    Requires authenticated session.
    """
    if not current_user.active_business_id:
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    integration = db.query(CalendarIntegration).filter(
        CalendarIntegration.id == integration_id,
        CalendarIntegration.business_id == current_user.active_business_id
    ).first()

    if not integration:
        raise HTTPException(
            status_code=404,
            detail="Integration not found or you don't have access to it"
        )

    integration.is_active = False
    db.commit()
    return {"success": True}


# ========== AVAILABILITY ENDPOINTS ==========

@router.get("/availability")
async def get_availability(
        start_date: datetime = Query(..., description="Start date for availability search (ISO 8601)"),
        end_date: datetime = Query(..., description="End date for availability search (ISO 8601)"),
        duration_minutes: int = Query(30, ge=1, le=480, description="Appointment duration in minutes"),
        limit: int = Query(20, ge=1, le=100, description="Maximum number of slots to return"),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Get available appointment slots for your business.
    Requires authenticated session.
    """
    if not current_user.active_business_id:
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    # Query the database to get an integration INSTANCE
    integration = db.query(CalendarIntegration).filter(
        CalendarIntegration.business_id == current_user.active_business_id,
        CalendarIntegration.is_active.is_(True),
        CalendarIntegration.is_primary.is_(True)
    ).first()

    if not integration:
        raise HTTPException(
            status_code=404,
            detail="No calendar integration found for your business"
        )

    # Now 'integration' is an instance, not the class
    if integration.provider == 'google':
        service = GoogleCalendarService()
        slots = await service.get_available_slots(
            integration=integration,
            db=db,
            start_date=start_date,
            end_date=end_date,
            duration_minutes=duration_minutes
        )
    elif integration.provider == 'outlook':
        service = OutlookCalendarService()
        slots = await service.get_available_slots(
            integration=integration,
            db=db,
            start_date=start_date,
            end_date=end_date,
            duration_minutes=duration_minutes
        )
    elif integration.provider == 'calendly':
        raise HTTPException(
            status_code=400,
            detail="Calendly doesn't support availability checks"
        )
    else:
        raise HTTPException(
            status_code=400,
            detail="Unsupported calendar provider"
        )

    slots = slots[:limit]

    return {
        "business_id": str(current_user.active_business_id),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "duration_minutes": duration_minutes,
        "total_slots": len(slots),
        "slots": slots
    }


@router.get("/availability/next-available")
async def get_next_available_slot(
        duration_minutes: int = Query(30, ge=1, le=480, description="Appointment duration in minutes"),
        days_ahead: int = Query(14, ge=1, le=90, description="How many days to look ahead"),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Get the next available appointment slot.
    Useful for "earliest available" feature.
    Requires authenticated session.
    """
    if not current_user.active_business_id:
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    start_date = datetime.now(timezone.utc)
    end_date = start_date + timedelta(days=days_ahead)

    slots = await AvailabilityService.get_available_slots(
        db=db,
        business_id=str(current_user.active_business_id),
        start_date=start_date,
        end_date=end_date,
        duration_minutes=duration_minutes,
        limit=1  # Only need the first one
    )

    if not slots:
        return {
            "available": False,
            "message": f"No availability found in the next {days_ahead} days"
        }

    return {
        "available": True,
        "slot": slots[0]
    }


@router.get("/availability/summary")
async def get_availability_summary(
        date: str = Query(..., description="Date in YYYY-MM-DD format"),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Get availability summary for a specific date.
    Shows how many slots are available for that day.
    Requires authenticated session.
    """
    if not current_user.active_business_id:
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    try:
        target_date = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use YYYY-MM-DD"
        )

    start_dt = target_date.replace(hour=0, minute=0, second=0)
    end_dt = target_date.replace(hour=23, minute=59, second=59)

    slots = await AvailabilityService.get_available_slots(
        db=db,
        business_id=str(current_user.active_business_id),
        start_date=start_dt,
        end_date=end_dt,
        duration_minutes=30
    )

    # Group by hour for summary
    hourly_summary = {}
    for slot in slots:
        hour = datetime.fromisoformat(slot['start']).hour
        if hour not in hourly_summary:
            hourly_summary[hour] = 0
        hourly_summary[hour] += 1

    return {
        "date": date,
        "total_slots": len(slots),
        "hourly_breakdown": hourly_summary,
        "has_availability": len(slots) > 0
    }