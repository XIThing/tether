"""Tests for MCP server wrapper (Phase 3.5)."""

import json

import pytest


class TestMCPToolDefinitions:
    """Test MCP tool definitions are properly formatted."""

    def test_mcp_tools_module_exists(self) -> None:
        """MCP tools module can be imported."""
        from tether.mcp import tools
        assert tools is not None

    def test_create_session_tool_defined(self) -> None:
        """create_session MCP tool is defined."""
        from tether.mcp.tools import get_tool_definitions

        tools = get_tool_definitions()
        tool_names = [t["name"] for t in tools]

        assert "create_session" in tool_names

    def test_send_output_tool_defined(self) -> None:
        """send_output MCP tool is defined."""
        from tether.mcp.tools import get_tool_definitions

        tools = get_tool_definitions()
        tool_names = [t["name"] for t in tools]

        assert "send_output" in tool_names

    def test_request_approval_tool_defined(self) -> None:
        """request_approval MCP tool is defined."""
        from tether.mcp.tools import get_tool_definitions

        tools = get_tool_definitions()
        tool_names = [t["name"] for t in tools]

        assert "request_approval" in tool_names

    def test_check_input_tool_defined(self) -> None:
        """check_input MCP tool is defined."""
        from tether.mcp.tools import get_tool_definitions

        tools = get_tool_definitions()
        tool_names = [t["name"] for t in tools]

        assert "check_input" in tool_names


class TestMCPToolExecution:
    """Test MCP tool execution calls underlying REST API."""

    @pytest.mark.asyncio
    async def test_create_session_executes_correctly(self, api_client) -> None:
        """MCP create_session tool format can be used."""
        # The tool execution requires the server to be running
        # For now, just test via direct API call with MCP-like format
        from tether.bridges.manager import bridge_manager
        from tests.test_external_agent_api import MockBridge

        # Register mock bridge
        bridge = MockBridge()
        bridge_manager.register_bridge("telegram", bridge)

        # Simulate MCP tool call via REST API
        response = await api_client.post(
            "/api/external/sessions",
            json={
                "agent_metadata": {
                    "name": "Claude Code",
                    "type": "claude_code",
                    "icon": "🤖",
                },
                "session_name": "Test MCP Session",
                "platform": "telegram",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert "session_id" in data

    @pytest.mark.asyncio
    async def test_send_output_executes_correctly(self, api_client) -> None:
        """MCP send_output tool format can be used."""
        from tether.bridges.manager import bridge_manager
        from tests.test_external_agent_api import MockBridge

        # Register mock bridge
        bridge = MockBridge()
        bridge_manager.register_bridge("mock", bridge)

        # Create session
        response = await api_client.post(
            "/api/external/sessions",
            json={
                "agent_metadata": {"name": "Test", "type": "test"},
                "session_name": "Test",
                "platform": "mock",
            },
        )
        session_id = response.json()["session_id"]

        # Send output (MCP format)
        response = await api_client.post(
            f"/api/external/sessions/{session_id}/events",
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
        from tether.mcp import server
        assert server is not None

    def test_mcp_server_has_main_function(self) -> None:
        """MCP server has a main() entry point."""
        from tether.mcp.server import main

        assert callable(main)
