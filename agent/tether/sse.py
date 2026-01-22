"""Helpers for producing server-sent event (SSE) responses."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator

from starlette.responses import StreamingResponse

from tether.store import store


def sse_event(data: dict) -> str:
    """Serialize an event payload into SSE wire format."""
    payload = json.dumps(data, separators=(",", ":"))
    return f"data: {payload}\n\n"


async def sse_stream(session_id: str) -> AsyncIterator[bytes]:
    """Stream SSE events for a session as UTF-8 bytes."""
    queue = store.new_subscriber(session_id)
    heartbeat_s = float(os.environ.get("SSE_KEEPALIVE_SECONDS", "15"))
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=heartbeat_s)
            except asyncio.TimeoutError:
                yield b": keepalive\n\n"
                continue
            yield sse_event(event).encode("utf-8")
    finally:
        store.remove_subscriber(session_id, queue)


def stream_response(session_id: str) -> StreamingResponse:
    """Build a StreamingResponse for the session SSE feed."""
    return StreamingResponse(sse_stream(session_id), media_type="text/event-stream")
