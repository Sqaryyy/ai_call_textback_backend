# ============================================================================
# app/services/conversation/conversation_state_service.py
# ============================================================================
"""Service for managing conversation states"""
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict
from sqlalchemy.orm import Session
from app.models.conversation_state import ConversationState


class ConversationStateService:
    """Handles conversation state management"""

    @staticmethod
    def get_or_create_state(
            db: Session,
            conversation_id: str,
            initial_state: Optional[Dict] = None
    ) -> ConversationState:
        """Get existing state or create new one"""
        state = db.query(ConversationState).filter(
            ConversationState.id == conversation_id
        ).first()

        if state:
            return state

        state = ConversationState(
            id=conversation_id,
            state_data=initial_state or {},
            flow_state="greeting",
            last_message_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            is_waiting_for_response=False,
            retry_count=0
        )

        db.add(state)
        db.commit()
        db.refresh(state)
        return state

    @staticmethod
    def update_state(
            db: Session,
            conversation_id: str,
            state_data: Optional[Dict] = None,
            flow_state: Optional[str] = None
    ) -> Optional[ConversationState]:
        """Update conversation state"""
        state = db.query(ConversationState).filter(
            ConversationState.id == conversation_id
        ).first()

        if not state:
            return None

        if state_data is not None:
            state.state_data = {**state.state_data, **state_data}
        if flow_state is not None:
            state.flow_state = flow_state

        state.last_message_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(state)
        return state
