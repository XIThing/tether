"""FastAPI application entrypoint for the agent server."""

from __future__ import annotations

import asyncio

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError

from tether.api import api_router, root_router
from tether.middleware import (
    http_exception_handler,
    request_logging_middleware,
    validation_exception_handler,
)
from tether.log_config import configure_logging
from tether.maintenance import maintenance_loop
from tether.settings import settings
from tether.startup import log_ui_urls
from tether.bridges.manager import bridge_manager

configure_logging()
logger = structlog.get_logger(__name__)

app = FastAPI()

app.middleware("http")(request_logging_middleware)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)


def _ensure_token() -> None:
    if settings.token() or settings.dev_mode():
        return
    raise RuntimeError(
        "TETHER_AGENT_TOKEN is required unless TETHER_AGENT_DEV_MODE=1"
    )


async def _init_bridges() -> None:
    """Initialize and register messaging platform bridges based on env vars."""
    # Telegram bridge
    telegram_token = settings.telegram_bot_token()
    telegram_group_id = settings.telegram_group_id()
    if telegram_token and telegram_group_id:
        try:
            from tether.bridges.telegram.bot import TelegramBridge

            bridge = TelegramBridge(
                bot_token=telegram_token,
                forum_group_id=telegram_group_id,
            )
            await bridge.start()
            bridge_manager.register_bridge("telegram", bridge)
            logger.info("Telegram bridge registered and started")
        except Exception:
            logger.exception("Failed to initialize Telegram bridge")

    # Slack bridge
    slack_token = settings.slack_bot_token()
    slack_channel = settings.slack_channel_id()
    if slack_token and slack_channel:
        try:
            from tether.bridges.slack.bot import SlackBridge

            bridge = SlackBridge(
                bot_token=slack_token,
                channel_id=slack_channel,
            )
            await bridge.start()
            bridge_manager.register_bridge("slack", bridge)
            logger.info("Slack bridge registered and started")
        except Exception:
            logger.exception("Failed to initialize Slack bridge")

    # Discord bridge
    discord_token = settings.discord_bot_token()
    discord_channel = settings.discord_channel_id()
    if discord_token and discord_channel:
        try:
            from tether.bridges.discord.bot import DiscordBridge

            bridge = DiscordBridge(
                bot_token=discord_token,
                channel_id=discord_channel,
            )
            await bridge.start()
            bridge_manager.register_bridge("discord", bridge)
            logger.info("Discord bridge registered and started")
        except Exception:
            logger.exception("Failed to initialize Discord bridge")


@app.on_event("startup")
async def _start_maintenance() -> None:
    _ensure_token()
    app.state.agent_token = settings.token()
    await _init_bridges()
    asyncio.create_task(maintenance_loop())
    log_ui_urls(port=settings.port())


app.include_router(api_router)
app.include_router(root_router)

def run() -> None:
    """Entry point for the tether-agent console script."""
    _ensure_token()
    app.state.agent_token = settings.token()
    uvicorn.run(
        "tether.main:app",
        host=settings.host(),
        port=settings.port(),
        reload=False,
    )


if __name__ == "__main__":
    run()
else:
    app.state.agent_token = settings.token()
