"""Health endpoint."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"ok": True, "version": "0.1.0", "protocol": 1}
