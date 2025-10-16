# app/api/v1/calendar.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.models import CalendarIntegration
from app.services.calendar.google_calendar_service import GoogleCalendarService
from app.services.calendar.outlook_service import OutlookCalendarService
from app.services.calendar.calendly_service import CalendlyService
from app.config.database import get_db

from datetime import datetime, timedelta, timezone
from app.services.availability.availability_service import AvailabilityService

router = APIRouter(tags=["calendar"])  # Remove prefix


# ========== GOOGLE CALENDAR ==========
@router.post("/google/authorize/{business_id}")
async def initiate_google_auth(business_id: str):
    """Returns authorization URL for business owner to visit"""
    service = GoogleCalendarService()
    auth_url = service.generate_authorization_url(business_id)
    return {"authorization_url": auth_url}


@router.get("/google/callback")
async def google_callback(
        code: str,
        state: str,  # business_id
        db: Session = Depends(get_db)
):
    """Google redirects here after authorization"""
    service = GoogleCalendarService()
    integration = service.handle_oauth_callback(code, state, db)

    return {
        "success": True,
        "integration_id": str(integration.id),
        "calendars": integration.provider_config['calendar_list']
    }


@router.patch("/google/{integration_id}/select-calendar")
async def select_google_calendar(
        integration_id: str,
        calendar_id: str = Query(...),
        db: Session = Depends(get_db)
):
    """Let business choose which Google calendar to use"""
    integration = db.query(CalendarIntegration).filter_by(id=integration_id).first()
    if not integration or integration.provider != 'google':
        raise HTTPException(status_code=404, detail="Google integration not found")

    integration.provider_config['selected_calendar_id'] = calendar_id
    db.commit()
    return {"success": True}


# ========== OUTLOOK CALENDAR ==========
@router.post("/outlook/authorize/{business_id}")
async def initiate_outlook_auth(business_id: str):
    """Returns authorization URL for business owner to visit"""
    service = OutlookCalendarService()
    auth_url = await service.generate_authorization_url(business_id)  # ← ADD await
    return {"authorization_url": auth_url}


@router.get("/outlook/callback")
async def outlook_callback(
        code: str,
        state: str,  # business_id
        db: Session = Depends(get_db)
):
    """Microsoft redirects here after authorization"""
    service = OutlookCalendarService()
    integration = await service.handle_oauth_callback(code, state, db)  # ← ADD await

    return {
        "success": True,
        "integration_id": str(integration.id),
        "calendars": integration.provider_config['calendar_list']
    }


@router.patch("/outlook/{integration_id}/select-calendar")
async def select_outlook_calendar(
        integration_id: str,
        calendar_id: str = Query(...),
        db: Session = Depends(get_db)
):
    """Let business choose which Outlook calendar to use"""
    integration = db.query(CalendarIntegration).filter_by(id=integration_id).first()
    if not integration or integration.provider != 'outlook':
        raise HTTPException(status_code=404, detail="Outlook integration not found")

    integration.provider_config['selected_calendar_id'] = calendar_id
    db.commit()
    return {"success": True}


# ========== CALENDLY ==========
@router.post("/calendly/setup/{business_id}")
async def setup_calendly(
        business_id: str,
        personal_access_token: str,
        db: Session = Depends(get_db)
):
    """Business owner provides their Calendly Personal Access Token"""
    service = CalendlyService()
    try:
        integration = service.setup_integration(business_id, personal_access_token, db)
        return {
            "success": True,
            "integration_id": str(integration.id),
            "event_types": integration.provider_config['event_types']
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/calendly/{integration_id}/select-event-type")
async def select_calendly_event_type(
        integration_id: str,
        event_type_uri: str = Query(...),
        db: Session = Depends(get_db)
):
    """Let business choose which Calendly event type to use"""
    integration = db.query(CalendarIntegration).filter_by(id=integration_id).first()
    if not integration or integration.provider != 'calendly':
        raise HTTPException(status_code=404, detail="Calendly integration not found")

    integration.provider_config['selected_event_type_uri'] = event_type_uri
    db.commit()
    return {"success": True}


# ========== GENERAL CALENDAR ENDPOINTS ==========
@router.get("/{business_id}/integrations")
async def list_calendar_integrations(
        business_id: str,
        db: Session = Depends(get_db)
):
    """List all calendar integrations for a business"""
    integrations = db.query(CalendarIntegration).filter_by(
        business_id=business_id,
        is_active=True
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


@router.delete("/{integration_id}")
async def remove_calendar_integration(
        integration_id: str,
        db: Session = Depends(get_db)
):
    """Remove a calendar integration"""
    integration = db.query(CalendarIntegration).filter_by(id=integration_id).first()
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    integration.is_active = False
    db.commit()
    return {"success": True}


@router.patch("/{integration_id}/set-primary")
async def set_primary_calendar(
        integration_id: str,
        db: Session = Depends(get_db)
):
    """Set this integration as the primary calendar"""
    integration = db.query(CalendarIntegration).filter_by(id=integration_id).first()
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    # Unset other primary calendars for this business
    db.query(CalendarIntegration).filter_by(
        business_id=integration.business_id
    ).update({"is_primary": False})

    integration.is_primary = True
    db.commit()
    return {"success": True}

# ========== AVAILABILITY ENDPOINTS ==========
# app/api/v1/endpoints/calendar.py

@router.get("/{business_id}/availability")
async def get_availability(
        business_id: str,
        start_date: datetime,
        end_date: datetime,
        duration_minutes: int = 30,
        limit: int = 20,
        db: Session = Depends(get_db)
):
    # Query the database to get an integration INSTANCE
    integration = db.query(CalendarIntegration).filter(
        CalendarIntegration.business_id == business_id,
        CalendarIntegration.is_active == True,
        CalendarIntegration.is_primary == True
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="No calendar integration found")

    # Now 'integration' is an instance, not the class
    if integration.provider == 'google':
        from app.services.calendar.google_calendar_service import GoogleCalendarService
        service = GoogleCalendarService()
        slots = await service.get_available_slots(
            integration=integration,  # This is now an instance
            db=db,
            start_date=start_date,
            end_date=end_date,
            duration_minutes=duration_minutes
        )
    elif integration.provider == 'outlook':
        from app.services.calendar.outlook_service import OutlookCalendarService
        service = OutlookCalendarService()
        slots = await service.get_available_slots(
            integration=integration,
            db=db,
            start_date=start_date,
            end_date=end_date,
            duration_minutes=duration_minutes
        )
    elif integration.provider == 'calendly':
        raise HTTPException(status_code=400, detail="Calendly doesn't support availability checks")
    else:
        raise HTTPException(status_code=400, detail="Unsupported calendar provider")

    slots = slots[:limit]

    return {
        "business_id": business_id,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "duration_minutes": duration_minutes,
        "total_slots": len(slots),
        "slots": slots
    }
@router.get("/{business_id}/availability/next-available")
async def get_next_available_slot(
        business_id: str,
        duration_minutes: int = Query(30),
        days_ahead: int = Query(14, description="How many days to look ahead"),
        db: Session = Depends(get_db)
):
    """
    Get the next available appointment slot
    Useful for "earliest available" feature
    """
    start_date = datetime.now(timezone.utc)
    end_date = start_date + timedelta(days=days_ahead)

    slots = await AvailabilityService.get_available_slots(
        db=db,
        business_id=business_id,
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


@router.get("/{business_id}/availability/summary")
async def get_availability_summary(
        business_id: str,
        date: str = Query(..., description="Date in YYYY-MM-DD format"),
        db: Session = Depends(get_db)
):
    """
    Get availability summary for a specific date
    Shows how many slots are available for that day
    """
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
        business_id=business_id,
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
