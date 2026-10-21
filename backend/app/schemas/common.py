"""Shared schema plumbing.

Owner: Person B — Domain & Contracts (Saviour Menebari Peba).
Contract: docs/technical-spec.md §5 (API conventions).

Everything cross-cutting about the wire format is defined here exactly once:

* `UTCDateTime` — renders datetimes as ISO-8601 UTC with a trailing `Z`
  ("2026-10-21T09:00:00Z"), never "+00:00". SQLite returns naive datetimes
  (it ignores DateTime(timezone=True)); naive values are treated as UTC,
  which is what `app.models.common.utcnow` wrote.
* `ApiModel` — the base every API shape inherits: reads ORM objects
  (`from_attributes`), accepts both the field name and its validation alias
  (`populate_by_name`).
* `ListResponse[T]` — the one list envelope: {"items": [...], "total": n}.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, PlainSerializer
from typing_extensions import Annotated


def _as_iso_z(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


UTCDateTime = Annotated[
    datetime,
    # Only when serialising to JSON — Python-side code keeps real datetimes.
    PlainSerializer(_as_iso_z, return_type=str, when_used="json"),
]

T = TypeVar("T")


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ListResponse(ApiModel, Generic[T]):
    items: list[T]
    total: int


class HealthOut(ApiModel):
    """GET /health (no auth)."""

    status: str = "ok"
