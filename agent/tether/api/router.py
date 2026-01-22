"""Composition of API routers under the /api prefix."""

from __future__ import annotations

from fastapi import APIRouter

from tether.api.directories import router as directories_router
from tether.api.sessions import router as sessions_router

router = APIRouter(prefix="/api")
router.include_router(sessions_router)
router.include_router(directories_router)
