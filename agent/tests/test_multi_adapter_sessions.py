"""Integration tests for multi-adapter session support."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tether.main import app
from tether.api.runner_registry import RunnerRegistry
from tether.models import SessionState
from tether.store import store


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Create auth headers with test token."""
    token = os.environ.get("TETHER_AGENT_TOKEN", "test-token")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def setup_test_env():
    """Set up test environment variables."""
    with patch.dict(
        os.environ,
        {
            "TETHER_AGENT_TOKEN": "test-token",
            "TETHER_AGENT_ADAPTER": "codex_cli",
        },
    ):
        yield


@pytest.fixture
def mock_runner():
    """Create a mock runner."""
    runner = MagicMock()
    runner.runner_type = "codex_cli"
    runner.start = AsyncMock()
    runner.stop = AsyncMock()
    runner.send_input = AsyncMock()
    runner.update_permission_mode = MagicMock()
    return runner


@pytest.fixture
def mock_claude_runner():
    """Create a mock Claude runner."""
    runner = MagicMock()
    runner.runner_type = "claude_api"
    runner.start = AsyncMock()
    runner.stop = AsyncMock()
    runner.send_input = AsyncMock()
    runner.update_permission_mode = MagicMock()
    return runner


def test_create_session_with_adapter(client, auth_headers, tmpdir):
    """Test creating a session with specific adapter."""
    test_dir = str(tmpdir.mkdir("test_project"))

    with patch("tether.api.runner_registry.get_runner") as mock_get_runner:
        mock_runner = MagicMock()
        mock_runner.runner_type = "claude_api"
        mock_get_runner.return_value = mock_runner

        response = client.post(
            "/api/sessions",
            json={"directory": test_dir, "adapter": "claude_api"},
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["adapter"] == "claude_api"
        assert data["directory"] == test_dir


def test_create_session_without_adapter(client, auth_headers, tmpdir):
    """Test creating a session without adapter uses default."""
    test_dir = str(tmpdir.mkdir("test_project"))

    response = client.post(
        "/api/sessions",
        json={"directory": test_dir},
        headers=auth_headers,
    )

    assert response.status_code == 201
    data = response.json()
    # Should use default adapter (None means default)
    assert data["adapter"] is None


def test_create_session_invalid_adapter(client, auth_headers, tmpdir):
    """Test creating a session with invalid adapter returns error."""
    test_dir = str(tmpdir.mkdir("test_project"))

    with patch("tether.api.runner_registry.get_runner") as mock_get_runner:
        mock_get_runner.side_effect = ValueError("Unknown agent adapter: invalid_adapter")

        response = client.post(
            "/api/sessions",
            json={"directory": test_dir, "adapter": "invalid_adapter"},
            headers=auth_headers,
        )

        assert response.status_code == 422
        data = response.json()
        assert "Invalid adapter" in data["error"]["message"]
        assert "invalid_adapter" in data["error"]["message"]


def test_session_adapter_routing_on_start(client, auth_headers, tmpdir, mock_runner, mock_claude_runner):
    """Test that sessions route to correct runner on start."""
    test_dir1 = str(tmpdir.mkdir("test_project1"))
    test_dir2 = str(tmpdir.mkdir("test_project2"))

    with patch("tether.api.runner_events.get_runner_registry") as mock_get_registry:
        mock_registry = MagicMock(spec=RunnerRegistry)

        # Set up registry to return different runners
        def get_runner_side_effect(adapter_name):
            if adapter_name == "claude_api":
                return mock_claude_runner
            return mock_runner

        mock_registry.get_runner.side_effect = get_runner_side_effect
        mock_registry.validate_adapter = MagicMock()
        mock_get_registry.return_value = mock_registry

        # Create two sessions with different adapters
        response1 = client.post(
            "/api/sessions",
            json={"directory": test_dir1},
            headers=auth_headers,
        )
        session1_id = response1.json()["id"]

        response2 = client.post(
            "/api/sessions",
            json={"directory": test_dir2, "adapter": "claude_api"},
            headers=auth_headers,
        )
        session2_id = response2.json()["id"]

        # Start both sessions
        response1_start = client.post(
            f"/api/sessions/{session1_id}/start",
            json={"prompt": "test prompt 1", "approval_choice": 2},
            headers=auth_headers,
        )
        assert response1_start.status_code == 200

        response2_start = client.post(
            f"/api/sessions/{session2_id}/start",
            json={"prompt": "test prompt 2", "approval_choice": 2},
            headers=auth_headers,
        )
        assert response2_start.status_code == 200

        # Verify correct runners were used
        assert mock_runner.start.called
        assert mock_claude_runner.start.called


def test_session_adapter_routing_on_input(client, auth_headers, tmpdir, mock_runner):
    """Test that send_input routes to correct runner."""
    test_dir = str(tmpdir.mkdir("test_project"))

    with patch("tether.api.runner_events.get_runner_registry") as mock_get_registry:
        mock_registry = MagicMock(spec=RunnerRegistry)
        mock_registry.get_runner.return_value = mock_runner
        mock_registry.validate_adapter = MagicMock()
        mock_get_registry.return_value = mock_registry

        # Create and start session
        response = client.post(
            "/api/sessions",
            json={"directory": test_dir, "adapter": "codex_cli"},
            headers=auth_headers,
        )
        session_id = response.json()["id"]

        # Manually set session to AWAITING_INPUT state
        session = store.get_session(session_id)
        session.state = SessionState.AWAITING_INPUT
        store.update_session(session)

        # Send input
        input_response = client.post(
            f"/api/sessions/{session_id}/input",
            json={"text": "test input"},
            headers=auth_headers,
        )

        assert input_response.status_code == 200
        assert mock_runner.send_input.called


def test_session_adapter_routing_on_interrupt(client, auth_headers, tmpdir, mock_runner):
    """Test that interrupt routes to correct runner."""
    test_dir = str(tmpdir.mkdir("test_project"))

    with patch("tether.api.runner_events.get_runner_registry") as mock_get_registry:
        mock_registry = MagicMock(spec=RunnerRegistry)
        mock_registry.get_runner.return_value = mock_runner
        mock_registry.validate_adapter = MagicMock()
        mock_get_registry.return_value = mock_registry

        # Create session
        response = client.post(
            "/api/sessions",
            json={"directory": test_dir, "adapter": "codex_cli"},
            headers=auth_headers,
        )
        session_id = response.json()["id"]

        # Manually set session to RUNNING state
        session = store.get_session(session_id)
        session.state = SessionState.RUNNING
        store.update_session(session)

        # Interrupt
        interrupt_response = client.post(
            f"/api/sessions/{session_id}/interrupt",
            headers=auth_headers,
        )

        assert interrupt_response.status_code == 200
        assert mock_runner.stop.called


def test_session_adapter_routing_on_approval_mode(client, auth_headers, tmpdir, mock_runner):
    """Test that approval mode update routes to correct runner."""
    test_dir = str(tmpdir.mkdir("test_project"))

    with patch("tether.api.runner_events.get_runner_registry") as mock_get_registry:
        mock_registry = MagicMock(spec=RunnerRegistry)
        mock_registry.get_runner.return_value = mock_runner
        mock_registry.validate_adapter = MagicMock()
        mock_get_registry.return_value = mock_registry

        # Create session
        response = client.post(
            "/api/sessions",
            json={"directory": test_dir, "adapter": "codex_cli"},
            headers=auth_headers,
        )
        session_id = response.json()["id"]

        # Manually set session to RUNNING state
        session = store.get_session(session_id)
        session.state = SessionState.RUNNING
        store.update_session(session)

        # Update approval mode
        approval_response = client.patch(
            f"/api/sessions/{session_id}/approval-mode",
            json={"approval_mode": 1},
            headers=auth_headers,
        )

        assert approval_response.status_code == 200
        assert mock_runner.update_permission_mode.called


def test_backward_compatibility_null_adapter(client, auth_headers, tmpdir, mock_runner):
    """Test that NULL adapter field uses default runner."""
    test_dir = str(tmpdir.mkdir("test_project"))

    with patch("tether.api.runner_events.get_runner_registry") as mock_get_registry:
        mock_registry = MagicMock(spec=RunnerRegistry)
        mock_registry.get_runner.return_value = mock_runner
        mock_get_registry.return_value = mock_registry

        # Create session without adapter (NULL)
        response = client.post(
            "/api/sessions",
            json={"directory": test_dir},
            headers=auth_headers,
        )
        session_id = response.json()["id"]

        # Start session - should use default runner
        start_response = client.post(
            f"/api/sessions/{session_id}/start",
            json={"prompt": "test", "approval_choice": 2},
            headers=auth_headers,
        )

        assert start_response.status_code == 200
        # Should have called get_runner with None (default)
        mock_registry.get_runner.assert_called_with(None)
