"""SQLAlchemy engine, session factory, and declarative base.

All ORM models register on ``Base.metadata`` (see ``models.py``). Foreign key
enforcement is turned on per-connection for SQLite, which ships with FKs off.

Timestamps everywhere are UTC, TZ-aware. Use ``utcnow()`` below — never
``datetime.utcnow()`` (deprecated and naive).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from polyforecast.config import settings


def utcnow() -> datetime:
    """TZ-aware current UTC timestamp. Use this as a column default."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _enable_sqlite_fks(dbapi_connection: Any, _connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def make_engine(url: str | None = None) -> Engine:
    """Build an Engine. Tests override ``url``; production uses settings."""
    engine = create_engine(url or settings.database_url, future=True)
    if engine.url.get_backend_name() == "sqlite":
        event.listen(engine, "connect", _enable_sqlite_fks)
    return engine


engine: Engine = make_engine()
SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine, autoflush=False, expire_on_commit=False
)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional session. Commits on success, rolls back on exception."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
