"""Pydantic models for API payloads and session metadata."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class SessionState(str, Enum):
    """Lifecycle states for a supervised session."""
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class RepoRef(BaseModel):
    """Reference to a repository target (path or URL)."""
    type: str
    value: str


class Session(BaseModel):
    """Server-side session metadata exposed over the API."""
    id: str
    repo_id: str
    repo_display: str
    repo_ref: RepoRef
    state: SessionState
    name: Optional[str] = None
    created_at: str
    started_at: Optional[str]
    ended_at: Optional[str]
    last_activity_at: str
    exit_code: Optional[int]
    summary: Optional[str]
    codex_header: Optional[str] = None
    directory: Optional[str] = None
    directory_has_git: bool = False


class ErrorDetail(BaseModel):
    """Structured error payload for API responses."""
    code: str
    message: str
    details: Optional[dict]


class ErrorResponse(BaseModel):
    """Envelope for API error responses."""
    error: ErrorDetail
