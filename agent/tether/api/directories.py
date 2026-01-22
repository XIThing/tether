"""Endpoints for validating local directory inputs."""

from __future__ import annotations

from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, Query

from tether.api.deps import require_token
from tether.git import has_git_repository, normalize_directory_path

router = APIRouter(tags=["directories"])
logger = structlog.get_logger("tether.api.directories")


@router.get("/directories/check", response_model=dict)
async def check_directory(
    path: str = Query(..., min_length=1),
    _: None = Depends(require_token),
) -> dict:
    """Return metadata about a local directory path."""
    logger.info("Directory check requested", path=path)
    normalized = normalize_directory_path(path)
    target = Path(normalized)
    exists = target.is_dir()
    response = {
        "path": normalized,
        "exists": exists,
        "is_git": exists and has_git_repository(normalized),
    }
    logger.info(
        "Directory check completed",
        path=normalized,
        exists=exists,
        is_git=response["is_git"],
    )
    return response
