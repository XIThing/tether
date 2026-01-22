"""Session storage and runtime process state."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
import tempfile
import uuid
from collections import deque
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional
from threading import Lock

from tether.git import has_git_repository, normalize_directory_path
from tether.models import RepoRef, Session, SessionState


class SessionStore:
    """Session registry with SQLite persistence and per-session process bookkeeping."""
    def __init__(self) -> None:
        self._data_dir = os.environ.get("AGENT_DATA_DIR") or os.path.join(
            os.path.dirname(__file__), "..", "data"
        )
        self._data_dir = os.path.abspath(self._data_dir)
        self._db_path = os.path.join(self._data_dir, "sessions.db")
        self._db_lock = Lock()
        os.makedirs(self._data_dir, exist_ok=True)
        os.makedirs(os.path.join(self._data_dir, "sessions"), exist_ok=True)
        self._db = sqlite3.connect(self._db_path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL;")
        self._db.execute("PRAGMA synchronous=NORMAL;")
        self._init_db()
        self._sessions: Dict[str, Session] = {}
        self._seq: Dict[str, int] = {}
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._procs: Dict[str, asyncio.subprocess.Process] = {}
        self._workdirs: Dict[str, str] = {}
        self._master_fds: Dict[str, int] = {}
        self._stdins: Dict[str, asyncio.StreamWriter] = {}
        self._input_locks: Dict[str, asyncio.Lock] = {}
        self._prompt_sent: Dict[str, bool] = {}
        self._pending_inputs: Dict[str, List[str]] = {}
        self._codex_session_ids: Dict[str, str] = {}
        self._recent_output: Dict[str, deque[str]] = {}
        self._workdir_managed: Dict[str, bool] = {}
        self._load_sessions()

    def _init_db(self) -> None:
        with self._db_lock:
            self._db.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    repo_id TEXT NOT NULL,
                    repo_display TEXT NOT NULL,
                    repo_ref_type TEXT NOT NULL,
                    repo_ref_value TEXT NOT NULL,
                    state TEXT NOT NULL,
                    name TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    ended_at TEXT,
                    last_activity_at TEXT NOT NULL,
                    exit_code INTEGER,
                    summary TEXT,
                    codex_header TEXT
                )
                """
            )
            self._db.commit()

    def _load_sessions(self) -> None:
        with self._db_lock:
            rows = self._db.execute("SELECT * FROM sessions").fetchall()
        for row in rows:
            session = self._session_from_row(row)
            self._sessions[session.id] = session
            self._seq[session.id] = 0
            self._subscribers.setdefault(session.id, [])

    def _session_from_row(self, row: tuple) -> Session:
        (
            session_id,
            repo_id,
            repo_display,
            repo_ref_type,
            repo_ref_value,
            state,
            name,
            created_at,
            started_at,
            ended_at,
            last_activity_at,
            exit_code,
            summary,
            codex_header,
        ) = row
        return Session(
            id=session_id,
            repo_id=repo_id,
            repo_display=repo_display,
            repo_ref=RepoRef(type=repo_ref_type, value=repo_ref_value),
            state=SessionState(state),
            name=name,
            created_at=created_at,
            started_at=started_at,
            ended_at=ended_at,
            last_activity_at=last_activity_at,
            exit_code=exit_code,
            summary=summary,
            codex_header=codex_header,
        )

    def _now(self) -> str:
        """Return an ISO8601 UTC timestamp suitable for API payloads."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def create_session(self, repo_id: str, base_ref: Optional[str]) -> Session:
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
            repo_ref=RepoRef(type="path", value=repo_id),
            state=SessionState.CREATED,
            name=None,
            created_at=now,
            started_at=None,
            ended_at=None,
            last_activity_at=now,
            exit_code=None,
            summary=None,
            codex_header=None,
        )
        self._sessions[session_id] = session
        self._seq[session_id] = 0
        self._subscribers.setdefault(session_id, [])
        self._persist_session(session)
        return session

    def list_sessions(self) -> List[Session]:
        """Return all sessions currently tracked in memory."""
        return list(self._sessions.values())

    def get_session(self, session_id: str) -> Optional[Session]:
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
            self._db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            self._db.commit()
        self._seq.pop(session_id, None)
        self._subscribers.pop(session_id, None)
        self.clear_process(session_id)
        self.clear_master_fd(session_id)
        self.clear_stdin(session_id)
        self.clear_prompt_sent(session_id)
        self.clear_pending_inputs(session_id)
        self.clear_codex_session_id(session_id)
        self.clear_last_output(session_id)
        self.clear_workdir(session_id)
        return True

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
        for queue in list(self._subscribers.get(session_id, [])):
            await queue.put(event)
        self._append_event_log(session_id, event)

    def _persist_session(self, session: Session) -> None:
        with self._db_lock:
            self._db.execute(
                """
                INSERT INTO sessions (
                    id, repo_id, repo_display, repo_ref_type, repo_ref_value, state,
                    name, created_at, started_at, ended_at, last_activity_at,
                    exit_code, summary, codex_header
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    repo_id=excluded.repo_id,
                    repo_display=excluded.repo_display,
                    repo_ref_type=excluded.repo_ref_type,
                    repo_ref_value=excluded.repo_ref_value,
                    state=excluded.state,
                    name=excluded.name,
                    created_at=excluded.created_at,
                    started_at=excluded.started_at,
                    ended_at=excluded.ended_at,
                    last_activity_at=excluded.last_activity_at,
                    exit_code=excluded.exit_code,
                    summary=excluded.summary,
                    codex_header=excluded.codex_header
                """,
                (
                    session.id,
                    session.repo_id,
                    session.repo_display,
                    session.repo_ref.type,
                    session.repo_ref.value,
                    session.state.value,
                    session.name,
                    session.created_at,
                    session.started_at,
                    session.ended_at,
                    session.last_activity_at,
                    session.exit_code,
                    session.summary,
                    session.codex_header,
                ),
            )
            self._db.commit()

    def _append_event_log(self, session_id: str, event: dict) -> None:
        path = os.path.join(self._data_dir, "sessions", session_id, "events.jsonl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, separators=(",", ":")) + "\n")

    def set_process(self, session_id: str, proc: asyncio.subprocess.Process) -> None:
        """Track the subprocess running for a session."""
        self._procs[session_id] = proc

    def get_process(self, session_id: str) -> Optional[asyncio.subprocess.Process]:
        """Return the tracked subprocess, if any."""
        return self._procs.get(session_id)

    def clear_process(self, session_id: str) -> None:
        self._procs.pop(session_id, None)

    def set_master_fd(self, session_id: str, fd: int) -> None:
        """Track the PTY master fd for a session."""
        self._master_fds[session_id] = fd

    def get_master_fd(self, session_id: str) -> Optional[int]:
        """Return the PTY master fd, if present."""
        return self._master_fds.get(session_id)

    def clear_master_fd(self, session_id: str) -> None:
        self._master_fds.pop(session_id, None)

    def set_stdin(self, session_id: str, stdin: asyncio.StreamWriter) -> None:
        """Store the stdin stream for a session's subprocess."""
        self._stdins[session_id] = stdin

    def get_stdin(self, session_id: str) -> Optional[asyncio.StreamWriter]:
        """Return the stored stdin stream for a session."""
        return self._stdins.get(session_id)

    def clear_stdin(self, session_id: str) -> None:
        self._stdins.pop(session_id, None)

    def get_input_lock(self, session_id: str) -> asyncio.Lock:
        """Return a per-session lock guarding stdin writes."""
        lock = self._input_locks.get(session_id)
        if not lock:
            lock = asyncio.Lock()
            self._input_locks[session_id] = lock
        return lock

    def is_prompt_sent(self, session_id: str) -> bool:
        """Check whether the initial prompt was sent to the runner."""
        return self._prompt_sent.get(session_id, False)

    def mark_prompt_sent(self, session_id: str) -> None:
        """Record that the initial prompt was sent to the runner."""
        self._prompt_sent[session_id] = True

    def clear_prompt_sent(self, session_id: str) -> None:
        self._prompt_sent.pop(session_id, None)

    def add_pending_input(self, session_id: str, text: str) -> None:
        """Queue input to send once the runner is ready."""
        self._pending_inputs.setdefault(session_id, []).append(text)

    def pop_pending_inputs(self, session_id: str) -> List[str]:
        """Drain and return all pending inputs."""
        return self._pending_inputs.pop(session_id, [])

    def clear_pending_inputs(self, session_id: str) -> None:
        self._pending_inputs.pop(session_id, None)

    def pop_next_pending_input(self, session_id: str) -> Optional[str]:
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

    def set_codex_session_id(self, session_id: str, codex_session_id: str) -> None:
        """Store the runner-specific session id."""
        self._codex_session_ids[session_id] = codex_session_id

    def get_codex_session_id(self, session_id: str) -> Optional[str]:
        """Fetch the runner-specific session id."""
        return self._codex_session_ids.get(session_id)

    def clear_codex_session_id(self, session_id: str) -> None:
        self._codex_session_ids.pop(session_id, None)

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

    def set_workdir(self, session_id: str, path: str, *, managed: bool) -> str:
        """Record a working directory and update the session metadata."""
        normalized = normalize_directory_path(path)
        self._workdirs[session_id] = normalized
        self._workdir_managed[session_id] = managed
        session = self._sessions.get(session_id)
        if session:
            session.directory = normalized
            session.directory_has_git = has_git_repository(normalized)
            self.update_session(session)
        return normalized

    def create_workdir(self, session_id: str) -> str:
        """Create a temporary working directory for the session."""
        path = tempfile.mkdtemp(prefix=f"tether_{session_id}_")
        return self.set_workdir(session_id, path, managed=True)

    def get_workdir(self, session_id: str) -> Optional[str]:
        """Return the session working directory, if created."""
        return self._workdirs.get(session_id)

    def clear_workdir(self, session_id: str) -> None:
        path = self._workdirs.pop(session_id, None)
        managed = self._workdir_managed.pop(session_id, False)
        if path and managed:
            shutil.rmtree(path, ignore_errors=True)


store = SessionStore()
