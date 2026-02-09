"""Utilities for detecting running external sessions."""

from __future__ import annotations

import subprocess
from pathlib import Path

CLAUDE_SESSION_ENV_DIR = Path.home() / ".claude" / "session-env"


def find_running_claude_sessions() -> set[str]:
    """Return set of Claude Code session IDs that are currently running.

    Detection method: Parse ``ps`` output for ``claude --resume <id>`` and
    bare ``claude`` processes.  We no longer rely on ``~/.claude/session-env/``
    directories because they are not cleaned up on crash and cause false
    positives that drop resume IDs, losing conversation context.
    """
    running: set[str] = set()
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return running

        for line in result.stdout.splitlines():
            # Match "claude --resume <session-id>"
            if "claude" not in line:
                continue
            parts = line.split()
            for i, part in enumerate(parts):
                if part == "--resume" and i + 1 < len(parts):
                    sid = parts[i + 1]
                    if len(sid) >= 32 and "-" in sid:
                        running.add(sid)
                    break
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return running


def find_running_codex_sessions() -> set[str]:
    """Return set of Codex CLI session IDs that are currently running.

    Detection method: Parse 'ps aux' for 'codex resume' processes.
    """
    running: set[str] = set()
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return running

        for line in result.stdout.splitlines():
            if "codex resume" in line:
                # Try to extract session ID from command line
                # Format: "codex resume <session-id>"
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == "resume" and i + 1 < len(parts):
                        session_id = parts[i + 1]
                        # Validate it looks like a UUID
                        if len(session_id) >= 32 and "-" in session_id:
                            running.add(session_id)
                        break
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return running


def is_claude_session_running(session_id: str) -> bool:
    """Check if a specific Claude Code session is running.

    Uses process-level detection rather than ``session-env`` directory
    existence, which is unreliable (stale dirs persist after crashes).
    """
    return session_id in find_running_claude_sessions()


def is_codex_session_running(session_id: str) -> bool:
    """Check if a specific Codex CLI session is running."""
    return session_id in find_running_codex_sessions()
