"""Debug endpoints for local development."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends

from tether.api.deps import require_token
from tether.api.errors import raise_http_error
from tether.models import SessionState
from tether.store import store

router = APIRouter(tags=["debug"])
logger = structlog.get_logger("tether.api.debug")


@router.post("/debug/clear_data", response_model=dict)
async def clear_data(_: None = Depends(require_token)) -> dict:
    """Clear all persisted sessions and event logs (debug only)."""
    for session in store.list_sessions():
        if session.state in (SessionState.RUNNING, SessionState.STOPPING):
            raise_http_error("INVALID_STATE", "Cannot clear data while sessions are active", 409)
    store.clear_all_data()
    logger.warning("Cleared all session data")
    return {"ok": True}
