"""SSE event endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from tether.api.deps import require_token
from tether.api.errors import raise_http_error
from tether.sse import stream_response
from tether.store import store

router = APIRouter(tags=["events"])


@router.get("/events/sessions/{session_id}")
async def events(session_id: str, _: None = Depends(require_token)):
    """SSE stream for a session's events."""
    session = store.get_session(session_id)
    if not session:
        raise_http_error("NOT_FOUND", "Session not found", 404)
    return stream_response(session_id)
