"""Discord bridge implementation with command handling and session threading."""

import structlog

from tether.bridges.base import ApprovalRequest, BridgeInterface
from tether.settings import settings

logger = structlog.get_logger(__name__)

_STATE_EMOJI = {
    "CREATED": "🆕",
    "RUNNING": "🔄",
    "AWAITING_INPUT": "📝",
    "INTERRUPTING": "⏳",
    "ERROR": "❌",
}

_EXTERNAL_PAGE_SIZE = 10
_EXTERNAL_MAX_FETCH = 200
_EXTERNAL_REPLAY_LIMIT = 10
_EXTERNAL_REPLAY_MAX_CHARS = 3500
_DISCORD_THREAD_NAME_MAX_LEN = 64


class DiscordBridge(BridgeInterface):
    """Discord bridge that routes agent events to Discord threads.

    Commands (in main channel): !help, !status, !list, !attach, !stop
    Session input: messages in session threads are forwarded as input.

    Args:
        bot_token: Discord bot token.
        channel_id: Discord channel ID (integer).
    """

    def __init__(self, bot_token: str, channel_id: int):
        self._bot_token = bot_token
        self._channel_id = channel_id
        self._client: any = None
        self._thread_ids: dict[str, int] = {}  # session_id -> thread_id
        self._cached_external: list[dict] = []
        # Current view of external sessions as presented to the user (may be filtered).
        self._external_query: str | None = None
        self._external_view: list[dict] = []

    async def start(self) -> None:
        """Initialize and start Discord client."""
        try:
            import discord
        except ImportError:
            logger.error("discord.py not installed. Install with: pip install discord.py")
            return

        intents = discord.Intents.default()
        intents.message_content = True
        self._client = discord.Client(intents=intents)

        @self._client.event
        async def on_ready():
            logger.info("Discord client ready", user=self._client.user)

        @self._client.event
        async def on_message(message):
            await self._handle_message(message)

        import asyncio
        asyncio.create_task(self._client.start(self._bot_token))

        logger.info("Discord bridge initialized and starting", channel_id=self._channel_id)

    async def stop(self) -> None:
        """Stop Discord client."""
        if self._client:
            await self._client.close()
        logger.info("Discord bridge stopped")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _api_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        token = settings.token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _api_url(self, path: str) -> str:
        return f"http://localhost:{settings.port()}/api{path}"

    def _make_external_thread_name(self, *, directory: str, session_id: str) -> str:
        dir_short = (directory or "").rstrip("/").rsplit("/", 1)[-1] or "session"
        raw_id = (session_id or "").strip()
        raw_id = raw_id.removeprefix("sess_")
        suffix = (raw_id[-6:] if raw_id else "") or "unknown"
        max_dir_len = max(1, _DISCORD_THREAD_NAME_MAX_LEN - (1 + len(suffix)))
        if len(dir_short) > max_dir_len:
            if max_dir_len <= 3:
                dir_short = dir_short[:max_dir_len]
            else:
                dir_short = dir_short[: max_dir_len - 3] + "..."
        return f"{dir_short} {suffix}"[:_DISCORD_THREAD_NAME_MAX_LEN]

    def _set_external_view(self, query: str | None) -> None:
        q = (query or "").strip()
        self._external_query = q or None
        if not self._cached_external:
            self._external_view = []
            return
        if not q:
            self._external_view = list(self._cached_external)
            return
        q_lower = q.lower()
        self._external_view = [
            s for s in self._cached_external if q_lower in str(s.get("directory", "")).lower()
        ]

    async def _send_external_session_replay(
        self, *, thread_id: int, external_id: str, runner_type: str
    ) -> None:
        """Send recent external session history into the Discord thread."""
        if not self._client:
            return

        import httpx

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self._api_url(f"/external-sessions/{external_id}/history"),
                    headers=self._api_headers(),
                    params={"runner_type": runner_type, "limit": _EXTERNAL_REPLAY_LIMIT},
                    timeout=10.0,
                )
                response.raise_for_status()
            payload = response.json()
        except Exception:
            logger.exception(
                "Failed to fetch external session history for replay",
                external_id=external_id,
                runner_type=runner_type,
            )
            return

        messages = payload.get("messages") or []
        if not messages:
            return

        lines: list[str] = [f"Recent history (last {min(_EXTERNAL_REPLAY_LIMIT, len(messages))} messages):\n"]
        for i, msg in enumerate(messages, 1):
            role = str(msg.get("role") or "").lower()
            prefix = "U" if role == "user" else ("A" if role == "assistant" else role[:1].upper() or "?")
            content = (msg.get("content") or "").strip()
            thinking = (msg.get("thinking") or "").strip()
            if content and len(content) > 800:
                content = content[:800] + "..."
            if thinking and len(thinking) > 400:
                thinking = thinking[:400] + "..."
            if content:
                lines.append(f"{i}. {prefix}: {content}")
            if thinking:
                lines.append(f"   {prefix} (thinking): {thinking}")

        text = "\n".join(lines)
        if len(text) > _EXTERNAL_REPLAY_MAX_CHARS:
            text = text[: _EXTERNAL_REPLAY_MAX_CHARS - 3] + "..."

        try:
            thread = self._client.get_channel(thread_id)
            if thread:
                await thread.send(text)
        except Exception:
            logger.exception("Failed to send Discord external session replay", external_id=external_id)

    def _session_for_thread(self, thread_id: int) -> str | None:
        for sid, tid in self._thread_ids.items():
            if tid == thread_id:
                return sid
        return None

    # ------------------------------------------------------------------
    # Message router
    # ------------------------------------------------------------------

    async def _handle_message(self, message: any) -> None:
        """Route incoming Discord messages to commands or session input."""
        try:
            import discord
        except ImportError:
            return

        if message.author.bot:
            return

        text = message.content.strip()
        if not text:
            return

        # Messages in threads → session input
        if isinstance(message.channel, discord.Thread):
            session_id = self._session_for_thread(message.channel.id)
            if not session_id:
                return
            await self._forward_input(message, session_id, text)
            return

        # Messages in the configured channel starting with ! → commands
        if message.channel.id == self._channel_id and text.startswith("!"):
            await self._dispatch_command(message, text)

    async def _dispatch_command(self, message: any, text: str) -> None:
        parts = text.split(None, 1)
        cmd = parts[0].lower()
        args = parts[1].strip() if len(parts) > 1 else ""

        if cmd in ("!help", "!start"):
            await self._cmd_help(message)
        elif cmd in ("!status", "!sessions"):
            await self._cmd_status(message)
        elif cmd == "!list":
            await self._cmd_list(message, args)
        elif cmd == "!attach":
            await self._cmd_attach(message, args)
        elif cmd == "!stop":
            await self._cmd_stop(message)
        else:
            await message.channel.send(f"Unknown command: {cmd}\nUse !help for available commands.")

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def _cmd_help(self, message: any) -> None:
        text = (
            "Tether Commands:\n\n"
            "!status — List all sessions\n"
            "!list [page|search] — List external sessions (Claude Code, Codex)\n"
            "!attach <number> — Attach to an external session\n"
            "!stop — Interrupt the session in this thread\n"
            "!help — Show this help\n\n"
            "Send a text message in a session thread to forward it as input."
        )
        await message.channel.send(text)

    async def _cmd_status(self, message: any) -> None:
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self._api_url("/sessions"),
                    headers=self._api_headers(),
                    timeout=10.0,
                )
                response.raise_for_status()
            sessions = response.json()
        except Exception:
            logger.exception("Failed to fetch sessions for !status")
            await message.channel.send("Failed to fetch sessions.")
            return

        if not sessions:
            await message.channel.send("No sessions.")
            return

        lines = ["Sessions:\n"]
        for s in sessions:
            emoji = _STATE_EMOJI.get(s.get("state", ""), "❓")
            name = s.get("name") or s.get("id", "")[:12]
            lines.append(f"  {emoji} {name}")
        await message.channel.send("\n".join(lines))

    async def _cmd_list(self, message: any, args: str) -> None:
        import httpx

        page = 1
        query: str | None = None
        if args:
            first = args.split()[0]
            try:
                page = int(first)
                query = self._external_query
            except ValueError:
                page = 1
                query = args.strip()

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self._api_url("/external-sessions"),
                    headers=self._api_headers(),
                    params={"limit": _EXTERNAL_MAX_FETCH},
                    timeout=10.0,
                )
                response.raise_for_status()
            self._cached_external = response.json()
            if not args:
                self._set_external_view(None)
            else:
                self._set_external_view(query)
        except Exception:
            logger.exception("Failed to fetch external sessions")
            await message.channel.send("Failed to list external sessions.")
            return

        text, _, _ = self._format_external_page(page)
        await message.channel.send(text)

    async def _cmd_attach(self, message: any, args: str) -> None:
        import httpx

        if not args:
            await message.channel.send("Usage: !attach <number>\n\nRun !list first.")
            return

        try:
            index = int(args.split()[0]) - 1
        except ValueError:
            await message.channel.send("Please provide a session number.")
            return

        if not self._cached_external:
            await message.channel.send("No external sessions cached. Run !list first.")
            return
        if not self._external_view:
            await message.channel.send("No external sessions listed. Run !list first.")
            return
        if index < 0 or index >= len(self._external_view):
            await message.channel.send(f"Invalid number. Use 1–{len(self._external_view)}.")
            return

        external = self._external_view[index]

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self._api_url("/sessions/attach"),
                    json={
                        "external_id": external["id"],
                        "runner_type": external["runner_type"],
                        "directory": external["directory"],
                    },
                    headers=self._api_headers(),
                    timeout=30.0,
                )
                response.raise_for_status()
            session = response.json()
            session_id = session["id"]

            # Check if already has a thread
            if session_id in self._thread_ids:
                await message.channel.send("Already attached — check the existing thread.")
                return

            # Create thread
            session_name = self._make_external_thread_name(
                directory=external.get("directory", ""),
                session_id=session_id,
            )
            thread_info = await self.create_thread(session_id, session_name)
            try:
                thread_id = int(thread_info.get("thread_id") or 0)
                if thread_id:
                    await self._send_external_session_replay(
                        thread_id=thread_id,
                        external_id=external["id"],
                        runner_type=str(external["runner_type"]),
                    )
            except Exception:
                logger.exception("Failed to replay external session history into Discord thread")

            # Bind platform
            from tether.store import store
            from tether.bridges.subscriber import bridge_subscriber

            db_session = store.get_session(session_id)
            if db_session:
                db_session.platform = "discord"
                db_session.platform_thread_id = thread_info.get("thread_id")
                store.update_session(db_session)

            bridge_subscriber.subscribe(session_id, "discord")

            dir_short = external.get("directory", "").rsplit("/", 1)[-1]
            await message.channel.send(
                f"✅ Attached to {external['runner_type']} session in {dir_short}\n\n"
                f"A new thread has been created — send messages there to interact."
            )

        except httpx.HTTPStatusError as e:
            await message.channel.send(f"Failed to attach: {e.response.text}")
        except Exception as e:
            logger.exception("Failed to attach to external session")
            await message.channel.send(f"Failed to attach: {e}")

    async def _cmd_stop(self, message: any) -> None:
        import discord
        import httpx

        if not isinstance(message.channel, discord.Thread):
            await message.channel.send("Use this command inside a session thread.")
            return

        session_id = self._session_for_thread(message.channel.id)
        if not session_id:
            await message.channel.send("No session linked to this thread.")
            return

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self._api_url(f"/sessions/{session_id}/interrupt"),
                    headers=self._api_headers(),
                    timeout=10.0,
                )
                response.raise_for_status()
            await message.channel.send("⏹️ Session interrupted.")
        except httpx.HTTPStatusError as e:
            try:
                error = e.response.json().get("error", {}).get("message", str(e))
            except Exception:
                error = str(e)
            await message.channel.send(f"Cannot interrupt: {error}")
        except Exception as e:
            logger.exception("Failed to interrupt session")
            await message.channel.send(f"Failed to interrupt: {e}")

    # ------------------------------------------------------------------
    # Session input forwarding
    # ------------------------------------------------------------------

    async def _forward_input(self, message: any, session_id: str, text: str) -> None:
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self._api_url(f"/sessions/{session_id}/input"),
                    json={"text": text},
                    headers=self._api_headers(),
                    timeout=10.0,
                )
                response.raise_for_status()
            logger.info(
                "Forwarded human input from Discord",
                session_id=session_id,
                thread_id=message.channel.id,
                username=message.author.name,
            )
        except httpx.HTTPStatusError as e:
            try:
                error = e.response.json().get("error", {}).get("message", e.response.text)
            except Exception:
                error = e.response.text
            await message.channel.send(f"Failed to send input: {error}")
        except Exception:
            logger.exception("Failed to forward human input", session_id=session_id)
            await message.channel.send("Failed to send input.")

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    def _format_external_page(self, page: int) -> tuple[str, int, int]:
        sessions = self._external_view or []
        if not sessions:
            if self._external_query:
                return (
                    f"No external sessions match directory search: {self._external_query}\n\n"
                    "Try a different query, or run !list to clear the search.",
                    1,
                    1,
                )
            return (
                "No external sessions found.\n\n"
                "Start a Claude Code or Codex session first, then use !list to see it.",
                1, 1,
            )

        total = len(sessions)
        total_pages = max(1, (total + _EXTERNAL_PAGE_SIZE - 1) // _EXTERNAL_PAGE_SIZE)
        page = max(1, min(page, total_pages))
        start = (page - 1) * _EXTERNAL_PAGE_SIZE
        end = min(start + _EXTERNAL_PAGE_SIZE, total)

        title = f"External Sessions (page {page}/{total_pages})"
        if self._external_query:
            title += f" [search: {self._external_query}]"
        lines: list[str] = [f"{title}:\n"]
        for idx in range(start, end):
            s = sessions[idx]
            n = idx + 1  # index in the current view for !attach
            runner = s.get("runner_type", "unknown")
            directory = s.get("directory", "")
            dir_short = directory.rsplit("/", 1)[-1] if directory else "unknown"
            running = "🟢" if s.get("is_running") else "⚪"
            prompt = s.get("first_prompt") or ""
            prompt_short = (prompt[:40] + "…") if len(prompt) > 40 else prompt
            lines.append(f"  {n}. {running} {runner} in {dir_short}")
            if prompt_short:
                lines.append(f"      {prompt_short}")

        if not self._external_query and len(self._cached_external) == _EXTERNAL_MAX_FETCH:
            lines.append(f"\nShowing up to {_EXTERNAL_MAX_FETCH} sessions (API limit).")
        lines.append("\nUse !attach <number> to attach.")
        return "\n".join(lines), page, total_pages

    # ------------------------------------------------------------------
    # Bridge interface (outgoing events)
    # ------------------------------------------------------------------

    async def on_output(
        self, session_id: str, text: str, metadata: dict | None = None
    ) -> None:
        """Send output text to Discord thread."""
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
                # Discord has a 2000 char limit per message
                for i in range(0, len(text), 2000):
                    await thread.send(text[i:i + 2000])
        except Exception:
            logger.exception("Failed to send Discord message", session_id=session_id)

    async def on_approval_request(
        self, session_id: str, request: ApprovalRequest
    ) -> None:
        """Send an approval request to Discord thread."""
        if not self._client:
            return

        thread_id = self._thread_ids.get(session_id)
        if not thread_id:
            return

        text = f"**Approval Required**\n\n{request.title}\n\n{request.description}\n\nReply with `allow` or `deny`."
        try:
            thread = self._client.get_channel(thread_id)
            if thread:
                await thread.send(text)
        except Exception:
            logger.exception("Failed to send Discord approval request", session_id=session_id)

    async def on_status_change(
        self, session_id: str, status: str, metadata: dict | None = None
    ) -> None:
        """Send status change to Discord thread."""
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
        """Create a Discord thread for a session."""
        if not self._client:
            raise RuntimeError("Discord client not initialized")

        try:
            channel = self._client.get_channel(self._channel_id)
            if not channel:
                raise RuntimeError(f"Discord channel {self._channel_id} not found")

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
