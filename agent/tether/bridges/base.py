"""Base interface for messaging platform bridges.

Bridges handle routing agent output to messaging platforms like Telegram, Slack, or Discord.
Each bridge implements platform-specific message formatting and API interactions.
"""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class ApprovalRequest(BaseModel):
    """An approval request from an agent to a human."""

    request_id: str
    title: str
    description: str
    options: list[str]
    timeout_s: int = 300  # Default 5 minutes


class HumanInput(BaseModel):
    """Human input message from a messaging platform."""

    input_id: str
    text: str
    username: str | None = None
    timestamp: str | None = None


class ApprovalResponse(BaseModel):
    """Human response to an approval request."""

    request_id: str
    option_selected: str
    username: str | None = None
    timestamp: str | None = None


class BridgeInterface(ABC):
    """Abstract interface for messaging platform bridges.

    Each platform (Telegram, Slack, Discord) implements this interface to handle
    platform-specific formatting and API calls.
    """

    @abstractmethod
    async def on_output(
        self, session_id: str, text: str, metadata: dict | None = None
    ) -> None:
        """Handle agent output text.

        Args:
            session_id: Internal Tether session ID.
            text: Output text (markdown format).
            metadata: Optional metadata about the output.
        """
        pass

    @abstractmethod
    async def on_approval_request(
        self, session_id: str, request: ApprovalRequest
    ) -> None:
        """Handle an approval request.

        Args:
            session_id: Internal Tether session ID.
            request: Approval request details.
        """
        pass

    @abstractmethod
    async def on_status_change(
        self, session_id: str, status: str, metadata: dict | None = None
    ) -> None:
        """Handle agent status change.

        Args:
            session_id: Internal Tether session ID.
            status: New status (e.g., "thinking", "executing", "done", "error").
            metadata: Optional metadata about the status.
        """
        pass

    @abstractmethod
    async def create_thread(self, session_id: str, session_name: str) -> dict:
        """Create a messaging thread for a new session.

        Args:
            session_id: Internal Tether session ID.
            session_name: Display name for the session.

        Returns:
            Dict with platform-specific thread info (thread_id, platform, etc.).
        """
        pass
