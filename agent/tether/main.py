"""FastAPI application entrypoint for the agent server."""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import structlog

from tether.logging import configure_logging

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

configure_logging()

from tether.api import require_token, router as api_router
from tether.models import ErrorDetail, ErrorResponse
from tether.sse import stream_response
from tether.store import store

app = FastAPI()

logger = structlog.get_logger("tether.http")


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
    )
    start_time = time.monotonic()
    logger.info("Request started")
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.monotonic() - start_time) * 1000
        logger.exception("Request failed", duration_ms=round(duration_ms, 2))
        structlog.contextvars.clear_contextvars()
        raise
    duration_ms = (time.monotonic() - start_time) * 1000
    logger.info(
        "Request completed",
        status_code=response.status_code,
        duration_ms=round(duration_ms, 2),
    )
    structlog.contextvars.clear_contextvars()
    return response

def _error(code: str, message: str, status_code: int) -> None:
    """Raise an HTTPException with a structured error payload.

    Args:
        code: Stable error code string.
        message: Human-readable error message.
        status_code: HTTP status to return.
    """
    raise HTTPException(
        status_code=status_code,
        detail=ErrorResponse(error=ErrorDetail(code=code, message=message, details=None)).dict(),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Convert HTTPException into the protocol error envelope.

    Args:
        request: Incoming request that triggered the error.
        exc: Raised HTTPException instance.
    """
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    code_map = {
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "INVALID_STATE",
        422: "VALIDATION_ERROR",
        500: "INTERNAL_ERROR",
    }
    code = code_map.get(exc.status_code, "INTERNAL_ERROR")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": code,
                "message": str(exc.detail),
                "details": None,
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Convert validation errors into the protocol error envelope.

    Args:
        request: Incoming request that failed validation.
        exc: Validation exception with details.
    """
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid request",
                "details": exc.errors(),
            }
        },
    )


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"ok": True, "version": "0.1.0", "protocol": 1}


@app.get("/events/sessions/{session_id}", tags=["events"])
async def events(session_id: str, _: None = Depends(require_token)):
    """SSE stream for a session's events."""
    session = store.get_session(session_id)
    if not session:
        _error("NOT_FOUND", "Session not found", 404)
    return stream_response(session_id)


app.include_router(api_router)


static_root = Path(__file__).parent / "static_ui"


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str, request: Request):
    """Serve static UI assets or fall back to index.html for SPA routes."""
    if full_path.startswith("api") or full_path.startswith("events") or full_path == "health":
        # Prevent SPA fallback from masking API and SSE routes.
        _error("NOT_FOUND", "Not found", 404)
    if full_path:
        file_path = static_root / full_path
        if file_path.is_file():
            return FileResponse(file_path)
    index_path = static_root / "index.html"
    if index_path.is_file():
        return FileResponse(index_path)
    return PlainTextResponse("UI not built", status_code=404)


if __name__ == "__main__":
    import uvicorn

    app.state.agent_token = os.environ.get("AGENT_TOKEN", "")
    uvicorn.run("tether.main:app", host="0.0.0.0", port=8787, reload=False)
else:
    app.state.agent_token = os.environ.get("AGENT_TOKEN", "")
