"""External agent API endpoints (WebSocket and REST).

This module provides the agent-facing API for external agents to connect,
send events, receive human input, and manage approvals.
"""

import asyncio
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from tether.bridges.base import ApprovalRequest
from tether.bridges.manager import bridge_manager
from tether.models import SessionState
from tether.store import store

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/external", tags=["external_agents"])


# --- Request/Response Models ---


class AgentMetadata(BaseModel):
    """Metadata about an external agent."""

    name: str
    type: str
    icon: str = "🤖"
    workspace: str | None = None


class CreateSessionRequest(BaseModel):
    """Request to create a new session for an external agent."""

    agent_metadata: AgentMetadata
    session_name: str
    platform: str = "telegram"  # Default platform


class CreateSessionResponse(BaseModel):
    """Response after creating a session."""

    session_id: str
    platform: str
    thread_info: dict


class AgentEvent(BaseModel):
    """Event from agent to Tether."""

    type: str  # "output", "approval_request", "status"
    data: dict


class TetherEvent(BaseModel):
    """Event from Tether to agent."""

    type: str  # "human_input", "approval_response"
    data: dict


# --- REST Endpoints ---


@router.post("/sessions", response_model=CreateSessionResponse, status_code=201)
async def create_external_session(req: CreateSessionRequest) -> CreateSessionResponse:
    """Create a new session for an external agent.

    The session is created in CREATED state and a messaging thread is
    automatically created on the configured platform.

    Args:
        req: Session creation request with agent metadata.

    Returns:
        Session ID and thread information.
    """
    # Create session
    session = store.create_session(
        repo_id="external_agent",  # Placeholder for external agents
        base_ref=None,
    )

    # Store agent metadata on session
    session.external_agent_id = f"agent_{uuid.uuid4().hex[:8]}"
    session.external_agent_name = req.agent_metadata.name
    session.external_agent_type = req.agent_metadata.type
    session.external_agent_icon = req.agent_metadata.icon
    session.external_agent_workspace = req.agent_metadata.workspace
    session.name = req.session_name
    session.platform = req.platform
    store.update_session(session)

    # Create messaging thread
    try:
        thread_info = await bridge_manager.create_thread(
            session.id, req.session_name, platform=req.platform
        )
        session.platform_thread_id = thread_info.get("thread_id")
        store.update_session(session)
    except ValueError as e:
        # Platform not configured - cleanup and return error
        store.delete_session(session.id)
        raise HTTPException(status_code=400, detail=str(e))

    logger.info(
        "External session created",
        session_id=session.id,
        agent_name=req.agent_metadata.name,
        platform=req.platform,
    )

    return CreateSessionResponse(
        session_id=session.id,
        platform=req.platform,
        thread_info=thread_info,
    )


@router.post("/sessions/{session_id}/events")
async def post_agent_event(session_id: str, event: AgentEvent) -> dict:
    """Post an event from an agent to Tether.

    Args:
        session_id: Internal Tether session ID.
        event: Agent event (output, approval_request, or status).

    Returns:
        Acknowledgement dict.
    """
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session.platform:
        raise HTTPException(status_code=400, detail="Session has no platform binding")

    # Handle different event types
    if event.type == "output":
        text = event.data.get("text", "")
        metadata = event.data.get("metadata")
        await bridge_manager.route_output(
            session_id, text, platform=session.platform, metadata=metadata
        )

    elif event.type == "approval_request":
        request = ApprovalRequest(**event.data)
        await bridge_manager.route_approval(
            session_id, request, platform=session.platform
        )

    elif event.type == "status":
        status = event.data.get("status", "")
        metadata = event.data.get("metadata")
        await bridge_manager.route_status(
            session_id, status, platform=session.platform, metadata=metadata
        )

    else:
        raise HTTPException(status_code=400, detail=f"Unknown event type: {event.type}")

    return {"ok": True}


@router.get("/sessions/{session_id}/events")
async def get_pending_events(session_id: str, since_seq: int = 0) -> dict:
    """Get pending events for an agent (human input, approval responses).

    Args:
        session_id: Internal Tether session ID.
        since_seq: Only return events after this sequence number.

    Returns:
        List of pending events.
    """
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Read events from log
    events = store.read_event_log(session_id, since_seq=since_seq)

    # Filter for agent-relevant events (human_input, approval_response)
    agent_events = []
    for evt in events:
        if evt.get("type") in ("human_input", "approval_response"):
            agent_events.append({
                "type": evt["type"],
                "data": evt.get("data", {}),
                "seq": evt.get("seq"),
            })

    return {"events": agent_events}


@router.post("/sessions/{session_id}/approvals/{request_id}/respond")
async def respond_to_approval(
    session_id: str, request_id: str, response: dict
) -> dict:
    """Respond to an approval request (called by bridge, not agent).

    Args:
        session_id: Internal Tether session ID.
        request_id: Approval request ID.
        response: Response details (option_selected, username, etc.).

    Returns:
        Success status.
    """
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    success = store.resolve_pending_permission(session_id, request_id, response)

    if not success:
        raise HTTPException(
            status_code=404, detail="Approval request not found or already resolved"
        )

    # Emit approval response event
    await store.emit(session_id, {
        "session_id": session_id,
        "ts": store._now(),
        "seq": store.next_seq(session_id),
        "type": "approval_response",
        "data": {
            "request_id": request_id,
            **response,
        },
    })

    return {"ok": True}


# --- WebSocket Endpoint ---


@router.websocket("/ws")
async def agent_websocket(websocket: WebSocket) -> None:
    """WebSocket endpoint for external agents.

    Provides bidirectional event streaming:
    - Agent sends: registration, session creation, output, approval requests, status
    - Tether sends: human input, approval responses

    Protocol:
    1. Agent connects and sends registration message
    2. Agent can create sessions
    3. Agent streams events, receives human input/approvals in real-time
    4. On disconnect, session persists and events are queued for replay
    """
    await websocket.accept()
    agent_id: str | None = None
    session_id: str | None = None

    try:
        # Receive registration message
        reg_data = await websocket.receive_json()
        if reg_data.get("type") != "register":
            await websocket.send_json({"error": "First message must be registration"})
            await websocket.close()
            return

        # Register agent
        agent_metadata = reg_data.get("agent_metadata", {})
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"

        await websocket.send_json({
            "type": "registered",
            "agent_id": agent_id,
        })

        logger.info(
            "Agent registered via WebSocket",
            agent_id=agent_id,
            agent_name=agent_metadata.get("name"),
        )

        # Main message loop
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "create_session":
                # Create session
                sess_name = data.get("session_name", "External Agent Session")
                platform = data.get("platform", "telegram")

                session = store.create_session(repo_id="external_agent", base_ref=None)
                session.external_agent_id = agent_id
                session.external_agent_name = agent_metadata.get("name", "External Agent")
                session.external_agent_type = agent_metadata.get("type", "unknown")
                session.external_agent_icon = agent_metadata.get("icon", "🤖")
                session.external_agent_workspace = agent_metadata.get("workspace")
                session.name = sess_name
                session.platform = platform
                store.update_session(session)

                # Create messaging thread
                try:
                    thread_info = await bridge_manager.create_thread(
                        session.id, sess_name, platform=platform
                    )
                    session.platform_thread_id = thread_info.get("thread_id")
                    store.update_session(session)
                except ValueError as e:
                    await websocket.send_json({
                        "type": "error",
                        "message": str(e),
                    })
                    continue

                session_id = session.id

                await websocket.send_json({
                    "type": "session_created",
                    "session_id": session_id,
                    "thread_info": thread_info,
                })

            elif msg_type == "event":
                # Handle agent events (output, approval_request, status)
                if not session_id:
                    await websocket.send_json({"error": "No active session"})
                    continue

                session = store.get_session(session_id)
                if not session or not session.platform:
                    await websocket.send_json({"error": "Invalid session"})
                    continue

                event_data = data.get("data", {})
                event_type = event_data.get("type")

                if event_type == "output":
                    text = event_data.get("text", "")
                    await bridge_manager.route_output(
                        session_id, text, platform=session.platform
                    )

                elif event_type == "approval_request":
                    request = ApprovalRequest(**event_data.get("request", {}))
                    await bridge_manager.route_approval(
                        session_id, request, platform=session.platform
                    )

                elif event_type == "status":
                    status = event_data.get("status", "")
                    await bridge_manager.route_status(
                        session_id, status, platform=session.platform
                    )

                await websocket.send_json({"type": "ack"})

            elif msg_type == "poll_events":
                # Poll for pending events (human input, approval responses)
                if not session_id:
                    await websocket.send_json({"events": []})
                    continue

                since_seq = data.get("since_seq", 0)
                events = store.read_event_log(session_id, since_seq=since_seq)

                # Filter for agent-relevant events
                agent_events = [
                    evt for evt in events
                    if evt.get("type") in ("human_input", "approval_response")
                ]

                await websocket.send_json({
                    "type": "events",
                    "events": agent_events,
                })

    except WebSocketDisconnect:
        logger.info("Agent disconnected", agent_id=agent_id, session_id=session_id)
        if session_id:
            # Emit disconnect notice
            await store.emit(session_id, {
                "session_id": session_id,
                "ts": store._now(),
                "seq": store.next_seq(session_id),
                "type": "agent_disconnected",
                "data": {"agent_id": agent_id},
            })

    except Exception as e:
        logger.error("WebSocket error", error=str(e), agent_id=agent_id)
        try:
            await websocket.send_json({"error": str(e)})
        except:
            pass
        await websocket.close()
