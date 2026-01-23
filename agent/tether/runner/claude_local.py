"""Runner adapter that uses the Claude Agent SDK (local OAuth via Claude CLI)."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import structlog

from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
    ThinkingBlock,
)

from tether.models import SessionState
from tether.runner.base import RunnerEvents
from tether.store import store

logger = structlog.get_logger("tether.runner.claude_local")

HEARTBEAT_INTERVAL = 5.0


class ClaudeLocalRunner:
    """Runner that uses the Claude Agent SDK with local OAuth authentication.

    This runner spawns the Claude Code binary which handles authentication
    using OAuth tokens stored in ~/.claude/.credentials.json.
    No ANTHROPIC_API_KEY required.
    """

    runner_type: str = "claude-local"

    def __init__(self, events: RunnerEvents) -> None:
        self._events = events
        # Map our session_id -> SDK session_id for resume
        self._sdk_sessions: dict[str, str] = {}
        # Active query tasks per session
        self._tasks: dict[str, asyncio.Task] = {}

    async def start(self, session_id: str, prompt: str, approval_choice: int) -> None:
        """Start a Claude conversation session.

        Args:
            session_id: Internal session identifier.
            prompt: Initial prompt to send.
            approval_choice: Approval policy (mapped to permission_mode).
        """
        logger.info("Starting claude_local session", session_id=session_id, approval_choice=approval_choice)
        store.clear_stop_requested(session_id)

        # Get session to determine working directory
        session = store.get_session(session_id)
        cwd = session.directory if session and session.directory else None

        # Map approval_choice to permission_mode
        permission_mode = self._map_permission_mode(approval_choice)

        # Start the query task
        task = asyncio.create_task(
            self._run_query(session_id, prompt, cwd, permission_mode, resume=None)
        )
        self._tasks[session_id] = task

    async def send_input(self, session_id: str, text: str) -> None:
        """Send follow-up input to the conversation.

        Args:
            session_id: Internal session identifier.
            text: Follow-up input text.
        """
        if not text.strip():
            return

        # Get SDK session_id for resume
        sdk_session_id = self._sdk_sessions.get(session_id)

        # Get session to determine working directory
        session = store.get_session(session_id)
        cwd = session.directory if session and session.directory else None

        # Check if there's an active task
        existing_task = self._tasks.get(session_id)
        if existing_task and not existing_task.done():
            logger.warning(
                "send_input called while query still running",
                session_id=session_id,
            )
            return

        store.clear_stop_requested(session_id)

        # Start new query with resume
        task = asyncio.create_task(
            self._run_query(
                session_id,
                text,
                cwd,
                permission_mode="default",
                resume=sdk_session_id,
            )
        )
        self._tasks[session_id] = task

    async def stop(self, session_id: str) -> int | None:
        """Stop the Claude session.

        Args:
            session_id: Internal session identifier.

        Returns:
            Exit code (always 0 for clean stop).
        """
        store.request_stop(session_id)

        task = self._tasks.get(session_id)
        if task and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        self._tasks.pop(session_id, None)
        store.clear_stop_requested(session_id)

        return 0

    def _map_permission_mode(self, approval_choice: int) -> str:
        """Map approval_choice to SDK permission_mode."""
        # 0 = suggest (default), 1 = auto-approve edits, 2 = full auto
        if approval_choice == 2:
            return "bypassPermissions"
        elif approval_choice == 1:
            return "acceptEdits"
        else:
            return "default"

    async def _run_query(
        self,
        session_id: str,
        prompt: str,
        cwd: str | None,
        permission_mode: str,
        resume: str | None,
    ) -> None:
        """Run the Agent SDK query and emit events.

        Args:
            session_id: Internal session identifier.
            prompt: User prompt.
            cwd: Working directory for the agent.
            permission_mode: SDK permission mode.
            resume: SDK session ID to resume, if any.
        """
        start_time = time.monotonic()
        heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(session_id, start_time)
        )

        try:
            options = ClaudeAgentOptions(
                cwd=Path(cwd) if cwd else None,
                permission_mode=permission_mode,
                resume=resume,
                # Only continue conversation when resuming an existing session
                continue_conversation=resume is not None,
                # Don't load external settings that might override permission_mode
                setting_sources=[],
            )

            logger.info("Starting query", session_id=session_id, cwd=cwd, permission_mode=permission_mode, resume=resume)
            async for message in query(prompt=prompt, options=options):
                # Check for stop request
                if store.is_stop_requested(session_id):
                    break

                logger.debug("Received message", session_id=session_id, message_type=type(message).__name__)
                await self._handle_message(session_id, message)

        except asyncio.CancelledError:
            logger.info("Claude query cancelled", session_id=session_id)
        except Exception as e:
            logger.exception("Claude query failed", session_id=session_id)
            await self._events.on_error(session_id, "CLAUDE_LOCAL_ERROR", str(e))
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

            # Emit final heartbeat
            elapsed = time.monotonic() - start_time
            await self._events.on_heartbeat(session_id, elapsed, done=True)

            # Signal completion
            if store.is_stop_requested(session_id):
                await self._events.on_exit(session_id, 0)
            else:
                await self._events.on_awaiting_input(session_id)

    async def _handle_message(self, session_id: str, message) -> None:
        """Process a message from the Agent SDK.

        Args:
            session_id: Internal session identifier.
            message: SDK message object.
        """
        if isinstance(message, SystemMessage):
            await self._handle_system_message(session_id, message)
        elif isinstance(message, AssistantMessage):
            await self._handle_assistant_message(session_id, message)
        elif isinstance(message, ResultMessage):
            await self._handle_result_message(session_id, message)
        # UserMessage typically echoes our input, skip it

    async def _handle_system_message(
        self, session_id: str, message: SystemMessage
    ) -> None:
        """Handle SystemMessage (init, etc.)."""
        if message.subtype == "init":
            data = message.data
            # Store SDK session ID for resume
            sdk_session_id = data.get("session_id")
            if sdk_session_id:
                self._sdk_sessions[session_id] = sdk_session_id

            # Emit header
            model = data.get("model", "claude")
            version = data.get("claude_code_version", "")
            title = f"Claude Code{f' {version}' if version else ''}"
            await self._events.on_header(
                session_id,
                title=title,
                model=model,
                provider="Anthropic (OAuth)",
            )

    async def _handle_assistant_message(
        self, session_id: str, message: AssistantMessage
    ) -> None:
        """Handle AssistantMessage (text, tool use, etc.)."""
        if message.error:
            await self._events.on_error(
                session_id, f"CLAUDE_{message.error.upper()}", message.error
            )
            return

        for block in message.content:
            if isinstance(block, TextBlock):
                await self._events.on_output(
                    session_id,
                    "combined",
                    block.text,
                    kind="final",
                    is_final=True,
                )
            elif isinstance(block, ToolUseBlock):
                # Emit tool invocation as step
                tool_info = f"[tool: {block.name}]"
                await self._events.on_output(
                    session_id,
                    "combined",
                    f"{tool_info}\n",
                    kind="step",
                    is_final=False,
                )
            elif isinstance(block, ToolResultBlock):
                # Emit truncated tool result
                content = block.content
                if isinstance(content, str):
                    truncated = content[:500] + "..." if len(content) > 500 else content
                    prefix = "[error] " if block.is_error else "[result] "
                    await self._events.on_output(
                        session_id,
                        "combined",
                        f"{prefix}{truncated}\n",
                        kind="step",
                        is_final=False,
                    )
            elif isinstance(block, ThinkingBlock):
                # Emit thinking output
                if block.thinking:
                    await self._events.on_output(
                        session_id,
                        "combined",
                        f"[thinking] {block.thinking}\n",
                        kind="step",
                        is_final=False,
                    )

    async def _handle_result_message(
        self, session_id: str, message: ResultMessage
    ) -> None:
        """Handle ResultMessage (completion with usage stats)."""
        # Emit usage metadata
        if message.usage:
            input_tokens = message.usage.get("input_tokens", 0)
            output_tokens = message.usage.get("output_tokens", 0)
            await self._events.on_metadata(
                session_id,
                "tokens",
                {"input": input_tokens, "output": output_tokens},
                f"input: {input_tokens}, output: {output_tokens}",
            )

        if message.total_cost_usd is not None:
            await self._events.on_metadata(
                session_id,
                "cost",
                message.total_cost_usd,
                f"${message.total_cost_usd:.4f}",
            )

        # Check for errors
        if message.is_error:
            await self._events.on_error(
                session_id,
                "CLAUDE_RESULT_ERROR",
                message.result or "Unknown error",
            )

    async def _heartbeat_loop(self, session_id: str, start_time: float) -> None:
        """Emit periodic heartbeats while the query is active.

        Args:
            session_id: Internal session identifier.
            start_time: Monotonic timestamp when query started.
        """
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                elapsed = time.monotonic() - start_time
                await self._events.on_heartbeat(session_id, elapsed, done=False)
        except asyncio.CancelledError:
            pass
