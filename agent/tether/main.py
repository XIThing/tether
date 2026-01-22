"""FastAPI application entrypoint for the agent server."""

from __future__ import annotations

import asyncio
import os

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError

from tether.api import api_router, root_router
from tether.http import (
    http_exception_handler,
    request_logging_middleware,
    validation_exception_handler,
)
from tether.logging import configure_logging
from tether.maintenance import maintenance_loop
from tether.startup import log_ui_urls

configure_logging()

app = FastAPI()

app.middleware("http")(request_logging_middleware)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)


def _is_dev_mode() -> bool:
    return os.environ.get("AGENT_DEV_MODE", "").strip().lower() in ("1", "true", "yes")


def _load_agent_token() -> str:
    return os.environ.get("AGENT_TOKEN", "")


def _ensure_token() -> None:
    if _load_agent_token() or _is_dev_mode():
        return
    raise RuntimeError("AGENT_TOKEN is required unless AGENT_DEV_MODE=1")


@app.on_event("startup")
async def _start_maintenance() -> None:
    _ensure_token()
    app.state.agent_token = _load_agent_token()
    asyncio.create_task(maintenance_loop())
    log_ui_urls(port=int(os.environ.get("AGENT_PORT", "8787")))


app.include_router(api_router)
app.include_router(root_router)

if __name__ == "__main__":
    import uvicorn

    _ensure_token()
    app.state.agent_token = _load_agent_token()
    host = os.environ.get("AGENT_HOST", "0.0.0.0")
    port = int(os.environ.get("AGENT_PORT", "8787"))
    uvicorn.run("tether.main:app", host=host, port=port, reload=False)
else:
    app.state.agent_token = _load_agent_token()
