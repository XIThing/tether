"""Database engine and session management."""

from __future__ import annotations

import os
from sqlmodel import SQLModel, create_engine, Session as DBSession
from sqlalchemy import Engine

from tether.settings import settings

# Lazy-initialized engine
_engine: Engine | None = None


def _get_engine() -> Engine:
    """Get or create the database engine."""
    global _engine
    if _engine is None:
        data_dir = settings.data_dir()
        os.makedirs(data_dir, exist_ok=True)
        db_path = os.path.join(data_dir, "sessions.db")
        db_url = f"sqlite:///{db_path}"
        _engine = create_engine(
            db_url,
            echo=False,
            connect_args={"check_same_thread": False},
        )
    return _engine


def reset_engine() -> None:
    """Reset the engine so it will be recreated with current settings.

    Used by tests to point at a fresh database after changing TETHER_AGENT_DATA_DIR.
    """
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None


def get_db_url() -> str:
    """Return the database URL for Alembic."""
    data_dir = settings.data_dir()
    db_path = os.path.join(data_dir, "sessions.db")
    return f"sqlite:///{db_path}"


def get_session() -> DBSession:
    """Get a new database session."""
    return DBSession(_get_engine())


def init_db() -> None:
    """Create all tables if they don't exist."""
    SQLModel.metadata.create_all(bind=_get_engine())


__all__ = [
    "get_session",
    "get_db_url",
    "init_db",
    "reset_engine",
    "DBSession",
]
