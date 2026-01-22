"""Session lifecycle endpoints."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import structlog
from fastapi import APIRouter, Body, Depends

from tether.api.deps import require_token
from tether.api.emit import emit_state
from tether.api.errors import raise_http_error
from tether.api.runner_events import runner
from tether.api.state import maybe_set_session_name, now, transition
from tether.diff import parse_git_diff
from tether.git import normalize_directory_path
from tether.models import SessionState
from tether.store import store

router = APIRouter(tags=["sessions"])
logger = structlog.get_logger("tether.api.sessions")


@contextmanager
def _session_logging_context(session_id: str):
    structlog.contextvars.bind_contextvars(session_id=session_id)
    try:
        yield
    finally:
        structlog.contextvars.unbind_contextvars("session_id")


@router.get("/sessions", response_model=dict)
async def list_sessions(_: None = Depends(require_token)) -> dict:
    """List all sessions in memory."""
    sessions = store.list_sessions()
    logger.info("Listed sessions", count=len(sessions))
    return {"sessions": sessions}


@router.post("/sessions", response_model=dict, status_code=201)
async def create_session(
    payload: dict = Body(...),
    _: None = Depends(require_token),
) -> dict:
    """Create a new session in CREATED state."""
    logger.info(
        "Create session requested",
        repo_id=payload.get("repo_id"),
        directory=payload.get("directory"),
        base_ref=payload.get("base_ref"),
    )
    repo_id = payload.get("repo_id")
    directory = payload.get("directory")
    base_ref = payload.get("base_ref")
    normalized_directory: str | None = None
    if directory:
        candidate = Path(directory).expanduser()
        if not candidate.is_dir():
            raise_http_error("VALIDATION_ERROR", "directory must be an existing folder", 422)
        normalized_directory = normalize_directory_path(directory)
    resolved_repo_id = repo_id or normalized_directory or "repo_local"
    session = store.create_session(repo_id=resolved_repo_id, base_ref=base_ref)
    if normalized_directory:
        session.repo_display = normalized_directory
        store.update_session(session)
        store.set_workdir(session.id, normalized_directory, managed=False)
    session = store.get_session(session.id) or session
    with _session_logging_context(session.id):
        logger.info(
            "Session created",
            repo_id=session.repo_id,
            directory=normalized_directory,
        )
        return {"session": session}


@router.get("/sessions/{session_id}", response_model=dict)
async def get_session(session_id: str, _: None = Depends(require_token)) -> dict:
    """Fetch a single session by id."""
    with _session_logging_context(session_id):
        session = store.get_session(session_id)
        if not session:
            raise_http_error("NOT_FOUND", "Session not found", 404)
        logger.info("Fetched session", state=session.state)
        return {"session": session}


@router.delete("/sessions/{session_id}", response_model=dict)
async def delete_session(session_id: str, _: None = Depends(require_token)) -> dict:
    """Delete a session if it is not running."""
    with _session_logging_context(session_id):
        session = store.get_session(session_id)
        if not session:
            raise_http_error("NOT_FOUND", "Session not found", 404)
        if session.state in (SessionState.RUNNING, SessionState.STOPPING):
            raise_http_error("INVALID_STATE", "Session is active", 409)
        store.delete_session(session_id)
        logger.info("Session deleted")
        return {"ok": True}


@router.post("/sessions/{session_id}/start", response_model=dict)
async def start_session(
    session_id: str,
    payload: dict = Body(...),
    _: None = Depends(require_token),
) -> dict:
    """Start a session and launch Codex process streaming."""
    with _session_logging_context(session_id):
        session = store.get_session(session_id)
        if not session:
            raise_http_error("NOT_FOUND", "Session not found", 404)
        if session.state != SessionState.CREATED:
            raise_http_error("INVALID_STATE", "Session not in CREATED state", 409)
        logger.info("Session start requested")
        transition(session, SessionState.RUNNING, started_at=True)
        store.clear_codex_session_id(session_id)
        store.get_workdir(session_id) or store.create_workdir(session_id)
        await emit_state(session)
        prompt = payload.get("prompt", "")
        maybe_set_session_name(session, prompt)
        approval_choice = payload.get("approval_choice", 1)
        if approval_choice not in (1, 2):
            raise_http_error("VALIDATION_ERROR", "approval_choice must be 1 or 2", 422)
        # The runner decides how to interpret approval_choice; codex_v1 ignores it.
        await runner.start(session_id, prompt, approval_choice)
        logger.info("Session started")
        return {"session": session}


@router.patch("/sessions/{session_id}/rename", response_model=dict)
async def rename_session(
    session_id: str,
    payload: dict = Body(...),
    _: None = Depends(require_token),
) -> dict:
    """Rename an existing session."""
    with _session_logging_context(session_id):
        session = store.get_session(session_id)
        if not session:
            raise_http_error("NOT_FOUND", "Session not found", 404)
        value = payload.get("name", "")
        cleaned = " ".join(str(value).split())
        if not cleaned:
            raise_http_error("VALIDATION_ERROR", "name is required", 422)
        session.name = cleaned[:80]
        store.update_session(session)
        logger.info("Session renamed", name=session.name)
        return {"session": session}


@router.post("/sessions/{session_id}/input", response_model=dict)
async def send_input(
    session_id: str,
    payload: dict = Body(...),
    _: None = Depends(require_token),
) -> dict:
    """Send input to a running session's process."""
    with _session_logging_context(session_id):
        text = payload.get("text")
        if not text:
            raise_http_error("VALIDATION_ERROR", "text is required", 422)
        session = store.get_session(session_id)
        if not session:
            raise_http_error("NOT_FOUND", "Session not found", 404)
        if session.state != SessionState.RUNNING:
            raise_http_error("INVALID_STATE", "Session not running", 409)
        logger.info("Session input received", text_length=len(text))
        maybe_set_session_name(session, text)
        await runner.send_input(session_id, text)
        session = store.get_session(session_id)
        if session:
            session.last_activity_at = now()
            store.update_session(session)
        logger.info("Session input forwarded")
        return {"session": session}


@router.post("/sessions/{session_id}/stop", response_model=dict)
async def stop_session(session_id: str, _: None = Depends(require_token)) -> dict:
    """Stop a running session (idempotent beyond terminal states)."""
    with _session_logging_context(session_id):
        session = store.get_session(session_id)
        if not session:
            raise_http_error("NOT_FOUND", "Session not found", 404)
        if session.state in (SessionState.STOPPED, SessionState.ERROR):
            logger.info("Session stop requested for terminal session")
            return {"session": session}
        if session.state == SessionState.CREATED:
            raise_http_error("INVALID_STATE", "Session not running", 409)
        if session.state == SessionState.RUNNING:
            transition(session, SessionState.STOPPING)
            await emit_state(session)
        logger.info("Stopping session")
        exit_code = await runner.stop(session_id)
        session = store.get_session(session_id)
        if not session:
            raise_http_error("NOT_FOUND", "Session not found", 404)
        if session.state not in (SessionState.STOPPED, SessionState.ERROR):
            transition(
                session,
                SessionState.STOPPED,
                ended_at=True,
                exit_code=exit_code,
            )
            await emit_state(session)
        logger.info("Session stopped", exit_code=exit_code)
        return {"session": session}


@router.get("/sessions/{session_id}/diff", response_model=dict)
async def get_diff(session_id: str, _: None = Depends(require_token)) -> dict:
    """Return placeholder diff output for a session."""
    with _session_logging_context(session_id):
        session = store.get_session(session_id)
        if not session:
            raise_http_error("NOT_FOUND", "Session not found", 404)
        logger.info("Session diff requested")
        diff = """diff --git a/ui/src/views/ActiveSession.vue b/ui/src/views/ActiveSession.vue
index 2bce3a1..d93c7c0 100644
--- a/ui/src/views/ActiveSession.vue
+++ b/ui/src/views/ActiveSession.vue
@@ -3,7 +3,11 @@
-    <h2>Active Session</h2>
-    <p v-if="session">State: {{ session.state }}</p>
+    <h2>
+      <span class="status"></span>
+      Active Session
+    </h2>
+    <p v-if="session">{{ session.repo_display }} · {{ session.state }}</p>
   </div>
@@ -42,6 +46,10 @@
-<pre class="diff">{{ diff }}</pre>
+<div class="diff-header">
+  <h3>Diff preview</h3>
+  <button>Copy</button>
+</div>
+<pre class="diff"><code>{{ diff }}</code></pre>
diff --git a/ui/src/App.vue b/ui/src/App.vue
index f5a12c3..bd901fe 100644
--- a/ui/src/App.vue
+++ b/ui/src/App.vue
@@ -1,6 +1,9 @@
 <header class="topbar">
-  <h1>Tether</h1>
+  <h1>
+    <span class="brand-dot"></span>
+    Tether
+  </h1>
 </header>
@@ -72,6 +75,8 @@
-.topbar { background: #121312; }
+.topbar { background: #121312; }
+.brand-dot { width: 8px; height: 8px; border-radius: 50%; }
diff --git a/ui/src/views/Sessions.vue b/ui/src/views/Sessions.vue
index 9b1bc4a..f63ce2a 100644
--- a/ui/src/views/Sessions.vue
+++ b/ui/src/views/Sessions.vue
@@ -18,7 +18,10 @@
-  <button @click="create">Create & open</button>
+  <button @click="create">Create & open</button>
+  <button class="ghost" @click="refresh">Refresh</button>
@@ -80,6 +83,8 @@
-.session-card { display: flex; }
+.session-card { display: flex; }
+.session-card.active { border-color: var(--accent); }
"""
        return {"diff": diff, "files": parse_git_diff(diff)}
