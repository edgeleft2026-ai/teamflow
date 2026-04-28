from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

_engine = None


def init_db(db_path: str | None = None) -> None:
    """Initialize the SQLite database, creating tables if needed."""
    global _engine

    if db_path is None:
        db_path = os.getenv("TEAMFLOW_DB_PATH", "data/teamflow.db")

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    url = f"sqlite:///{path}"
    _engine = create_engine(url, echo=False)

    # Import models to register them with SQLModel metadata before create_all.
    from teamflow.storage.models import (  # noqa: F401
        ActionLog,
        ConversationState,
        EventLog,
        Project,
    )

    SQLModel.metadata.create_all(_engine)


def get_engine():
    """Return the current engine, raising if init_db hasn't been called."""
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _engine


@contextmanager
def get_session():
    """Yield a SQLModel Session, committing on success, rolling back on error."""
    session = Session(get_engine())
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
