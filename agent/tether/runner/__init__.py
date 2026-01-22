"""Runner selection utilities for choosing an execution backend."""

from __future__ import annotations

import os

from tether.runner.base import Runner, RunnerEvents
from tether.runner.codex_v1 import CodexV1Runner
from tether.runner.sidecar import SidecarRunner


def get_runner(events: RunnerEvents) -> Runner:
    """Return the configured runner adapter based on environment settings.

    Args:
        events: RunnerEvents callback sink.
    """
    name = os.environ.get("AGENT_ADAPTER", "codex_v1").strip().lower()
    if name in ("codex_v1", "codex"):
        return CodexV1Runner(events)
    if name in ("sidecar", "codex_sidecar"):
        base_url = os.environ.get("SIDECAR_URL")
        return SidecarRunner(events, base_url=base_url)
    raise ValueError(f"Unknown agent adapter: {name}")


__all__ = ["get_runner", "Runner", "RunnerEvents"]
