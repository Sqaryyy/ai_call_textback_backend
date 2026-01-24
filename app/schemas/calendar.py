# app/schemas/calendar.py
from pydantic import BaseModel, Field
from typing import Literal, Optional


class SelectCalendarRequest(BaseModel):
    sync_direction: Literal["read_only", "write_only", "bidirectional"] = Field(
        default="bidirectional",
        description="Sync direction for the calendar integration"
    )

    class Config:
        # This ensures the model uses defaults even when no body is provided
        use_enum_values = True


class SelectCalendarResponse(BaseModel):
    success: bool
    selected_calendar_id: str
    sync_direction: str
    calendar_name: Optional[str] = None  # ← ADD THIS