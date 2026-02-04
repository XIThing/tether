"""Tests for external agent to Telegram integration (Phase 3)."""

import pytest

from tether.bridges.manager import bridge_manager
from tether.store import SessionStore


class MockTelegramBridge:
    """Mock Telegram bridge for testing."""

    def __init__(self):
        self.output_calls = []
        self.approval_calls = []
        self.status_calls = []
        self.thread_calls = []

    async def on_output(self, session_id: str, text: str, metadata: dict | None = None) -> None:
        self.output_calls.append({"session_id": session_id, "text": text, "metadata": metadata})

    async def on_approval_request(self, session_id: str, request) -> None:
        self.approval_calls.append({"session_id": session_id, "request": request})

    async def on_status_change(self, session_id: str, status: str, metadata: dict | None = None) -> None:
        self.status_calls.append({"session_id": session_id, "status": status, "metadata": metadata})

    async def create_thread(self, session_id: str, session_name: str) -> dict:
        self.thread_calls.append({"session_id": session_id, "session_name": session_name})
        return {"thread_id": f"mock_{session_id}", "platform": "telegram"}


class TestExternalAgentToTelegramIntegration:
    """Test that external agent events are routed to Telegram."""

    @pytest.mark.asyncio
    async def test_external_session_creates_telegram_thread(self, api_client, fresh_store: SessionStore) -> None:
        """Creating an external session auto-creates a Telegram thread."""
        # Register mock Telegram bridge
        mock_bridge = MockTelegramBridge()
        bridge_manager.register_bridge("telegram", mock_bridge)

        # Create external session via API
        response = await api_client.post(
            "/api/external/sessions",
            json={
                "agent_metadata": {
                    "name": "Test Agent",
                    "type": "test",
                    "icon": "🤖",
                },
                "session_name": "Test Session",
                "platform": "telegram",
            },
        )

        assert response.status_code == 201
        data = response.json()

        # Verify thread was created
        assert len(mock_bridge.thread_calls) == 1
        assert mock_bridge.thread_calls[0]["session_name"] == "Test Session"

    @pytest.mark.asyncio
    async def test_external_output_routes_to_telegram(self, api_client, fresh_store: SessionStore) -> None:
        """External agent output events route to Telegram."""
        # Register mock bridge
        mock_bridge = MockTelegramBridge()
        bridge_manager.register_bridge("telegram", mock_bridge)

        # Create external session
        response = await api_client.post(
            "/api/external/sessions",
            json={
                "agent_metadata": {"name": "Test", "type": "test"},
                "session_name": "Test",
                "platform": "telegram",
            },
        )
        session_id = response.json()["session_id"]

        # Send output event
        response = await api_client.post(
            f"/api/external/sessions/{session_id}/events",
            json={
                "type": "output",
                "data": {
                    "text": "Hello from external agent!",
                },
            },
        )

        assert response.status_code == 200

        # Verify output was routed to Telegram
        assert len(mock_bridge.output_calls) == 1
        assert mock_bridge.output_calls[0]["text"] == "Hello from external agent!"

    @pytest.mark.asyncio
    async def test_external_approval_routes_to_telegram(self, api_client, fresh_store: SessionStore) -> None:
        """External agent approval requests route to Telegram."""
        # Register mock bridge
        mock_bridge = MockTelegramBridge()
        bridge_manager.register_bridge("telegram", mock_bridge)

        # Create external session
        response = await api_client.post(
            "/api/external/sessions",
            json={
                "agent_metadata": {"name": "Test", "type": "test"},
                "session_name": "Test",
                "platform": "telegram",
            },
        )
        session_id = response.json()["session_id"]

        # Send approval request
        response = await api_client.post(
            f"/api/external/sessions/{session_id}/events",
            json={
                "type": "approval_request",
                "data": {
                    "request_id": "req_123",
                    "title": "Approve action?",
                    "description": "Details here",
                    "options": ["Yes", "No"],
                    "timeout_s": 300,
                },
            },
        )

        assert response.status_code == 200

        # Verify approval was routed to Telegram
        assert len(mock_bridge.approval_calls) == 1
        assert mock_bridge.approval_calls[0]["request"].title == "Approve action?"

    @pytest.mark.asyncio
    async def test_external_status_routes_to_telegram(self, api_client, fresh_store: SessionStore) -> None:
        """External agent status updates route to Telegram."""
        # Register mock bridge
        mock_bridge = MockTelegramBridge()
        bridge_manager.register_bridge("telegram", mock_bridge)

        # Create external session
        response = await api_client.post(
            "/api/external/sessions",
            json={
                "agent_metadata": {"name": "Test", "type": "test"},
                "session_name": "Test",
                "platform": "telegram",
            },
        )
        session_id = response.json()["session_id"]

        # Send status event
        response = await api_client.post(
            f"/api/external/sessions/{session_id}/events",
            json={
                "type": "status",
                "data": {
                    "status": "thinking",
                },
            },
        )

        assert response.status_code == 200

        # Verify status was routed to Telegram
        assert len(mock_bridge.status_calls) == 1
        assert mock_bridge.status_calls[0]["status"] == "thinking"
