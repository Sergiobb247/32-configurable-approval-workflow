"""Shared column helpers for the domain models.

Owner: Person B — Domain & Contracts (Saviour Menebari Peba).

These two helpers exist so that the conventions in `docs/schema.md` §1
("Enum storage" and "Timestamps") are written once and imported everywhere,
instead of being re-typed — and mistyped — in five tables.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypeVar

from sqlalchemy import DateTime, Enum
from sqlalchemy.orm import Mapped, mapped_column

_E = TypeVar("_E", bound=type)


def utcnow() -> datetime:
    """Timezone-aware UTC now. The only clock the domain uses."""
    return datetime.now(timezone.utc)


def created_at_column() -> Any:
    """The `created_at` column required on every table (schema.md §4).

    Stored as `DateTime(timezone=True)`; SQLite ignores the timezone flag and
    returns naive datetimes — API schemas normalise back to UTC on the way
    out, so behaviour is identical on SQLite and Postgres.
    """
    return mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


def role_enum_column(enum_class: _E, **kwargs: Any) -> Mapped[Any]:
    """Portable enum column per schema.md §1.

    `Enum(..., native_enum=False)` stores the value as a VARCHAR with a CHECK
    constraint, which behaves identically on SQLite and Postgres (native PG
    enums would be a migration headache we deliberately skipped).
    `values_callable` pins the stored strings to the enum *values*
    ("MANAGER"), never the member spellings, on every Python version.
    """
    return mapped_column(
        Enum(
            enum_class,
            native_enum=False,
            values_callable=lambda e: [m.value for m in e],
            validate_strings=True,
        ),
        **kwargs,
    )
