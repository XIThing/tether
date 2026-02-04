"""Discord bridge implementation (PoC - output streaming + threading only)."""

import structlog

from tether.bridges.base import ApprovalRequest, BridgeInterface

logger = structlog.get_logger(__name__)


class DiscordBridge(BridgeInterface):
    """Discord bridge that routes agent events to Discord threads.

    PoC scope: output streaming and threading only. Approvals deferred.

    Args:
        bot_token: Discord bot token.
        channel_id: Discord channel ID (integer).
    """

    def __init__(self, bot_token: str, channel_id: int):
        self._bot_token = bot_token
        self._channel_id = channel_id
        self._client: any = None
        self._thread_ids: dict[str, int] = {}  # session_id -> thread_id

    async def start(self) -> None:
        """Initialize and start Discord client."""
        try:
            import discord
        except ImportError:
            logger.error("discord.py not installed. Install with: pip install discord.py")
            return

        # Create Discord client with message content intent
        intents = discord.Intents.default()
        intents.message_content = True
        self._client = discord.Client(intents=intents)

        # Register event handlers
        @self._client.event
        async def on_ready():
            logger.info("Discord client ready", user=self._client.user)

        @self._client.event
        async def on_message(message):
            await self._handle_message(message)

        # Start the client in background
        import asyncio
        asyncio.create_task(self._client.start(self._bot_token))

        logger.info("Discord bridge initialized and starting", channel_id=self._channel_id)

    async def stop(self) -> None:
        """Stop Discord client."""
        if self._client:
            await self._client.close()
        logger.info("Discord bridge stopped")

    async def _handle_message(self, message: any) -> None:
        """Handle incoming messages from Discord and forward to event log.

        Args:
            message: Discord message object.
        """
        # Import discord here to check types
        try:
            import discord
        except ImportError:
            return

        # Ignore bot messages
        if message.author.bot:
            return

        # Check if message is in a thread
        if not isinstance(message.channel, discord.Thread):
            return

        # Get message text
        text = message.content
        if not text:
            return

        # Find session for this thread
        thread_id = message.channel.id
        session_id = None
        for sid, tid in self._thread_ids.items():
            if tid == thread_id:
                session_id = sid
                break

        if not session_id:
            logger.debug("Received message in thread with no session mapping", thread_id=thread_id)
            return

        # Import store here to avoid circular import
        from tether.store import store

        # Emit human_input event
        try:
            await store.emit(session_id, {
                "session_id": session_id,
                "ts": store._now(),
                "seq": store.next_seq(session_id),
                "type": "human_input",
                "data": {
                    "text": text,
                    "username": message.author.name,
                    "user_id": str(message.author.id),
                    "platform": "discord",
                },
            })
            logger.info(
                "Forwarded human input from Discord",
                session_id=session_id,
                thread_id=thread_id,
                username=message.author.name,
            )
        except Exception:
            logger.exception(
                "Failed to forward human input",
                session_id=session_id,
                thread_id=thread_id,
            )

    async def on_output(
        self, session_id: str, text: str, metadata: dict | None = None
    ) -> None:
        """Send output text to Discord thread.

        Args:
            session_id: Internal Tether session ID.
            text: Output text.
            metadata: Optional metadata.
        """
        if not self._client:
            logger.warning("Discord client not initialized")
            return

        thread_id = self._thread_ids.get(session_id)
        if not thread_id:
            logger.warning("No Discord thread for session", session_id=session_id)
            return

        try:
            thread = self._client.get_channel(thread_id)
            if thread:
                await thread.send(text)
        except Exception:
            logger.exception("Failed to send Discord message", session_id=session_id)

    async def on_approval_request(
        self, session_id: str, request: ApprovalRequest
    ) -> None:
        """Approval requests not implemented in Discord PoC.

        Args:
            session_id: Internal Tether session ID.
            request: Approval request (ignored).
        """
        logger.warning(
            "Approval requests not implemented in Discord PoC",
            session_id=session_id,
            request_id=request.request_id,
        )

    async def on_status_change(
        self, session_id: str, status: str, metadata: dict | None = None
    ) -> None:
        """Send status change to Discord thread.

        Args:
            session_id: Internal Tether session ID.
            status: New status.
            metadata: Optional metadata.
        """
        if not self._client:
            return

        thread_id = self._thread_ids.get(session_id)
        if not thread_id:
            return

        emoji_map = {
            "thinking": "💭",
            "executing": "⚙️",
            "done": "✅",
            "error": "❌",
        }
        emoji = emoji_map.get(status, "ℹ️")

        text = f"{emoji} Status: {status}"

        try:
            thread = self._client.get_channel(thread_id)
            if thread:
                await thread.send(text)
        except Exception:
            logger.exception("Failed to send Discord status", session_id=session_id)

    async def create_thread(self, session_id: str, session_name: str) -> dict:
        """Create a Discord thread for a session.

        Args:
            session_id: Internal Tether session ID.
            session_name: Display name for the session.

        Returns:
            Dict with thread_id and platform info.
        """
        if not self._client:
            raise RuntimeError("Discord client not initialized")

        try:
            # Get channel and create thread
            channel = self._client.get_channel(self._channel_id)
            if not channel:
                raise RuntimeError(f"Discord channel {self._channel_id} not found")

            # Create thread with initial message
            thread = await channel.create_thread(
                name=session_name[:100],  # Discord limit
                auto_archive_duration=1440,  # 24 hours
            )

            thread_id = thread.id
            self._thread_ids[session_id] = thread_id

            logger.info(
                "Created Discord thread",
                session_id=session_id,
                thread_id=thread_id,
                name=session_name,
            )

            return {
                "thread_id": str(thread_id),
                "platform": "discord",
            }

        except Exception as e:
            logger.exception("Failed to create Discord thread", session_id=session_id)
            raise RuntimeError(f"Failed to create Discord thread: {e}")
