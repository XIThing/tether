"""API package for session control and observability endpoints."""

from __future__ import annotations

from tether.api.deps import require_token
from tether.api.router import router

__all__ = ["router", "require_token"]
