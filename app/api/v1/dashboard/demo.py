"""
Demo API - Interactive SMS conversation testing for authenticated business owners
Dashboard authenticated endpoints - requires active business
UPDATED: Enhanced logging with consistent audit trail
NOW USING: OpenAI Agents SDK
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
import uuid

from app.config.database import get_db
from app.models.auth.user import User
from app.api.dependencies import get_current_user
from app.services.business.business_service import BusinessService
from app.services.ai.ai_service import AIService
from app.models.business.business import Business
from app.services.demo.demo_storage_service import DemoStorageService
from app.models.demo import DemoMessage
from app.services.demo.demo_session_service import DemoSessionService
from app.schemas.demo import (
    StartDemoRequest,
    StartDemoResponse,
    SendMessageRequest,
    SendMessageResponse,
    ConversationMessage,
    GetConversationResponse
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["dashboard-demo"])


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/start", response_model=StartDemoResponse)
async def start_demo(
        request: StartDemoRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Start a new demo conversation session."""
    logger.info(f"User {current_user.id} initiating demo session start")

    try:
        business_id = request.business_id or str(current_user.active_business_id)

        if not business_id:
            logger.warning(
                f"User {current_user.id} attempted to start demo without active business"
            )
            raise HTTPException(
                status_code=403,
                detail="User not associated with a business"
            )

        # Validate business exists and user has access
        business = db.query(Business).filter(Business.id == business_id).first()
        if not business:
            logger.warning(
                f"Demo start failed: Business {business_id} not found - User: {current_user.id}"
            )
            raise HTTPException(status_code=404, detail="Business not found")

        if str(business.id) != str(current_user.active_business_id):
            logger.warning(
                f"User {current_user.id} attempted to start demo for unauthorized business {business_id}"
            )
            raise HTTPException(
                status_code=403,
                detail="You don't have access to this business"
            )

        # Generate demo customer phone
        customer_phone = f"+1555DEMO{uuid.uuid4().hex[:4]}"
        business_name = business.name or "our business"

        logger.debug(
            f"Creating demo conversation - Business: {business_id}, User: {current_user.id}"
        )

        # Create demo conversation in database FIRST
        demo_conversation = DemoStorageService.create_demo_conversation(
            db=db,
            session_id=str(uuid.uuid4()),  # Temporary session_id, will be updated
            business_id=str(business.id),
            customer_phone=customer_phone
        )

        # NOW create session in DemoSessionService with the conversation_id
        session_id = DemoSessionService.create_session(
            conversation_id=str(demo_conversation.id),
            customer_phone=customer_phone,
            business_id=str(business.id)
        )

        # Update demo_conversation with the actual session_id
        demo_conversation.session_id = session_id

        # Add user_id to session for auth
        session = DemoSessionService.get_session(session_id)
        if session:
            session["user_id"] = str(current_user.id)
            session["flow_state"] = "gathering_info"
            session["customer_info"] = {}
            session["service_context"] = {}

        # Send initial greeting
        greeting = f"Hey, this is {business_name}. We have missed your call. How can we help?"

        # Log greeting message
        DemoStorageService.log_demo_message(
            db=db,
            demo_conversation_id=demo_conversation.id,
            role="assistant",
            content=greeting
        )

        db.commit()

        logger.info(
            f"Demo session created successfully - "
            f"Session ID: {session_id}, Business: {business_id}, "
            f"User: {current_user.id}, Conversation ID: {demo_conversation.id}"
        )

        return StartDemoResponse(
            session_id=session_id,
            customer_phone=customer_phone,
            greeting=greeting,
            business_name=business_name
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(
            f"Error starting demo session - User: {current_user.id}, Business: {business_id}: {e}",
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Failed to start demo: {str(e)}")


@router.post("/message", response_model=SendMessageResponse)
async def send_message(
        request: SendMessageRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Send a customer message and get AI response.
    Now using Agents SDK - function calls handled internally.
    """
    logger.info(
        f"User {current_user.id} sending demo message - Session: {request.session_id}"
    )
    logger.debug(f"Message length: {len(request.message)} chars")

    # Get session from DemoSessionService
    session = DemoSessionService.get_session(request.session_id)
    if not session:
        logger.warning(
            f"Demo message failed: Session {request.session_id} not found - User: {current_user.id}"
        )
        raise HTTPException(status_code=404, detail="Demo session not found or expired")

    # Verify user owns this demo session
    if str(session.get("user_id")) != str(current_user.id):
        logger.warning(
            f"User {current_user.id} attempted to access unauthorized demo session {request.session_id}"
        )
        raise HTTPException(
            status_code=403,
            detail="You don't have access to this demo session"
        )

    demo_conversation_id = session["conversation_id"]
    customer_phone = session["customer_phone"]
    business_id = session["business_id"]

    # Get business
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        logger.warning(
            f"Demo message failed: Business {business_id} not found for session {request.session_id}"
        )
        raise HTTPException(status_code=404, detail="Business not found")

    # Log customer message
    try:
        customer_message = DemoStorageService.log_demo_message(
            db=db,
            demo_conversation_id=demo_conversation_id,
            role="user",
            content=request.message
        )
        db.commit()
        logger.debug(
            f"Customer message logged - Session: {request.session_id}, "
            f"Conversation: {demo_conversation_id}"
        )
    except Exception as e:
        logger.error(
            f"Error logging customer message - Session: {request.session_id}: {e}",
            exc_info=True
        )
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to log message: {str(e)}")

    # Get conversation state from demo session
    conv_state = {
        "flow_state": session.get("flow_state", "gathering_info"),
        "customer_info": session.get("customer_info", {})
    }

    logger.debug(f"Current flow state: {conv_state['flow_state']}")

    # Get business context
    business_context = BusinessService.get_business_context(db, business_id)
    business_context["business_id"] = business_id

    # Apply session-specific overrides
    business_overrides = session.get("business_overrides", {})
    if business_overrides:
        business_context.update(business_overrides)
        logger.debug(f"Applied {len(business_overrides)} business overrides")

    # Get all previous messages for context
    try:
        demo_conversation = DemoStorageService.get_demo_conversation(db, request.session_id)
        if not demo_conversation:
            logger.error(
                f"Demo conversation not found in database - Session: {request.session_id}"
            )
            raise HTTPException(status_code=404, detail="Demo conversation not found in database")

        all_messages = db.query(DemoMessage).filter(
            DemoMessage.demo_conversation_id == demo_conversation.id
        ).order_by(DemoMessage.created_at).all()

        logger.debug(
            f"Retrieved {len(all_messages)} messages from conversation history - "
            f"Conversation: {demo_conversation.id}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error fetching demo conversation - Session: {request.session_id}: {e}",
            exc_info=True
        )
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to fetch conversation: {str(e)}")

    # Format messages for AI
    formatted_messages = []
    for msg in all_messages:
        role = msg.role
        if role == "customer":
            role = "user"
        formatted_messages.append({
            "role": role,
            "content": msg.content
        })

    logger.debug(f"Formatted {len(formatted_messages)} messages for AI context")

    # Initialize AI service
    ai_service = AIService()

    # Call Agents SDK - it handles ALL function calls internally
    logger.info(
        f"Calling Agents SDK for response generation - "
        f"Session: {request.session_id}, Business: {business_id}"
    )

    try:
        ai_response = await ai_service.generate_response(
            messages=formatted_messages,
            business_context=business_context,
            conversation_context=conv_state,
            db=db,
            conversation_id=demo_conversation_id,
            customer_phone=customer_phone,
            business_id=business_id,
            session_id=request.session_id
        )

        logger.info(
            f"Agents SDK response generated - Session: {request.session_id}, "
            f"Response length: {len(ai_response.get('content', ''))} chars"
        )

    except Exception as e:
        logger.error(
            f"Agents SDK error - Session: {request.session_id}, Business: {business_id}: {e}",
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"AI service error: {str(e)}")

    # Save final AI response to database with NEW session
    if ai_response.get("content"):
        try:
            from app.config.database import SessionLocal
            log_db = SessionLocal()
            try:
                DemoStorageService.log_demo_message(
                    db=log_db,
                    demo_conversation_id=demo_conversation_id,
                    role="assistant",
                    content=ai_response["content"]
                )
                log_db.commit()
                logger.debug(
                    f"Assistant response logged - Conversation: {demo_conversation_id}"
                )
            finally:
                log_db.close()
        except Exception as e:
            logger.error(
                f"Error logging assistant message - Conversation: {demo_conversation_id}: {e}",
                exc_info=True
            )
            # Don't raise - message was already processed

    # Get updated session state
    updated_session = DemoSessionService.get_session(request.session_id)
    flow_state = updated_session.get("flow_state", "gathering_info") if updated_session else "gathering_info"

    logger.info(
        f"Demo message processed successfully - "
        f"Session: {request.session_id}, Flow state: {flow_state}, User: {current_user.id}"
    )

    return SendMessageResponse(
        ai_response=ai_response.get("content", ""),
        conversation_state=flow_state
    )


@router.get("/conversation/{session_id}", response_model=GetConversationResponse)
async def get_conversation(
        session_id: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Get full conversation history for a demo session."""
    logger.info(
        f"User {current_user.id} requesting conversation history - Session: {session_id}"
    )

    session = DemoSessionService.get_session(session_id)
    if not session:
        logger.warning(
            f"Conversation retrieval failed: Session {session_id} not found - User: {current_user.id}"
        )
        raise HTTPException(status_code=404, detail="Demo session not found or expired")

    # Verify user owns this demo session
    if str(session.get("user_id")) != str(current_user.id):
        logger.warning(
            f"User {current_user.id} attempted to access unauthorized conversation {session_id}"
        )
        raise HTTPException(
            status_code=403,
            detail="You don't have access to this demo session"
        )

    demo_conversation_id = session["conversation_id"]

    # Get messages from database
    messages = db.query(DemoMessage).filter(
        DemoMessage.demo_conversation_id == demo_conversation_id
    ).order_by(DemoMessage.created_at).all()

    logger.info(
        f"Conversation history retrieved - "
        f"Session: {session_id}, Messages: {len(messages)}, "
        f"Conversation: {demo_conversation_id}"
    )

    # Get state from session
    conv_state = {
        "flow_state": session.get("flow_state", "gathering_info"),
        "customer_info": session.get("customer_info", {})
    }

    # Normalize roles for frontend
    normalized_messages = []
    for msg in messages:
        role = msg.role
        if role == "customer":
            role = "user"
        normalized_messages.append(
            ConversationMessage(
                role=role,
                content=msg.content,
                timestamp=msg.created_at
            )
        )

    logger.debug(
        f"Normalized {len(normalized_messages)} messages for response - "
        f"Flow state: {conv_state['flow_state']}"
    )

    return GetConversationResponse(
        messages=normalized_messages,
        state=conv_state
    )


@router.get("/sessions")
async def list_demo_sessions(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """List all demo sessions for the current user."""
    logger.info(f"User {current_user.id} requesting demo sessions list")

    if not current_user.active_business_id:
        logger.warning(
            f"User {current_user.id} attempted to list sessions without active business"
        )
        raise HTTPException(
            status_code=403,
            detail="User not associated with a business"
        )

    # Get all session IDs
    all_session_ids = DemoSessionService.get_all_sessions()
    logger.debug(f"Found {len(all_session_ids)} total sessions in system")

    # Filter sessions by user
    user_sessions = []
    for session_id in all_session_ids:
        session_data = DemoSessionService.get_session(session_id)
        if session_data and str(session_data.get("user_id")) == str(current_user.id):
            user_sessions.append({
                "session_id": session_id,
                "business_id": session_data["business_id"],
                "customer_phone": session_data["customer_phone"],
                "demo_conversation_id": session_data["conversation_id"]
            })

    logger.info(
        f"Demo sessions list retrieved - User: {current_user.id}, Count: {len(user_sessions)}"
    )

    return {
        "sessions": user_sessions,
        "total": len(user_sessions)
    }


@router.delete("/sessions/{session_id}")
async def delete_demo_session(
        session_id: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Delete a demo session."""
    logger.warning(
        f"User {current_user.id} DELETING demo session {session_id}"
    )

    session = DemoSessionService.get_session(session_id)
    if not session:
        logger.warning(
            f"Session deletion failed: Session {session_id} not found - User: {current_user.id}"
        )
        raise HTTPException(status_code=404, detail="Demo session not found")

    # Verify user owns this demo session
    if str(session.get("user_id")) != str(current_user.id):
        logger.warning(
            f"User {current_user.id} attempted to delete unauthorized session {session_id}"
        )
        raise HTTPException(
            status_code=403,
            detail="You don't have access to this demo session"
        )

    conversation_id = session.get("conversation_id")
    business_id = session.get("business_id")

    # Remove from memory
    DemoSessionService.cleanup_session(session_id)

    logger.warning(
        f"Demo session DELETED - "
        f"Session: {session_id}, Conversation: {conversation_id}, "
        f"Business: {business_id}, User: {current_user.id}"
    )

    return {"success": True, "message": "Demo session deleted"}