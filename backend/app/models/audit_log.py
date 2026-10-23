"""AuditLog model and the agreed action vocabulary.

Owner: Person B — Domain & Contracts (Saviour Menebari Peba).
Contract: docs/schema.md §4.6.

Append-only by design: there is no update endpoint and no delete endpoint —
not even for admins — and rows are written only by `services/audit.record()`
(Person D), which flushes but never commits. This file provides the table
and the *vocabulary*; it cannot enforce those two process rules.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

from .common import created_at_column

if TYPE_CHECKING:  # pragma: no cover
    from .request import Request
    from .user import User


class AuditAction:
    """The agreed action vocabulary (schema.md §4.6) — written once, used
    everywhere.

    Deliberately plain string constants, NOT an Enum: the column is a
    VARCHAR(40) so the vocabulary can grow without a schema change, and
    str-Enum members have version-dependent str() behaviour that has no
    place in an audit trail.
    """

    REQUEST_CREATED = "REQUEST_CREATED"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    WORKFLOW_CREATED = "WORKFLOW_CREATED"
    WORKFLOW_UPDATED = "WORKFLOW_UPDATED"
    USER_ROLE_CHANGED = "USER_ROLE_CHANGED"
    USER_DEACTIVATED = "USER_DEACTIVATED"


class EntityType:
    """Values for `entity_type` (schema.md §4.6)."""

    REQUEST = "request"
    WORKFLOW = "workflow"
    USER = "user"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    # Nullable: workflow and user events have no request (§2, §4.6).
    request_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("requests.id"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    from_state: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    to_state: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = created_at_column()

    # Defined after the columns so the DESC index can reference the column
    # object directly. The global feed (GET /audit) reads newest-first (§4.6).
    __table_args__ = (
        Index("ix_audit_logs_created_at_desc", created_at.desc()),
    )

    actor: Mapped["User"] = relationship(back_populates="audit_entries")
    request: Mapped[Optional["Request"]] = relationship(back_populates="audit_logs")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AuditLog id={self.id} action={self.action!r} actor={self.actor_id}>"
