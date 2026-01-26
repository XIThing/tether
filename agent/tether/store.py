"""Session storage and runtime process state."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import uuid
from collections import deque
import re
from datetime import datetime, timedelta, timezone
from threading import Lock

import structlog
from sqlalchemy import func as sa_func
from sqlmodel import select

from tether.db import get_session as get_db_session
from tether.git import has_git_repository, normalize_directory_path
from tether.models import Message, RepoRef, Session, SessionState
from tether.settings import settings

logger = structlog.get_logger("tether.store")


class SessionStore:
    """Session registry with SQLModel persistence and per-session process bookkeeping."""

    def __init__(self) -> None:
        self._data_dir = settings.data_dir()
        self._db_lock = Lock()
        os.makedirs(self._data_dir, exist_ok=True)
        os.makedirs(os.path.join(self._data_dir, "sessions"), exist_ok=True)
        self._sessions: dict[str, Session] = {}
        self._seq: dict[str, int] = {}
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        self._procs: dict[str, asyncio.subprocess.Process] = {}
        self._pending_inputs: dict[str, list[str]] = {}
        self._recent_output: dict[str, deque[str]] = {}
        self._claude_tasks: dict[str, asyncio.Task] = {}
        self._stop_requested: dict[str, bool] = {}
        self._synced_message_counts: dict[str, int] = {}
        self._load_sessions()

    def _load_sessions(self) -> None:
        with self._db_lock:
            with get_db_session() as db:
                rows = db.exec(select(Session)).all()
                for row in rows:
                    self._sessions[row.id] = row
                    self._seq[row.id] = 0
                    self._subscribers.setdefault(row.id, [])

    def _now(self) -> str:
        """Return an ISO8601 UTC timestamp suitable for API payloads."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _parse_ts(self, value: str) -> datetime:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )

    def create_session(self, repo_id: str, base_ref: str | None) -> Session:
        """Create and register a new session in CREATED state.

        Args:
            repo_id: Identifier for the repo being worked on.
            base_ref: Optional base ref name or branch.
        """
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        now = self._now()
        session = Session(
            id=session_id,
            repo_id=repo_id,
            repo_display=repo_id,
            repo_ref_type="path",
            repo_ref_value=repo_id,
            state=SessionState.CREATED.value,
            name="New session",
            created_at=now,
            started_at=None,
            ended_at=None,
            last_activity_at=now,
            exit_code=None,
            summary=None,
            runner_header=None,
        )
        self._sessions[session_id] = session
        self._seq[session_id] = 0
        self._subscribers.setdefault(session_id, [])
        self._persist_session(session)
        return session

    def list_sessions(self) -> list[Session]:
        """Return all sessions currently tracked in memory."""
        return list(self._sessions.values())

    def get_session(self, session_id: str) -> Session | None:
        """Fetch a session by id, or None if missing."""
        return self._sessions.get(session_id)

    def update_session(self, session: Session) -> None:
        """Persist an updated session snapshot."""
        self._sessions[session.id] = session
        self._persist_session(session)

    def delete_session(self, session_id: str) -> bool:
        """Remove a session and its associated runtime state."""
        session = self._sessions.pop(session_id, None)
        if not session:
            return False
        with self._db_lock:
            with get_db_session() as db:
                # Delete messages first
                messages = db.exec(select(Message).where(Message.session_id == session_id)).all()
                for msg in messages:
                    db.delete(msg)
                # Delete session
                db_session = db.get(Session, session_id)
                if db_session:
                    db.delete(db_session)
                db.commit()
        self._seq.pop(session_id, None)
        self._subscribers.pop(session_id, None)
        self.clear_process(session_id)
        self.clear_pending_inputs(session_id)
        self.clear_last_output(session_id)
        self.clear_workdir(session_id)
        self.clear_claude_task(session_id)
        self.clear_stop_requested(session_id)
        return True

    def clear_all_data(self) -> None:
        """Delete all persisted sessions and in-memory session state."""
        with self._db_lock:
            with get_db_session() as db:
                # Delete all messages
                messages = db.exec(select(Message)).all()
                for msg in messages:
                    db.delete(msg)
                # Delete all sessions
                sessions = db.exec(select(Session)).all()
                for sess in sessions:
                    db.delete(sess)
                db.commit()
        self._sessions.clear()
        self._seq.clear()
        self._subscribers.clear()
        self._procs.clear()
        self._pending_inputs.clear()
        self._recent_output.clear()
        self._claude_tasks.clear()
        self._stop_requested.clear()
        logs_root = os.path.join(self._data_dir, "sessions")
        shutil.rmtree(logs_root, ignore_errors=True)
        os.makedirs(logs_root, exist_ok=True)

    def next_seq(self, session_id: str) -> int:
        """Advance and return the per-session event sequence counter."""
        current = self._seq.get(session_id, 0) + 1
        self._seq[session_id] = current
        return current

    def new_subscriber(self, session_id: str) -> asyncio.Queue:
        """Register a new SSE subscriber queue for a session.

        Args:
            session_id: Internal session identifier.
        """
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(session_id, []).append(queue)
        logger.debug(
            "New SSE subscriber",
            session_id=session_id,
            total_subscribers=len(self._subscribers.get(session_id, [])),
        )
        return queue

    def remove_subscriber(self, session_id: str, queue: asyncio.Queue) -> None:
        """Unregister an SSE subscriber queue."""
        queues = self._subscribers.get(session_id, [])
        if queue in queues:
            queues.remove(queue)

    async def emit(self, session_id: str, event: dict) -> None:
        """Broadcast an event payload to all session subscribers.

        Args:
            session_id: Internal session identifier.
            event: Event payload to broadcast.
        """
        queues = self._subscribers.get(session_id, [])
        logger.debug(
            "Broadcasting event",
            session_id=session_id,
            event_type=event.get("type"),
            subscriber_count=len(queues),
        )
        for queue in list(queues):
            await queue.put(event)
        self._append_event_log(session_id, event)

    def _persist_session(self, session: Session) -> None:
        with self._db_lock:
            with get_db_session() as db:
                db.merge(session)
                db.commit()

    def _append_event_log(self, session_id: str, event: dict) -> None:
        path = os.path.join(self._data_dir, "sessions", session_id, "events.jsonl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        max_bytes = 5_000_000  # 5MB
        if max_bytes > 0 and os.path.exists(path):
            try:
                if os.path.getsize(path) > max_bytes:
                    rotated = f"{path}.1"
                    if os.path.exists(rotated):
                        os.remove(rotated)
                    os.replace(path, rotated)
            except OSError:
                pass
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, separators=(",", ":")) + "\n")

    def prune_sessions(self, retention_days: int) -> int:
        """Delete sessions (and logs) older than the retention window."""
        if retention_days <= 0:
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        removed = 0
        for session in list(self._sessions.values()):
            if session.state in (SessionState.RUNNING.value, SessionState.INTERRUPTING.value):
                continue
            ts = session.ended_at or session.last_activity_at or session.created_at
            if not ts:
                continue
            try:
                when = self._parse_ts(ts)
            except ValueError:
                continue
            if when < cutoff:
                if self.delete_session(session.id):
                    removed += 1
        return removed

    def set_process(self, session_id: str, proc: asyncio.subprocess.Process) -> None:
        """Track the subprocess running for a session."""
        self._procs[session_id] = proc

    def get_process(self, session_id: str) -> asyncio.subprocess.Process | None:
        """Return the tracked subprocess, if any."""
        return self._procs.get(session_id)

    def clear_process(self, session_id: str) -> None:
        self._procs.pop(session_id, None)

    def add_pending_input(self, session_id: str, text: str) -> None:
        """Queue input to send once the runner is ready."""
        self._pending_inputs.setdefault(session_id, []).append(text)

    def pop_pending_inputs(self, session_id: str) -> list[str]:
        """Drain and return all pending inputs."""
        return self._pending_inputs.pop(session_id, [])

    def clear_pending_inputs(self, session_id: str) -> None:
        self._pending_inputs.pop(session_id, None)

    def pop_next_pending_input(self, session_id: str) -> str | None:
        """Pop the next queued input, if any."""
        queue = self._pending_inputs.get(session_id)
        if not queue:
            return None
        item = queue.pop(0)
        if not queue:
            self._pending_inputs.pop(session_id, None)
        return item

    def has_pending_inputs(self, session_id: str) -> bool:
        """Return True if there is queued input."""
        return bool(self._pending_inputs.get(session_id))

    def set_runner_session_id(self, session_id: str, runner_session_id: str) -> None:
        """Store the runner-specific session id and persist to database."""
        session = self._sessions.get(session_id)
        if session:
            session.runner_session_id = runner_session_id
            self._persist_session(session)

    def get_runner_session_id(self, session_id: str) -> str | None:
        """Fetch the runner-specific session id."""
        session = self._sessions.get(session_id)
        return session.runner_session_id if session else None

    def clear_runner_session_id(self, session_id: str) -> None:
        """Clear the runner-specific session id."""
        session = self._sessions.get(session_id)
        if session:
            session.runner_session_id = None
            self._persist_session(session)

    def find_session_by_runner_session_id(self, runner_session_id: str) -> str | None:
        """Find a Tether session ID that is attached to the given runner session ID.

        Args:
            runner_session_id: The external/runner session ID to look up.

        Returns:
            The Tether session ID if found, None otherwise.
        """
        for session in self._sessions.values():
            if session.runner_session_id == runner_session_id:
                return session.id
        return None

    def set_synced_message_count(self, session_id: str, count: int) -> None:
        """Store the number of messages synced from external session."""
        self._synced_message_counts[session_id] = count

    def get_synced_message_count(self, session_id: str) -> int:
        """Get the number of messages previously synced from external session."""
        return self._synced_message_counts.get(session_id, 0)

    def should_emit_output(self, session_id: str, text: str) -> bool:
        """Return True if output is non-empty and not recently emitted.

        Args:
            session_id: Internal session identifier.
            text: Raw output text.
        """
        normalized = self._normalize_output(text)
        if not normalized:
            return False
        history = self._recent_output.get(session_id)
        if history is None:
            history = deque(maxlen=10)
            self._recent_output[session_id] = history
        if normalized in history:
            return False
        history.append(normalized)
        return True

    def _normalize_output(self, text: str) -> str:
        """Normalize output to de-duplicate noisy repeated lines.

        Args:
            text: Output text to normalize.
        """
        # Strip ANSI codes and collapse whitespace for stable comparisons.
        stripped = re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", text)
        compact = " ".join(stripped.strip().split())
        return compact

    def clear_last_output(self, session_id: str) -> None:
        self._recent_output.pop(session_id, None)

    def get_recent_output(self, session_id: str) -> list[str]:
        """Get recent output chunks for a session.

        Args:
            session_id: Internal session identifier.

        Returns:
            List of recent output strings (up to 10).
        """
        return list(self._recent_output.get(session_id, []))

    def set_workdir(self, session_id: str, path: str, *, managed: bool) -> str:
        """Record a working directory and update the session metadata."""
        normalized = normalize_directory_path(path)
        session = self._sessions.get(session_id)
        if session:
            session.directory = normalized
            session.directory_has_git = has_git_repository(normalized)
            session.workdir_managed = managed
            self.update_session(session)
        return normalized

    def create_workdir(self, session_id: str) -> str:
        """Create a temporary working directory for the session."""
        path = tempfile.mkdtemp(prefix=f"tether_{session_id}_")
        return self.set_workdir(session_id, path, managed=True)

    def get_workdir(self, session_id: str) -> str | None:
        """Return the session working directory, if set."""
        session = self._sessions.get(session_id)
        return session.directory if session else None

    def clear_workdir(self, session_id: str, *, force: bool = True) -> None:
        """Clear the working directory, removing temp dirs if managed."""
        session = self._sessions.get(session_id)
        if not session:
            return
        if not force and not session.workdir_managed:
            return
        path = session.directory
        if path and session.workdir_managed:
            shutil.rmtree(path, ignore_errors=True)
        session.directory = None
        session.workdir_managed = False

    def add_message(self, session_id: str, role: str, content: object) -> Message:
        """Add a message to conversation history.

        Args:
            session_id: Internal session identifier.
            role: Message role ("user" or "assistant").
            content: Content blocks (will be JSON-encoded).
        """
        message_id = f"msg_{uuid.uuid4().hex[:12]}"
        now = self._now()
        content_json = json.dumps(content)
        with self._db_lock:
            with get_db_session() as db:
                max_seq = db.exec(
                    select(sa_func.coalesce(sa_func.max(Message.seq), 0)).where(
                        Message.session_id == session_id
                    )
                ).one()
                seq = max_seq + 1
                message = Message(
                    id=message_id,
                    session_id=session_id,
                    role=role,
                    content=content_json,
                    created_at=now,
                    seq=seq,
                )
                db.add(message)
                db.commit()
        return Message(
            id=message_id,
            session_id=session_id,
            role=role,
            content=content_json,
            seq=seq,
            created_at=now,
        )

    def get_messages(self, session_id: str) -> list[dict]:
        """Get conversation history for a session.

        Args:
            session_id: Internal session identifier.

        Returns:
            List of message dicts with role and content for Anthropic API.
        """
        with self._db_lock:
            with get_db_session() as db:
                rows = db.exec(
                    select(Message).where(Message.session_id == session_id).order_by(Message.seq)
                ).all()
                messages = []
                for row in rows:
                    content = json.loads(row.content) if row.content else []
                    messages.append({"role": row.role, "content": content})
                return messages

    def clear_messages(self, session_id: str) -> None:
        """Clear conversation history for a session.

        Args:
            session_id: Internal session identifier.
        """
        with self._db_lock:
            with get_db_session() as db:
                messages = db.exec(select(Message).where(Message.session_id == session_id)).all()
                for msg in messages:
                    db.delete(msg)
                db.commit()

    def get_message_count(self, session_id: str) -> int:
        """Get the number of messages for a session.

        Args:
            session_id: Internal session identifier.

        Returns:
            Number of messages in the session.
        """
        with self._db_lock:
            with get_db_session() as db:
                count = db.exec(
                    select(sa_func.count(Message.id)).where(Message.session_id == session_id)
                ).one()
                return count or 0

    def set_claude_task(self, session_id: str, task: asyncio.Task) -> None:
        """Track the Claude conversation loop task for a session."""
        self._claude_tasks[session_id] = task

    def get_claude_task(self, session_id: str) -> asyncio.Task | None:
        """Return the Claude conversation loop task, if any."""
        return self._claude_tasks.get(session_id)

    def clear_claude_task(self, session_id: str) -> None:
        self._claude_tasks.pop(session_id, None)

    def request_stop(self, session_id: str) -> None:
        """Signal the Claude conversation loop to stop."""
        self._stop_requested[session_id] = True

    def is_stop_requested(self, session_id: str) -> bool:
        """Check if stop was requested for a session."""
        return self._stop_requested.get(session_id, False)

    def clear_stop_requested(self, session_id: str) -> None:
        self._stop_requested.pop(session_id, None)

    def read_event_log(
        self, session_id: str, *, since_seq: int = 0, limit: int | None = None
    ) -> list[dict]:
        """Read persisted SSE events for a session.

        Args:
            session_id: Internal session identifier.
            since_seq: Only return events with seq greater than this value.
            limit: Optional maximum number of events to return.
        """
        path = os.path.join(self._data_dir, "sessions", session_id, "events.jsonl")
        if not os.path.exists(path):
            return []
        events: list[dict] = []
        try:
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    seq = int(event.get("seq") or 0)
                    if seq and seq <= since_seq:
                        continue
                    events.append(event)
                    if limit and len(events) >= limit:
                        break
        except OSError:
            return []
        return events


store = SessionStore()
