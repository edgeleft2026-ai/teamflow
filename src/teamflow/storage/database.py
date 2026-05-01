from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

logger = logging.getLogger(__name__)

_engine = None


def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable WAL mode and set busy timeout for concurrent access."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA busy_timeout=5000;")
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.close()


def init_db(db_path: str | None = None) -> None:
    """Initialize the SQLite database, creating tables if needed."""
    global _engine

    if db_path is None:
        db_path = os.getenv("TEAMFLOW_DB_PATH", "data/teamflow.db")

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    url = f"sqlite:///{path}"
    _engine = create_engine(
        url,
        echo=False,
        connect_args={"check_same_thread": False},
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )

    event.listen(_engine, "connect", _set_sqlite_pragma)

    from teamflow.storage.models import (  # noqa: F401
        ActionLog,
        ConversationState,
        EventLog,
        Project,
        ProjectAccessBinding,
        ProjectFormSubmission,
        ProjectMember,
        UserIdentityBinding,
    )

    SQLModel.metadata.create_all(_engine)
    logger.info("数据库初始化完成 (WAL模式, busy_timeout=5000ms): %s", path)


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
        logger.warning("数据库会话异常，已回滚事务")
        raise
    finally:
        session.close()
