"""Tests for MCP server wrapper."""

import pytest

from tether.store import SessionStore


class TestMCPToolDefinitions:
    """Test MCP tool definitions are properly formatted."""

    def test_mcp_tools_module_exists(self) -> None:
        """MCP tools module can be imported."""
        from tether.mcp_server import tools
        assert tools is not None

    def test_create_session_tool_defined(self) -> None:
        """create_session MCP tool is defined."""
        from tether.mcp_server.tools import get_tool_definitions

        tools = get_tool_definitions()
        tool_names = [t["name"] for t in tools]

        assert "create_session" in tool_names

    def test_send_output_tool_defined(self) -> None:
        """send_output MCP tool is defined."""
        from tether.mcp_server.tools import get_tool_definitions

        tools = get_tool_definitions()
        tool_names = [t["name"] for t in tools]

        assert "send_output" in tool_names

    def test_request_approval_tool_defined(self) -> None:
        """request_approval MCP tool is defined."""
        from tether.mcp_server.tools import get_tool_definitions

        tools = get_tool_definitions()
        tool_names = [t["name"] for t in tools]

        assert "request_approval" in tool_names

    def test_check_input_tool_defined(self) -> None:
        """check_input MCP tool is defined."""
        from tether.mcp_server.tools import get_tool_definitions

        tools = get_tool_definitions()
        tool_names = [t["name"] for t in tools]

        assert "check_input" in tool_names


class TestMCPToolExecution:
    """Test MCP tool execution via converged API endpoints."""

    @pytest.mark.anyio
    async def test_create_session_via_api(self, api_client, fresh_store: SessionStore) -> None:
        """MCP create_session maps to POST /api/sessions with agent fields."""
        from tether.bridges.manager import bridge_manager
        from test_external_agent_api import MockBridge

        bridge = MockBridge()
        bridge_manager.register_bridge("telegram", bridge)

        # Simulate MCP tool call via converged API
        response = await api_client.post(
            "/api/sessions",
            json={
                "agent_name": "Claude Code",
                "agent_type": "claude_code",
                "session_name": "Test MCP Session",
                "platform": "telegram",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["external_agent_name"] == "Claude Code"

    @pytest.mark.anyio
    async def test_send_output_via_api(self, api_client, fresh_store: SessionStore) -> None:
        """MCP send_output maps to POST /api/sessions/{id}/events."""
        session = fresh_store.create_session("external", None)

        response = await api_client.post(
            f"/api/sessions/{session.id}/events",
            json={
                "type": "output",
                "data": {"text": "Test output from MCP"},
            },
        )

        assert response.status_code == 200
        assert response.json().get("ok") is True


class TestMCPServerIntegration:
    """Test MCP server can be started and responds to requests."""

    def test_mcp_server_module_exists(self) -> None:
        """MCP server module can be imported."""
        from tether.mcp_server import server
        assert server is not None

    def test_mcp_server_has_main_function(self) -> None:
        """MCP server has a main() entry point."""
        from tether.mcp_server.server import main

        assert callable(main)
