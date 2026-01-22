"""Background maintenance tasks for pruning and idle timeouts."""

from __future__ import annotations

import asyncio
import os
import time

import structlog

from tether.api.emit import emit_state
from tether.api.runner_events import runner
from tether.api.state import transition
from tether.models import SessionState
from tether.store import store

logger = structlog.get_logger("tether.maintenance")


def _parse_ts(value: str) -> float | None:
    try:
        return time.mktime(time.strptime(value, "%Y-%m-%dT%H:%M:%SZ"))
    except Exception:
        return None


async def maintenance_loop() -> None:
    """Periodically prune sessions and stop idle runs."""
    retention_days = int(os.environ.get("AGENT_SESSION_RETENTION_DAYS", "7"))
    idle_timeout_s = int(os.environ.get("AGENT_SESSION_IDLE_SECONDS", "0"))
    interval_s = int(os.environ.get("AGENT_MAINTENANCE_SECONDS", "60"))
    while True:
        try:
            removed = store.prune_sessions(retention_days)
            if removed:
                logger.info("Pruned sessions", count=removed)
            if idle_timeout_s > 0:
                now_ts = time.time()
                for session in list(store.list_sessions()):
                    if session.state != SessionState.RUNNING:
                        continue
                    last = _parse_ts(session.last_activity_at)
                    if last is None:
                        continue
                    if now_ts - last > idle_timeout_s:
                        logger.warning("Idle timeout reached; stopping session", session_id=session.id)
                        transition(session, SessionState.STOPPING)
                        await emit_state(session)
                        await runner.stop(session.id)
                        transition(session, SessionState.STOPPED, ended_at=True)
                        await emit_state(session)
        except Exception:
            logger.exception("Maintenance loop failed")
        await asyncio.sleep(interval_s)
