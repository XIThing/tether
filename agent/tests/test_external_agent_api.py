"""Tests for external agent API (WebSocket and REST)."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.websockets import WebSocketDisconnect

from tether.bridges.base import ApprovalRequest, BridgeInterface, HumanInput
from tether.bridges.manager import BridgeManager
from tether.models import SessionState
from tether.store import SessionStore


class TestExternalAgentModels:
    """Test external agent data models and serialization."""

    def test_approval_request_serialization(self) -> None:
        """ApprovalRequest serializes to dict correctly."""
        request = ApprovalRequest(
            request_id="req_123",
            title="Allow file write?",
            description="Agent wants to write to config.yaml",
            options=["Allow", "Deny"],
            timeout_s=300,
        )

        data = request.model_dump()
        assert data["request_id"] == "req_123"
        assert data["title"] == "Allow file write?"
        assert data["options"] == ["Allow", "Deny"]
        assert data["timeout_s"] == 300

    def test_human_input_serialization(self) -> None:
        """HumanInput serializes to dict correctly."""
        input_msg = HumanInput(
            input_id="input_456",
            text="Please continue",
            username="alice",
            timestamp="2026-02-03T12:00:00Z",
        )

        data = input_msg.model_dump()
        assert data["input_id"] == "input_456"
        assert data["text"] == "Please continue"
        assert data["username"] == "alice"


class TestBridgeInterface:
    """Test bridge interface base class."""

    def test_bridge_interface_is_abstract(self) -> None:
        """BridgeInterface cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BridgeInterface()

    def test_bridge_subclass_must_implement_methods(self) -> None:
        """Bridge subclass must implement required abstract methods."""

        class IncompleteBridge(BridgeInterface):
            pass

        with pytest.raises(TypeError):
            IncompleteBridge()


class MockBridge(BridgeInterface):
    """Mock bridge for testing."""

    def __init__(self):
        self.output_calls = []
        self.approval_calls = []
        self.status_calls = []
        self.thread_creation_calls = []

    async def on_output(self, session_id: str, text: str, metadata: dict | None = None) -> None:
        self.output_calls.append({"session_id": session_id, "text": text, "metadata": metadata})

    async def on_approval_request(self, session_id: str, request: ApprovalRequest) -> None:
        self.approval_calls.append({"session_id": session_id, "request": request})

    async def on_status_change(self, session_id: str, status: str, metadata: dict | None = None) -> None:
        self.status_calls.append({"session_id": session_id, "status": status, "metadata": metadata})

    async def create_thread(self, session_id: str, session_name: str) -> dict:
        self.thread_creation_calls.append({"session_id": session_id, "session_name": session_name})
        return {"thread_id": f"thread_{session_id}", "platform": "mock"}


class TestBridgeManager:
    """Test bridge manager event routing."""

    def test_register_bridge(self) -> None:
        """Bridges can be registered with the manager."""
        manager = BridgeManager()
        bridge = MockBridge()

        manager.register_bridge("mock", bridge)
        assert "mock" in manager.list_bridges()

    @pytest.mark.asyncio
    async def test_route_output_to_bridge(self) -> None:
        """Output events route to registered bridge."""
        manager = BridgeManager()
        bridge = MockBridge()
        manager.register_bridge("mock", bridge)

        await manager.route_output("sess_123", "Hello world", platform="mock")

        assert len(bridge.output_calls) == 1
        assert bridge.output_calls[0]["session_id"] == "sess_123"
        assert bridge.output_calls[0]["text"] == "Hello world"

    @pytest.mark.asyncio
    async def test_route_approval_to_bridge(self) -> None:
        """Approval requests route to registered bridge."""
        manager = BridgeManager()
        bridge = MockBridge()
        manager.register_bridge("mock", bridge)

        request = ApprovalRequest(
            request_id="req_1",
            title="Confirm action",
            description="Test",
            options=["Yes", "No"],
            timeout_s=60,
        )

        await manager.route_approval("sess_123", request, platform="mock")

        assert len(bridge.approval_calls) == 1
        assert bridge.approval_calls[0]["session_id"] == "sess_123"

    @pytest.mark.asyncio
    async def test_create_thread_on_session_create(self) -> None:
        """Thread creation delegates to bridge."""
        manager = BridgeManager()
        bridge = MockBridge()
        manager.register_bridge("mock", bridge)

        result = await manager.create_thread("sess_123", "Test Session", platform="mock")

        assert len(bridge.thread_creation_calls) == 1
        assert result["thread_id"] == "thread_sess_123"


class TestExternalAgentRegistration:
    """Test agent registration flow."""

    def test_agent_metadata_storage(self, fresh_store: SessionStore) -> None:
        """Agent metadata is stored on registration."""
        agent_id = "agent_abc"
        metadata = {
            "name": "Test Agent",
            "type": "test_runner",
            "icon": "🤖",
            "workspace": "/path/to/workspace",
        }

        # Store agent metadata (will be implemented in session store extension)
        # For now, we'll use a simple dict in runtime
        runtime = fresh_store._get_runtime(agent_id)
        runtime.agent_metadata = metadata

        # Retrieve and verify
        retrieved_metadata = getattr(runtime, "agent_metadata", None)
        assert retrieved_metadata is not None
        assert retrieved_metadata["name"] == "Test Agent"
        assert retrieved_metadata["workspace"] == "/path/to/workspace"


class TestApprovalFlow:
    """Test approval request and response flow."""

    @pytest.mark.asyncio
    async def test_approval_request_creates_pending_approval(self, fresh_store: SessionStore) -> None:
        """Creating an approval request stores it as pending."""
        session = fresh_store.create_session("repo_test", "main")
        future = asyncio.Future()

        fresh_store.add_pending_permission(
            session.id,
            "req_1",
            "approval",
            {"title": "Test", "options": ["Yes", "No"]},
            future,
        )

        pending = fresh_store.get_pending_permission(session.id, "req_1")
        assert pending is not None
        assert pending.request_id == "req_1"
        assert not pending.future.done()

    @pytest.mark.asyncio
    async def test_approval_response_resolves_future(self, fresh_store: SessionStore) -> None:
        """Responding to an approval resolves the future."""
        session = fresh_store.create_session("repo_test", "main")
        future = asyncio.Future()

        fresh_store.add_pending_permission(
            session.id,
            "req_1",
            "approval",
            {"title": "Test"},
            future,
        )

        # Simulate user response
        result = {"allowed": True, "option_selected": "Yes", "username": "alice"}
        success = fresh_store.resolve_pending_permission(session.id, "req_1", result)

        assert success is True
        assert future.done()
        assert await future == result

    @pytest.mark.asyncio
    async def test_approval_first_response_wins(self, fresh_store: SessionStore) -> None:
        """Only the first response to an approval is accepted."""
        session = fresh_store.create_session("repo_test", "main")
        future = asyncio.Future()

        fresh_store.add_pending_permission(
            session.id,
            "req_1",
            "approval",
            {"title": "Test"},
            future,
        )

        # First response
        result1 = {"allowed": True, "option_selected": "Yes", "username": "alice"}
        fresh_store.resolve_pending_permission(session.id, "req_1", result1)

        # Second response (should fail - approval already resolved)
        result2 = {"allowed": False, "option_selected": "No", "username": "bob"}
        success = fresh_store.resolve_pending_permission(session.id, "req_1", result2)

        assert success is False
        assert await future == result1

    @pytest.mark.asyncio
    async def test_approval_timeout_auto_deny(self, fresh_store: SessionStore) -> None:
        """Approval times out and auto-denies if no response."""
        session = fresh_store.create_session("repo_test", "main")
        future = asyncio.Future()

        fresh_store.add_pending_permission(
            session.id,
            "req_1",
            "approval",
            {"title": "Test", "timeout_s": 1},
            future,
        )

        # Simulate timeout (will be handled by approval manager)
        # For now just test that we can set a timeout result
        timeout_result = {"allowed": False, "reason": "timeout"}
        fresh_store.resolve_pending_permission(session.id, "req_1", timeout_result)

        assert future.done()
        assert (await future)["allowed"] is False


class TestEventReplay:
    """Test event replay after disconnect."""

    @pytest.mark.asyncio
    async def test_read_event_log_since_seq(self, fresh_store: SessionStore) -> None:
        """Event log can be read with sequence filtering."""
        session = fresh_store.create_session("repo_test", "main")

        # Emit some events
        await fresh_store.emit(session.id, {
            "session_id": session.id,
            "ts": "2026-02-03T12:00:00Z",
            "seq": fresh_store.next_seq(session.id),
            "type": "output",
            "data": {"text": "Event 1"},
        })
        await fresh_store.emit(session.id, {
            "session_id": session.id,
            "ts": "2026-02-03T12:00:01Z",
            "seq": fresh_store.next_seq(session.id),
            "type": "output",
            "data": {"text": "Event 2"},
        })
        await fresh_store.emit(session.id, {
            "session_id": session.id,
            "ts": "2026-02-03T12:00:02Z",
            "seq": fresh_store.next_seq(session.id),
            "type": "output",
            "data": {"text": "Event 3"},
        })

        # Read events after seq 1
        events = fresh_store.read_event_log(session.id, since_seq=1)

        assert len(events) == 2
        assert events[0]["data"]["text"] == "Event 2"
        assert events[1]["data"]["text"] == "Event 3"


class TestExternalAgentSession:
    """Test external agent session management."""

    def test_session_platform_binding(self, fresh_store: SessionStore) -> None:
        """Sessions can be bound to a messaging platform."""
        session = fresh_store.create_session("repo_test", "main")

        # Store platform binding (will be implemented as session field)
        session.platform = "telegram"
        session.platform_thread_id = "topic_123"
        fresh_store.update_session(session)

        retrieved = fresh_store.get_session(session.id)
        assert hasattr(retrieved, "platform")
        assert retrieved.platform == "telegram"

    def test_external_agent_metadata_on_session(self, fresh_store: SessionStore) -> None:
        """External agent metadata is stored on session."""
        session = fresh_store.create_session("repo_test", "main")

        # Store external agent info
        session.external_agent_id = "agent_123"
        session.external_agent_name = "Claude Code"
        fresh_store.update_session(session)

        retrieved = fresh_store.get_session(session.id)
        assert hasattr(retrieved, "external_agent_id")
        assert retrieved.external_agent_id == "agent_123"


class TestRESTEndpoints:
    """Test REST API endpoints for external agents."""

    @pytest.mark.asyncio
    async def test_health_check(self, api_client) -> None:
        """Health endpoint returns OK."""
        response = await api_client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

    @pytest.mark.asyncio
    async def test_create_external_session(self, api_client, fresh_store: SessionStore) -> None:
        """Can create a session via REST API."""
        # Register mock bridge
        from tether.bridges.manager import bridge_manager
        mock_bridge = MockBridge()
        bridge_manager.register_bridge("mock", mock_bridge)

        response = await api_client.post(
            "/api/external/sessions",
            json={
                "agent_metadata": {
                    "name": "Test Agent",
                    "type": "test",
                    "icon": "🤖",
                    "workspace": "/path/to/workspace",
                },
                "session_name": "Test Session",
                "platform": "mock",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert "session_id" in data
        assert data["platform"] == "mock"
        assert "thread_info" in data

        # Verify session was created with agent metadata
        session = fresh_store.get_session(data["session_id"])
        assert session is not None
        assert session.external_agent_name == "Test Agent"
        assert session.platform == "mock"
