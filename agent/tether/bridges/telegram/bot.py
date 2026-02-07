"""Telegram bot bridge implementation."""

import asyncio
import json
import os
import time
from typing import Any

import structlog

from tether.bridges.base import ApprovalRequest, BridgeInterface
from tether.bridges.telegram.formatting import chunk_message, escape_markdown, markdown_to_telegram_html, strip_tool_markers
from tether.bridges.telegram.state import StateManager
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
_EXTERNAL_MAX_FETCH = 200  # API max is 200; this is a UX cap for Telegram pagination.
_TELEGRAM_TOPIC_NAME_MAX_LEN = 64
_EXTERNAL_REPLAY_LIMIT = 10
_EXTERNAL_REPLAY_MAX_CHARS = 3500
_ALLOW_ALL_DURATION_S = 30 * 60  # 30 minutes


class TelegramBridge(BridgeInterface):
    """Telegram bridge that routes agent events to Telegram forum topics.

    Each session gets its own forum topic. Implements the BridgeInterface
    to handle output, approvals, and status updates.

    Args:
        bot_token: Telegram bot API token.
        forum_group_id: Telegram forum group chat ID.
        state_manager: Optional state manager (created if not provided).
    """

    def __init__(
        self,
        bot_token: str,
        forum_group_id: int,
        state_manager: StateManager | None = None,
    ):
        self._bot_token = bot_token
        self._forum_group_id = forum_group_id
        self._app: Any = None
        self._state = state_manager or StateManager(
            os.path.join(settings.data_dir(), "telegram_state.json")
        )
        self._state.load()
        self._cached_external: list[dict] = []
        # Current view of external sessions as presented to the user (may be filtered).
        self._external_query: str | None = None
        self._external_view: list[dict] = []
        # Auto-approve: session_id -> expiry timestamp
        self._allow_all_until: dict[str, float] = {}
        self._allow_tool_until: dict[str, dict[str, float]] = {}  # session → {tool: expiry}

    async def start(self) -> None:
        """Start the Telegram bot."""
        try:
            from telegram.ext import (
                Application,
                CallbackQueryHandler,
                CommandHandler,
                MessageHandler,
                filters,
            )
        except ImportError:
            logger.error("python-telegram-bot not installed. Install with: pip install python-telegram-bot")
            return

        self._app = Application.builder().token(self._bot_token).build()

        # Command handlers
        self._app.add_handler(CommandHandler("help", self._cmd_help))
        self._app.add_handler(CommandHandler("start", self._cmd_help))
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(CommandHandler("sessions", self._cmd_status))
        self._app.add_handler(CommandHandler("list", self._cmd_list))
        self._app.add_handler(CommandHandler("attach", self._cmd_attach))
        self._app.add_handler(CommandHandler("stop", self._cmd_stop))

        # Plain text handler for human input (in session topics)
        self._app.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND & filters.ChatType.SUPERGROUP,
                self._handle_message,
            )
        )

        # External session pagination handler
        self._app.add_handler(
            CallbackQueryHandler(self._handle_list_callback_query, pattern=r"^list:")
        )

        # Approval button handler
        self._app.add_handler(
            CallbackQueryHandler(self._handle_callback_query, pattern=r"^approval:")
        )

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()
        await self._ensure_control_topic()
        logger.info("Telegram bridge initialized and started", forum_group_id=self._forum_group_id)

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        if self._app:
            if self._app.updater.running:
                await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
        logger.info("Telegram bridge stopped")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ensure_control_topic(self) -> None:
        """Create the control topic if it doesn't exist yet."""
        if self._state.control_topic_id:
            logger.debug("Control topic already exists", topic_id=self._state.control_topic_id)
            return

        try:
            topic = await self._app.bot.create_forum_topic(
                chat_id=self._forum_group_id,
                name="Tether",
                icon_color=7322096,
            )
            self._state.control_topic_id = topic.message_thread_id
            self._state.save()

            await self._app.bot.send_message(
                chat_id=self._forum_group_id,
                message_thread_id=topic.message_thread_id,
                text=(
                    "Tether control topic\n\n"
                    "Commands:\n"
                    "/status — List all sessions\n"
                    "/list — List external sessions\n"
                    "/attach <number> — Attach to an external session\n"
                    "/help — Show all commands"
                ),
            )

            logger.info("Created control topic", topic_id=topic.message_thread_id)
        except Exception:
            logger.exception("Failed to create control topic")

    @staticmethod
    def _display_name(user: Any) -> str:
        """Get a human-readable display name from a Telegram user object."""
        if not user:
            return "unknown"
        if user.username:
            return f"@{user.username}"
        parts = [user.first_name or "", user.last_name or ""]
        name = " ".join(p for p in parts if p).strip()
        return name or "unknown"

    def _api_headers(self) -> dict[str, str]:
        """Build auth headers for internal API calls."""
        headers: dict[str, str] = {}
        token = settings.token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _api_url(self, path: str) -> str:
        """Build a localhost API URL."""
        return f"http://localhost:{settings.port()}/api{path}"

    @staticmethod
    def _format_tool_input(raw: str) -> str:
        """Pretty-format a tool_input description for Telegram.

        If the raw string looks like a JSON dict, format key-value pairs
        on separate lines. Otherwise return as-is (truncated).
        """
        try:
            obj = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            obj = None

        if isinstance(obj, dict):
            lines: list[str] = []
            for key, value in obj.items():
                v = str(value)
                if len(v) > 200:
                    v = v[:200] + "..."
                lines.append(f"  {key}: {v}")
            return "\n".join(lines)

        text = str(raw)
        if len(text) > 600:
            text = text[:600] + "..."
        return text

    def _make_external_topic_name(self, *, directory: str, session_id: str) -> str:
        """Generate a topic name from the directory, UpperCased.

        If a topic with the same name already exists, append a number.
        """
        dir_short = (directory or "").rstrip("/").rsplit("/", 1)[-1] or "Session"
        base_name = (dir_short[:1].upper() + dir_short[1:])[:_TELEGRAM_TOPIC_NAME_MAX_LEN]

        # Check existing topic names for duplicates
        existing_names = {m.name for m in self._state._mappings.values()}

        if base_name not in existing_names:
            return base_name

        for i in range(2, 100):
            candidate = f"{base_name} {i}"[:_TELEGRAM_TOPIC_NAME_MAX_LEN]
            if candidate not in existing_names:
                return candidate

        return base_name

    async def _send_external_session_replay(
        self,
        *,
        topic_id: int,
        external_id: str,
        runner_type: str,
        limit: int = _EXTERNAL_REPLAY_LIMIT,
    ) -> None:
        """Send recent external session history into the Telegram topic.

        Each conversation message is sent as a separate Telegram message so the
        topic reads like a real chat rather than a single text wall.
        """
        if not self._app:
            return

        import httpx

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self._api_url(f"/external-sessions/{external_id}/history"),
                    headers=self._api_headers(),
                    params={"runner_type": runner_type, "limit": limit},
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

        # Header message
        try:
            await self._app.bot.send_message(
                chat_id=self._forum_group_id,
                message_thread_id=topic_id,
                text=f"📜 Replaying last {len(messages)} messages:",
            )
        except Exception:
            logger.exception("Failed to send replay header")
            return

        # Each conversation message as a separate Telegram message
        for msg in messages:
            role = str(msg.get("role") or "").lower()
            content = strip_tool_markers((msg.get("content") or "").strip())
            thinking = (msg.get("thinking") or "").strip()

            if not content and not thinking:
                continue

            if role == "user":
                prefix = "👤"
            elif role == "assistant":
                prefix = "🤖"
            else:
                prefix = "💬"

            parts: list[str] = []
            if thinking:
                truncated = thinking[:400] + "..." if len(thinking) > 400 else thinking
                parts.append(f"💭 {truncated}")
            if content:
                truncated = content[:800] + "..." if len(content) > 800 else content
                parts.append(truncated)

            text = prefix + " " + "\n\n".join(parts)

            for part in chunk_message(text):
                try:
                    await self._app.bot.send_message(
                        chat_id=self._forum_group_id,
                        message_thread_id=topic_id,
                        text=part,
                    )
                except Exception:
                    logger.exception(
                        "Failed to send replay message",
                        external_id=external_id,
                        topic_id=topic_id,
                    )

    async def _refresh_external_cache(self) -> None:
        """Refresh cached external session list from the API."""
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get(
                self._api_url("/external-sessions"),
                headers=self._api_headers(),
                params={"limit": _EXTERNAL_MAX_FETCH},
                timeout=10.0,
            )
            response.raise_for_status()
        self._cached_external = response.json()

    def _set_external_view(self, query: str | None) -> None:
        """Set the current external sessions view (optionally filtered by directory substring)."""
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

    def _format_external_page(self, page: int) -> tuple[str, int, int]:
        """Format one page of cached external sessions.

        Returns:
            (text, page, total_pages)
        """
        sessions = self._external_view or []
        if not sessions:
            if self._external_query:
                return (
                    f"No external sessions match directory search: {self._external_query}\n\n"
                    "Try a different query, or run /list to clear the search.",
                    1,
                    1,
                )
            return (
                "No external sessions found.\n\n"
                "Start a Claude Code or Codex session first, then use /list to see it.",
                1,
                1,
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
            n = idx + 1  # index in the current view for /attach
            runner = s.get("runner_type", "unknown")
            directory = s.get("directory", "")
            dir_short = directory.rsplit("/", 1)[-1] if directory else "unknown"
            running = "🟢" if s.get("is_running") else "⚪"
            prompt = s.get("first_prompt") or ""
            prompt_short = (prompt[:40] + "…") if len(prompt) > 40 else prompt
            lines.append(f"  {n}. {running} {runner} in {dir_short}")
            if prompt_short:
                lines.append(f"      {prompt_short}")

        # We can only fetch up to the API max; if we hit that cap, hint that there may be more.
        if not self._external_query and len(self._cached_external) == _EXTERNAL_MAX_FETCH:
            lines.append(f"\nShowing up to {_EXTERNAL_MAX_FETCH} sessions (API limit).")
        lines.append("\nUse /attach <number> to attach.")
        return "\n".join(lines), page, total_pages

    def _external_pagination_markup(self, page: int, total_pages: int):
        """Build inline keyboard markup for external session pagination."""
        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        except ImportError:
            return None

        if total_pages <= 1:
            return None

        buttons = []
        if page > 1:
            buttons.append(InlineKeyboardButton("Prev", callback_data=f"list:page:{page - 1}"))
        buttons.append(InlineKeyboardButton("Refresh", callback_data="list:refresh"))
        if page < total_pages:
            buttons.append(InlineKeyboardButton("Next", callback_data=f"list:page:{page + 1}"))
        return InlineKeyboardMarkup([buttons])

    async def _auto_approve(self, session_id: str, request: ApprovalRequest, *, reason: str = "Allow All") -> None:
        """Silently approve a permission request (used by Allow All / Allow Tool)."""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    self._api_url(f"/sessions/{session_id}/permission"),
                    json={
                        "request_id": request.request_id,
                        "allow": True,
                        "message": f"Auto-approved ({reason} active)",
                    },
                    headers=self._api_headers(),
                    timeout=10.0,
                )
            logger.info("Auto-approved via %s", reason, session_id=session_id, request_id=request.request_id)
        except Exception:
            logger.exception("Failed to auto-approve", request_id=request.request_id)

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------

    async def _cmd_help(self, update: Any, context: Any) -> None:
        """Handle /help and /start commands."""
        text = (
            "Tether Bot Commands:\n\n"
            "/status — List all sessions\n"
            "/list [page|search] — List external sessions (Claude Code, Codex)\n"
            "/attach <number> — Attach to an external session\n"
            "/stop — Interrupt the session in this topic\n"
            "/help — Show this help\n\n"
            "Send a text message in a session topic to forward it as input."
        )
        await update.message.reply_text(text)

    async def _cmd_status(self, update: Any, context: Any) -> None:
        """Handle /status — list all Tether sessions."""
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
            logger.exception("Failed to fetch sessions for /status")
            await update.message.reply_text("Failed to fetch sessions.")
            return

        if not sessions:
            await update.message.reply_text("No sessions.")
            return

        lines = ["Sessions:\n"]
        for s in sessions:
            emoji = _STATE_EMOJI.get(s.get("state", ""), "❓")
            name = s.get("name") or s.get("id", "")[:12]
            lines.append(f"  {emoji} {name}")
        await update.message.reply_text("\n".join(lines))

    async def _cmd_list(self, update: Any, context: Any) -> None:
        """Handle /list — list external sessions available for attachment."""
        page = 1
        query: str | None = None
        args = getattr(context, "args", None) or []
        if args:
            first = args[0]
            try:
                page = int(first)
                # Keep existing search (if any) when navigating by page number.
                query = self._external_query
            except Exception:
                query = " ".join(args).strip()
                page = 1

        try:
            await self._refresh_external_cache()
            # If no args, clear the search.
            if not args:
                self._set_external_view(None)
            else:
                self._set_external_view(query)
        except Exception:
            logger.exception("Failed to fetch external sessions")
            await update.message.reply_text("Failed to list external sessions.")
            return

        text, page, total_pages = self._format_external_page(page)
        reply_markup = self._external_pagination_markup(page, total_pages)
        await update.message.reply_text(text, reply_markup=reply_markup)

    async def _cmd_attach(self, update: Any, context: Any) -> None:
        """Handle /attach <number> — attach to an external session and create a topic."""
        import httpx

        args = context.args
        if not args:
            await update.message.reply_text("Usage: /attach <number>\n\nRun /list first.")
            return

        try:
            index = int(args[0]) - 1
        except ValueError:
            await update.message.reply_text("Please provide a session number.")
            return

        if not self._cached_external:
            await update.message.reply_text("No external sessions cached. Run /list first.")
            return
        if not self._external_view:
            await update.message.reply_text("No external sessions listed. Run /list first.")
            return
        if index < 0 or index >= len(self._external_view):
            await update.message.reply_text(f"Invalid number. Use 1–{len(self._external_view)}.")
            return

        external = self._external_view[index]

        try:
            # Create Tether session via attach endpoint
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

            # Check if this session already has a topic
            existing_topic = self._state.get_topic_for_session(session_id)
            if existing_topic:
                await update.message.reply_text(
                    f"Already attached — check the existing topic for this session."
                )
                return

            # Create forum topic
            session_name = self._make_external_topic_name(
                directory=external.get("directory", ""),
                session_id=session_id,
            )
            thread_info = await self.create_thread(session_id, session_name)
            try:
                topic_id = int(thread_info.get("topic_id") or 0)
                if topic_id:
                    await self._send_external_session_replay(
                        topic_id=topic_id,
                        external_id=external["id"],
                        runner_type=str(external["runner_type"]),
                    )
            except Exception:
                # Replay is best-effort; it should never block attachment.
                logger.exception("Failed to replay external session history into Telegram topic")

            # Bind session to Telegram platform
            from tether.store import store
            from tether.bridges.subscriber import bridge_subscriber

            db_session = store.get_session(session_id)
            if db_session:
                db_session.platform = "telegram"
                db_session.platform_thread_id = thread_info.get("thread_id")
                store.update_session(db_session)

            bridge_subscriber.subscribe(session_id, "telegram")

            dir_short = external.get("directory", "").rsplit("/", 1)[-1]
            await update.message.reply_text(
                f"✅ Attached to {external['runner_type']} session in {dir_short}\n\n"
                f"A new topic has been created — send messages there to interact."
            )

        except httpx.HTTPStatusError as e:
            await update.message.reply_text(f"Failed to attach: {e.response.text}")
        except Exception as e:
            logger.exception("Failed to attach to external session")
            await update.message.reply_text(f"Failed to attach: {e}")

    async def _cmd_stop(self, update: Any, context: Any) -> None:
        """Handle /stop — interrupt the session in the current topic."""
        import httpx

        topic_id = update.message.message_thread_id
        if not topic_id:
            await update.message.reply_text("Use this command inside a session topic.")
            return

        session_id = self._state.get_session_for_topic(topic_id)
        if not session_id:
            await update.message.reply_text("No session linked to this topic.")
            return

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self._api_url(f"/sessions/{session_id}/interrupt"),
                    headers=self._api_headers(),
                    timeout=10.0,
                )
                response.raise_for_status()
            await update.message.reply_text("⏹️ Session interrupted.")
        except httpx.HTTPStatusError as e:
            error = e.response.json().get("error", {}).get("message", str(e))
            await update.message.reply_text(f"Cannot interrupt: {error}")
        except Exception as e:
            logger.exception("Failed to interrupt session")
            await update.message.reply_text(f"Failed to interrupt: {e}")

    # ------------------------------------------------------------------
    # Message and callback handlers
    # ------------------------------------------------------------------

    async def _handle_list_callback_query(self, update: Any, context: Any) -> None:
        """Handle pagination callbacks for /list."""
        query = update.callback_query
        if not query or not getattr(query, "data", None):
            return

        data = query.data
        await query.answer()

        if data == "list:refresh":
            try:
                await self._refresh_external_cache()
            except Exception:
                logger.exception("Failed to refresh external sessions")
                try:
                    await query.edit_message_text("Failed to refresh external sessions.")
                except Exception:
                    pass
                return
            self._set_external_view(self._external_query)
            page = 1
        else:
            # list:page:<n>
            try:
                _, kind, value = data.split(":", 2)
                if kind != "page":
                    return
                page = int(value)
            except Exception:
                return

        # If we somehow lost cache (restart), try a refresh for best UX.
        if not self._cached_external:
            try:
                await self._refresh_external_cache()
            except Exception:
                logger.exception("Failed to fetch external sessions for pagination")
                try:
                    await query.edit_message_text("Failed to list external sessions. Run /list again.")
                except Exception:
                    pass
                return
            self._set_external_view(self._external_query)

        text, page, total_pages = self._format_external_page(page)
        reply_markup = self._external_pagination_markup(page, total_pages)
        try:
            await query.edit_message_text(text=text, reply_markup=reply_markup)
        except Exception:
            # If edit fails (message too old, etc.), send a new message.
            try:
                await query.message.reply_text(text, reply_markup=reply_markup)
            except Exception:
                logger.exception("Failed to send external pagination message")

    async def _handle_message(self, update: Any, context: Any) -> None:
        """Handle incoming text messages from Telegram and forward via internal API."""
        if not update.message or not update.message.text:
            return

        topic_id = update.message.message_thread_id
        if not topic_id:
            return

        session_id = self._state.get_session_for_topic(topic_id)
        if not session_id:
            logger.debug(
                "Received message in topic with no session mapping",
                topic_id=topic_id,
            )
            return

        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self._api_url(f"/sessions/{session_id}/input"),
                    json={"text": update.message.text},
                    headers=self._api_headers(),
                    timeout=10.0,
                )
                response.raise_for_status()

            logger.info(
                "Forwarded human input from Telegram",
                session_id=session_id,
                topic_id=topic_id,
                username=update.message.from_user.username,
            )
        except httpx.HTTPStatusError as e:
            try:
                data = e.response.json()
                message = data.get("error", {}).get("message") or e.response.text
            except Exception:
                message = e.response.text
            await update.message.reply_text(f"Failed to send input: {message}")
        except Exception:
            logger.exception(
                "Failed to forward human input",
                session_id=session_id,
                topic_id=topic_id,
            )
            await update.message.reply_text("Failed to send input.")

    async def _handle_callback_query(self, update: Any, context: Any) -> None:
        """Handle approval button clicks in Telegram."""
        query = update.callback_query
        if not query:
            return

        await query.answer()

        # Parse callback data: "approval:request_id:option"
        try:
            parts = query.data.split(":", 2)
            if len(parts) != 3 or parts[0] != "approval":
                logger.warning("Invalid callback data format", data=query.data)
                return
            request_id = parts[1]
            option_selected = parts[2]
        except Exception:
            logger.exception("Failed to parse callback data", data=query.data)
            return

        topic_id = query.message.message_thread_id
        if not topic_id:
            logger.warning("Callback from message with no topic ID")
            return

        session_id = self._state.get_session_for_topic(topic_id)
        if not session_id:
            logger.warning("No session for topic", topic_id=topic_id)
            await query.edit_message_text(
                text=f"{query.message.text}\n\n❌ Error: Session not found"
            )
            return

        try:
            import httpx

            username = self._display_name(query.from_user)

            # Handle "Allow All (30m)" and "Allow {tool} (30m)" options
            if option_selected == "AllowAll":
                self._allow_all_until[session_id] = time.time() + _ALLOW_ALL_DURATION_S
                allow = True
                display_option = "Allow All (30m)"
            elif option_selected.startswith("AllowTool:"):
                tool_name = option_selected.split(":", 1)[1]
                self._allow_tool_until.setdefault(session_id, {})[tool_name] = (
                    time.time() + _ALLOW_ALL_DURATION_S
                )
                allow = True
                display_option = f"Allow {tool_name} (30m)"
            else:
                allow = option_selected.lower() in ("allow", "yes", "approve")
                display_option = option_selected

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self._api_url(f"/sessions/{session_id}/permission"),
                    json={
                        "request_id": request_id,
                        "allow": allow,
                        "message": f"{display_option} by {username}",
                    },
                    headers=self._api_headers(),
                    timeout=10.0,
                )
                response.raise_for_status()

            await query.edit_message_text(
                text=f"{query.message.text}\n\n✅ {display_option} by {username}"
            )
            logger.info(
                "Approval response submitted",
                session_id=session_id,
                request_id=request_id,
                option=display_option,
                username=username,
            )

        except httpx.HTTPStatusError as e:
            error_msg = "already resolved" if e.response.status_code == 404 else str(e)
            logger.warning(
                "Failed to submit approval",
                session_id=session_id,
                request_id=request_id,
                error=error_msg,
            )
            await query.edit_message_text(
                text=f"{query.message.text}\n\n❌ Error: {error_msg}"
            )
        except Exception:
            logger.exception(
                "Failed to handle callback",
                session_id=session_id,
                request_id=request_id,
            )
            await query.edit_message_text(
                text=f"{query.message.text}\n\n❌ Error: Failed to submit response"
            )

    # ------------------------------------------------------------------
    # Bridge interface (outgoing events)
    # ------------------------------------------------------------------

    async def on_output(
        self, session_id: str, text: str, metadata: dict | None = None
    ) -> None:
        """Send output text to the session's Telegram topic."""
        if not self._app:
            logger.warning("Telegram app not initialized")
            return

        topic_id = self._state.get_topic_for_session(session_id)
        if not topic_id:
            logger.warning("No Telegram topic for session", session_id=session_id)
            return

        formatted = markdown_to_telegram_html(text)
        chunks = chunk_message(formatted)
        for chunk in chunks:
            try:
                await self._app.bot.send_message(
                    chat_id=self._forum_group_id,
                    message_thread_id=topic_id,
                    text=chunk,
                    parse_mode="HTML",
                )
            except Exception:
                # Fallback to plain text if HTML parsing fails
                try:
                    await self._app.bot.send_message(
                        chat_id=self._forum_group_id,
                        message_thread_id=topic_id,
                        text=text[:4096],
                    )
                except Exception:
                    logger.exception(
                        "Failed to send Telegram message",
                        session_id=session_id,
                        topic_id=topic_id,
                    )

    async def on_typing(self, session_id: str) -> None:
        """Send a typing indicator (chat action) to the session's topic."""
        if not self._app:
            return

        topic_id = self._state.get_topic_for_session(session_id)
        if not topic_id:
            return

        try:
            await self._app.bot.send_chat_action(
                chat_id=self._forum_group_id,
                message_thread_id=topic_id,
                action="typing",
            )
        except Exception:
            logger.debug("Failed to send typing action", session_id=session_id)

    async def on_approval_request(
        self, session_id: str, request: ApprovalRequest
    ) -> None:
        """Send an approval request with inline keyboard buttons."""
        if not self._app:
            logger.warning("Telegram app not initialized")
            return

        # Auto-approve if "Allow All" or "Allow {tool}" is active
        now = time.time()
        if now < self._allow_all_until.get(session_id, 0):
            await self._auto_approve(session_id, request, reason="Allow All")
            return
        tool_expiry = self._allow_tool_until.get(session_id, {}).get(request.title, 0)
        if now < tool_expiry:
            await self._auto_approve(session_id, request, reason=f"Allow {request.title}")
            return

        topic_id = self._state.get_topic_for_session(session_id)
        if not topic_id:
            logger.warning("No Telegram topic for session", session_id=session_id)
            return

        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        except ImportError:
            logger.error("python-telegram-bot not installed")
            return

        description = self._format_tool_input(request.description)

        tool_name = request.title
        keyboard = [
            [
                InlineKeyboardButton("Allow", callback_data=f"approval:{request.request_id}:Allow"),
                InlineKeyboardButton("Deny", callback_data=f"approval:{request.request_id}:Deny"),
            ],
            [
                InlineKeyboardButton(f"Allow {tool_name} (30m)", callback_data=f"approval:{request.request_id}:AllowTool:{tool_name}"),
                InlineKeyboardButton("Allow All (30m)", callback_data=f"approval:{request.request_id}:AllowAll"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = f"⚠️ Approval Required\n\n{request.title}\n\n{description}"

        try:
            await self._app.bot.send_message(
                chat_id=self._forum_group_id,
                message_thread_id=topic_id,
                text=text,
                reply_markup=reply_markup,
            )
        except Exception:
            logger.exception(
                "Failed to send approval request",
                session_id=session_id,
                request_id=request.request_id,
            )

    async def on_status_change(
        self, session_id: str, status: str, metadata: dict | None = None
    ) -> None:
        """Send status change notification to Telegram."""
        if not self._app:
            return

        topic_id = self._state.get_topic_for_session(session_id)
        if not topic_id:
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
            await self._app.bot.send_message(
                chat_id=self._forum_group_id,
                message_thread_id=topic_id,
                text=text,
            )
        except Exception:
            logger.exception(
                "Failed to send status update",
                session_id=session_id,
                status=status,
            )

    async def create_thread(self, session_id: str, session_name: str) -> dict:
        """Create a Telegram forum topic for a session."""
        if not self._app:
            raise RuntimeError("Telegram app not initialized")

        try:
            topic = await self._app.bot.create_forum_topic(
                chat_id=self._forum_group_id,
                name=session_name[:128],  # Telegram limit
                icon_color=7322096,  # Light blue
            )

            topic_id = topic.message_thread_id
            self._state.set_topic_for_session(session_id, topic_id, session_name)

            logger.info(
                "Created Telegram topic",
                session_id=session_id,
                topic_id=topic_id,
                name=session_name,
            )

            return {
                "thread_id": str(topic_id),
                "platform": "telegram",
                "topic_id": topic_id,
            }

        except Exception as e:
            logger.exception(
                "Failed to create Telegram topic",
                session_id=session_id,
                name=session_name,
            )
            raise RuntimeError(f"Failed to create Telegram topic: {e}")
