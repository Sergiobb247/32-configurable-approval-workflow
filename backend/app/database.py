"""SQLAlchemy declarative base, engine, and FastAPI session dependency.

Owner: Person A — Identity & Access (Gogo Frank).
Contract: docs/technical-spec.md §1, §2, §9, §11 and docs/schema.md §1, §7.

Local development uses SQLite (`sqlite:///./app.db`); production uses
PostgreSQL (`postgresql://...`). Engine arguments adapt automatically so
SQLite receives `check_same_thread=False` + foreign-key enforcement while
PostgreSQL receives connection health pings (`pool_pre_ping=True`).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Single declarative base shared by all 6 tables in `app/models/`."""


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """Ensure SQLite honors `ON DELETE CASCADE` (e.g. `refresh_tokens.user_id`)
    identically to PostgreSQL."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def build_engine(database_url: str) -> Engine:
    """Create a SQLAlchemy engine tuned for either SQLite or PostgreSQL."""
    is_sqlite = database_url.startswith("sqlite")
    connect_args = {"check_same_thread": False} if is_sqlite else {}
    engine_kwargs = {} if is_sqlite else {"pool_pre_ping": True}
    return create_engine(
        database_url,
        connect_args=connect_args,
        **engine_kwargs,
    )


engine = build_engine(settings.DATABASE_URL)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


def get_db() -> Generator[Session, None, None]:
    """Yield one database session per HTTP request and close it cleanly."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
