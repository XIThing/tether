"""Runner selection utilities for choosing an execution backend."""

from __future__ import annotations

import os

from tether.runner.base import Runner, RunnerEvents
from tether.runner.claude import ClaudeRunner
from tether.runner.codex_cli import CodexCliRunner
from tether.runner.sidecar import SidecarRunner

# Cache the runner type after first initialization
_active_runner_type: str | None = None


def get_runner(events: RunnerEvents) -> Runner:
    """Return the configured runner adapter based on environment settings.

    Args:
        events: RunnerEvents callback sink.
    """
    global _active_runner_type
    name = os.environ.get("AGENT_ADAPTER", "codex_cli").strip().lower()
    if name in ("codex_cli", "codex_v1", "codex"):
        runner = CodexCliRunner(events)
        _active_runner_type = runner.runner_type
        return runner
    if name in ("codex_sdk_sidecar", "sidecar", "codex_sidecar"):
        base_url = os.environ.get("CODEX_SDK_SIDECAR_URL") or os.environ.get("SIDECAR_URL")
        runner = SidecarRunner(events, base_url=base_url)
        _active_runner_type = runner.runner_type
        return runner
    if name in ("claude", "anthropic"):
        runner = ClaudeRunner(events)
        _active_runner_type = runner.runner_type
        return runner
    raise ValueError(f"Unknown agent adapter: {name}")


def get_runner_type() -> str | None:
    """Return the runner type of the active runner, or None if not initialized."""
    return _active_runner_type


__all__ = ["get_runner", "get_runner_type", "Runner", "RunnerEvents"]
