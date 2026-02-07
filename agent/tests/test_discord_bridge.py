"""Tests for Discord bridge (Phase 5 PoC)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tether.bridges.base import BridgeInterface
from tether.store import SessionStore


class TestDiscordBridgePoC:
    """Test Discord bridge PoC implementation."""

    def test_discord_bridge_implements_interface(self) -> None:
        """DiscordBridge implements BridgeInterface."""
        from tether.bridges.discord.bot import DiscordBridge

        assert issubclass(DiscordBridge, BridgeInterface)

    def test_discord_bridge_can_be_instantiated(self) -> None:
        """DiscordBridge can be created with bot token and channel."""
        from tether.bridges.discord.bot import DiscordBridge

        bridge = DiscordBridge(
            bot_token="discord_bot_token",
            channel_id=1234567890,
        )
        assert bridge is not None

    @pytest.mark.anyio
    async def test_on_output_sends_to_discord_thread(self, fresh_store: SessionStore) -> None:
        """on_output sends text to Discord thread."""
        from tether.bridges.discord.bot import DiscordBridge

        # Create session with Discord binding
        session = fresh_store.create_session("repo_test", "main")
        session.platform = "discord"
        session.platform_thread_id = "9876543210"
        fresh_store.update_session(session)

        # Mock Discord client
        mock_client = MagicMock()
        mock_thread = AsyncMock()
        mock_client.get_channel.return_value = mock_thread

        bridge = DiscordBridge(
            bot_token="discord_bot_token",
            channel_id=1234567890,
        )
        bridge._client = mock_client
        bridge._thread_ids[session.id] = 9876543210  # Register thread

        # Send output
        await bridge.on_output(session.id, "Test Discord output")

        # Verify message was sent to Discord thread
        assert mock_thread.send.called

    @pytest.mark.anyio
    async def test_create_thread_creates_discord_thread(self, fresh_store: SessionStore) -> None:
        """create_thread creates a Discord thread."""
        from tether.bridges.discord.bot import DiscordBridge

        session = fresh_store.create_session("repo_test", "main")

        # Mock Discord client
        mock_client = MagicMock()
        mock_channel = AsyncMock()
        mock_thread = MagicMock()
        mock_thread.id = 9876543210
        mock_channel.create_thread.return_value = mock_thread
        mock_client.get_channel.return_value = mock_channel

        bridge = DiscordBridge(
            bot_token="discord_bot_token",
            channel_id=1234567890,
        )
        bridge._client = mock_client

        # Create thread
        result = await bridge.create_thread(session.id, "Test Session")

        # Verify thread was created
        assert mock_channel.create_thread.called
        assert result["thread_id"] == "9876543210"
        assert result["platform"] == "discord"

    @pytest.mark.anyio
    async def test_on_status_change_sends_to_discord(self, fresh_store: SessionStore) -> None:
        """on_status_change sends status to Discord thread."""
        from tether.bridges.discord.bot import DiscordBridge

        session = fresh_store.create_session("repo_test", "main")
        session.platform = "discord"
        session.platform_thread_id = "9876543210"
        fresh_store.update_session(session)

        # Mock Discord client
        mock_client = MagicMock()
        mock_thread = AsyncMock()
        mock_client.get_channel.return_value = mock_thread

        bridge = DiscordBridge(
            bot_token="discord_bot_token",
            channel_id=1234567890,
        )
        bridge._client = mock_client
        bridge._thread_ids[session.id] = 9876543210  # Register thread

        # Send status
        await bridge.on_status_change(session.id, "executing")

        # Verify status was sent
        assert mock_thread.send.called

    @pytest.mark.anyio
    async def test_on_approval_request_sends_message(self, fresh_store: SessionStore) -> None:
        """Approval requests send message to Discord thread."""
        from tether.bridges.discord.bot import DiscordBridge
        from tether.bridges.base import ApprovalRequest

        session = fresh_store.create_session("repo_test", "main")
        session.platform = "discord"
        fresh_store.update_session(session)

        mock_client = MagicMock()
        mock_thread = AsyncMock()
        mock_client.get_channel.return_value = mock_thread

        bridge = DiscordBridge(
            bot_token="discord_bot_token",
            channel_id=1234567890,
        )
        bridge._client = mock_client
        bridge._thread_ids[session.id] = 9876543210

        request = ApprovalRequest(
            request_id="req_123",
            title="Read",
            description="Read config.yaml",
            options=["Allow", "Deny"],
        )

        await bridge.on_approval_request(session.id, request)

        assert mock_thread.send.called
        sent_text = mock_thread.send.call_args.args[0]
        assert "Approval Required" in sent_text
        assert "allow all" in sent_text

    @pytest.mark.anyio
    async def test_on_approval_request_auto_approves(self, fresh_store: SessionStore) -> None:
        """Approval requests auto-approve when allow-all timer is active."""
        from tether.bridges.discord.bot import DiscordBridge
        from tether.bridges.base import ApprovalRequest

        session = fresh_store.create_session("repo_test", "main")
        session.platform = "discord"
        fresh_store.update_session(session)

        mock_client = MagicMock()
        mock_thread = AsyncMock()
        mock_client.get_channel.return_value = mock_thread

        bridge = DiscordBridge(
            bot_token="discord_bot_token",
            channel_id=1234567890,
        )
        bridge._client = mock_client
        bridge._thread_ids[session.id] = 9876543210
        bridge.set_allow_all(session.id)

        request = ApprovalRequest(
            request_id="req_123",
            title="Read",
            description="Read config.yaml",
            options=["Allow", "Deny"],
        )

        with patch("httpx.AsyncClient") as mock_http:
            mock_http_inst = AsyncMock()
            mock_http_inst.__aenter__ = AsyncMock(return_value=mock_http_inst)
            mock_http_inst.__aexit__ = AsyncMock(return_value=False)
            mock_http.return_value = mock_http_inst

            await bridge.on_approval_request(session.id, request)

        # Should have sent a short notification (not the full approval prompt)
        assert mock_thread.send.called
        sent_text = mock_thread.send.call_args.args[0]
        assert "auto-approved" in sent_text
        assert "Approval Required" not in sent_text
